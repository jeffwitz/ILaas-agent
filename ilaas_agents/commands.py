"""Generate the Claude Code `/economy` slash command.

The command wraps ``scripts/token_economy.py`` so users can get the token-savings
report from inside any Claude Code session started by the openrouter/GLM
launchers. It is written into that config home's ``commands/`` directory.

Portability: the absolute path to the script is substituted at install time
(like the shell wrappers). The projects directory is *not* hardcoded — the script
defaults to ``$CLAUDE_CONFIG_DIR/projects``, which the openrouter launcher already
sets, so the command reads the right transcripts on any machine.
"""
from __future__ import annotations

from pathlib import Path

from . import paths


def economy_command_content(script_path: Path) -> str:
    script = str(script_path)
    return f"""---
description: Token savings of the multi-tier / delegation strategy vs all-on-Opus
argument-hint: "[--all | --project <name> | --by-session]  (default: all projects)"
allowed-tools: Bash(python3 {script}:*)
---

Token-economy report for the openrouter/GLM launchers (supervisor GLM 5.2 plus
`ctx-pro` / `code-pro` / `code-flash` delegation). Reads this config home's
transcripts (`$CLAUDE_CONFIG_DIR/projects`, subagent files included).

Economy vs the basic strategy (everything on the premium Opus supervisor):

!`python3 {script} --economy ${{ARGUMENTS:---all}}`

Full breakdown by model / role (fresh vs cache_read, sidechain split):

!`python3 {script} ${{ARGUMENTS:---all}}`

From these outputs, present concisely:
1. **The saving** — baseline cost vs real cost, gain in `$` and `%`, tokens offloaded from the supervisor.
2. **The dominant cost** — usually the supervisor's `cache_read` (recurring cost of its growing context).
3. **The sidechain split** — share of input absorbed by delegated subagents.

Note in one line that prices are indicative (editable in `PRICES` /
`BASELINE_PRICE` of the script) until replaced by real rates.
"""


def economy_command_path(home: Path | None = None) -> Path:
    home = home or paths.claude_openrouter_home()
    return home / "commands" / "economy.md"


def write_economy_command(path: Path, script_path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(economy_command_content(script_path), encoding="utf-8")


def install_economy_command(home: Path | None = None, script_path: Path | None = None) -> Path:
    target = economy_command_path(home)
    write_economy_command(target, script_path or paths.token_economy_script())
    return target
