from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    key: str
    command: str
    package: str | None
    install_command: list[str] | None
    required_runtime: str | None = "npm"


AGENT_TOOLS = {
    "codex": ToolSpec("codex", "codex", "@openai/codex", ["npm", "install", "-g", "@openai/codex"]),
    "claude": ToolSpec("claude", "claude", "@anthropic-ai/claude-code", ["npm", "install", "-g", "@anthropic-ai/claude-code"]),
    "opencode": ToolSpec("opencode", "opencode", "opencode-ai", ["npm", "install", "-g", "opencode-ai"]),
}

RUNTIME_TOOLS = {
    "node": ToolSpec("node", "node", None, None, None),
    "npm": ToolSpec("npm", "npm", None, None, None),
    "bun": ToolSpec("bun", "bun", None, None, None),
}


def command_path(command: str) -> str | None:
    return shutil.which(command)


def command_version(command: str) -> str | None:
    if not command_path(command):
        return None
    try:
        output = subprocess.check_output([command, "--version"], stderr=subprocess.STDOUT, text=True, timeout=15)
    except Exception:
        return "installed"
    return output.strip().splitlines()[0] if output.strip() else "installed"


def tool_status(spec: ToolSpec) -> tuple[bool, str]:
    version = command_version(spec.command)
    if version is None:
        if spec.install_command:
            return False, "missing; install with: " + " ".join(spec.install_command)
        return False, "missing"
    path = command_path(spec.command) or spec.command
    return True, f"{version} ({path})"


def agent_statuses() -> list[tuple[str, bool, str]]:
    return [(key, *tool_status(spec)) for key, spec in AGENT_TOOLS.items()]


def runtime_statuses() -> list[tuple[str, bool, str]]:
    return [(key, *tool_status(spec)) for key, spec in RUNTIME_TOOLS.items()]


def missing_agents(selected: list[str] | None = None) -> list[ToolSpec]:
    keys = list(AGENT_TOOLS) if not selected or "all" in selected else selected
    missing = []
    for key in keys:
        spec = AGENT_TOOLS[key]
        ok, _ = tool_status(spec)
        if not ok:
            missing.append(spec)
    return missing


def npm_available() -> bool:
    return command_path("npm") is not None


def install_agents(selected: list[str] | None = None) -> None:
    targets = missing_agents(selected)
    if not targets:
        print("All selected code-agent CLIs are already installed.")
        return
    if not npm_available():
        print("npm is required to install missing agent CLIs automatically.")
        print("Install Node.js/npm first, then retry or install the agents manually.")
        raise SystemExit(1)
    for spec in targets:
        if not spec.install_command:
            continue
        print("Installing", spec.key, "with:", " ".join(spec.install_command))
        subprocess.check_call(spec.install_command)


def print_status() -> None:
    print("Runtimes:")
    for key, ok, detail in runtime_statuses():
        print(f"[{'OK' if ok else 'WARN'}] {key}: {detail}")
    print("Code agents:")
    for key, ok, detail in agent_statuses():
        print(f"[{'OK' if ok else 'WARN'}] {key}: {detail}")


def prompt_install_missing() -> bool:
    missing = missing_agents()
    if not missing:
        return False
    print("Missing code-agent CLIs:")
    for spec in missing:
        print(f"- {spec.key}: {' '.join(spec.install_command or [])}")
    answer = input("Install missing code-agent CLIs with npm now? [y/N] ").strip().lower()
    if answer in {"y", "yes", "o", "oui"}:
        install_agents([spec.key for spec in missing])
        return True
    return False
