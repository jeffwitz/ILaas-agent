# Configure ILaaS

ILaaS Agent installs a local LiteLLM gateway and adapters for Codex CLI, Claude Code, and OpenCode. The three tools then share the model catalog returned by the ILaaS API.

## Install

Clone the repository, export the ILaaS key for the installer, then remove it from the current shell when installation is complete:

```bash
git clone https://github.com/jeffwitz/ILaas-agent.git
cd ILaas-agent
read -rsp "ILaaS API key: " ILAAS_API_KEY
export ILAAS_API_KEY
python3 install.py
unset ILAAS_API_KEY
```

The hidden `read` prompt keeps the key out of the terminal display and shell history. Do not put an ILaaS key in a tracked repository file.

The installer fetches the account's current model list and creates the local configuration under `~/.config`. The LiteLLM configuration containing the key is stored at `~/.config/litellm/ilaas-mistral.yaml` with restrictive file permissions; it is not written into the Git checkout.

If the installer reports that `~/.local/bin` is not in `PATH`, add it to the shell configuration:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Verify the installation

Check the local configuration, dependencies, and endpoints:

```bash
Ilaas-doctor
Ilaas-opencode --list-models
Ilaas-claude --list-models
```

Run a short request through each agent:

```bash
Ilaas-codex exec --skip-git-repo-check "Reply exactly: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Reply exactly: OK"
Ilaas-opencode run --model qwen-3.6-35b-instruct "Reply exactly: OK"
```

## Choose a model interactively

Start the desired wrapper, then use the tool's native command:

```text
Codex CLI:   /model
Claude Code: /model
OpenCode:    /models
```

OpenCode uses `/models` in the plural. The list reflects the model catalog fetched from ILaaS when the configuration was generated.

## Refresh the key or model catalog

Rerun the installer to fetch the current catalog and rewrite the generated configuration. `--force` preserves backups of existing generated configuration files before replacing them:

```bash
read -rsp "ILaaS API key: " ILAAS_API_KEY
export ILAAS_API_KEY
python3 install.py --force
unset ILAAS_API_KEY
```

## Runtime layout

The wrappers start only the local services required by the selected frontend:

```text
ILaaS API
  <- local LiteLLM gateway
    <- Responses adapter for Codex CLI
    <- Messages adapter for Claude Code
    <- OpenAI-compatible connection for OpenCode
```

Use `Ilaas-servers` to inspect or stop the local services. See {doc}`troubleshooting` if a port, dependency, or generated configuration is invalid.

## Codex sandbox mode

The default generated Codex configuration uses `danger-full-access` to avoid known Linux user-namespace failures. On a compatible system, generate a stricter configuration with:

```bash
python3 install.py --codex-sandbox-mode workspace-write
```
