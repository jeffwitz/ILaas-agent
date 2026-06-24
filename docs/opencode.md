# OpenCode via ILaaS

OpenCode can use an OpenAI-compatible provider directly. This project injects an `ilaas` provider through `OPENCODE_CONFIG_CONTENT`:

```text
OpenCode -> LiteLLM http://127.0.0.1:4000/v1/chat/completions -> ILaaS
```

Model names use the OpenCode form:

```text
ilaas/<slug>
```

The wrapper accepts raw ILaaS slugs and rewrites them automatically.

## Usage

```bash
Ilaas-opencode --list-models
Ilaas-opencode run --model qwen-3.6-35b-instruct "Reply exactly: OK"
Ilaas-opencode run -m ilaas/qwen-3.6-35b-instruct "Reply exactly: OK"
```

Tool smoke test:

```bash
Ilaas-opencode run --model qwen-3.6-35b-instruct \
  "Read the file refresh_ilaas_models.py and reply only with the value of DEFAULT_ALIAS."
```

Validated locally with Qwen and the OpenCode `Read` tool.
