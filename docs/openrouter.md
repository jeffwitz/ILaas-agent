# Configure OpenRouter

The `openrouter-*` launchers connect Codex CLI, Claude Code, and OpenCode directly to OpenRouter. They do not route requests through ILaaS or expose the OpenRouter key to the Git repository.

## Configure the API key

The recommended option is an environment variable:

```bash
read -rsp "OpenRouter API key: " OPENROUTER_API_KEY
export OPENROUTER_API_KEY
```

For a persistent local setup, put only the key on one line in `~/.config/ilaas-agent/keys/openrouter.token` (override the directory with `ILAAS_KEYS_DIR`). This file is read when `OPENROUTER_API_KEY` is not set:

```text
sk-or-v1-...
```

Create the key file with restrictive permissions:

```bash
mkdir -p ~/.config/ilaas-agent/keys
chmod 700 ~/.config/ilaas-agent/keys
printf '%s' "sk-or-v1-..." > ~/.config/ilaas-agent/keys/openrouter.token
chmod 600 ~/.config/ilaas-agent/keys/openrouter.token
```

Resolution order: the `OPENROUTER_API_KEY` environment variable, then `OPENROUTER_TOKEN_FILE` (an explicit path), then the `~/.config/ilaas-agent/keys/openrouter.token` default. Legacy root-level files `OPENROUTER.md` and `OPEN_ROUTER.md` at the repository root are still supported for compatibility and ignored by Git, but the keys-directory default is preferred because it stays outside the repository and outside code indexing.

## Launch the agents

After the normal project installation, the commands are available from `~/.local/bin`. From an uninstalled checkout, use the corresponding executable with a `./` prefix.

```bash
openrouter-codex exec --skip-git-repo-check "Reply exactly: OK"
openrouter-claude -p "Reply exactly: OK"
openrouter-opencode run "Reply exactly: OK"
```

The default models are `~openai/gpt-latest` for Codex and OpenCode, and `~anthropic/claude-sonnet-latest` for Claude Code.

## Choose a model

Set one default for every launcher or override it per frontend:

```bash
export OPENROUTER_MODEL="z-ai/glm-5.2"
export OPENROUTER_CODEX_MODEL="openai/gpt-5.3-codex"
export OPENROUTER_CLAUDE_MODEL="~anthropic/claude-sonnet-latest"
export OPENROUTER_OPENCODE_MODEL="z-ai/glm-5.2"
```

Command-line model arguments take precedence:

```bash
openrouter-codex -m openai/gpt-5.3-codex
openrouter-claude --model '~anthropic/claude-sonnet-latest'
openrouter-opencode run -m z-ai/glm-5.2 "Reply exactly: OK"
```

To inspect the catalog before launching an interactive session:

```bash
openrouter-codex --list-models
openrouter-claude --list-models
openrouter-opencode --list-models
```

Inside each tool, use its native model picker:

```text
Codex CLI:   /model
Claude Code: /model
OpenCode:    /models
```

Codex and Claude Code show the OpenRouter text models that advertise tool support. OpenCode uses its built-in OpenRouter catalog. The selected OpenRouter slug is preserved when a request is sent upstream.

If an already-running session does not show the updated list, exit it and start it again through the `openrouter-*` launcher. OpenCode's picker command is `/models`, not `/model`.

## Endpoint overrides

The standard OpenRouter endpoints normally need no configuration. They can be changed for a compatible gateway:

```bash
export OPENROUTER_BASE_URL="https://openrouter.ai/api/v1"
export OPENROUTER_ANTHROPIC_BASE_URL="https://openrouter.ai/api"
```

Codex uses the project's Responses adapter, Claude Code uses a local Anthropic-compatible discovery and passthrough adapter, and OpenCode uses its native OpenRouter provider.

## Codex isolation from your real ~/.codex

`openrouter-codex` runs Codex with a dedicated `CODEX_HOME` so it never touches
your regular Codex install. This matters because a ChatGPT login in `~/.codex`
makes Codex reject non-OpenAI models ("model is not supported when using Codex
with a ChatGPT account"). The bridge points Codex at its own home instead:

```text
openrouter-codex -> ~/.codex-openrouter    ($OPENROUTER_CODEX_HOME)
glm52-codex      -> ~/.codex-glm52          ($GLM52_CODEX_HOME)
Ilaas-codex      -> ~/.codex-ilaas          ($ILAAS_CODEX_HOME)
```

Your own `~/.codex` (and its ChatGPT/OpenAI login) is left untouched. Override
the isolated home with the matching environment variable if needed.
