"""Shared, declarative retry policy for the ILaaS proxies.

A rule matches a failed upstream call when the request model starts with
``model_prefix`` (optional), the request carries tools (when
``requires_tools`` is set), and the error body contains ``error_substring``.
On a match the proxy retries once with ``corrective_message`` prepended as a
system message. The substring and the corrective text live here only.

The default table holds the Qwen "Unterminated string" rule. Override or
extend it by writing a JSON list of rule objects to
``$XDG_CONFIG_HOME/ilaas-agent/retry-policies.json`` (or
``~/.config/ilaas-agent/retry-policies.json``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_RULES = [
    {
        "model_prefix": "qwen-",
        "requires_tools": True,
        "error_substring": "Unterminated string",
        "corrective_message": (
            "When calling tools, function arguments must be a complete valid JSON object. "
            "Do not emit unterminated strings."
        ),
    }
]


def config_path() -> Path:
    """Where the optional override retry-policies.json is read from."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "ilaas-agent" / "retry-policies.json"


def load_rules() -> list[dict]:
    rules = list(DEFAULT_RULES)
    path = config_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"retry_policy: failed to load {path}: {error}", flush=True)
            return rules
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("rules"), list):
            return data["rules"]
    return rules


_RULES: list[dict] | None = None


def rules() -> list[dict]:
    global _RULES
    if _RULES is None:
        _RULES = load_rules()
    return _RULES


def reload_rules() -> list[dict]:
    """Force a re-read of the config file (used by tests)."""
    global _RULES
    _RULES = load_rules()
    return _RULES


def match(chat_payload: dict, body: str) -> dict | None:
    """Return the first rule matching the failed request, or None."""
    model = str(chat_payload.get("model", ""))
    has_tools = bool(chat_payload.get("tools"))
    body = body or ""
    for rule in rules():
        prefix = rule.get("model_prefix", "")
        if prefix and not model.startswith(prefix):
            continue
        if rule.get("requires_tools") and not has_tools:
            continue
        substring = rule.get("error_substring", "")
        if substring and substring not in body:
            continue
        return rule
    return None


def retry_payload(chat_payload: dict, rule: dict) -> dict:
    """Return a copy of chat_payload with the rule's corrective system message prepended."""
    new = dict(chat_payload)
    new["messages"] = [
        {"role": "system", "content": rule.get("corrective_message", "")},
        *chat_payload["messages"],
    ]
    return new
