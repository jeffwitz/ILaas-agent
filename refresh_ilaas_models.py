#!/usr/bin/env python3
import argparse
import json
import re
import urllib.request
from pathlib import Path


DEFAULT_LITELLM_CONFIG = Path.home() / ".config/litellm/ilaas-mistral.yaml"
DEFAULT_CODEX_CATALOG = Path.home() / ".codex-ilaas/model-catalogs/ilaas-mistral.json"
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


def extract_value(pattern, text, fallback=None):
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    if fallback is not None:
        return fallback
    raise SystemExit(f"Missing required value matching: {pattern}")


def load_existing_settings(path):
    text = path.read_text()
    api_key = extract_value(r"api_key:\s*[\"']?([^\"'\s]+)", text)
    api_base = extract_value(r"api_base:\s*([^\s]+)", text, DEFAULT_API_BASE)
    return api_base.rstrip("/"), api_key


def fetch_models(api_base, api_key):
    request = urllib.request.Request(
        f"{api_base}/models",
        headers={"authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return sorted(
        item["id"]
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )


def model_entries(model_ids):
    entries = [(DEFAULT_ALIAS, DEFAULT_ALIAS_TARGET)]
    entries.extend(LEGACY_ALIASES)
    entries.extend((model_id, model_id) for model_id in model_ids)
    return entries


def write_litellm_config(path, api_base, api_key, model_ids):
    lines = ["model_list:"]
    for alias, target in model_entries(model_ids):
        lines.extend(
            [
                f"  - model_name: {alias}",
                "    litellm_params:",
                f"      model: openai/{target}",
                f"      api_base: {api_base}",
                f'      api_key: "{api_key}"',
                "      use_chat_completions_api: true",
                "      max_tokens: 4096",
            ]
        )
    lines.extend(["", "litellm_settings:", "  drop_params: true", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    path.chmod(0o600)


def display_name(slug):
    if slug == DEFAULT_ALIAS:
        return "ILaaS Default"
    if slug == "mistral-ilaas":
        return "Mistral ILaaS Legacy"
    return slug.replace("-", " ").replace(".", ".").title()


def model_identity_instruction(alias, target):
    return (
        f"Selected ILaaS model slug: {alias}. Upstream ILaaS model: {target}. "
        "If asked which model is selected, answer with these names. "
        "Do not claim to be Mistral unless the selected or upstream model name starts with mistral."
    )


def write_codex_catalog(path, model_ids):
    models = []
    for alias, target in model_entries(model_ids):
        model = dict(MODEL_TEMPLATE)
        model["slug"] = alias
        model["display_name"] = display_name(alias)
        model["description"] = f"{alias} routed to {target} through the local LiteLLM Responses proxy."
        model["base_instructions"] = MODEL_TEMPLATE["base_instructions"] + "\n\n" + model_identity_instruction(alias, target)
        models.append(model)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"models": models}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Refresh LiteLLM and Codex model lists from ILaaS /v1/models.")
    parser.add_argument("--litellm-config", type=Path, default=DEFAULT_LITELLM_CONFIG)
    parser.add_argument("--codex-catalog", type=Path, default=DEFAULT_CODEX_CATALOG)
    args = parser.parse_args()

    api_base, api_key = load_existing_settings(args.litellm_config)
    model_ids = fetch_models(api_base, api_key)
    if DEFAULT_ALIAS_TARGET not in model_ids:
        raise SystemExit(f"Default alias target not available on ILaaS: {DEFAULT_ALIAS_TARGET}")

    write_litellm_config(args.litellm_config, api_base, api_key, model_ids)
    write_codex_catalog(args.codex_catalog, model_ids)

    print(f"Refreshed {len(model_ids)} ILaaS models plus aliases {DEFAULT_ALIAS}, mistral-ilaas.")
    for model_id in model_ids:
        print(model_id)


if __name__ == "__main__":
    main()
