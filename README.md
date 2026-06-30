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
glm52-codex
glm52-claude
glm52-opencode
openrouter-codex
openrouter-claude
openrouter-opencode
```

They let you use the same ILaaS model catalog from three code-agent tools:

| Tool | Command | Local interface |
| --- | --- | --- |
| Codex CLI | `Ilaas-codex` | OpenAI Responses-compatible proxy |
| Claude Code | `Ilaas-claude` | Anthropic Messages-compatible proxy |
| OpenCode | `Ilaas-opencode` | OpenAI-compatible provider via LiteLLM |

The `glm52-*` commands use the GLM 5.2 API directly, independently of the ILaaS gateway.

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

Detailed provider setup:

- [Configure ILaaS](docs/ilaas.md)
- [Configure OpenRouter](docs/openrouter.md)

## Important Security Note

The generated Codex config defaults to `sandbox_mode = "danger-full-access"` because this avoids known Linux bubblewrap/AppArmor user namespace failures. This disables Codex filesystem sandboxing.

Use a stricter mode when your system supports it:

```bash
python3 install.py --codex-sandbox-mode workspace-write
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

## GLM 5.2 Direct API

Put the Z.AI token alone on one line in `GLM5.2.md` at the repository root, or export it without a file:

```bash
export GLM52_API_KEY="your_zai_key"
```

The token file is ignored by Git and read only when a `glm52-*` command starts. Run the three agents with:

```bash
glm52-codex exec --skip-git-repo-check "Reply exactly: OK"
glm52-claude -p "Reply exactly: OK"
glm52-opencode run "Reply exactly: OK"
```

All launchers default to the API model `glm-5.2`. Optional overrides are available for another account or endpoint:

```bash
export GLM52_MODEL="glm-5.2"
export GLM52_TOKEN_FILE="/path/to/token-file"
export GLM52_OPENAI_BASE_URL="https://api.z.ai/api/paas/v4"
export GLM52_ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
```

Codex uses the repository's local Responses-to-Chat-Completions adapter because Codex speaks the Responses API. Claude Code uses Z.AI's Anthropic-compatible endpoint, and OpenCode uses its OpenAI-compatible endpoint directly.

## OpenRouter Direct API

Put the OpenRouter key alone on one line in `OPENROUTER.md` or `OPEN_ROUTER.md`, or export it:

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

The key files are ignored by Git. The launchers use OpenRouter's native integrations directly:

```bash
openrouter-codex exec --skip-git-repo-check "Reply exactly: OK"
openrouter-claude -p "Reply exactly: OK"
openrouter-opencode run "Reply exactly: OK"
```

Defaults are `~openai/gpt-latest` for Codex and OpenCode, and `~anthropic/claude-sonnet-latest` for Claude Code. Override them globally or per agent:

```bash
export OPENROUTER_MODEL="z-ai/glm-5.2"
export OPENROUTER_CODEX_MODEL="openai/gpt-5.3-codex"
export OPENROUTER_CLAUDE_MODEL="~anthropic/claude-sonnet-latest"
export OPENROUTER_OPENCODE_MODEL="z-ai/glm-5.2"
```

You can also choose a model on the command line:

```bash
openrouter-codex -m openai/gpt-5.3-codex
openrouter-claude --model '~anthropic/claude-sonnet-latest'
openrouter-opencode run -m z-ai/glm-5.2 "Reply exactly: OK"
```

List the models exposed by the account with any wrapper's `--list-models` option.

Inside each interactive tool, use its native model picker:

```text
Codex CLI:  /model
Claude Code: /model
OpenCode:    /models
```

Codex and Claude Code receive a filtered catalog of OpenRouter text models that support tools. OpenCode uses its built-in OpenRouter catalog. After selecting a model, the bridge preserves the exact OpenRouter slug sent upstream; Codex and Claude also receive an explicit runtime identity instruction for accurate model-identification answers.

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
python3 install.py --codex-sandbox-mode workspace-write
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

The Codex and Claude Code proxies are minimal compatibility layers for the tested agent workflows. They are not complete OpenAI Responses or Anthropic Messages API implementations.

Read the details in [docs/interfaces.md](docs/interfaces.md).

## Documentation

Start here:

```text
docs/index.md
docs/interfaces.md
docs/compatibility.md
docs/dependencies.md
docs/codex.md
docs/claude-code.md
docs/opencode.md
docs/models.md
docs/troubleshooting.md
docs/windows.md
```

Maintainer notes are in [CODEX.md](CODEX.md). The implementation roadmap is in [CdC.md](CdC.md).

The online documentation is configured for Read the Docs with `.readthedocs.yaml`, `docs/conf.py`, and the Read the Docs Sphinx theme. To publish it, import this GitHub repository in Read the Docs; the build uses `docs/requirements.txt`.

The package also exposes a Python console script for development and future package-first installs:

```bash
python3 -m pip install .
ilaas-agent --help
```

## Development Checks

```bash
python3 -m py_compile install.py ilaas_agents/*.py proxies/*.py scripts/clone_isolated_check.py
python3 -m unittest discover -s tests
bash -n Ilaas-codex Ilaas-claude Ilaas-opencode Ilaas-doctor Ilaas-servers glm52-codex glm52-claude glm52-opencode openrouter-codex openrouter-claude openrouter-opencode install.sh
python3 -m sphinx -b html -W --keep-going docs docs/_build/html
python3 -m pip install .
ilaas-agent --help
python3 scripts/wine_windows_wrapper_check.py
python3 scripts/clone_isolated_check.py
```
