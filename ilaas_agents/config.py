from __future__ import annotations

from pathlib import Path


def write_codex_config(path: Path, catalog_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''model = "ilaas-default"
model_provider = "ilaas_responses_proxy"
model_catalog_json = "{catalog_path}"

approval_policy = "on-request"
sandbox_mode = "danger-full-access"

model_context_window = 262144
model_auto_compact_token_limit = 220000
model_reasoning_summary = "none"
model_supports_reasoning_summaries = false

[model_providers.ilaas_responses_proxy]
name = "ILaaS Responses Proxy"
base_url = "http://127.0.0.1:4001/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
supports_websockets = false
'''
    )
