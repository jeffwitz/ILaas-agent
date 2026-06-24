# Cahier des charges - ILaaS Code Agents

## 1. Objectif

Créer un dépôt GitHub installable permettant d'utiliser les modèles ILaaS avec plusieurs agents de code locaux :

- Codex CLI
- Claude Code
- OpenCode

Le dépôt doit permettre, après clonage, de configurer automatiquement les proxies, les fichiers de configuration, les wrappers exécutables et les tests de diagnostic.

Objectif utilisateur :

```bash
git clone https://github.com/<owner>/ilaas-code-agents.git
cd ilaas-code-agents
python install.py
```

Puis utiliser directement :

```bash
Ilaas-codex
Ilaas-claude
Ilaas-opencode
```

Le projet doit être pensé multi-OS dès le départ :

- Linux
- macOS
- Windows via WSL2
- Windows natif, si les outils ciblés sont disponibles et testables

## 2. Contexte technique actuel

Un prototype fonctionne déjà dans :

```text
/home/jeff/Code/Codex_Mistral
```

Scripts existants :

```text
Ilaas-codex
Ilaas-claude
Ilaas-opencode
mistral-codex
codex_ilaas_responses_proxy.py
claude_ilaas_messages_proxy.py
refresh_ilaas_models.py
```

Wrappers globaux existants :

```text
~/.local/bin/Ilaas-codex
~/.local/bin/Ilaas-claude
~/.local/bin/Ilaas-opencode
```

Configurations locales existantes :

```text
~/.config/litellm/ilaas-mistral.yaml
~/.codex-ilaas/config.toml
~/.codex-ilaas/model-catalogs/ilaas-mistral.json
```

Important : aucune clé ILaaS ne doit être versionnée.

## 3. Modèles ILaaS actuellement connus

Le script `refresh_ilaas_models.py` interroge l'endpoint ILaaS `/v1/models` et génère les listes locales.

Modèles actuellement vus :

```text
ilaas-default -> mistral-medium-latest
mistral-ilaas -> mistral-medium-latest (alias legacy)
gemma-4-31b
gpt-oss-120b
llama-3.1-8b
llama-3.3-70b
mistral-medium-latest
mistral-small-3.2-24b
mistral-small-4-119b
qwen-3.6-35b-instruct
```

Recommandation actuelle pour agents de code :

```text
qwen-3.6-35b-instruct : recommandé
mistral-medium-latest : recommandé
gemma-4-31b : utilisable
```

Modèles à marquer comme non recommandés pour agent de code :

```text
llama-3.1-8b
llama-3.3-70b
```

Raison : ces modèles répondent en chat simple, mais leur tool-calling échoue ou est trop faible dans les montages Claude Code / OpenCode / LiteLLM.

## 4. Contraintes principales

### 4.1 Sécurité

- Ne jamais stocker de clé API dans Git.
- Ne jamais afficher la clé API ILaaS dans les logs ou les messages de diagnostic.
- Les fichiers locaux contenant la clé doivent être en permission restrictive quand l'OS le permet.
- Les scripts doivent accepter la clé via :

```bash
ILAAS_API_KEY=...
```

ou via une saisie interactive.

### 4.2 Portabilité

La logique principale ne doit pas dépendre de Bash.

Approche requise :

- coeur en Python ;
- wrappers shell très minces ;
- wrappers PowerShell / CMD pour Windows ;
- pas de dépendance dure à `lsof`, `/dev/tcp`, `kill`, `sed`, `awk`, `jq`.

Les fonctions portables doivent utiliser :

- `pathlib` pour les chemins ;
- `socket.create_connection()` pour tester les ports ;
- `subprocess.Popen()` pour lancer les serveurs ;
- PID files pour suivre les processus ;
- `platform.system()` pour détecter l'OS.

### 4.3 Compatibilité agents

Chaque agent a une interface différente :

```text
Codex CLI    -> OpenAI Responses API attendue par Codex
Claude Code  -> Anthropic Messages API attendue par Claude Code
OpenCode     -> Provider OpenAI-compatible via @ai-sdk/openai-compatible
```

Il faut donc garder trois chemins distincts, mais réutiliser :

- la configuration LiteLLM ;
- la découverte des modèles ;
- la gestion des processus ;
- le catalogue de modèles ;
- les tests de diagnostic.

## 5. Architecture cible du dépôt

Structure recommandée :

```text
ilaas-code-agents/
  README.md
  CdC.md
  LICENSE
  .gitignore
  install.py
  install.sh
  install.ps1
  pyproject.toml

  ilaas_agents/
    __init__.py
    cli.py
    paths.py
    config.py
    install.py
    models.py
    litellm.py
    processes.py
    wrappers.py
    doctor.py
    smoke.py

  proxies/
    codex_ilaas_responses_proxy.py
    claude_ilaas_messages_proxy.py

  templates/
    litellm_ilaas.yaml
    codex_config.toml
    wrappers/
      posix/
        Ilaas-codex
        Ilaas-claude
        Ilaas-opencode
      windows/
        Ilaas-codex.cmd
        Ilaas-claude.cmd
        Ilaas-opencode.cmd
        Ilaas-codex.ps1
        Ilaas-claude.ps1
        Ilaas-opencode.ps1

  docs/
    codex.md
    claude-code.md
    opencode.md
    models.md
    windows.md
    troubleshooting.md

  tests/
    test_paths.py
    test_config_generation.py
    test_model_catalog.py
```

## 6. Chemins par plateforme

### 6.1 Linux

```text
LiteLLM config:
  ~/.config/litellm/ilaas-mistral.yaml

Codex home:
  ~/.codex-ilaas/

Model catalog:
  ~/.codex-ilaas/model-catalogs/ilaas-mistral.json

Wrappers:
  ~/.local/bin/Ilaas-codex
  ~/.local/bin/Ilaas-claude
  ~/.local/bin/Ilaas-opencode

Logs:
  ~/.cache/ilaas-code-agents/logs/

Runtime:
  ~/.cache/ilaas-code-agents/run/
```

### 6.2 macOS

Utiliser les chemins POSIX par défaut, sauf si une convention macOS dédiée est ajoutée plus tard :

```text
~/.config/litellm/ilaas-mistral.yaml
~/.codex-ilaas/
~/.local/bin/
~/Library/Caches/ilaas-code-agents/
```

### 6.3 Windows natif

Chemins proposés :

```text
LiteLLM config:
  %APPDATA%\litellm\ilaas-mistral.yaml

Codex home:
  %USERPROFILE%\.codex-ilaas\

Model catalog:
  %USERPROFILE%\.codex-ilaas\model-catalogs\ilaas-mistral.json

Wrappers:
  %LOCALAPPDATA%\Programs\IlaasCodeAgents\bin\

Logs:
  %LOCALAPPDATA%\ilaas-code-agents\logs\

Runtime:
  %LOCALAPPDATA%\ilaas-code-agents\run\
```

### 6.4 Windows WSL2

Chemin recommandé pour Windows au début :

```text
Installer et utiliser le projet dans WSL2.
```

Raison :

- Codex CLI et les sandboxes sont plus prévisibles sous Linux/WSL.
- Les chemins POSIX sont déjà validés.
- Les wrappers Bash existants sont réutilisables.

## 7. Composants à développer

### 7.1 `install.py`

Installeur principal portable.

Responsabilités :

1. détecter l'OS ;
2. vérifier Python ;
3. créer ou réutiliser un venv LiteLLM ;
4. installer ou vérifier `litellm[proxy]` ;
5. demander ou lire la clé ILaaS ;
6. générer la config LiteLLM ;
7. interroger `/v1/models` ILaaS ;
8. générer le catalogue de modèles ;
9. générer `~/.codex-ilaas/config.toml` ;
10. installer les wrappers ;
11. vérifier que le dossier de wrappers est dans le `PATH` ;
12. proposer de lancer `doctor`.

Options souhaitées :

```bash
python install.py
python install.py --non-interactive
python install.py --api-key-env ILAAS_API_KEY
python install.py --prefix ~/.local
python install.py --force
python install.py --skip-litellm-install
```

### 7.2 `ilaas_agents paths`

Module Python responsable des chemins.

Fonctions attendues :

```python
get_os()
config_dir()
cache_dir()
runtime_dir()
wrapper_dir()
litellm_config_path()
codex_home()
codex_config_path()
model_catalog_path()
```

### 7.3 `ilaas_agents models`

Responsabilités :

- lire la clé ILaaS depuis la config existante ou l'environnement ;
- appeler `https://llm.ilaas.fr/v1/models` ;
- générer les alias :

```text
ilaas-default -> mistral-medium-latest
mistral-ilaas -> mistral-medium-latest
```

- générer un catalogue JSON unique ;
- annoter les modèles non recommandés.

### 7.4 `ilaas_agents litellm`

Responsabilités :

- générer `ilaas-mistral.yaml` ;
- démarrer LiteLLM ;
- vérifier `/v1/models` ;
- tester `/v1/chat/completions` ;
- ne jamais logger la clé.

### 7.5 `ilaas_agents processes`

Responsabilités :

- tester si un port écoute ;
- démarrer un processus ;
- écrire un PID file ;
- vérifier si un PID est vivant ;
- arrêter proprement les processus lancés par le projet ;
- afficher les logs.

Commandes cibles :

```bash
Ilaas-servers start
Ilaas-servers stop
Ilaas-servers status
Ilaas-servers logs
```

Cette commande est optionnelle mais recommandée pour éviter de dupliquer la logique dans chaque wrapper.

### 7.6 Proxies

Conserver les deux proxies actuels :

```text
codex_ilaas_responses_proxy.py
claude_ilaas_messages_proxy.py
```

Les déplacer dans :

```text
proxies/
```

#### Proxy Codex

Expose :

```text
http://127.0.0.1:4001/v1/responses
```

Relaye vers :

```text
http://127.0.0.1:4000/v1/chat/completions
```

Raison :

Codex CLI v0.141.0 utilise `wire_api = "responses"`, mais LiteLLM `/v1/responses` a renvoyé une réponse vide avec `tokens used 0` sur la requête réelle Codex.

#### Proxy Claude Code

Expose :

```text
http://127.0.0.1:4002/v1/messages
http://127.0.0.1:4002/v1/messages/count_tokens
http://127.0.0.1:4002/v1/models
```

Relaye vers :

```text
http://127.0.0.1:4000/v1/chat/completions
```

Raison :

Claude Code attend l'API Anthropic Messages. Les modèles doivent être exposés avec un préfixe compatible découverte :

```text
claude-ilaas-<slug>
```

### 7.7 Wrappers

Wrappers à générer :

```text
Ilaas-codex
Ilaas-claude
Ilaas-opencode
```

Sur Windows :

```text
Ilaas-codex.cmd
Ilaas-claude.cmd
Ilaas-opencode.cmd
Ilaas-codex.ps1
Ilaas-claude.ps1
Ilaas-opencode.ps1
```

Les wrappers doivent être minces. Ils doivent appeler un entrypoint Python commun, par exemple :

```bash
python -m ilaas_agents.cli codex "$@"
python -m ilaas_agents.cli claude "$@"
python -m ilaas_agents.cli opencode "$@"
```

## 8. Commandes finales attendues

### 8.1 Codex

```bash
Ilaas-codex
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-codex exec --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

Variables nécessaires :

```text
CODEX_HOME=<codex_home>
OPENAI_API_KEY=sk-local-dummy
```

Config Codex attendue :

```toml
model = "ilaas-default"
model_provider = "ilaas_responses_proxy"
model_catalog_json = "<path>/ilaas-mistral.json"

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

### 8.2 Claude Code

```bash
Ilaas-claude
Ilaas-claude --list-models
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

Variables nécessaires :

```text
ANTHROPIC_BASE_URL=http://127.0.0.1:4002
ANTHROPIC_API_KEY=sk-local-dummy
CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
MAX_THINKING_TOKENS=0
```

Les slugs modèles ILaaS doivent être acceptés directement :

```bash
Ilaas-claude --model qwen-3.6-35b-instruct
```

Le wrapper doit réécrire vers :

```text
claude-ilaas-qwen-3.6-35b-instruct
```

### 8.3 OpenCode

```bash
Ilaas-opencode
Ilaas-opencode --list-models
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
Ilaas-opencode run -m ilaas/qwen-3.6-35b-instruct "Réponds exactement: OK"
```

OpenCode utilise un provider OpenAI-compatible injecté par `OPENCODE_CONFIG_CONTENT`.

Config logique :

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "ilaas/ilaas-default",
  "small_model": "ilaas/ilaas-default",
  "provider": {
    "ilaas": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "ILaaS via LiteLLM",
      "options": {
        "baseURL": "http://127.0.0.1:4000/v1",
        "apiKey": "{env:OPENAI_API_KEY}",
        "timeout": 600000,
        "chunkTimeout": 60000
      },
      "models": {}
    }
  }
}
```

## 9. Diagnostics

Créer une commande :

```bash
python -m ilaas_agents.cli doctor
```

ou :

```bash
Ilaas-doctor
```

Tests à effectuer :

1. OS détecté ;
2. Python détecté ;
3. venv LiteLLM présent ;
4. binaire LiteLLM présent ;
5. `codex` présent ou absent ;
6. `claude` présent ou absent ;
7. `opencode` présent ou absent ;
8. config LiteLLM présente ;
9. clé ILaaS présente sans l'afficher ;
10. `GET https://llm.ilaas.fr/v1/models` OK ;
11. LiteLLM démarre sur `127.0.0.1:4000` ;
12. `GET http://127.0.0.1:4000/v1/models` OK ;
13. `POST /v1/chat/completions` OK ;
14. proxy Codex démarre sur `127.0.0.1:4001` ;
15. `POST /v1/responses` via proxy Codex OK ;
16. proxy Claude démarre sur `127.0.0.1:4002` ;
17. `POST /v1/messages` via proxy Claude OK ;
18. `Ilaas-opencode --list-models` OK.

Sortie attendue :

```text
[OK] Python
[OK] LiteLLM
[OK] ILaaS /v1/models
[OK] LiteLLM /v1/chat/completions
[OK] Codex Responses proxy
[OK] Claude Messages proxy
[OK] OpenCode config generation
[WARN] Codex not installed
```

## 10. Tests de fumée

### 10.1 Test modèle simple

Prompt :

```text
Réponds exactement: OK
```

Attendu :

```text
OK
```

À tester avec :

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

### 10.2 Test outil fichier

Prompt :

```text
Lis le fichier refresh_ilaas_models.py et réponds uniquement avec la valeur de DEFAULT_ALIAS.
```

Attendu :

```text
ilaas-default
```

Ce test vérifie le comportement agentique avec lecture de fichier.

Validations déjà obtenues dans le prototype :

```text
Claude Code + qwen-3.6-35b-instruct + Read : OK
Claude Code + mistral-medium-latest + Read : OK
OpenCode + qwen-3.6-35b-instruct + Read : OK
```

## 11. Documentation attendue

### 11.1 `README.md`

README court :

1. objectif ;
2. prérequis ;
3. installation ;
4. configuration de la clé ILaaS ;
5. usage Codex ;
6. usage Claude Code ;
7. usage OpenCode ;
8. modèles recommandés ;
9. dépannage rapide.

### 11.2 `docs/codex.md`

Expliquer :

- pourquoi Codex nécessite `wire_api = "responses"` ;
- pourquoi LiteLLM `/v1/responses` n'a pas suffi ;
- rôle du proxy `codex_ilaas_responses_proxy.py` ;
- configuration `CODEX_HOME`.

### 11.3 `docs/claude-code.md`

Expliquer :

- rôle de l'API Anthropic Messages ;
- rôle du proxy `claude_ilaas_messages_proxy.py` ;
- préfixe `claude-ilaas-` ;
- variables `ANTHROPIC_*`.

### 11.4 `docs/opencode.md`

Expliquer :

- provider custom OpenAI-compatible ;
- `@ai-sdk/openai-compatible` ;
- `OPENCODE_CONFIG_CONTENT` ;
- format modèle `ilaas/<slug>`.

### 11.5 `docs/windows.md`

Inclure :

- recommandation WSL2 ;
- état Windows natif ;
- chemins Windows ;
- wrappers `.cmd` et `.ps1` ;
- limites connues.

### 11.6 `docs/troubleshooting.md`

Inclure :

- `tokens used 0` avec Codex ;
- warning Codex model metadata ;
- warning bubblewrap Linux ;
- clé ILaaS absente ou invalide ;
- port déjà occupé ;
- LiteLLM non installé ;
- Llama non recommandé pour agent code.

## 12. Gestion des dépendances

### 12.1 Python

Version minimale :

```text
Python 3.10+
```

Dépendances souhaitées minimales :

```text
standard library autant que possible
```

Éviter d'ajouter des dépendances lourdes pour l'installeur.

LiteLLM doit rester dans son venv dédié :

```text
~/.venvs/litellm
```

ou équivalent plateforme.

### 12.2 Node / OpenCode

Ne pas installer OpenCode automatiquement par défaut.

Le doctor doit détecter :

```bash
opencode --version
```

Si absent, afficher l'instruction d'installation adaptée.

OpenCode sait charger `@ai-sdk/openai-compatible` via sa configuration, mais il faut vérifier en pratique si le package est disponible selon l'installation locale. Si nécessaire, documenter l'installation.

### 12.3 Claude Code

Ne pas installer Claude Code automatiquement par défaut.

Le doctor doit détecter :

```bash
claude --version
```

Si absent, afficher une instruction de dépannage sans casser l'installation des autres agents.

### 12.4 Codex

Ne pas installer Codex automatiquement par défaut.

Le doctor doit détecter :

```bash
codex --version
```

Si absent, afficher une instruction de dépannage.

## 13. Critères d'acceptation

### 13.1 Installation Linux

Sur une machine Linux avec Python et une clé ILaaS :

```bash
python install.py
Ilaas-doctor
```

doit produire :

```text
LiteLLM OK
ILaaS models OK
Codex config OK
Claude proxy OK
OpenCode config OK
```

Les wrappers doivent être présents dans le `PATH`.

### 13.2 Codex

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
```

doit retourner `OK` et consommer des tokens.

Ne doit pas afficher :

```text
tokens used 0
Model metadata not found
```

### 13.3 Claude Code

```bash
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

doit retourner `OK`.

Test outil :

```bash
Ilaas-claude -p --model qwen-3.6-35b-instruct --allowedTools Read --permission-mode bypassPermissions \
  "Lis le fichier refresh_ilaas_models.py et réponds uniquement avec la valeur de DEFAULT_ALIAS."
```

doit retourner :

```text
ilaas-default
```

### 13.4 OpenCode

```bash
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

doit retourner `OK`.

Test outil :

```bash
Ilaas-opencode run --model qwen-3.6-35b-instruct \
  "Lis le fichier refresh_ilaas_models.py et réponds uniquement avec la valeur de DEFAULT_ALIAS."
```

doit retourner :

```text
ilaas-default
```

## 14. Ordre d'implémentation recommandé

1. Créer la structure de dépôt propre.
2. Déplacer les proxies dans `proxies/`.
3. Créer `ilaas_agents/paths.py`.
4. Créer `ilaas_agents/models.py`.
5. Porter `refresh_ilaas_models.py` dans le package.
6. Créer la génération de config LiteLLM.
7. Créer la génération de config Codex.
8. Créer les wrappers POSIX depuis templates.
9. Créer `install.py`.
10. Créer `doctor.py`.
11. Porter `Ilaas-codex` vers l'entrypoint Python.
12. Porter `Ilaas-claude` vers l'entrypoint Python.
13. Porter `Ilaas-opencode` vers l'entrypoint Python.
14. Ajouter les wrappers Windows.
15. Tester depuis un clone local temporaire dans `/tmp`.
16. Publier sur GitHub seulement après validation.

## 15. Tests depuis clone temporaire

Avant publication :

```bash
cd /tmp
git clone /home/jeff/Code/Codex_Mistral ilaas-code-agents-test
cd ilaas-code-agents-test
python install.py --force
Ilaas-doctor
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

## 16. Points ouverts

1. Choisir le nom final du dépôt GitHub.
2. Choisir la licence.
3. Décider si `Ilaas-servers` est inclus dès la première version.
4. Décider si Windows natif est supporté officiellement ou marqué expérimental.
5. Décider si les Llama sont masqués par défaut ou seulement annotés.
6. Vérifier OpenCode sur macOS.
7. Vérifier Claude Code sur macOS.
8. Vérifier Codex sur macOS.
9. Vérifier le comportement Windows natif.

## 17. Résumé court pour reprise

Le dépôt doit devenir un installateur multi-agent et multi-OS pour utiliser ILaaS dans les outils de code.

Principe central :

```text
ILaaS
  <- LiteLLM /v1/chat/completions
    <- Codex Responses proxy pour Codex
    <- Claude Messages proxy pour Claude Code
    <- OpenCode provider openai-compatible direct
```

Une seule source de vérité pour les modèles :

```text
model catalog JSON généré depuis ILaaS /v1/models
```

Une seule commande d'installation :

```bash
python install.py
```

Une seule commande de diagnostic :

```bash
Ilaas-doctor
```

Wrappers finaux :

```bash
Ilaas-codex
Ilaas-claude
Ilaas-opencode
```
