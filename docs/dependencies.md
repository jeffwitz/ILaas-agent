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
