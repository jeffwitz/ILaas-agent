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

import json
import os
import shutil
from pathlib import Path

from . import paths, tiers


HARNESS_DIR = paths.repo_root() / "harness"
HIERARCHY_PATH = HARNESS_DIR / "hierarchy.json"
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


def load_hierarchy() -> dict:
    """Load and parse harness/hierarchy.json.

    Raises SystemExit if the file is missing or contains invalid JSON.
    """
    if not HIERARCHY_PATH.is_file():
        raise SystemExit(f"hierarchy file not found: {HIERARCHY_PATH}")
    try:
        return json.loads(HIERARCHY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"hierarchy file is invalid: {HIERARCHY_PATH}: {exc}") from exc


def resolve_agent_model(hierarchy: dict, name: str) -> str:
    """Resolve the concrete model string for agent ``name`` from the hierarchy.

    Looks up the agent's tier via ``tiers.resolve``; falls back to the
    ``default_slug`` defined in hierarchy.json if the tier catalog has no entry.
    """
    entry = hierarchy["agents"][name]
    slug = tiers.resolve(hierarchy["provider"], entry["tier"]) or entry["default_slug"]
    return f'{hierarchy["model_prefix"]}{slug}'


def resolve_supervisor_display(hierarchy: dict) -> str:
    """Return the supervisor display name from the hierarchy."""
    return hierarchy["supervisor"]["display"]


def render_roster(hierarchy: dict) -> str:
    """Generate a compact block listing the supervisor and each agent."""
    sup = hierarchy["supervisor"]
    lines: list[str] = []
    lines.append(
        f"   - supervisor (tier={sup['tier']}, model={sup['display']})"
        " — holds the plan, reviews diffs, synthesizes, commits"
    )
    for name, entry in hierarchy["agents"].items():
        lines.append(
            f"   - {name} (tier={entry['tier']}, model={entry['display']})"
            f" — {entry['role']}"
        )
    return "\n".join(lines)


def _render(template: str, bin_path: str) -> str:
    if PLACEHOLDER not in template:
        return template
    return template.replace(PLACEHOLDER, bin_path)


def _apply_placeholders(content: str, placeholders: dict[str, str]) -> str:
    """Replace every key in *placeholders* with its value in *content*."""
    for key, value in placeholders.items():
        if key in content:
            content = content.replace(key, value)
    return content


def _install_file(
    src: Path,
    dst: Path,
    bin_path: str | None,
    executable: bool = False,
    placeholders: dict[str, str] | None = None,
) -> Path:
    content = src.read_text(encoding="utf-8")
    if bin_path is not None:
        content = _render(content, bin_path)
    if placeholders:
        content = _apply_placeholders(content, placeholders)
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


def _ensure_pre_tool_use_matcher(
    settings_path: Path, matcher: str, command: str, timeout: int = 5,
) -> bool:
    """Idempotently add a PreToolUse matcher entry to a settings.json file.

    Returns True if the matcher was added; False if it already existed or the
    settings file is missing/invalid.
    """
    if not settings_path.is_file():
        return False
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    data.setdefault("hooks", {})
    hooks = data["hooks"]
    if not isinstance(hooks, dict):
        return False
    hooks.setdefault("PreToolUse", [])
    pre = hooks["PreToolUse"]
    if not isinstance(pre, list):
        return False
    for entry in pre:
        if isinstance(entry, dict) and entry.get("matcher") == matcher:
            return False  # already present
    pre.append({
        "matcher": matcher,
        "hooks": [
            {"type": "command", "command": command, "timeout": timeout},
        ],
    })
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def rtk_bin() -> str | None:
    """Resolve the rtk (Rust Token Killer) binary path.

    Precedence: $RTK_BIN > PATH lookup > ~/.local/bin/rtk.
    Returns None if not found.
    """
    configured = os.environ.get("RTK_BIN")
    if configured:
        return configured
    found = shutil.which("rtk")
    if found:
        return found
    default = paths.home() / ".local" / "bin" / "rtk"
    return str(default) if default.exists() else None


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

    hierarchy = load_hierarchy()
    supervisor_display = resolve_supervisor_display(hierarchy)
    deployed: dict[str, list[str]] = {"agents": [], "hooks": [], "mcp": [], "symlinks": []}

    # Agents -> openrouter config home (they need the launcher proxy env).
    agents_src = HARNESS_DIR / "agents"
    agents_dst = openrouter_home / "agents"
    agents_dst.mkdir(parents=True, exist_ok=True)
    for src in sorted(agents_src.glob("*.md")):
        name = src.stem
        if name not in hierarchy["agents"]:
            raise SystemExit(
                f"agent template '{src.name}' has no entry in hierarchy.json"
            )
        model = resolve_agent_model(hierarchy, name)
        self_display = hierarchy["agents"][name]["display"]
        dst = _install_file(
            src, agents_dst / src.name, bin_path=None,
            placeholders={
                "__MODEL__": model,
                "__SELF_DISPLAY__": self_display,
                "__SUPERVISOR_DISPLAY__": supervisor_display,
            },
        )
        deployed["agents"].append(str(dst))

    # Hooks -> ~/.claude/hooks (shared). Templates are rendered with the bin path,
    # roster, and supervisor display.
    hooks_src = HARNESS_DIR / "hooks"
    hooks_dst = claude_home / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    roster = render_roster(hierarchy)
    for src in sorted(hooks_src.iterdir()):
        name = src.name.removesuffix(".template") if src.name.endswith(".template") else src.name
        dst = _install_file(
            src, hooks_dst / name, bin_path=bin_path, executable=True,
            placeholders={
                "__ROSTER__": roster,
                "__SUPERVISOR_DISPLAY__": supervisor_display,
            },
        )
        deployed["hooks"].append(str(dst))

    # Ensure openrouter hooks dir mirrors ~/.claude/hooks (symlink if absent).
    or_hooks = openrouter_home / "hooks"
    if _ensure_symlink(or_hooks, hooks_dst):
        deployed["symlinks"].append(f"{or_hooks} -> {hooks_dst}")

    # Register the Read cost-gate as a PreToolUse matcher in both settings.json.
    read_hook_command = str(hooks_dst / "cbm-read-cost-gate")
    deployed.setdefault("settings", [])
    for sp in (claude_home / "settings.json", openrouter_home / "settings.json"):
        if _ensure_pre_tool_use_matcher(sp, "Read", read_hook_command):
            deployed["settings"].append(str(sp))

    # Advise if rtk is not installed (non-fatal).
    if rtk_bin() is None:
        print(
            "rtk (Rust Token Killer) not found; install it to compress shell "
            "command output and save tokens (rtk gain for analytics)."
        )

    # MCP config -> ~/.claude/.mcp.json, symlinked from the openrouter home.
    mcp_template = HARNESS_DIR / "mcp.json.template"
    mcp_dst = claude_home / ".mcp.json"
    _install_file(mcp_template, mcp_dst, bin_path=bin_path)
    deployed["mcp"].append(str(mcp_dst))
    or_mcp = openrouter_home / ".mcp.json"
    if _ensure_symlink(or_mcp, mcp_dst):
        deployed["symlinks"].append(f"{or_mcp} -> {mcp_dst}")

    return deployed
