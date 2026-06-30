from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

from . import paths
from .models import MODEL_TEMPLATE
from .processes import ProcessManager, python_executable


DEFAULT_MODEL = "glm-5.2"
DEFAULT_OPENAI_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.z.ai/api/anthropic"
PROVIDER_ID = "glm52"


def model_name() -> str:
    return os.environ.get("GLM52_MODEL", DEFAULT_MODEL)


def api_key() -> str:
    configured = os.environ.get("GLM52_API_KEY")
    if configured:
        return configured.strip()

    token_path = Path(os.environ.get("GLM52_TOKEN_FILE", paths.repo_root() / "GLM5.2.md")).expanduser()
    if not token_path.is_file():
        raise SystemExit(
            f"GLM 5.2 token not found: {token_path}. "
            "Set GLM52_API_KEY or GLM52_TOKEN_FILE."
        )
    token = token_path.read_text(encoding="utf-8").strip()
    if not token or any(character.isspace() for character in token):
        raise SystemExit(f"GLM 5.2 token file must contain exactly one token: {token_path}")
    return token


def openai_base_url() -> str:
    return os.environ.get("GLM52_OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/")


def anthropic_base_url() -> str:
    return os.environ.get("GLM52_ANTHROPIC_BASE_URL", DEFAULT_ANTHROPIC_BASE_URL).rstrip("/")


def opencode_config_content() -> str:
    model = model_name()
    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{PROVIDER_ID}/{model}",
        "small_model": f"{PROVIDER_ID}/{model}",
        "provider": {
            PROVIDER_ID: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "GLM 5.2 via Z.AI",
                "options": {
                    "baseURL": openai_base_url(),
                    "apiKey": "{env:GLM52_API_KEY}",
                    "timeout": 600000,
                    "chunkTimeout": 60000,
                },
                "models": {
                    model: {
                        "name": "GLM 5.2",
                        "limit": {"context": 200000, "output": 128000},
                    }
                },
            }
        },
    }
    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


def available_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def codex_catalog_path(destination: Path | None = None) -> Path:
    destination = destination or paths.cache_home() / paths.APP_NAME / "glm52-model-catalog.json"
    model = dict(MODEL_TEMPLATE)
    model.update(
        {
            "slug": model_name(),
            "display_name": "GLM 5.2",
            "description": "GLM 5.2 through the Z.AI API and a local Responses adapter.",
            "base_instructions": (
                "You are Codex, a coding agent using GLM 5.2 through Z.AI. "
                "Follow user and developer instructions, use tools when needed, "
                "and keep responses concise and actionable."
            ),
            "context_window": 200000,
            "max_context_window": 200000,
        }
    )
    content = json.dumps({"models": [model]}, indent=2) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_text(encoding="utf-8") != content:
        destination.write_text(content, encoding="utf-8")
    return destination


def start_codex_proxy(manager: ProcessManager, host: str, port: int) -> None:
    proxy = paths.repo_root() / "proxies" / "codex_ilaas_responses_proxy.py"
    manager.start(
        "glm52-codex-proxy",
        [
            python_executable(),
            str(proxy),
            "--host",
            host,
            "--port",
            str(port),
            "--upstream",
            openai_base_url(),
        ],
        paths.log_dir() / "glm52-codex-responses-proxy.log",
    )
    manager.wait_for_port("GLM 5.2 Codex Responses proxy", host, port)


def run_codex(argv: list[str]) -> int:
    key = api_key()
    model = model_name()
    host = "127.0.0.1"
    port = available_port(host)
    manager = ProcessManager()
    try:
        start_codex_proxy(manager, host, port)
        catalog = codex_catalog_path()
        env = os.environ.copy()
        env["GLM52_API_KEY"] = key
        overrides = [
            "-c",
            f'model="{model}"',
            "-c",
            f'model_provider="{PROVIDER_ID}"',
            "-c",
            f'model_providers.{PROVIDER_ID}.name="GLM 5.2 via local Responses adapter"',
            "-c",
            f'model_providers.{PROVIDER_ID}.base_url="http://{host}:{port}/v1"',
            "-c",
            f'model_providers.{PROVIDER_ID}.env_key="GLM52_API_KEY"',
            "-c",
            f'model_providers.{PROVIDER_ID}.wire_api="responses"',
            "-c",
            "model_context_window=200000",
            "-c",
            f'model_catalog_json="{catalog}"',
        ]
        return subprocess.call(["codex", *overrides, *argv], env=env)
    finally:
        manager.cleanup()


def run_claude(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        print(model_name())
        return 0

    key = api_key()
    model = model_name()
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env["ANTHROPIC_AUTH_TOKEN"] = key
    env["ANTHROPIC_BASE_URL"] = anthropic_base_url()
    env["API_TIMEOUT_MS"] = env.get("API_TIMEOUT_MS", "3000000")
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = env.get(
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1"
    )
    for variable in (
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_DEFAULT_FABLE_MODEL",
    ):
        env[variable] = model
    env["ANTHROPIC_CUSTOM_MODEL_OPTION"] = model
    env["ANTHROPIC_CUSTOM_MODEL_OPTION_NAME"] = "GLM 5.2"
    env["ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION"] = "GLM 5.2 through Z.AI"
    return subprocess.call(["claude", *argv], env=env)


def run_opencode(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        print(model_name())
        return 0

    env = os.environ.copy()
    env["GLM52_API_KEY"] = api_key()
    env["OPENCODE_CONFIG_CONTENT"] = opencode_config_content()
    return subprocess.call(["opencode", *argv], env=env)
