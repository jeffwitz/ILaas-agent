# Codex CLI via ILaaS

Codex CLI uses the OpenAI Responses API shape. In this project Codex points to a local proxy instead of LiteLLM directly:

```text
Codex CLI -> http://127.0.0.1:4001/v1/responses
          -> LiteLLM http://127.0.0.1:4000/v1/chat/completions
          -> ILaaS
```

The proxy is required because LiteLLM `/v1/responses` returned empty output and `tokens used 0` for real Codex requests, while `/v1/chat/completions` worked.

The proxy is a minimal compatibility layer. It does not implement the complete OpenAI Responses API and does not provide native upstream token-by-token streaming.

## Usage

```bash
Ilaas-codex exec --skip-git-repo-check "Reply exactly: OK"
Ilaas-codex exec --model qwen-3.6-35b-instruct --skip-git-repo-check "Reply exactly: OK"
```

The wrapper sets:

```text
CODEX_HOME=~/.codex-ilaas
OPENAI_API_KEY=sk-local-dummy
```

The local Codex config is generated at:

```text
~/.codex-ilaas/config.toml
```

Key fields:

```toml
model = "ilaas-default"
model_provider = "ilaas_responses_proxy"
wire_api = "responses"
supports_websockets = false
```

`supports_websockets = false` avoids Codex attempting WebSocket transport against LiteLLM.

## Sandbox Mode

The installer defaults to:

```toml
sandbox_mode = "danger-full-access"
```

This avoids Codex bubblewrap/AppArmor user namespace failures on affected Linux systems, but it disables Codex filesystem sandboxing.

Choose a stricter mode during install if your machine supports it:

```bash
python3 install.py --codex-sandbox-mode workspace-write
python3 install.py --codex-sandbox-mode read-only
```
