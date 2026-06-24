# Codex CLI via ILaaS

Codex CLI uses the OpenAI Responses API shape. In this project Codex points to a local proxy instead of LiteLLM directly:

```text
Codex CLI -> http://127.0.0.1:4001/v1/responses
          -> LiteLLM http://127.0.0.1:4000/v1/chat/completions
          -> ILaaS
```

The proxy is required because LiteLLM `/v1/responses` returned empty output and `tokens used 0` for real Codex requests, while `/v1/chat/completions` worked.

## Usage

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-codex exec --model qwen-3.6-35b-instruct --skip-git-repo-check "Réponds exactement: OK"
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
