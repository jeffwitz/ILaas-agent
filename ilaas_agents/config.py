from __future__ import annotations

from pathlib import Path


CODEX_SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")


def write_codex_config(path: Path, catalog_path: Path, sandbox_mode: str = "danger-full-access") -> None:
    if sandbox_mode not in CODEX_SANDBOX_MODES:
        allowed = ", ".join(CODEX_SANDBOX_MODES)
        raise ValueError(f"unsupported Codex sandbox mode: {sandbox_mode}. Expected one of: {allowed}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''model = "ilaas-default"
model_provider = "ilaas_responses_proxy"
model_catalog_json = "{catalog_path}"

approval_policy = "on-request"
sandbox_mode = "{sandbox_mode}"

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
