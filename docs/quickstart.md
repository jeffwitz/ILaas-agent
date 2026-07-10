# Quickstart

One page from zero to a working `openrouter-claude` session with the
GLM-supervisor / DeepSeek-coder harness. Follow it top to bottom.

## 0. Prerequisites

- Python ≥ 3.10
- A code-agent CLI you intend to drive: `codex`, `claude`, and/or `opencode` on `PATH`
- For OpenRouter: an OpenRouter API key
- For the harness: the `codebase-memory-mcp` binary (used by the `ctx-pro` agent and the graph hooks). It is resolved by precedence: `$CODEBASE_MEMORY_MCP_BIN` > `which codebase-memory-mcp` > `~/.local/bin/codebase-memory-mcp`. Install it on `PATH` or set the env var.

## 1. Clone and install

```bash
git clone https://github.com/jeffwitz/ILaas-agent.git
cd ILaas-agent
python3 install.py
```

`install.py` writes the LiteLLM config, the Codex catalog, the Codex `config.toml`, and the wrapper scripts (`openrouter-claude`, `glm52-claude`, `Ilaas-claude`, …) into `~/.local/bin`.

Make sure `~/.local/bin` is on your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"      # add to your shell profile to persist
```

Check the install:

```bash
Ilaas-doctor
```

## 2. Provide your OpenRouter key

Either export it, or put it in the file the launcher reads by default (`~/.config/ilaas-agent/keys/openrouter.token` — override the directory with `$ILAAS_KEYS_DIR`, or the file with `$OPENROUTER_TOKEN_FILE`):

```bash
export OPENROUTER_API_KEY=sk-or-...        # preferred
```

## 3. Install the harness

Deploy the agents, hooks, and MCP config into Claude Code's config dirs:

```bash
python3 -m ilaas_agents.cli harness install
python3 -m ilaas_agents.cli harness status
```

This writes:

- agents → `~/.claude_openrouter/agents/` (`ctx-pro`, `code-pro`, `code-flash`)
- hooks → `~/.claude/hooks/` (`cbm-session-reminder`, `cbm-code-discovery-gate`), symlinked from `~/.claude_openrouter/hooks`
- MCP config → `~/.claude/.mcp.json`, symlinked from `~/.claude_openrouter/.mcp.json`

Restart Claude Code (or open `/hooks` once) so the new agents and hooks load.

## 4. First launch and verification

Launch the openrouter Claude session:

```bash
openrouter-claude
```

Inside Claude Code, verify the harness is live:

- `/model` → should show `OpenRouter · Z.ai: GLM 5.2` (the supervisor). **Do not pin a different model here** — it would be saved to `~/.claude_openrouter/settings.json` and bypass the tier routing. The launcher cleans a stale pin on each start, but keep it clean.
- `/agents` → should list `ctx-pro`, `code-pro`, `code-flash` (the DeepSeek subagents).
- The tier routing is set by the launcher env: GLM 5.2 for `opus`/`fable`, DeepSeek V4 Pro for `sonnet`, DeepSeek V4 Flash for `haiku`. See {doc}`tiers`.

Quick functional check (no tokens spent beyond the call):

```bash
openrouter-claude --version
openrouter-claude --list-models
```

## 5. Run a real task

```bash
openrouter-claude -p "Reply exactly: OK"
```

For a coding task, the supervisor (GLM 5.2) should delegate to `code-pro` (DeepSeek V4 Pro) — the SessionStart hook protocol tells it when to delegate and how to verify parallel dispatch safety. Verbose graph queries (`detect_changes`, `trace_path`, …) are routed to `ctx-pro` so the dumps stay out of the supervisor context.

## 6. Measure the savings

```bash
python3 scripts/token_economy.py --economy --all \
  --projects-dir ~/.claude_openrouter/projects
```

Or from inside Claude Code: `/economy`. See {doc}`economy`.

## 7. Where to go next

- {doc}`harness` — what each agent/hook/MCP piece does, and the repo-vs-config distinction.
- {doc}`tiers` — the per-provider tier-map (supervisor / coder / small).
- {doc}`interfaces` — how the local proxies fit together.
- {doc}`openrouter` — OpenRouter-specific setup details.
- {doc}`troubleshooting` — when something breaks.
