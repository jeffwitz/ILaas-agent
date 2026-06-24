from __future__ import annotations

import argparse

from . import runners


def run(args: argparse.Namespace) -> int:
    failures = 0
    agents = ["codex", "claude", "opencode"] if args.agent == "all" else [args.agent]
    for agent in agents:
        status = run_agent(agent, args.model, args.tool_test)
        if status != 0:
            failures += 1
    return 0 if failures == 0 else 1


def run_agent(agent: str, model: str, tool_test: bool) -> int:
    if tool_test:
        prompt = "Read the file refresh_ilaas_models.py and reply only with the value of DEFAULT_ALIAS."
    else:
        prompt = "Reply exactly: OK"

    print(f"[SMOKE] {agent} model={model} tool_test={tool_test}", flush=True)
    if agent == "codex":
        argv = ["exec", "--skip-git-repo-check", "--model", model, prompt]
        return runners.run_codex(argv)
    if agent == "claude":
        argv = ["-p", "--model", model]
        if tool_test:
            argv.extend(["--allowedTools", "Read", "--permission-mode", "bypassPermissions"])
        argv.append(prompt)
        return runners.run_claude(argv)
    if agent == "opencode":
        return runners.run_opencode(["run", "--model", model, prompt])
    raise SystemExit(f"unknown smoke agent: {agent}")


def add_parser(subparsers) -> None:
    parser = subparsers.add_parser("smoke", help="Run token-consuming smoke tests against one or more agents.")
    parser.add_argument("--agent", choices=["all", "codex", "claude", "opencode"], default="all")
    parser.add_argument("--model", default="qwen-3.6-35b-instruct")
    parser.add_argument("--tool-test", action="store_true", help="Ask agents to read refresh_ilaas_models.py when supported.")
