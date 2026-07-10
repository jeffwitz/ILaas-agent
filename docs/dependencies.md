# Dependencies

The installer handles Python/LiteLLM automatically unless `--skip-litellm-install` is used.

External code-agent CLIs are detected by default in `Ilaas-doctor`, but are not installed unless explicitly requested. This avoids surprising global npm changes.

## Detect

```bash
python -m ilaas_agents.cli deps status
python install.py --check-agent-deps
```

Detected runtimes:

```text
node
npm
bun
```

Detected agents:

```text
codex
claude
opencode
```

## Install Missing Agents

Install all missing supported agents:

```bash
python -m ilaas_agents.cli deps install all
```

Install a specific agent:

```bash
python -m ilaas_agents.cli deps install codex
python -m ilaas_agents.cli deps install claude
python -m ilaas_agents.cli deps install opencode
```

Equivalent during install:

```bash
python install.py --check-agent-deps --install-agent-deps
python install.py --check-agent-deps --install-agent-deps --install-agent opencode
```

Packages used:

```text
codex   -> npm install -g @openai/codex
claude  -> npm install -g @anthropic-ai/claude-code
opencode -> npm install -g opencode-ai
```

Do not install the npm package named `codex`; it is not the OpenAI Codex CLI. Use `@openai/codex`.

## Optional token-saving tools

These tools are not bundled but are recommended by the harness protocol:

- **`rtk`** (Rust Token Killer) — compresses shell command output to save tokens.
  Install to `~/.local/bin/rtk`. The harness prints a non-fatal advisory if it is
  missing during `harness install`.
- **`codebase-memory-mcp`** — MCP server that provides graph-based code exploration
  tools. Required by the harness (the install fails without it). The binary is
  resolved via `$CODEBASE_MEMORY_MCP_BIN` > `which codebase-memory-mcp` >
  `~/.local/bin/codebase-memory-mcp`.
