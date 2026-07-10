# Configure ILaaS

ILaaS Agent installs a local LiteLLM gateway and adapters for Codex CLI, Claude Code, and OpenCode. The three tools then share the model catalog returned by the ILaaS API.

## Install

Clone the repository, then keep the ILaaS key outside the Git checkout. The default local key file is `~/.config/ilaas-agent/keys/ilaas.token` (override the directory with `ILAAS_KEYS_DIR`):

```bash
git clone https://github.com/jeffwitz/ILaas-agent.git
cd ILaas-agent
mkdir -p ~/.config/ilaas-agent/keys
chmod 700 ~/.config/ilaas-agent/keys
printf '%s' "YOUR_ILAAS_KEY" > ~/.config/ilaas-agent/keys/ilaas.token
chmod 600 ~/.config/ilaas-agent/keys/ilaas.token
python3 install.py
```

The installer reads `~/.config/ilaas-agent/keys/ilaas.token` when `ILAAS_API_KEY` is not set. You can override the path with `--api-key-file`, point `ILAAS_KEYS_DIR` at another directory, or keep using an environment variable:

```bash
read -rsp "ILaaS API key: " ILAAS_API_KEY
export ILAAS_API_KEY
python3 install.py
unset ILAAS_API_KEY
```

Do not put an ILaaS key in a tracked repository file.

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
python3 install.py --force
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
