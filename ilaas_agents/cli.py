from __future__ import annotations

import argparse
import sys

from . import deps, doctor, glm52, harness, models, openrouter, paths, runners, smoke, tiers
from .install import main as install_main


def refresh_models() -> None:
    existing = models.extract_existing_settings(paths.litellm_config_path())
    if not existing:
        raise SystemExit(f"Missing LiteLLM config or API key: {paths.litellm_config_path()}")
    api_base, api_key = existing
    model_ids = models.fetch_models(api_base, api_key)
    models.write_litellm_config(paths.litellm_config_path(), api_base, api_key, model_ids)
    models.write_codex_catalog(paths.model_catalog_path(), model_ids)
    print(f"Refreshed {len(model_ids)} ILaaS models plus aliases.")
    for model_id in model_ids:
        print(model_id)


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "install":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        install_main()
        return

    if len(sys.argv) >= 2 and sys.argv[1] in {"codex", "claude", "opencode"}:
        command = sys.argv[1]
        argv = sys.argv[2:]
        if command == "codex":
            raise SystemExit(runners.run_codex(argv))
        if command == "claude":
            raise SystemExit(runners.run_claude(argv))
        raise SystemExit(runners.run_opencode(argv))

    if len(sys.argv) >= 2 and sys.argv[1] in {"glm52-codex", "glm52-claude", "glm52-opencode"}:
        command = sys.argv[1].removeprefix("glm52-")
        argv = sys.argv[2:]
        if command == "codex":
            raise SystemExit(glm52.run_codex(argv))
        if command == "claude":
            raise SystemExit(glm52.run_claude(argv))
        raise SystemExit(glm52.run_opencode(argv))

    if len(sys.argv) >= 2 and sys.argv[1] in {
        "openrouter-codex",
        "openrouter-claude",
        "openrouter-opencode",
    }:
        command = sys.argv[1].removeprefix("openrouter-")
        argv = sys.argv[2:]
        if command == "codex":
            raise SystemExit(openrouter.run_codex(argv))
        if command == "claude":
            raise SystemExit(openrouter.run_claude(argv))
        raise SystemExit(openrouter.run_opencode(argv))

    parser = argparse.ArgumentParser(description="ILaaS code-agent helper CLI.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install")
    sub.add_parser("doctor")
    sub.add_parser("refresh-models")

    servers = sub.add_parser("servers")
    servers.add_argument("action", choices=["start", "stop", "status", "logs"])

    deps_parser = sub.add_parser("deps", help="Detect or install external code-agent CLI dependencies.")
    deps_sub = deps_parser.add_subparsers(dest="deps_action", required=True)
    deps_sub.add_parser("status")
    deps_install = deps_sub.add_parser("install")
    deps_install.add_argument("agents", nargs="*", choices=["all", "codex", "claude", "opencode"], default=["all"])

    smoke.add_parser(sub)

    tiers_parent = argparse.ArgumentParser(add_help=False)
    tiers_parent.add_argument("--provider", choices=["ilaas", "glm52", "openrouter"], required=True)
    tiers_parser = sub.add_parser("tiers", help="Manage tier-to-model mappings per provider.")
    tiers_sub = tiers_parser.add_subparsers(dest="tiers_action", required=True)
    tiers_sub.add_parser("list", parents=[tiers_parent], help="Show the currently resolved tier mapping.")
    tiers_sub.add_parser("show", parents=[tiers_parent], help="Show resolved tiers with the source of each.")
    tiers_sub.add_parser("suggest", parents=[tiers_parent], help="Suggest a tier mapping from the catalog.")
    tiers_apply = tiers_sub.add_parser("apply", parents=[tiers_parent], help="Write the tier field onto every catalog entry.")
    tiers_apply.add_argument("--tier", action="append", metavar="tier=slug")
    tiers_set = tiers_sub.add_parser("set", parents=[tiers_parent], help="Pin a specific slug to a tier.")
    tiers_set.add_argument("set_tier", metavar="tier", help="tier to pin (supervisor/coder/small).")
    tiers_set.add_argument("set_slug", metavar="slug", help="slug to pin to the tier.")

    harness_parser = sub.add_parser("harness", help="Install/inspect the GLM-supervisor + DeepSeek-coder harness (agents, hooks, MCP).")
    harness_sub = harness_parser.add_subparsers(dest="harness_action", required=True)
    harness_install = harness_sub.add_parser("install", help="Deploy agents, hooks, and MCP config into the Claude Code config dirs.")
    harness_install.add_argument("--bin", default=None, help="Path to the codebase-memory-mcp binary. Defaults to $CODEBASE_MEMORY_MCP_BIN, PATH lookup, then ~/.local/bin/codebase-memory-mcp.")
    harness_sub.add_parser("status", help="Show where the harness artifacts are deployed.")

    args = parser.parse_args()

    if args.command == "install":
        install_main()
    elif args.command == "doctor":
        raise SystemExit(doctor.run())
    elif args.command == "refresh-models":
        refresh_models()
    elif args.command == "servers":
        raise SystemExit(runners.servers(args.action))
    elif args.command == "deps":
        if args.deps_action == "status":
            deps.print_status()
            raise SystemExit(0)
        deps.install_agents(args.agents)
        raise SystemExit(0)
    elif args.command == "smoke":
        raise SystemExit(smoke.run(args))
    elif args.command == "tiers":
        if args.tiers_action == "list":
            for tier in tiers.TIERS:
                resolved = tiers.resolve(args.provider, tier)
                print(f"{args.provider} {tier}: {resolved or '(unset)'}")
            print(f"catalog: {tiers.catalog_path(args.provider)}")
            raise SystemExit(0)
        if args.tiers_action == "set":
            if args.set_tier not in tiers.TIERS:
                raise SystemExit(f"Unknown tier '{args.set_tier}'; expected one of: {', '.join(tiers.TIERS)}")
            mapping = {args.set_tier: args.set_slug}
            counts = tiers.apply(args.provider, mapping)
            print(f"Pinned {args.provider} {args.set_tier} -> {args.set_slug}; applied tiers: {counts}")
            raise SystemExit(0)
        if args.tiers_action == "show":
            for tier in tiers.TIERS:
                slug, source = tiers.resolve_with_source(args.provider, tier)
                print(f"{args.provider} {tier}: {slug or '(unset)'}  [source: {source}]")
            print(f"catalog: {tiers.catalog_path(args.provider)}  [source: {tiers.catalog_source(args.provider)}]")
            raise SystemExit(0)
        if args.tiers_action == "suggest":
            mapping = tiers.suggest(args.provider)
            for tier in tiers.TIERS:
                print(f"{args.provider} {tier}: {mapping.get(tier, '(none)')}")
            raise SystemExit(0)
        # tiers_action == "apply"
        if args.tier:
            mapping = {}
            for entry in args.tier:
                if "=" not in entry:
                    raise SystemExit(f"Invalid --tier format '{entry}': expected tier=slug (e.g. --tier supervisor=qwen-3.6-35b-instruct)")
                key, _, val = entry.partition("=")
                key, val = key.strip(), val.strip()
                if not key or not val:
                    raise SystemExit(f"Invalid --tier format '{entry}': both tier and slug must be non-empty")
                if key not in tiers.TIERS:
                    raise SystemExit(f"Unknown tier '{key}'; expected one of: {', '.join(tiers.TIERS)}")
                mapping[key] = val
        else:
            mapping = None
        counts = tiers.apply(args.provider, mapping)
        print(f"Applied tiers to {args.provider} catalog: {counts}")
        raise SystemExit(0)
    elif args.command == "harness":
        if args.harness_action == "status":
            print(f"repo source:  {harness.HARNESS_DIR}")
            print(f"openrouter home: {paths.claude_openrouter_home()}")
            print(f"claude home:      {paths.home() / '.claude'}")
            bin_path = harness.codebase_memory_bin()
            print(f"codebase-memory-mcp: {bin_path or '(not found)'}")
            raise SystemExit(0)
        # install
        deployed = harness.install_harness(bin_path=args.bin)
        for category, paths_list in deployed.items():
            if not paths_list:
                continue
            print(f"{category}:")
            for p in paths_list:
                print(f"  {p}")
        raise SystemExit(0)
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
