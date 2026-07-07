# The GLM-supervisor / DeepSeek-coder harness

## Repository vs Claude Code config — read this first

This repo contains two distinct things, and confusing them is the main
stumbling block for newcomers:

1. **The Python package `ilaas_agents/`** — the *launchers* (`openrouter-claude`,
   `glm52-claude`, `Ilaas-claude`, …). They are plain Python programs that start
   local proxies, set environment variables, and `exec` the real `claude` / `codex`
   / `opencode` binaries. They live in the repo and are installed by `install.py`.
2. **The harness** — *Claude Code configuration* (agent definitions, hooks, MCP
   server config) that tells the `claude` binary how to behave once launched: which
   subagents exist, what the SessionStart protocol is, which MCP server to load.
   These are Markdown/YAML/JSON files, not Python.

The harness is **versioned in this repo under `harness/`** but it is *deployed*
into Claude Code's config directories (`~/.claude_openrouter/`, `~/.claude/`) by
`ilaas-agents harness install`. A bare `git clone` gives you the source; the
install command turns it into a live Claude Code setup.

## What the harness does

The `openrouter-claude` (and `glm52-claude`) launchers run a **two-layer harness**:

1. **Native tier routing** inside Claude Code — configured by the launchers (see {doc}`tiers`): GLM 5.2 supervises (opus/fable), DeepSeek V4 Pro codes (sonnet), DeepSeek V4 Flash handles trivial work (haiku).
2. **Subagent delegation** — GLM 5.2 (the supervisor) delegates coding to `code-pro` (DeepSeek V4 Pro) and verbose graph queries to `ctx-pro` (DeepSeek V4 Pro), so heavy dumps stay out of the supervisor's persistent context.

The harness artifacts — agent definitions, SessionStart/PreToolUse hooks, and the codebase-memory-mcp server config — live in the repo under `harness/` so a clone reproduces the setup.

## Layout

```text
harness/
  agents/
    ctx-pro.md       # DeepSeek V4 Pro, read-only MCP tools, synthesizes verbose queries
    code-pro.md      # DeepSeek V4 Pro, coding tasks
    code-flash.md    # DeepSeek V4 Flash, mechanical/trivial tasks
  hooks/
    cbm-session-reminder          # SessionStart: Code Discovery Protocol (points 1-5)
    cbm-code-discovery-gate.template  # PreToolUse: augments Grep/Glob with graph context
  mcp.json.template   # declares the codebase-memory-mcp server
```

Templates use the `__CODEBASE_MEMORY_BIN__` placeholder, resolved at install time.

## What each piece does

- **`ctx-pro`** — the synthesizer the user asked for: it calls the codebase-memory-mcp tools (`detect_changes`, `get_architecture`, `trace_path`, `query_graph`, `search_graph`) and returns a compact synthesis, never the raw dump. This is what keeps the GLM 5.2 supervisor context small.
- **`cbm-session-reminder`** — injects the protocol at every session start: (1-3) use the graph first, (4) prove no conflict edge before parallel subagent dispatch, (5) delegate verbose MCP queries to `ctx-pro`.
- **`cbm-code-discovery-gate`** — PreToolUse hook on `Grep|Glob` that augments text search with graph context (never blocks).
- **`mcp.json`** — declares the `codebase-memory-mcp` server so its tools are available to the supervisor and to `ctx-pro`.

## Install

```bash
python3 -m ilaas_agents.cli harness install
```

This deploys:

- agents → `~/.claude_openrouter/agents/` (they need the launcher's proxy env to resolve their OpenRouter model IDs),
- hooks → `~/.claude/hooks/` (shared), symlinked from `~/.claude_openrouter/hooks`,
- MCP config → `~/.claude/.mcp.json`, symlinked from `~/.claude_openrouter/.mcp.json`.

The `codebase-memory-mcp` binary is resolved by precedence: `$CODEBASE_MEMORY_MCP_BIN` > `which codebase-memory-mcp` > `~/.local/bin/codebase-memory-mcp`. Override with `--bin`.

Inspect the current deployment:

```bash
python3 -m ilaas_agents.cli harness status
```

## After installing

Restart Claude Code (or open `/hooks`) so the new hooks and agents load. The harness is then active in every session started by `openrouter-claude` / `glm52-claude`.
