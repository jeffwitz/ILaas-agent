from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import paths
from . import tiers
from .processes import ProcessManager, foreground_call, pid_file, python_executable, read_pid, terminate_pid


MODEL_PREFIX = "claude-ilaas-"
DEFAULT_CLAUDE_MODEL = "claude-ilaas-ilaas-default"
DEFAULT_OPENCODE_MODEL = "ilaas-default"
PROVIDER_ID = "ilaas"


@dataclass
class RuntimeConfig:
    litellm_host: str = "127.0.0.1"
    litellm_port: int = 4000
    responses_host: str = "127.0.0.1"
    responses_port: int = 4001
    claude_host: str = "127.0.0.1"
    claude_port: int = 4002

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            litellm_host=os.environ.get("LITELLM_HOST", "127.0.0.1"),
            litellm_port=int(os.environ.get("LITELLM_PORT", "4000")),
            responses_host=os.environ.get("RESPONSES_HOST", "127.0.0.1"),
            responses_port=int(os.environ.get("RESPONSES_PORT", "4001")),
            claude_host=os.environ.get("CLAUDE_ILAAS_HOST", "127.0.0.1"),
            claude_port=int(os.environ.get("CLAUDE_ILAAS_PORT", "4002")),
        )


def litellm_bin() -> str:
    configured = os.environ.get("LITELLM_BIN")
    if configured:
        return configured
    venv_bin = paths.litellm_venv() / ("Scripts/litellm.exe" if paths.is_windows() else "bin/litellm")
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("litellm")
    if found:
        return found
    raise SystemExit("litellm not found. Run python install.py or set LITELLM_BIN.")


def http_json(url: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status >= 400:
                return None
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def http_json_ok(url: str, timeout: float = 2.0) -> bool:
    return http_json(url, timeout) is not None


def wait_for_http_json(name: str, url: str, attempts: int = 80) -> None:
    for _ in range(attempts):
        if http_json_ok(url):
            return
        time.sleep(0.25)
    raise SystemExit(f"timed out waiting for {name} at {url}")


def require_existing_http_service(name: str, url: str, port_hint: str, expected_service: str | None = None) -> None:
    payload = http_json(url)
    if payload is not None and (expected_service is None or payload.get("service") == expected_service):
        return
    expected = f" with service={expected_service}" if expected_service else ""
    raise SystemExit(
        f"{name} port is open but the expected ILaaS service{expected} did not answer at {url}. "
        f"Stop the conflicting service or use {port_hint} to choose another port."
    )


def ensure_litellm(manager: ProcessManager, cfg: RuntimeConfig, persistent: bool = False) -> None:
    health_url = f"http://{cfg.litellm_host}:{cfg.litellm_port}/v1/models"
    if manager.port_open(cfg.litellm_host, cfg.litellm_port):
        require_existing_http_service("LiteLLM", health_url, "LITELLM_PORT")
        print(f"ILaaS: LiteLLM already listening on {cfg.litellm_host}:{cfg.litellm_port}", file=sys.stderr)
        return
    config_path = Path(os.environ.get("LITELLM_CONFIG", paths.litellm_config_path()))
    if not config_path.exists():
        raise SystemExit(f"LiteLLM config not found: {config_path}")
    print(f"ILaaS: starting LiteLLM on {cfg.litellm_host}:{cfg.litellm_port}", file=sys.stderr)
    manager.start(
        "litellm",
        [litellm_bin(), "--config", str(config_path), "--host", cfg.litellm_host, "--port", str(cfg.litellm_port)],
        paths.log_dir() / "litellm.log",
        pid_file("litellm") if persistent else None,
        detach=persistent,
    )
    manager.wait_for_port("LiteLLM", cfg.litellm_host, cfg.litellm_port)
    wait_for_http_json("LiteLLM", health_url)


def ensure_codex_proxy(manager: ProcessManager, cfg: RuntimeConfig, persistent: bool = False) -> None:
    health_url = f"http://{cfg.responses_host}:{cfg.responses_port}/health"
    if manager.port_open(cfg.responses_host, cfg.responses_port):
        require_existing_http_service("Codex Responses proxy", health_url, "RESPONSES_PORT", "ilaas-codex-responses-proxy")
        print(f"ILaaS: Codex Responses proxy already listening on {cfg.responses_host}:{cfg.responses_port}", file=sys.stderr)
        return
    proxy = paths.repo_root() / "proxies" / "codex_ilaas_responses_proxy.py"
    print(f"ILaaS: starting Codex Responses proxy on {cfg.responses_host}:{cfg.responses_port}", file=sys.stderr)
    manager.start(
        "codex-proxy",
        [
            python_executable(),
            str(proxy),
            "--host",
            cfg.responses_host,
            "--port",
            str(cfg.responses_port),
            "--upstream",
            f"http://{cfg.litellm_host}:{cfg.litellm_port}/v1",
        ],
        paths.log_dir() / "codex-responses-proxy.log",
        pid_file("codex-proxy") if persistent else None,
        detach=persistent,
    )
    manager.wait_for_port("Codex Responses proxy", cfg.responses_host, cfg.responses_port)
    wait_for_http_json("Codex Responses proxy", health_url)


def ensure_claude_proxy(manager: ProcessManager, cfg: RuntimeConfig, persistent: bool = False) -> None:
    health_url = f"http://{cfg.claude_host}:{cfg.claude_port}/health"
    if manager.port_open(cfg.claude_host, cfg.claude_port):
        require_existing_http_service("Claude Messages proxy", health_url, "CLAUDE_ILAAS_PORT", "ilaas-claude-messages-proxy")
        print(f"ILaaS: Claude Messages proxy already listening on {cfg.claude_host}:{cfg.claude_port}", file=sys.stderr)
        return
    proxy = paths.repo_root() / "proxies" / "claude_ilaas_messages_proxy.py"
    print(f"ILaaS: starting Claude Messages proxy on {cfg.claude_host}:{cfg.claude_port}", file=sys.stderr)
    manager.start(
        "claude-proxy",
        [
            python_executable(),
            str(proxy),
            "--host",
            cfg.claude_host,
            "--port",
            str(cfg.claude_port),
            "--upstream",
            f"http://{cfg.litellm_host}:{cfg.litellm_port}/v1",
        ],
        paths.log_dir() / "claude-messages-proxy.log",
        pid_file("claude-proxy") if persistent else None,
        detach=persistent,
    )
    manager.wait_for_port("Claude Messages proxy", cfg.claude_host, cfg.claude_port)
    wait_for_http_json("Claude Messages proxy", health_url)


def list_models(claude: bool = False) -> None:
    catalog_path = Path(os.environ.get("ILAAS_MODEL_CATALOG", paths.model_catalog_path()))
    if not catalog_path.exists():
        raise SystemExit(f"model catalog not found: {catalog_path}. Run python -m ilaas_agents.cli refresh-models first.")
    catalog = json.loads(catalog_path.read_text())
    for model in catalog.get("models", []):
        slug = model.get("slug")
        if not slug:
            continue
        name = f"{MODEL_PREFIX}{slug}" if claude else slug
        note = ""
        if slug.startswith("llama-3.1-") or slug.startswith("llama-3.3-"):
            note = "  # chat only / weak tool-calling candidate"
        print(f"{name}{note}")


def run_codex(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        list_models(claude=False)
        return 0
    cfg = RuntimeConfig.from_env()
    manager = ProcessManager()
    keep = os.environ.get("ILAAS_CODEX_KEEP_SERVERS", os.environ.get("MISTRAL_CODEX_KEEP_SERVERS", "0")) == "1"
    try:
        ensure_litellm(manager, cfg)
        ensure_codex_proxy(manager, cfg)
        env = os.environ.copy()
        env["CODEX_HOME"] = env.get("CODEX_HOME", str(paths.codex_home()))
        env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "sk-local-dummy")
        return foreground_call(["codex", *argv], env=env)
    finally:
        manager.cleanup(keep=keep)


def rewrite_claude_model_args(argv: list[str]) -> tuple[list[str], str]:
    rewritten: list[str] = []
    selected = ""
    rewrite_next = False
    for arg in argv:
        if rewrite_next:
            model = claude_model_name(arg)
            selected = model
            rewritten.append(model)
            rewrite_next = False
            continue
        if arg == "--model":
            rewritten.append(arg)
            rewrite_next = True
        elif arg.startswith("--model="):
            model = claude_model_name(arg.split("=", 1)[1])
            selected = model
            rewritten.append(f"--model={model}")
        else:
            rewritten.append(arg)
    return rewritten, selected or DEFAULT_CLAUDE_MODEL


def claude_model_name(model: str) -> str:
    if model.startswith(("claude-", "anthropic")) or model in {"opus", "sonnet", "haiku", "fable"}:
        return model
    return MODEL_PREFIX + model


def run_claude(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        list_models(claude=True)
        return 0
    cfg = RuntimeConfig.from_env()
    manager = ProcessManager()
    keep = os.environ.get("ILAAS_CLAUDE_KEEP_SERVERS", "0") == "1"
    try:
        ensure_litellm(manager, cfg)
        ensure_claude_proxy(manager, cfg)
        rewritten, selected = rewrite_claude_model_args(argv)
        if "llama-3.1-8b" in selected or "llama-3.3-70b" in selected:
            print(
                f"ILaaS: warning: {selected.removeprefix(MODEL_PREFIX)} is not recommended for Claude Code tools.",
                file=sys.stderr,
            )
        supervisor = tiers.resolve("ilaas", "supervisor") or DEFAULT_CLAUDE_MODEL
        coder = tiers.resolve("ilaas", "coder") or supervisor
        small = tiers.resolve("ilaas", "small") or supervisor
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = f"http://{cfg.claude_host}:{cfg.claude_port}"
        env["ANTHROPIC_API_KEY"] = env.get("ANTHROPIC_API_KEY", "sk-local-dummy")
        env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"] = env.get("CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "1")
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", supervisor)
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", coder)
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", small)
        env["ANTHROPIC_DEFAULT_FABLE_MODEL"] = env.get("ANTHROPIC_DEFAULT_FABLE_MODEL", supervisor)
        env["MAX_THINKING_TOKENS"] = env.get("MAX_THINKING_TOKENS", "0")
        env["ANTHROPIC_CUSTOM_MODEL_OPTION"] = env.get("ANTHROPIC_CUSTOM_MODEL_OPTION", selected)
        env["ANTHROPIC_CUSTOM_MODEL_OPTION_NAME"] = env.get("ANTHROPIC_CUSTOM_MODEL_OPTION_NAME", f"ILaaS {selected.removeprefix(MODEL_PREFIX)}")
        env["ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION"] = env.get("ANTHROPIC_CUSTOM_MODEL_OPTION_DESCRIPTION", "ILaaS model through local gateway")
        return foreground_call(["claude", *rewritten], env=env)
    finally:
        manager.cleanup(keep=keep)


def opencode_config_content(cfg: RuntimeConfig) -> str:
    catalog_path = Path(os.environ.get("ILAAS_MODEL_CATALOG", paths.model_catalog_path()))
    if not catalog_path.exists():
        raise SystemExit(f"model catalog not found: {catalog_path}")
    catalog = json.loads(catalog_path.read_text())
    models = {}
    for model in catalog.get("models", []):
        slug = model.get("slug")
        if not slug:
            continue
        models[slug] = {
            "name": model.get("display_name") or slug,
            "limit": {
                "context": int(model.get("context_window") or 262144),
                "output": 4096,
            },
        }
    default_model = os.environ.get("ILAAS_OPENCODE_MODEL", DEFAULT_OPENCODE_MODEL)
    supervisor = tiers.resolve("ilaas", "supervisor") or default_model
    small = tiers.resolve("ilaas", "small") or supervisor
    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"{PROVIDER_ID}/{supervisor}",
        "small_model": f"{PROVIDER_ID}/{small}",
        "provider": {
            PROVIDER_ID: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "ILaaS via LiteLLM",
                "options": {
                    "baseURL": f"http://{cfg.litellm_host}:{cfg.litellm_port}/v1",
                    "apiKey": "{env:OPENAI_API_KEY}",
                    "timeout": 600000,
                    "chunkTimeout": 60000,
                },
                "models": models,
            }
        },
    }
    return json.dumps(config, ensure_ascii=False, separators=(",", ":"))


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


def opencode_model_name(model: str) -> str:
    if "/" in model:
        return model
    return f"{PROVIDER_ID}/{model}"


def run_opencode(argv: list[str]) -> int:
    if argv == ["--list-models"]:
        list_models()
        return 0
    cfg = RuntimeConfig.from_env()
    manager = ProcessManager()
    keep = os.environ.get("ILAAS_OPENCODE_KEEP_SERVERS", "0") == "1"
    try:
        ensure_litellm(manager, cfg)
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = env.get("OPENAI_API_KEY", "sk-local-dummy")
        env["OPENCODE_CONFIG_CONTENT"] = opencode_config_content(cfg)
        return foreground_call(["opencode", *rewrite_opencode_model_args(argv)], env=env)
    finally:
        manager.cleanup(keep=keep)


def servers(action: str) -> int:
    cfg = RuntimeConfig.from_env()
    manager = ProcessManager()
    if action == "start":
        ensure_litellm(manager, cfg, persistent=True)
        ensure_codex_proxy(manager, cfg, persistent=True)
        ensure_claude_proxy(manager, cfg, persistent=True)
        print(f"Logs: {paths.log_dir()}")
        return 0
    if action == "status":
        for name in ["litellm", "codex-proxy", "claude-proxy"]:
            pid = read_pid(name)
            state = f"pid {pid}" if pid else "no pid"
            print(f"{name}: {state}")
        for label, host, port in [
            ("LiteLLM", cfg.litellm_host, cfg.litellm_port),
            ("Codex proxy", cfg.responses_host, cfg.responses_port),
            ("Claude proxy", cfg.claude_host, cfg.claude_port),
        ]:
            print(f"{label} {host}:{port}: {'listening' if manager.port_open(host, port) else 'stopped'}")
        return 0
    if action == "stop":
        for name in ["claude-proxy", "codex-proxy", "litellm"]:
            pid = read_pid(name)
            if pid:
                terminate_pid(pid)
                pid_file(name).unlink(missing_ok=True)
                print(f"stopped {name} ({pid})")
        return 0
    if action == "logs":
        print(paths.log_dir())
        return 0
    raise SystemExit(f"unknown servers action: {action}")
