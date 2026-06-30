"""Per-provider tier-map (supervisor / coder / small) stored in the model catalog.

Each model entry in a provider's catalog carries a ``tier`` field. The launcher
families (runners / glm52 / openrouter) call :func:`resolve` to pick the concrete
model for a given tier instead of hardcoding a single default. The complexity
routing itself is left to each agent's native multi-tier behavior (Claude Code
opus/sonnet/haiku, OpenCode model/small_model, Codex reasoning effort).

This module depends only on :mod:`paths`; it must not import the provider
modules (they import this one), to avoid circular imports.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import paths


TIERS = ("supervisor", "coder", "small")


def catalog_path(provider: str) -> Path:
    """Locate the catalog that carries tier info for ``provider``."""
    if provider == "ilaas":
        override = os.environ.get("ILAAS_MODEL_CATALOG")
        return Path(override) if override else paths.model_catalog_path()
    if provider == "glm52":
        return paths.cache_home() / paths.APP_NAME / "glm52-model-catalog.json"
    if provider == "openrouter":
        override = os.environ.get("OPENROUTER_TIER_CATALOG")
        if override:
            return Path(override)
        directory = paths.cache_home() / paths.APP_NAME
        if directory.is_dir():
            # OpenRouter catalogs are per-selected-model (openrouter-<slug>.json);
            # pick the most recently written one as the active tier source.
            candidates = sorted(
                directory.glob("openrouter-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                return candidates[0]
        return directory / "openrouter-tiers.json"
    raise SystemExit(f"unknown provider: {provider}. Expected one of: ilaas, glm52, openrouter.")


def load(provider: str) -> list[dict]:
    path = catalog_path(provider)
    if not path.exists():
        raise SystemExit(f"{provider} catalog not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("models", []) if isinstance(payload, dict) else []


def resolve(provider: str, tier: str) -> str | None:
    """Return the slug for ``tier`` of ``provider``, or None if undecided.

    Precedence: env override ``{PROVIDER}_TIER_{TIER}_MODEL`` > catalog entry
    with ``tier == tier``. Returns None (no exception) so callers can fall back
    to their own provider default when no tier has been assigned yet.
    """
    if tier not in TIERS:
        raise SystemExit(f"unknown tier: {tier}. Expected one of: {', '.join(TIERS)}.")
    override = os.environ.get(f"{provider.upper()}_TIER_{tier.upper()}_MODEL")
    if override:
        return override
    try:
        models = load(provider)
    except SystemExit:
        return None
    for model in models:
        if model.get("tier") == tier and model.get("slug"):
            return model["slug"]
    return None


def assign_tier(provider: str, slug: str, metadata: dict | None = None) -> str:
    """Heuristically classify ``slug`` into a tier.

    GLM 5.2 has a single model, so every tier maps to it. OpenRouter uses rich
    metadata when available (context length + tool support + output modalities).
    ILaaS (and OpenRouter without metadata) falls back to a name-based heuristic
    since its ``/models`` endpoint only exposes ids.
    """
    if provider == "glm52":
        return "supervisor"

    if provider == "openrouter" and metadata:
        context = int(metadata.get("context_length") or 0)
        supported = set(metadata.get("supported_parameters") or [])
        output = set((metadata.get("architecture") or {}).get("output_modalities") or [])
        if "tools" not in supported or "text" not in output:
            return "small"
        if context and context >= 200000:
            return "supervisor"
        if context and context < 64000:
            return "small"
        return "coder"

    name = (slug or "").lower()
    if not name:
        return "coder"
    if name in {"ilaas-default", "mistral-ilaas"}:
        return "supervisor"
    if re.search(r"(70b|405b|medium|max|large)", name) or "3.6-35b" in name:
        return "supervisor"
    if re.search(r"(\b8b\b|\b3b\b|\b1b\b|mini|tiny|small)", name):
        return "small"
    return "coder"


def suggest(provider: str) -> dict[str, str]:
    """Pick one slug per tier from the provider's catalog (first match wins)."""
    mapping: dict[str, str] = {}
    try:
        models = load(provider)
    except SystemExit:
        return mapping
    for model in models:
        slug = model.get("slug")
        if not slug:
            continue
        tier = model.get("tier") or assign_tier(provider, slug, model)
        if tier and tier not in mapping:
            mapping[tier] = slug
    return mapping


def apply(provider: str, mapping: dict[str, str] | None = None) -> dict[str, int]:
    """Write a ``tier`` field onto every catalog entry. Idempotent.

    With ``mapping`` (tier -> slug) the matched slug is tagged with that tier;
    every other entry is classified by :func:`assign_tier`. Without ``mapping``
    every entry is classified heuristically. Returns per-tier counts.
    """
    path = catalog_path(provider)
    if not path.exists():
        raise SystemExit(f"{provider} catalog not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = payload.get("models", []) if isinstance(payload, dict) else []
    counts = {tier: 0 for tier in TIERS}
    for model in models:
        slug = model.get("slug", "")
        tier = None
        if mapping:
            for want, want_slug in mapping.items():
                if want_slug == slug:
                    tier = want
                    break
        if tier is None:
            tier = assign_tier(provider, slug, model)
        model["tier"] = tier
        counts[tier] = counts.get(tier, 0) + 1
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return counts
