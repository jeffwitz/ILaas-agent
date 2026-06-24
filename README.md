# ILaaS Agent

Installable local tooling to use ILaaS models with code agents:

- Codex CLI
- Claude Code
- OpenCode

The current implementation uses LiteLLM as the local OpenAI-compatible gateway, plus small compatibility proxies where an agent expects a different API shape.

```text
ILaaS
  <- LiteLLM /v1/chat/completions
    <- Codex Responses proxy for Codex CLI
    <- Claude Messages proxy for Claude Code
    <- OpenCode OpenAI-compatible provider directly
```

## Quick Start

```bash
git clone https://github.com/jeffwitz/ILaas-agent.git
cd ILaas-agent
python install.py
```

Useful install options:

```bash
python install.py --non-interactive --skip-litellm-install
python install.py --prefix ~/.local
python install.py --force
```

The installer never writes API keys into the repository. Provide the ILaaS key with:

```bash
ILAAS_API_KEY=... python install.py
```

or enter it interactively when prompted.

After installation:

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

## Shared CLI

The wrappers call a shared Python CLI:

```bash
python -m ilaas_agents.cli doctor
python -m ilaas_agents.cli refresh-models
python -m ilaas_agents.cli servers status
python -m ilaas_agents.cli servers start
python -m ilaas_agents.cli servers stop
python -m ilaas_agents.cli smoke --agent opencode --model qwen-3.6-35b-instruct
python scripts/clone_isolated_check.py
```

`doctor` avoids token-consuming prompts. `smoke` intentionally runs model calls and may consume tokens.

`servers start` launches LiteLLM plus the Codex and Claude compatibility proxies as persistent background services. The agent wrappers can also start only what they need for a single run.

## Model Refresh

```bash
python -m ilaas_agents.cli refresh-models
```

This updates:

```text
~/.config/litellm/ilaas-mistral.yaml
~/.codex-ilaas/model-catalogs/ilaas-mistral.json
```

## Recommended Models

For code-agent use:

```text
qwen-3.6-35b-instruct
mistral-medium-latest
gemma-4-31b
```

Currently not recommended for code agents:

```text
llama-3.1-8b
llama-3.3-70b
```

They may answer simple chat prompts, but their tool-calling path is weak or broken in the tested LiteLLM/ILaaS setups.

## Status

The Linux path is validated locally with the Python runners:

```text
Codex CLI -> OK, Responses proxy, tokens consumed
Claude Code -> OK with qwen-3.6-35b-instruct
OpenCode -> OK with qwen-3.6-35b-instruct and Read tool
```

The installer supports path overrides for isolated tests and advanced installs:

```text
ILAAS_HOME
ILAAS_CONFIG_HOME
ILAAS_CACHE_HOME
ILAAS_BIN_DIR
ILAAS_LITELLM_CONFIG
ILAAS_CODEX_HOME
ILAAS_MODEL_CATALOG
ILAAS_LITELLM_VENV
```

Windows native support is planned but should be considered experimental until tested. On Windows, WSL2 is the recommended path for now.

Detailed docs:

```text
docs/codex.md
docs/claude-code.md
docs/opencode.md
docs/models.md
docs/windows.md
docs/troubleshooting.md
```

See [CdC.md](CdC.md) for the full implementation plan, and [CODEX.md](CODEX.md) for current maintainer notes.
