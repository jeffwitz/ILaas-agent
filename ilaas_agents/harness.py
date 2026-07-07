"""Install the supervisor/coder harness into Claude Code config dirs.

The harness is the GLM-5.2-supervisor + DeepSeek-coder setup used by the
openrouter/GLM launchers: agent definitions (``ctx-pro``, ``code-pro``,
``code-flash``), SessionStart/PreToolUse hooks, and the codebase-memory-mcp
server config. The source templates live in the repo under ``harness/`` so a
``git clone`` + ``harness install`` reproduces the setup on any machine.

Agents go into the openrouter config home (they reference OpenRouter-routed
model IDs that only resolve under the launcher's proxy env). Hooks and the
MCP config go into ``~/.claude`` (shared) and are symlinked from the
openrouter config home, matching the existing layout.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import paths


HARNESS_DIR = paths.repo_root() / "harness"
PLACEHOLDER = "__CODEBASE_MEMORY_BIN__"


def codebase_memory_bin() -> str | None:
    """Resolve the codebase-memory-mcp binary path.

    Precedence: $CODEBASE_MEMORY_MCP_BIN > PATH lookup > ~/.local/bin/codebase-memory-mcp.
    Returns None if not found.
    """
    configured = os.environ.get("CODEBASE_MEMORY_MCP_BIN")
    if configured:
        return configured
    found = shutil.which("codebase-memory-mcp")
    if found:
        return found
    default = paths.home() / ".local" / "bin" / "codebase-memory-mcp"
    return str(default) if default.exists() else None


def _render(template: str, bin_path: str) -> str:
    if PLACEHOLDER not in template:
        return template
    return template.replace(PLACEHOLDER, bin_path)


def _install_file(src: Path, dst: Path, bin_path: str | None, executable: bool = False) -> Path:
    content = src.read_text(encoding="utf-8")
    if bin_path is not None:
        content = _render(content, bin_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    if executable:
        dst.chmod(dst.stat().st_mode | 0o755)
    return dst


def _ensure_symlink(link: Path, target: Path) -> bool:
    """Create a symlink link -> target if link does not exist. Returns True if created."""
    if link.exists() or link.is_symlink():
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return True


def install_harness(
    openrouter_home: Path | None = None,
    claude_home: Path | None = None,
    bin_path: str | None = None,
) -> dict[str, list[str]]:
    """Deploy agents, hooks, and MCP config into the config dirs.

    Returns a dict with the lists of deployed paths per category.
    Raises SystemExit if the codebase-memory-mcp binary cannot be resolved.
    """
    openrouter_home = openrouter_home or paths.claude_openrouter_home()
    claude_home = claude_home or paths.home() / ".claude"
    bin_path = bin_path if bin_path is not None else codebase_memory_bin()
    if not bin_path:
        raise SystemExit(
            "codebase-memory-mcp binary not found. Set CODEBASE_MEMORY_MCP_BIN, "
            "install it on PATH, or place it at ~/.local/bin/codebase-memory-mcp."
        )

    deployed: dict[str, list[str]] = {"agents": [], "hooks": [], "mcp": [], "symlinks": []}

    # Agents -> openrouter config home (they need the launcher proxy env).
    agents_src = HARNESS_DIR / "agents"
    agents_dst = openrouter_home / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    for src in sorted(agents_src.glob("*.md")):
        dst = _install_file(src, agents_dst / src.name, bin_path=None)
        deployed["agents"].append(str(dst))

    # Hooks -> ~/.claude/hooks (shared). Templates are rendered with the bin path.
    hooks_src = HARNESS_DIR / "hooks"
    hooks_dst = claude_home / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for src in sorted(hooks_src.iterdir()):
        name = src.name.removesuffix(".template") if src.name.endswith(".template") else src.name
        dst = _install_file(src, hooks_dst / name, bin_path=bin_path, executable=True)
        deployed["hooks"].append(str(dst))

    # Ensure openrouter hooks dir mirrors ~/.claude/hooks (symlink if absent).
    or_hooks = openrouter_home / "hooks"
    if _ensure_symlink(or_hooks, hooks_dst):
        deployed["symlinks"].append(f"{or_hooks} -> {hooks_dst}")

    # MCP config -> ~/.claude/.mcp.json, symlinked from the openrouter home.
    mcp_template = HARNESS_DIR / "mcp.json.template"
    mcp_dst = claude_home / ".mcp.json"
    _install_file(mcp_template, mcp_dst, bin_path=bin_path)
    deployed["mcp"].append(str(mcp_dst))
    or_mcp = openrouter_home / ".mcp.json"
    if _ensure_symlink(or_mcp, mcp_dst):
        deployed["symlinks"].append(f"{or_mcp} -> {mcp_dst}")

    return deployed
