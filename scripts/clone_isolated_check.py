#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(argv), flush=True)
    subprocess.check_call(argv, cwd=cwd, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone this repo and run non-network isolated checks.")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--workdir", default="/tmp/ILaas-agent-isolated-check")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    workdir = Path(args.workdir).resolve()
    clone = workdir / "repo"
    fake = workdir / "fake-home"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    run(["git", "clone", str(source), str(clone)], cwd=workdir)
    env = os.environ.copy()
    env.update({
        "ILAAS_API_KEY": "dummy",
        "ILAAS_HOME": str(fake / "home"),
        "ILAAS_CONFIG_HOME": str(fake / "config"),
        "ILAAS_CACHE_HOME": str(fake / "cache"),
    })

    py_files = ["install.py"]
    py_files.extend(str(path.relative_to(clone)) for path in sorted((clone / "ilaas_agents").glob("*.py")))
    py_files.extend(str(path.relative_to(clone)) for path in sorted((clone / "proxies").glob("*.py")))
    run([sys.executable, "-m", "py_compile", *py_files], cwd=clone, env=env)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=clone, env=env)
    run(["bash", "-n", "Ilaas-codex", "Ilaas-claude", "Ilaas-opencode", "Ilaas-doctor", "Ilaas-servers", "install.sh"], cwd=clone, env=env)
    print(f"isolated clone checks OK: {clone}", flush=True)


if __name__ == "__main__":
    main()
