from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path


DEFAULT_API_BASE = "https://llm.ilaas.fr/v1"
DEFAULT_ALIAS = "ilaas-default"
DEFAULT_ALIAS_TARGET = "mistral-medium-latest"
LEGACY_ALIASES = [("mistral-ilaas", DEFAULT_ALIAS_TARGET)]


MODEL_TEMPLATE = {
    "description": "ILaaS model routed through the local LiteLLM Responses proxy.",
    "base_instructions": (
        "You are Codex, a coding agent running through ILaaS. Follow the user and "
        "developer instructions, use tools when needed, and keep responses concise "
        "and actionable."
    ),
    "default_reasoning_level": None,
    "supported_reasoning_levels": [],
    "shell_type": "shell_command",
    "visibility": "list",
    "supported_in_api": True,
    "priority": 0,
    "additional_speed_tiers": [],
    "service_tiers": [],
    "availability_nux": None,
    "upgrade": None,
    "supports_reasoning_summaries": False,
    "default_reasoning_summary": "none",
    "support_verbosity": False,
    "default_verbosity": "low",
    "apply_patch_tool_type": "freeform",
    "web_search_tool_type": "text_and_image",
    "truncation_policy": {"mode": "tokens", "limit": 10000},
    "supports_parallel_tool_calls": True,
    "supports_image_detail_original": False,
    "context_window": 262144,
    "max_context_window": 262144,
    "effective_context_window_percent": 95,
    "experimental_supported_tools": [],
    "input_modalities": ["text"],
    "supports_search_tool": False,
    "use_responses_lite": False,
}


def extract_existing_settings(path: Path) -> tuple[str, str] | None:
    if not path.exists():
        return None
    text = path.read_text()
    key_match = re.search(r"api_key:\s*[\"']?([^\"'\s]+)", text)
    if not key_match:
        return None
    base_match = re.search(r"api_base:\s*([^\s]+)", text)
    return (base_match.group(1).rstrip("/") if base_match else DEFAULT_API_BASE, key_match.group(1))


def fetch_models(api_base: str, api_key: str) -> list[str]:
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/models",
        headers={"authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return sorted(
        item["id"]
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )


def model_entries(model_ids: list[str]) -> list[tuple[str, str]]:
    entries = [(DEFAULT_ALIAS, DEFAULT_ALIAS_TARGET)]
    entries.extend(LEGACY_ALIASES)
    entries.extend((model_id, model_id) for model_id in model_ids)
    return entries


def write_litellm_config(path: Path, api_base: str, api_key: str, model_ids: list[str]) -> None:
    lines = ["model_list:"]
    for alias, target in model_entries(model_ids):
        lines.extend(
            [
                f"  - model_name: {alias}",
                "    litellm_params:",
                f"      model: openai/{target}",
                f"      api_base: {api_base.rstrip('/')}",
                f'      api_key: "{api_key}"',
                "      use_chat_completions_api: true",
                "      max_tokens: 4096",
            ]
        )
    lines.extend(["", "litellm_settings:", "  drop_params: true", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def display_name(slug: str) -> str:
    if slug == DEFAULT_ALIAS:
        return "ILaaS Default"
    if slug == "mistral-ilaas":
        return "Mistral ILaaS Legacy"
    return slug.replace("-", " ").title()


def model_identity_instruction(alias: str, target: str) -> str:
    return (
        f"Selected ILaaS model slug: {alias}. Upstream ILaaS model: {target}. "
        "If asked which model is selected, answer with these names. "
        "Do not claim to be Mistral unless the selected or upstream model name starts with mistral."
    )


def write_codex_catalog(path: Path, model_ids: list[str]) -> None:
    models = []
    for alias, target in model_entries(model_ids):
        model = dict(MODEL_TEMPLATE)
        model["slug"] = alias
        model["display_name"] = display_name(alias)
        model["description"] = f"{alias} routed to {target} through the local LiteLLM Responses proxy."
        model["base_instructions"] = MODEL_TEMPLATE["base_instructions"] + "\n\n" + model_identity_instruction(alias, target)
        if alias.startswith("llama-3.1-") or alias.startswith("llama-3.3-"):
            model["description"] += " Not recommended for code-agent tool use."
        models.append(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"models": models}, indent=2) + "\n")
