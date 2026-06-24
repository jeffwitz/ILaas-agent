# ILaaS Agent

Run Codex CLI, Claude Code, and OpenCode with ILaaS models through a local LiteLLM gateway.

This repository is meant to be practical first: clone it, install it, run an agent, then read the implementation details if you need them.

## What You Get

After installation, these commands are available:

```bash
Ilaas-codex
Ilaas-claude
Ilaas-opencode
Ilaas-doctor
Ilaas-servers
```

They let you use the same ILaaS model catalog from three code-agent tools:

| Tool | Command | Local interface |
| --- | --- | --- |
| Codex CLI | `Ilaas-codex` | OpenAI Responses-compatible proxy |
| Claude Code | `Ilaas-claude` | Anthropic Messages-compatible proxy |
| OpenCode | `Ilaas-opencode` | OpenAI-compatible provider via LiteLLM |

## Quick Start

```bash
git clone https://github.com/jeffwitz/ILaas-agent.git
cd ILaas-agent
ILAAS_API_KEY="your_ilaas_key" python3 install.py
```

If `~/.local/bin` is not already in your shell path:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Check the installation:

```bash
Ilaas-doctor
```

Run the fastest practical smoke test:

```bash
Ilaas-opencode run --model qwen-3.6-35b-instruct "Reply exactly: OK"
```

## Run Each Agent

Codex CLI:

```bash
Ilaas-codex exec --skip-git-repo-check "Reply exactly: OK"
```

Claude Code:

```bash
Ilaas-claude -p --model qwen-3.6-35b-instruct "Reply exactly: OK"
```

OpenCode:

```bash
Ilaas-opencode run --model qwen-3.6-35b-instruct "Reply exactly: OK"
```

List available models:

```bash
Ilaas-opencode --list-models
Ilaas-claude --list-models
```

## Install Missing Agent CLIs

The installer does not modify global npm packages unless you explicitly ask it to.

Detect what is installed:

```bash
python3 -m ilaas_agents.cli deps status
```

Install all missing supported CLIs:

```bash
python3 -m ilaas_agents.cli deps install all
```

Install only one:

```bash
python3 -m ilaas_agents.cli deps install codex
python3 -m ilaas_agents.cli deps install claude
python3 -m ilaas_agents.cli deps install opencode
```

Packages used:

```text
codex    -> npm install -g @openai/codex
claude   -> npm install -g @anthropic-ai/claude-code
opencode -> npm install -g opencode-ai
```

## Useful Install Options

```bash
python3 install.py --check-agent-deps
python3 install.py --check-agent-deps --install-agent-deps
python3 install.py --prefix ~/.local
python3 install.py --force
python3 install.py --skip-litellm-install
```

The ILaaS API key is written only to the local LiteLLM config, outside the repository.

Default generated paths on Linux:

```text
~/.config/litellm/ilaas-mistral.yaml
~/.codex-ilaas/config.toml
~/.codex-ilaas/model-catalogs/ilaas-mistral.json
~/.local/bin/Ilaas-*
```

## Test Without Touching Your Real Config

```bash
export ILAAS_HOME=/tmp/ilaas-test-home
export ILAAS_CONFIG_HOME=/tmp/ilaas-test-config
export ILAAS_CACHE_HOME=/tmp/ilaas-test-cache
export ILAAS_BIN_DIR=/tmp/ilaas-test-bin

ILAAS_API_KEY="your_ilaas_key" python3 install.py --prefix /tmp/ilaas-test
export PATH="/tmp/ilaas-test/bin:$PATH"

Ilaas-doctor
Ilaas-opencode run --model qwen-3.6-35b-instruct "Reply exactly: OK"
```

## Server Management

The wrappers start the local services they need on demand. You can also manage them explicitly:

```bash
Ilaas-servers status
Ilaas-servers start
Ilaas-servers stop
Ilaas-servers logs
```

## Recommended Models

Recommended for code-agent use:

```text
qwen-3.6-35b-instruct
mistral-medium-latest
gemma-4-31b
```

Currently not recommended for code-agent tool use:

```text
llama-3.1-8b
llama-3.3-70b
```

They may answer simple chat prompts, but their tool-calling path is weak or broken in the tested LiteLLM/ILaaS setups.

## How The Interfaces Fit Together

The project keeps one ILaaS/LiteLLM backend and adapts it to each agent frontend:

```text
ILaaS
  <- LiteLLM /v1/chat/completions
    <- Codex Responses proxy for Codex CLI
    <- Claude Messages proxy for Claude Code
    <- OpenCode OpenAI-compatible provider directly
```

Short version:

- LiteLLM talks to ILaaS through `/v1/chat/completions`.
- Codex CLI expects `/v1/responses`, so this repo provides a local Responses proxy.
- Claude Code expects Anthropic `/v1/messages`, so this repo provides a local Messages proxy.
- OpenCode can use an OpenAI-compatible provider directly, so it points to LiteLLM.

Read the details in [docs/interfaces.md](docs/interfaces.md).

## Documentation

Start here:

```text
docs/interfaces.md
docs/dependencies.md
docs/codex.md
docs/claude-code.md
docs/opencode.md
docs/models.md
docs/troubleshooting.md
docs/windows.md
```

Maintainer notes are in [CODEX.md](CODEX.md). The implementation roadmap is in [CdC.md](CdC.md).

## Development Checks

```bash
python3 -m py_compile install.py ilaas_agents/*.py proxies/*.py scripts/clone_isolated_check.py
python3 -m unittest discover -s tests
bash -n Ilaas-codex Ilaas-claude Ilaas-opencode Ilaas-doctor Ilaas-servers install.sh
python3 scripts/clone_isolated_check.py
```
