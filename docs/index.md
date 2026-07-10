# ILaaS Agent

Run Codex CLI, Claude Code, and OpenCode with ILaaS models through a local LiteLLM gateway, or connect the same tools directly to OpenRouter.

This documentation starts with the commands needed to install and launch the tools. The interface details are available after the quick start.

## Quick Start

```bash
git clone https://github.com/jeffwitz/ILaas-agent.git
cd ILaas-agent
python3 install.py
```

If `~/.local/bin` is not already in your shell path:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Check the installation:

```bash
Ilaas-doctor
```

Run a first model call:

```bash
Ilaas-opencode run --model qwen-3.6-35b-instruct "Reply exactly: OK"
```

## Provider Setup

- {doc}`ilaas`: install the local gateway, configure the ILaaS key, and launch each agent.
- {doc}`openrouter`: configure an ignored local key file or environment variable, choose a model, and use each tool's model picker.

## Available Commands

```bash
Ilaas-codex
Ilaas-claude
Ilaas-opencode
Ilaas-doctor
Ilaas-servers
openrouter-codex
openrouter-claude
openrouter-opencode
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

## What The Project Provides

ILaaS Agent keeps one ILaaS/LiteLLM backend and adapts it to each code-agent frontend:

```text
ILaaS
  <- LiteLLM /v1/chat/completions
    <- Codex Responses proxy for Codex CLI
    <- Claude Messages proxy for Claude Code
    <- OpenCode OpenAI-compatible provider directly
```

The ILaaS API key is written only to the local LiteLLM config outside the repository.

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

```{toctree}
:maxdepth: 2
:caption: User Guide

quickstart
ilaas
openrouter
interfaces
compatibility
dependencies
tiers
harness
economy
models
codex
claude-code
opencode
troubleshooting
windows
```

```{toctree}
:maxdepth: 1
:caption: Project Notes

maintainer-notes
history
```
