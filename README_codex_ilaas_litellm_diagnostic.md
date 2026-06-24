# Codex + ILaaS via LiteLLM — état actuel et diagnostic

## Objectif

Faire fonctionner **OpenAI Codex CLI** avec un modèle ILaaS, en particulier :

```text
mistral-medium-latest
```

via le proxy local **LiteLLM**, tout en conservant l’usage normal de Codex avec le compte ChatGPT / GPT‑5.5.

L’objectif initial était :

```text
Codex CLI
  -> LiteLLM local
  -> ILaaS OpenAI-compatible API
  -> mistral-medium-latest
```

---

## État actuel

### Ce qui fonctionne

L’appel direct à LiteLLM en mode `/chat/completions` fonctionne.

Commande de test :

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-ilaas",
    "messages": [
      {"role": "user", "content": "Réponds exactement: OK"}
    ],
    "max_tokens": 20
  }' | jq
```

Réponse obtenue :

```json
{
  "id": "80c33e75f2c04d3bb184bef64a03345d",
  "created": 1782246573,
  "model": "mistral-ilaas",
  "object": "chat.completion",
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "message": {
        "content": "OK",
        "role": "assistant",
        "provider_specific_fields": {
          "refusal": null
        }
      },
      "provider_specific_fields": {}
    }
  ],
  "usage": {
    "completion_tokens": 2,
    "prompt_tokens": 9,
    "total_tokens": 11,
    "prompt_tokens_details": {
      "cached_tokens": 0
    }
  }
}
```

Donc :

```text
ILaaS -> OK
LiteLLM -> OK
mistral-medium-latest -> OK via /chat/completions
```

---

### Ce qui ne fonctionnait pas avec LiteLLM direct

Codex CLI v0.141.0 n’affiche aucune sortie utile avec ce montage.

Commande testée :

```bash
CODEX_HOME="$HOME/.codex-ilaas" \
OPENAI_API_KEY="sk-local-dummy" \
codex exec "Réponds exactement: OK"
```

Sortie obtenue :

```text
OpenAI Codex v0.141.0
--------
workdir: /home/jeff/tmp/test-codex-ilaas
model: mistral-ilaas
provider: litellm_ilaas_http
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR]
reasoning effort: minimal
reasoning summaries: none
session id: 019ef643-3845-7340-b4f1-f1b4262f7856
--------
user
Réponds exactement: OK
warning: Codex's Linux sandbox uses bubblewrap and needs access to create user namespaces.
warning: Model metadata for `mistral-ilaas` not found. Defaulting to fallback metadata; this can degrade performance and cause issues.
codex

tokens used
0
```

Le point important est :

```text
tokens used
0
```

Codex ne semble pas exploiter la réponse renvoyée par LiteLLM sur `/v1/responses`.

Diagnostic confirmé :

- Codex appelle bien `POST http://127.0.0.1:4000/v1/responses`.
- LiteLLM répond bien en `200 text/event-stream`.
- Pour la requête Responses complète émise par Codex v0.141.0, LiteLLM renvoie lui-même un message assistant vide et `usage.total_tokens = 0`.
- Codex n’est donc pas bloqué localement : il affiche correctement la réponse vide reçue de LiteLLM.

Le test `/chat/completions` reste valide et consomme des tokens. Le problème est spécifique au pont LiteLLM `/v1/responses` avec la forme réelle des requêtes Codex.

### Correction retenue

Un proxy local minimal a été ajouté dans ce dépôt :

```text
codex_ilaas_responses_proxy.py
codex-ilaas-responses-proxy
```

Il expose :

```text
http://127.0.0.1:4001/v1/responses
```

et relaie vers :

```text
http://127.0.0.1:4000/v1/chat/completions
```

La configuration `~/.codex-ilaas/config.toml` pointe maintenant sur le provider `ilaas_responses_proxy`, qui garde `wire_api = "responses"` et `supports_websockets = false`.

Validation obtenue :

```bash
env CODEX_HOME=/home/jeff/.codex-ilaas \
  OPENAI_API_KEY=sk-local-dummy \
  codex exec --skip-git-repo-check 'Réponds exactement: OK'
```

Résultat :

```text
provider: ilaas_responses_proxy
codex
OK
tokens used
8,308
```

Le proxy supporte la réponse texte et le comptage de tokens. Il transmet les outils `function` compatibles Chat Completions, et ignore les types Responses non standards de Codex comme `namespace` et `web_search`.

---

## Historique des problèmes rencontrés

### 1. Modèle inconnu côté ChatGPT

Erreur initiale :

```text
The 'mistral-ilaas' model is not supported when using Codex with a ChatGPT account.
```

Cause probable :

Codex était lancé avec :

```bash
codex --model mistral-ilaas
```

mais sans changer correctement le provider. Il essayait donc d’utiliser le modèle `mistral-ilaas` avec le provider OpenAI/ChatGPT standard.

Résolution partielle :

Définition d’un provider custom dans la configuration Codex.

---

### 2. Provider Codex introuvable

Erreur :

```text
Error loading configuration: Model provider `litellm_ilaas` not found
```

Cause probable :

Le fichier Codex actif contenait :

```toml
model_provider = "litellm_ilaas"
```

mais ne contenait pas le bloc correspondant :

```toml
[model_providers.litellm_ilaas]
```

Résolution :

Création d’une configuration séparée pour ILaaS.

---

### 3. Préservation de Codex GPT‑5.5

Contrainte importante :

Il ne faut pas casser l’usage normal :

```bash
codex
```

avec le compte ChatGPT / GPT‑5.5.

Solution retenue :

Utiliser un `CODEX_HOME` séparé :

```text
~/.codex-ilaas
```

Ainsi :

```bash
codex
```

reste inchangé, et :

```bash
CODEX_HOME="$HOME/.codex-ilaas" codex ...
```

utilise la configuration ILaaS.

---

### 4. Erreur LiteLLM `Unknown model`

Erreur rencontrée côté LiteLLM :

```json
{
  "error": {
    "message": "litellm.NotFoundError: NotFoundError: OpenAIException - Error code: 404 - {'object': 'error', 'error': 'Unknown model'}. Received Model Group=mistral-ilaas\nAvailable Model Group Fallbacks=None",
    "type": null,
    "param": null,
    "code": "404"
  }
}
```

Cause probable :

La configuration LiteLLM utilisait initialement :

```yaml
model: openai/chat_completions/mistral-medium-latest
```

Ce préfixe posait problème.

Correction qui a permis de faire fonctionner `/chat/completions` :

```yaml
model: openai/mistral-medium-latest
```

---

### 5. Erreurs `prisma` et `opentelemetry`

Erreurs rencontrées côté LiteLLM :

```text
ModuleNotFoundError: No module named 'prisma'
ModuleNotFoundError: No module named 'opentelemetry'
POST /v1/responses HTTP/1.1" 500 Internal Server Error
```

Cause probable :

Installation LiteLLM proxy incomplète ou dépendances optionnelles déclenchées par l’endpoint `/v1/responses`.

Contournements appliqués / proposés :

1. Supprimer le `master_key` LiteLLM pour éviter la couche d’auth locale.
2. Installer les dépendances manquantes :

```bash
source ~/.venvs/litellm/bin/activate
pip install -U "litellm[proxy]" prisma opentelemetry-api opentelemetry-sdk
```

---

### 6. Problème WebSocket Codex -> LiteLLM

Avec la configuration `openai_base_url`, Codex essayait d’abord de se connecter en WebSocket :

```text
failed to connect to websocket: HTTP error: 403 Forbidden, url: ws://127.0.0.1:4000/v1/responses
```

Puis il bouclait en reconnexion.

Correction testée :

Revenir à un provider custom Codex avec :

```toml
supports_websockets = false
```

Cela a bien supprimé les tentatives WebSocket. Codex utilise alors le provider :

```text
provider: litellm_ilaas_http
```

Mais il reste le problème :

```text
tokens used
0
```

---

## Fichiers actuels

### 1. Configuration LiteLLM

Chemin :

```text
~/.config/litellm/ilaas-mistral.yaml
```

Contenu actuel recommandé :

```yaml
model_list:
  - model_name: mistral-ilaas
    litellm_params:
      model: openai/mistral-medium-latest
      api_base: https://llm.ilaas.fr/v1
      api_key: "TA_CLE_ILAAS_ICI"
      use_chat_completions_api: true
      max_tokens: 4096

litellm_settings:
  drop_params: true
```

Remarque :

Le bloc suivant a été supprimé volontairement :

```yaml
general_settings:
  master_key: "sk-litellm-local"
```

Raison : il déclenchait la couche d’auth locale LiteLLM, avec des erreurs liées à `prisma`.

---

### 2. Configuration Codex séparée ILaaS

Chemin :

```text
~/.codex-ilaas/config.toml
```

Contenu actuel :

```toml
model = "ilaas-default"
model_provider = "ilaas_responses_proxy"
model_catalog_json = "/home/jeff/.codex-ilaas/model-catalogs/ilaas-mistral.json"

approval_policy = "never"
sandbox_mode = "danger-full-access"

model_context_window = 262144
model_auto_compact_token_limit = 220000
model_reasoning_summary = "none"
model_supports_reasoning_summaries = false

[model_providers.ilaas_responses_proxy]
name = "ILaaS Responses Proxy"
base_url = "http://127.0.0.1:4001/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
supports_websockets = false
```

Le catalogue `model_catalog_json` déclare `mistral-ilaas` comme modèle connu de Codex. Sans lui, Codex CLI v0.141.0 affiche :

```text
Model metadata for `mistral-ilaas` not found. Defaulting to fallback metadata
```

`model_context_window` seul ne suffit pas à supprimer cet avertissement, car il corrige la taille de contexte mais n’ajoute pas le slug au catalogue interne des modèles.

Le profil ILaaS utilise aussi `sandbox_mode = "danger-full-access"` pour éviter le warning Linux `bubblewrap` quand AppArmor bloque les user namespaces non privilégiés. Le diagnostic local correspondant est :

```text
kernel.apparmor_restrict_unprivileged_userns = 1
unshare -Ur true -> Operation not permitted
```

Le correctif système préférable est de charger le profil AppArmor `bwrap-userns-restrict` pour `bubblewrap`, ou en dernier recours de passer `kernel.apparmor_restrict_unprivileged_userns=0`. Ces deux variantes nécessitent `sudo`.

Modèles actuellement exposés par ILaaS et déclarés dans LiteLLM/Codex :

```text
ilaas-default -> mistral-medium-latest
mistral-ilaas -> mistral-medium-latest (legacy)
gemma-4-31b
gpt-oss-120b
llama-3.1-8b
llama-3.3-70b
mistral-medium-latest
mistral-small-3.2-24b
mistral-small-4-119b
qwen-3.6-35b-instruct
```

`ilaas-default` est maintenant l'alias par défaut neutre. `mistral-ilaas` reste disponible en alias legacy. Pour choisir un autre modèle :

```bash
Ilaas-codex exec --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

La liste peut être rafraîchie depuis l'endpoint ILaaS `/v1/models` avec :

```bash
./refresh_ilaas_models.py
```

Le script réécrit `~/.config/litellm/ilaas-mistral.yaml` et `~/.codex-ilaas/model-catalogs/ilaas-mistral.json` sans afficher la clé API. Redémarrer LiteLLM ensuite, ou laisser `Ilaas-codex` le relancer si aucun serveur n'écoute sur le port 4000.

Remarque :

On utilise volontairement :

```toml
supports_websockets = false
```

car le transport WebSocket de Codex vers LiteLLM échouait avec :

```text
HTTP error: 403 Forbidden, url: ws://127.0.0.1:4000/v1/responses
```

---

## Lancement

### Terminal 1 — lancer LiteLLM

```bash
source ~/.venvs/litellm/bin/activate

litellm \
  --config ~/.config/litellm/ilaas-mistral.yaml \
  --host 127.0.0.1 \
  --port 4000
```

Variante debug :

```bash
source ~/.venvs/litellm/bin/activate

LITELLM_LOG=DEBUG litellm \
  --config ~/.config/litellm/ilaas-mistral.yaml \
  --host 127.0.0.1 \
  --port 4000
```

---

### Terminal 2 — lancer le proxy Responses Codex

```bash
cd /home/jeff/Code/Codex_Mistral
./codex-ilaas-responses-proxy
```

---

### Terminal 3 — tester LiteLLM et Codex

Test `/chat/completions`, actuellement OK :

```bash
curl -s http://127.0.0.1:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-ilaas",
    "messages": [
      {"role": "user", "content": "Réponds exactement: OK"}
    ],
    "max_tokens": 20
  }' | jq
```

Test `/responses` direct LiteLLM, utile seulement pour information :

```bash
curl -s http://127.0.0.1:4000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-ilaas",
    "input": "Réponds exactement: OK",
    "max_output_tokens": 20
  }' | jq
```

Test `/responses` direct LiteLLM en streaming, utile seulement pour information :

```bash
curl -N http://127.0.0.1:4000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-ilaas",
    "input": "Réponds exactement: OK",
    "max_output_tokens": 20,
    "stream": true
  }'
```

---

### Terminal 2 — tester Codex

Dans un dépôt Git :

```bash
cd ~/tmp/test-codex-ilaas

CODEX_HOME="$HOME/.codex-ilaas" \
OPENAI_API_KEY="sk-local-dummy" \
codex exec "Réponds exactement: OK"
```

Hors dépôt Git :

```bash
CODEX_HOME="$HOME/.codex-ilaas" \
OPENAI_API_KEY="sk-local-dummy" \
codex exec --skip-git-repo-check "Réponds exactement: OK"
```

Ancien résultat avec LiteLLM direct :

```text
provider: litellm_ilaas_http
...
tokens used
0
```

Résultat actuel avec `ilaas_responses_proxy` :

```text
provider: ilaas_responses_proxy
codex
OK
tokens used
4
```

---

## Lanceurs pratiques

### Lanceur LiteLLM

Chemin :

```text
~/.local/bin/litellm-ilaas
```

Contenu :

```bash
#!/usr/bin/env bash
source "$HOME/.venvs/litellm/bin/activate"
exec litellm \
  --config "$HOME/.config/litellm/ilaas-mistral.yaml" \
  --host 127.0.0.1 \
  --port 4000
```

Installation :

```bash
mkdir -p ~/.local/bin

cat > ~/.local/bin/litellm-ilaas <<'EOF'
#!/usr/bin/env bash
source "$HOME/.venvs/litellm/bin/activate"
exec litellm \
  --config "$HOME/.config/litellm/ilaas-mistral.yaml" \
  --host 127.0.0.1 \
  --port 4000
EOF

chmod +x ~/.local/bin/litellm-ilaas
```

Utilisation :

```bash
litellm-ilaas
```

---

### Lanceur Codex ILaaS

Chemin :

```text
~/.local/bin/codex-ilaas
```

Contenu :

```bash
#!/usr/bin/env bash
export CODEX_HOME="$HOME/.codex-ilaas"
export OPENAI_API_KEY="sk-local-dummy"
exec codex "$@"
```

Installation :

```bash
mkdir -p ~/.local/bin

cat > ~/.local/bin/codex-ilaas <<'EOF'
#!/usr/bin/env bash
export CODEX_HOME="$HOME/.codex-ilaas"
export OPENAI_API_KEY="sk-local-dummy"
exec codex "$@"
EOF

chmod +x ~/.local/bin/codex-ilaas
```

Utilisation :

```bash
codex-ilaas exec "Réponds exactement: OK"
```

ou dans un dépôt :

```bash
cd ~/Code/ton-depot
codex-ilaas exec "Analyse ce dépôt et propose un patch minimal."
```

---

## Usage normal Codex GPT‑5.5

L’usage normal ne doit pas être modifié.

Commande normale :

```bash
codex
```

Configuration normale :

```text
~/.codex/config.toml
```

Cette configuration ne doit pas être remplacée par la configuration ILaaS.

---

## Hypothèse technique principale

Le problème restant semble être une incompatibilité entre :

```text
Codex CLI v0.141.0
  -> wire_api = "responses"
  -> LiteLLM /v1/responses
  -> bridge LiteLLM vers /chat/completions
  -> ILaaS
```

Le fait que `/chat/completions` fonctionne prouve que le modèle ILaaS et LiteLLM fonctionnent.

Le fait que Codex termine avec :

```text
tokens used
0
```

suggère que Codex ne reçoit pas ou n’interprète pas correctement la réponse de LiteLLM sur `/v1/responses`, malgré `supports_websockets = false`.

À vérifier côté Codex / LiteLLM :

1. Format exact de la réponse HTTP `/v1/responses` renvoyée par LiteLLM.
2. Format exact attendu par Codex CLI v0.141.0.
3. Support réel du streaming SSE `/v1/responses` dans LiteLLM pour un modèle défini comme `openai/mistral-medium-latest`.
4. Éventuelle nécessité d’un paramètre Codex supplémentaire pour désactiver le streaming.
5. Éventuelle nécessité d’un petit proxy intermédiaire plus simple que LiteLLM, traduisant strictement :
   - `/v1/responses` Codex
   - vers `/v1/chat/completions` ILaaS
   - puis reformatant la réponse au format exact attendu par Codex.

---

## Instruction possible à donner à Codex

```text
Je veux faire fonctionner Codex CLI v0.141.0 avec ILaaS via LiteLLM.

Le modèle ILaaS `mistral-medium-latest` fonctionne déjà via LiteLLM en `/v1/chat/completions`.
Le test curl sur `http://127.0.0.1:4000/v1/chat/completions` renvoie bien `OK`.

En revanche, Codex doit utiliser `wire_api = "responses"` et l’exécution :

CODEX_HOME="$HOME/.codex-ilaas" OPENAI_API_KEY="sk-local-dummy" codex exec "Réponds exactement: OK"

charge bien le provider custom `litellm_ilaas_http`, ne tente plus WebSocket grâce à `supports_websockets = false`, mais termine sans réponse avec `tokens used 0`.

Analyse les fichiers suivants :
- `~/.config/litellm/ilaas-mistral.yaml`
- `~/.codex-ilaas/config.toml`

Puis diagnostique pourquoi Codex ne consomme aucun token malgré un `/chat/completions` fonctionnel.
Il faut vérifier en priorité le comportement de `/v1/responses` dans LiteLLM, le format attendu par Codex CLI v0.141.0, et proposer soit une correction de configuration, soit un proxy minimal compatible Responses API.
```

---

## Résumé court

```text
OK :
- ILaaS fonctionne.
- LiteLLM fonctionne en /chat/completions.
- Codex lit bien la config isolée ~/.codex-ilaas.
- Le WebSocket Codex -> LiteLLM a été désactivé avec supports_websockets = false.

Pas OK :
- Codex ne produit aucune sortie.
- Codex affiche tokens used 0.
- Le problème restant est probablement sur /v1/responses ou le format de stream/réponse attendu par Codex.
```
---

## Claude Code via ILaaS

Un prototype Claude Code est disponible avec :

```bash
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

Le lanceur démarre LiteLLM, puis un proxy local Anthropic Messages sur `127.0.0.1:4002`, et configure `ANTHROPIC_BASE_URL` pour Claude Code. Les modèles ILaaS sont exposés à Claude Code sous la forme `claude-ilaas-<slug>`, mais le lanceur accepte aussi directement les slugs ILaaS :

```bash
Ilaas-claude --list-models
Ilaas-claude -p --model gemma-4-31b "Réponds exactement: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

`--list-models` réutilise le catalogue `~/.codex-ilaas/model-catalogs/ilaas-mistral.json`, donc la liste reste alignée avec `refresh_ilaas_models.py` et `Ilaas-codex`.

État validé :

```text
qwen-3.6-35b-instruct : OK avec Claude Code, y compris outil Read
gemma-4-31b : OK avec Claude Code
mistral-medium-latest : OK avec Claude Code, y compris outil Read
modèles Mistral ILaaS : transport outils accepté côté LiteLLM
llama-3.1-8b / llama-3.3-70b : répondent sans outils, mais échouent actuellement avec les outils Claude Code via LiteLLM/ILaaS
```

Conclusion pratique : pour choisir un agent de code ILaaS dans Claude Code aujourd'hui, utiliser en priorité Qwen, Gemma ou Mistral. Les modèles Llama restent à traiter séparément tant que le tool-calling LiteLLM/ILaaS échoue avec eux.
---

## OpenCode via ILaaS

OpenCode fonctionne plus directement que Claude Code, car il sait déclarer un provider OpenAI-compatible. Le lanceur disponible est :

```bash
Ilaas-opencode --list-models
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
Ilaas-opencode run --model mistral-medium-latest "Réponds exactement: OK"
```

Le lanceur démarre LiteLLM si nécessaire, puis injecte une configuration OpenCode temporaire via `OPENCODE_CONFIG_CONTENT`. Le provider s'appelle `ilaas`, donc les modèles complets ont la forme :

```text
ilaas/qwen-3.6-35b-instruct
ilaas/mistral-medium-latest
```

Le lanceur accepte aussi les slugs ILaaS seuls avec `--model` et les réécrit automatiquement.

État validé :

```text
qwen-3.6-35b-instruct : OK avec OpenCode, y compris outil Read
mistral-medium-latest : OK avec OpenCode en run simple
```

`Ilaas-opencode --list-models` réutilise le même catalogue que `Ilaas-codex` et `Ilaas-claude`.

