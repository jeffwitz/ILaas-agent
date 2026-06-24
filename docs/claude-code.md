# Claude Code via ILaaS

Claude Code expects an Anthropic Messages API gateway. This project runs a local compatibility proxy:

```text
Claude Code -> http://127.0.0.1:4002/v1/messages
            -> LiteLLM http://127.0.0.1:4000/v1/chat/completions
            -> ILaaS
```

Models are exposed to Claude Code with the prefix:

```text
claude-ilaas-<slug>
```

The wrapper accepts raw ILaaS slugs and rewrites them automatically.

## Usage

```bash
Ilaas-claude --list-models
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

Tool smoke test:

```bash
Ilaas-claude -p --model qwen-3.6-35b-instruct \
  --allowedTools Read --permission-mode bypassPermissions \
  "Lis le fichier refresh_ilaas_models.py et réponds uniquement avec la valeur de DEFAULT_ALIAS."
```

The wrapper sets:

```text
ANTHROPIC_BASE_URL=http://127.0.0.1:4002
ANTHROPIC_API_KEY=sk-local-dummy
CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
MAX_THINKING_TOKENS=0
```

`llama-3.1-8b` and `llama-3.3-70b` are listed but not recommended for Claude Code tool use.
