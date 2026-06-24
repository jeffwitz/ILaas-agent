# Codex avec ILaaS/Mistral via LiteLLM

Ce README documente le montage mis en place pour utiliser **Codex** avec un modèle ILaaS, par exemple `mistral-medium-latest`, sans casser l’usage normal de Codex avec un modèle OpenAI/ChatGPT comme GPT-5.5.

L’idée est de garder deux chemins séparés :

- `codex` seul : usage normal avec le compte ChatGPT / OpenAI.
- `codex --profile ilaas` : usage via ILaaS, en passant par un proxy LiteLLM local.

LiteLLM sert de pont entre ILaaS et l’API OpenAI-compatible `/chat/completions`.

Pour Codex CLI v0.141.0, un second petit proxy local est nécessaire : Codex parle en `/v1/responses` au proxy `codex_ilaas_responses_proxy.py`, qui traduit ensuite vers LiteLLM en `/v1/chat/completions`.

---

## 1. Installation de LiteLLM dans un venv Ubuntu

Installer les dépendances système :

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip jq
```

Créer un environnement Python dédié :

```bash
python3 -m venv ~/.venvs/litellm
source ~/.venvs/litellm/bin/activate
python -m pip install --upgrade pip
pip install -U "litellm[proxy]"
```

Vérifier l’installation :

```bash
which litellm
litellm --version
```

La commande `which litellm` doit normalement afficher quelque chose comme :

```text
/home/jeff/.venvs/litellm/bin/litellm
```

---

## 2. Configuration LiteLLM pour ILaaS/Mistral

Créer le dossier de configuration :

```bash
mkdir -p ~/.config/litellm
nano ~/.config/litellm/ilaas-mistral.yaml
```

Contenu du fichier :

```yaml
model_list:
  - model_name: mistral-ilaas
    litellm_params:
      model: openai/chat_completions/mistral-medium-latest
      api_base: https://llm.ilaas.fr/v1
      api_key: "TA_CLE_ILAAS_ICI"
      use_chat_completions_api: true
      max_tokens: 4096

litellm_settings:
  drop_params: true

general_settings:
  master_key: "sk-litellm-local"
```

Remplacer seulement :

```text
COLLE_TA_CLE_ILAAS_ICI
```

par la vraie clé API ILaaS.

Sécuriser le fichier, car il contient une clé API en dur :

```bash
chmod 600 ~/.config/litellm/ilaas-mistral.yaml
```

Remarque : la clé ILaaS est stockée ici côté LiteLLM, pas dans la configuration Codex.

---

## 3. Lancer le proxy LiteLLM

Dans un premier terminal :

```bash
source ~/.venvs/litellm/bin/activate
litellm --config ~/.config/litellm/ilaas-mistral.yaml --host 127.0.0.1 --port 4000
```

Ce terminal doit rester ouvert pendant l’utilisation de Codex avec ILaaS.

Le proxy écoute alors sur :

```text
http://127.0.0.1:4000/v1
```

---

## 4. Test rapide du proxy LiteLLM

Alternative manuelle, si les deux serveurs sont déjà lancés :

```bash
curl -s http://127.0.0.1:4000/v1/responses \
  -H "Authorization: Bearer sk-litellm-local" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral-ilaas",
    "input": "Réponds en une phrase : es-tu opérationnel pour coder ?"
  }' | jq
```

Ce test `/v1/responses` simple peut fonctionner, mais il ne suffit pas pour Codex CLI v0.141.0. Avec la requête Responses complète envoyée par Codex, LiteLLM peut répondre avec un message vide et `usage.total_tokens = 0`.

Le test déterminant côté LiteLLM reste donc `/chat/completions` :

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

Si cette commande échoue, corriger LiteLLM avant de lancer le proxy Codex.

---

## 5. Lancer le proxy Responses pour Codex

Dans ce dépôt :

```bash
cd /home/jeff/Code/Codex_Mistral
./codex-ilaas-responses-proxy
```

Le proxy écoute alors sur :

```text
http://127.0.0.1:4001/v1/responses
```

et relaie vers LiteLLM :

```text
http://127.0.0.1:4000/v1/chat/completions
```

---

## 6. Configuration Codex sans casser GPT-5.5

Ne pas remplacer entièrement le fichier global :

```text
~/.codex/config.toml
```

Il faut garder ce fichier pour l’usage normal de Codex avec OpenAI/ChatGPT.

Créer plutôt un profil séparé :

```bash
mkdir -p ~/.codex
nano ~/.codex/ilaas.config.toml
```

Contenu du profil ILaaS :

```toml
model = "ilaas-default"
model_provider = "ilaas_responses_proxy"
model_catalog_json = "/home/jeff/.codex-ilaas/model-catalogs/ilaas-mistral.json"

approval_policy = "on-request"
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

Point important :

```toml
env_key = "OPENAI_API_KEY"
```

ne contient pas la clé ILaaS. C’est seulement le nom de la variable d’environnement que Codex lit pour s’authentifier auprès du proxy local.

Le champ `model_catalog_json` évite l’avertissement :

```text
Model metadata for `mistral-ilaas` not found
```

Codex charge ainsi des métadonnées locales pour `ilaas-default` / `mistral-ilaas` au lieu de tomber sur ses métadonnées de secours. Le catalogue actuel est :

```text
~/.codex-ilaas/model-catalogs/ilaas-mistral.json
```

Le profil dédié `~/.codex-ilaas` utilise `sandbox_mode = "danger-full-access"` pour éviter le warning Linux `bubblewrap` sur les systèmes où AppArmor bloque les user namespaces non privilégiés. Le correctif système plus strict consiste à charger le profil AppArmor `bwrap-userns-restrict` ou à ajuster `kernel.apparmor_restrict_unprivileged_userns`, mais cela nécessite `sudo`.

---

## 7. Lancer Codex normalement avec GPT-5.5 / OpenAI

Pour garder l’usage habituel de Codex :

```bash
codex
```

ou, si besoin de forcer un modèle OpenAI explicitement :

```bash
codex --model gpt-5.5
```

Ce chemin n’utilise pas ILaaS ni LiteLLM.

---

## 8. Lancer Codex avec ILaaS/Mistral

Il faut d’abord que LiteLLM soit lancé sur le port `4000`, puis que le proxy Responses soit lancé sur le port `4001`.

Le lanceur recommandé automatise ces étapes :

```bash
Ilaas-codex
```

Il démarre LiteLLM et le proxy Responses seulement s’ils ne sont pas déjà actifs, puis lance Codex avec :

```text
CODEX_HOME=$HOME/.codex-ilaas
OPENAI_API_KEY=sk-local-dummy
```

Alternative manuelle en mode non interactif :

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
```

Dans un second terminal :

```bash
CODEX_HOME="$HOME/.codex-ilaas" \
OPENAI_API_KEY="sk-local-dummy" \
codex
```

En mode non interactif :

```bash
CODEX_HOME="$HOME/.codex-ilaas" \
OPENAI_API_KEY="sk-local-dummy" \
codex exec --skip-git-repo-check \
  "Analyse ce dépôt et dis-moi quel est le point d'entrée principal."
```

Résumé :

```bash
# Codex normal, OpenAI / GPT-5.5
codex

# Codex via ILaaS/Mistral
CODEX_HOME="$HOME/.codex-ilaas" OPENAI_API_KEY="sk-local-dummy" codex
```

---

## 9. Petit lanceur optionnel pour LiteLLM

Pour éviter de refaire la commande longue à chaque fois :

```bash
mkdir -p ~/.local/bin
nano ~/.local/bin/litellm-ilaas
```

Contenu :

```bash
#!/usr/bin/env bash
source "$HOME/.venvs/litellm/bin/activate"
exec litellm --config "$HOME/.config/litellm/ilaas-mistral.yaml" --host 127.0.0.1 --port 4000
```

Rendre le script exécutable :

```bash
chmod +x ~/.local/bin/litellm-ilaas
```

Vérifier que `~/.local/bin` est dans le `PATH` :

```bash
echo "$PATH" | tr ':' '\n' | grep "$HOME/.local/bin"
```

Ensuite, lancer le proxy avec :

```bash
litellm-ilaas
```

Puis lancer le proxy Responses Codex dans un autre terminal :

```bash
cd /home/jeff/Code/Codex_Mistral
./codex-ilaas-responses-proxy
```

Puis lancer Codex ILaaS :

```bash
CODEX_HOME="$HOME/.codex-ilaas" OPENAI_API_KEY="sk-local-dummy" codex
```

---

## 9. Erreurs rencontrées et corrections

### Erreur : modèle non supporté avec un compte ChatGPT

Message typique :

```text
The 'mistral-ilaas' model is not supported when using Codex with a ChatGPT account.
```

Cause probable : Codex n’utilise pas le provider LiteLLM. Il part sur le provider OpenAI/ChatGPT par défaut et envoie le nom `mistral-ilaas` à ChatGPT.

Correction : utiliser le `CODEX_HOME` ILaaS :

```bash
CODEX_HOME="$HOME/.codex-ilaas" OPENAI_API_KEY="sk-local-dummy" codex
```

ou vérifier que la configuration contient bien :

```toml
model_provider = "ilaas_responses_proxy"
```

---

### Erreur : provider non trouvé

Message typique :

```text
Error loading configuration: Model provider `ilaas_responses_proxy` not found
```

Cause probable : Codex voit :

```toml
model_provider = "ilaas_responses_proxy"
```

mais ne voit pas le bloc :

```toml
[model_providers.ilaas_responses_proxy]
```

Correction : vérifier le fichier :

```bash
cat ~/.codex-ilaas/config.toml
```

Il doit contenir les deux éléments :

```toml
model_provider = "ilaas_responses_proxy"

[model_providers.ilaas_responses_proxy]
name = "ILaaS Responses Proxy"
base_url = "http://127.0.0.1:4001/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
supports_websockets = false
```

Attention aux fautes de nom :

```toml
[model_provider.ilaas_responses_proxy]       # faux
[model_providers.ilaas-responses-proxy]      # faux si model_provider utilise ilaas_responses_proxy
[model_providers.ilaas_responses_proxy]      # bon
```

---

### Erreur 401 ou 403 côté Codex

Avec le montage actuel, Codex s’authentifie seulement auprès du proxy local avec une valeur factice :

```bash
OPENAI_API_KEY="sk-local-dummy"
```

Si un `master_key` LiteLLM est réintroduit dans `~/.config/litellm/ilaas-mistral.yaml`, il faut alors aligner cette clé avec ce que le proxy envoie à LiteLLM. Le montage actuel évite volontairement cette couche d’auth locale.

---

### Erreur 401 ou 403 côté ILaaS

Cause probable : clé ILaaS absente, mauvaise ou expirée dans le YAML LiteLLM.

Vérifier :

```bash
grep api_key ~/.config/litellm/ilaas-mistral.yaml
```

Puis tester directement ILaaS si besoin :

```bash
curl -s https://llm.ilaas.fr/v1/models \
  -H "Authorization: Bearer TA_CLE_ILAAS" | jq
```

---

### Erreur `/responses` non trouvé

Cause probable : appel direct à ILaaS sans LiteLLM, ou mauvaise configuration du proxy.

Le montage prévu est :

```text
Codex -> http://127.0.0.1:4001/v1 -> proxy Responses
      -> http://127.0.0.1:4000/v1/chat/completions -> LiteLLM
      -> https://llm.ilaas.fr/v1
```

Codex ne doit pas pointer directement vers :

```text
https://llm.ilaas.fr/v1
```

Le profil Codex doit pointer vers le proxy local :

```toml
base_url = "http://127.0.0.1:4001/v1"
wire_api = "responses"
```

Et le YAML LiteLLM doit utiliser le modèle en chat completions :

```yaml
model: openai/mistral-medium-latest
use_chat_completions_api: true
```

---

## 10. Rafraîchir les modèles ILaaS

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

