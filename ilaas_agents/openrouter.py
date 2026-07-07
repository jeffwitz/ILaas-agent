from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import quote

from . import paths
from . import tiers
from .models import MODEL_TEMPLATE
from .processes import ProcessManager, foreground_call, python_executable


DEFAULT_CODEX_MODEL = "~openai/gpt-latest"
DEFAULT_CLAUDE_MODEL = "z-ai/glm-5.2"
# Tier defaults for Claude Code's native routing: GLM 5.2 supervises (opus/fable),
# DeepSeek V4 Pro codes (sonnet), DeepSeek V4 Flash handles trivial work (haiku).
# Overridable per-tier via tiers.resolve (env OPENROUTER_TIER_*_MODEL or catalog).
DEFAULT_CODER_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_SMALL_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_OPENCODE_MODEL = "~openai/gpt-latest"
DEFAULT_OPENAI_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://openrouter.ai/api"
PROVIDER_ID = "openrouter"
DEFAULT_TOKEN_FILE = Path("/home/jeff/Code/clef_api/OPEN_ROUTER.md")


def api_key() -> str:
    configured = os.environ.get("OPENROUTER_API_KEY")
    if configured:
        token = configured.strip()
    else:
        explicit = os.environ.get("OPENROUTER_TOKEN_FILE")
        candidates = [
            Path(explicit).expanduser() if explicit else None,
            DEFAULT_TOKEN_FILE,
            paths.repo_root() / "OPENROUTER.md",
            paths.repo_root() / "OPEN_ROUTER.md",
        ]
        token_path = next((path for path in candidates if path and path.is_file()), None)
        if token_path is None:
            raise SystemExit(
                "OpenRouter token not found. Set OPENROUTER_API_KEY or "
                f"put it in {DEFAULT_TOKEN_FILE}, OPENROUTER.md or OPEN_ROUTER.md."
            )
        token = token_path.read_text(encoding="utf-8").strip()

    if not token or any(character.isspace() for character in token):
        raise SystemExit("The OpenRouter token must be a single non-empty value.")
    return token


def openai_base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/")


def anthropic_base_url() -> str:
    return os.environ.get("OPENROUTER_ANTHROPIC_BASE_URL", DEFAULT_ANTHROPIC_BASE_URL).rstrip("/")


def available_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def start_claude_proxy(manager: ProcessManager, host: str, port: int) -> None:
    proxy = paths.repo_root() / "proxies" / "openrouter_anthropic_proxy.py"
    manager.start(
        "openrouter-claude-proxy",
        [
            python_executable(),
            str(proxy),
            "--host",
            host,
            "--port",
            str(port),
            "--upstream",
            anthropic_base_url(),
        ],
        paths.log_dir() / "openrouter-claude-proxy.log",
    )
    manager.wait_for_port("OpenRouter Claude discovery proxy", host, port)


def codex_model() -> str:
    return tiers.resolve("openrouter", "supervisor") or os.environ.get("OPENROUTER_CODEX_MODEL", os.environ.get("OPENROUTER_MODEL", DEFAULT_CODEX_MODEL))


def claude_model() -> str:
    return os.environ.get("OPENROUTER_CLAUDE_MODEL", None) or tiers.resolve("openrouter", "supervisor") or DEFAULT_CLAUDE_MODEL


def opencode_model() -> str:
    return tiers.resolve("openrouter", "supervisor") or os.environ.get("OPENROUTER_OPENCODE_MODEL", os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENCODE_MODEL))


def fetch_models() -> list[dict]:
    request = urllib.request.Request(
        f"{openai_base_url()}/models",
        headers={"authorization": f"Bearer {api_key()}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [item for item in payload.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]


def fetch_model(model: str) -> dict:
    request = urllib.request.Request(
        f"{openai_base_url()}/model/{quote(model, safe='/~:')}",
        headers={"authorization": f"Bearer {api_key()}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    metadata = payload.get("data")
    if not isinstance(metadata, dict):
        raise SystemExit(f"OpenRouter model metadata unavailable: {model}")
    return metadata


def selected_codex_model(argv: list[str]) -> str:
    read_next = False
    for arg in argv:
        if read_next:
            return arg
        if arg in {"-m", "--model"}:
            read_next = True
        elif arg.startswith("--model="):
            return arg.split("=", 1)[1]
    return codex_model()


def codex_model_entry(metadata: dict) -> dict:
    model_id = metadata["id"]
    context_window = int(metadata.get("context_length") or 200000)
    input_modalities = (metadata.get("architecture") or {}).get("input_modalities") or ["text"]
    model = dict(MODEL_TEMPLATE)
    model.update(
        {
            "slug": model_id,
            "display_name": metadata.get("name") or model_id,
            "description": f"{model_id} through the OpenRouter Responses API.",
            "base_instructions": (
                "You are Codex, a coding agent using OpenRouter model "
                f"{model_id}. If asked which model is active, answer exactly "
                f"'{model_id}' and do not infer another identity. Follow user "
                "and developer instructions, use tools when needed, and keep "
                "responses concise and actionable."
            ),
            "context_window": context_window,
            "max_context_window": context_window,
            "input_modalities": [item for item in input_modalities if item in {"text", "image"}],
            "tier": tiers.assign_tier("openrouter", model_id, metadata),
        }
    )
    return model


def codex_catalog_path(selected_model: str, destination: Path | None = None) -> Path:
    metadata = fetch_models()
    by_id = {item["id"]: item for item in metadata}
    if selected_model not in by_id:
        selected_metadata = fetch_model(selected_model)
        by_id[selected_model] = selected_metadata

    eligible = []
    for item in by_id.values():
        supported = set(item.get("supported_parameters") or [])
        output_modalities = set((item.get("architecture") or {}).get("output_modalities") or ["text"])
        if item["id"] == selected_model or ("tools" in supported and "text" in output_modalities):
            eligible.append(item)

    eligible.sort(key=lambda item: (item["id"] != selected_model, item["id"]))
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", selected_model).strip("-")
    destination = destination or paths.cache_home() / paths.APP_NAME / f"openrouter-{safe_name}.json"
    content = json.dumps({"models": [codex_model_entry(item) for item in eligible]}, indent=2) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_text(encoding="utf-8") != content:
        destination.write_text(content, encoding="utf-8")
    return destination


def list_models(*, claude: bool = False, opencode: bool = False) -> None:
    for model in sorted(fetch_models(), key=lambda item: item["id"]):
        model_id = model["id"]
        if claude and not model_id.startswith(("~anthropic/", "anthropic/")):
            continue
        print(f"{PROVIDER_ID}/{model_id}" if opencode else model_id)


def run_codex(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        list_models()
        return 0

    model = selected_codex_model(argv)
    catalog = codex_catalog_path(model)
    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = api_key()
    # Isolate from the user's real Codex (~/.codex): otherwise Codex picks up a
    # ChatGPT login there and rejects non-OpenAI models ("not supported when
    # using Codex with a ChatGPT account"). Codex requires the home to exist.
    codex_home = paths.codex_home_openrouter()
    codex_home.mkdir(parents=True, exist_ok=True)
    env["CODEX_HOME"] = str(codex_home)
    overrides = [
        "-c",
        f'model="{model}"',
        "-c",
        f'model_provider="{PROVIDER_ID}"',
        "-c",
        f'model_providers.{PROVIDER_ID}.name="OpenRouter"',
        "-c",
        f'model_providers.{PROVIDER_ID}.base_url="{openai_base_url()}"',
        "-c",
        f'model_providers.{PROVIDER_ID}.env_key="OPENROUTER_API_KEY"',
        "-c",
        f'model_providers.{PROVIDER_ID}.wire_api="responses"',
        "-c",
        f'model_catalog_json="{catalog}"',
    ]
    return foreground_call(["codex", *overrides, *argv], env=env)


def run_claude(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        list_models(claude=True)
        return 0

    key = api_key()
    model = claude_model()
    host = "127.0.0.1"
    port = available_port(host)
    manager = ProcessManager()
    try:
        start_claude_proxy(manager, host, port)
        env = os.environ.copy()
        env["OPENROUTER_API_KEY"] = key
        env["ANTHROPIC_AUTH_TOKEN"] = key
        env["ANTHROPIC_API_KEY"] = ""
        env["ANTHROPIC_BASE_URL"] = f"http://{host}:{port}"
        env["ANTHROPIC_MODEL"] = model
        env["API_TIMEOUT_MS"] = env.get("API_TIMEOUT_MS", "3000000")
        env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = "1"
        env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
        # Native tier routing: GLM 5.2 supervises (opus/fable), DeepSeek codes
        # (sonnet) and handles trivial work (haiku). Overridable via tiers.resolve
        # (env OPENROUTER_TIER_*_MODEL or the openrouter catalog).
        supervisor = tiers.resolve("openrouter", "supervisor") or model
        coder = tiers.resolve("openrouter", "coder") or DEFAULT_CODER_MODEL
        small = tiers.resolve("openrouter", "small") or DEFAULT_SMALL_MODEL
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = supervisor
        env["ANTHROPIC_DEFAULT_FABLE_MODEL"] = supervisor
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = coder
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = small
        env["CLAUDE_CONFIG_DIR"] = str(paths.claude_openrouter_home())
        env["ANTHROPIC_CUSTOM_MODEL_OPTION"] = model
        env["ANTHROPIC_CUSTOM_MODEL_OPTION_NAME"] = f"OpenRouter {model}"
        env["ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION"] = "Anthropic model through OpenRouter"
        return foreground_call(["claude", *argv], env=env)
    finally:
        manager.cleanup()


def opencode_model_name(model: str) -> str:
    if model.startswith(f"{PROVIDER_ID}/"):
        return model
    return f"{PROVIDER_ID}/{model}"


def rewrite_opencode_model_args(argv: list[str]) -> list[str]:
    rewritten: list[str] = []
    rewrite_next = False
    for arg in argv:
        if rewrite_next:
            rewritten.append(opencode_model_name(arg))
            rewrite_next = False
            continue
        if arg in {"-m", "--model"}:
            rewritten.append(arg)
            rewrite_next = True
        elif arg.startswith("--model="):
            rewritten.append(f"--model={opencode_model_name(arg.split('=', 1)[1])}")
        else:
            rewritten.append(arg)
    return rewritten


def opencode_config_content() -> str:
    model = opencode_model_name(opencode_model())
    return json.dumps(
        {"$schema": "https://opencode.ai/config.json", "model": model, "small_model": model},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def run_opencode(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        list_models(opencode=True)
        return 0

    env = os.environ.copy()
    env["OPENROUTER_API_KEY"] = api_key()
    env["OPENCODE_CONFIG_CONTENT"] = opencode_config_content()
    return foreground_call(["opencode", *rewrite_opencode_model_args(argv)], env=env)
