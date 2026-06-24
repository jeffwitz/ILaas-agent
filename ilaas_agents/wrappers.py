from __future__ import annotations

import os
from pathlib import Path

from . import paths


POSIX_NAMES = ["Ilaas-codex", "Ilaas-claude", "Ilaas-opencode"]


def install_wrappers(wrapper_dir: Path | None = None) -> list[Path]:
    wrapper_dir = wrapper_dir or paths.bin_dir()
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    installed = []
    for name in POSIX_NAMES:
        if paths.is_windows():
            installed.extend(write_windows_wrappers(wrapper_dir, name))
        else:
            installed.append(write_posix_wrapper(wrapper_dir, name))
    return installed


def write_posix_wrapper(wrapper_dir: Path, name: str) -> Path:
    target = wrapper_dir / name
    target.write_text(
        "#!/usr/bin/env bash\n"
        f"exec {paths.repo_root() / name} \"$@\"\n"
    )
    target.chmod(target.stat().st_mode | 0o755)
    return target


def write_windows_wrappers(wrapper_dir: Path, name: str) -> list[Path]:
    repo = paths.repo_root()
    module = name.replace("Ilaas-", "")
    cmd = wrapper_dir / f"{name}.cmd"
    ps1 = wrapper_dir / f"{name}.ps1"
    cmd.write_text(f'@echo off\r\npython -m ilaas_agents.cli {module} %*\r\n')
    ps1.write_text(f'python -m ilaas_agents.cli {module} @args\r\n')
    return [cmd, ps1]


def path_hint(wrapper_dir: Path | None = None) -> str | None:
    wrapper_dir = wrapper_dir or paths.bin_dir()
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if str(wrapper_dir) in path_entries:
        return None
    if paths.is_windows():
        return f"Add {wrapper_dir} to PATH."
    return f'Add this to your shell profile: export PATH="{wrapper_dir}:$PATH"'
