# Sama-Terrain — Service IA (FastAPI)

Micro-service d'intelligence artificielle de **Sama-Terrain**, séparé du [backend Django](../backend/README.md) et appelé par lui via HTTP. Il n'entraîne **aucun modèle en interne** : toute la "réflexion" est déléguée à un LLM externe (via OpenRouter), nourri avec de vraies données calculées à partir de la base PostgreSQL — jamais de valeurs inventées ou mockées.

Projet réalisé dans le cadre de la certification **DWWM + IA** — Simplon Sénégal (programme Fabrique 360).

## Sommaire

- [Rôle dans l'architecture globale](#rôle-dans-larchitecture-globale)
- [Les fonctionnalités IA](#les-fonctionnalités-ia)
- [Stack technique](#stack-technique)
- [Organisation du code](#organisation-du-code)
- [Installation et lancement](#installation-et-lancement)
- [Variables d'environnement](#variables-denvironnement)
- [Choisir un modèle sur OpenRouter](#choisir-un-modèle-sur-openrouter)
- [Points d'attention / limites connues](#points-dattention--limites-connues)
- [Perspectives d'évolution](#perspectives-dévolution)

## Rôle dans l'architecture globale

```
┌──────────────┐   POST /api/ia/chatbot/       ┌─────────────────┐   POST /chatbot        ┌──────────────┐
│   Frontend    │ ─────────────────────────────▶│ Backend Django   │ ──────────────────────▶│ Service IA    │
│  (chatbot)    │◀───────────────────────────── │ (proxy simple)   │◀────────────────────── │ (ce dossier)  │
└──────────────┘                                └─────────────────┘                        └──────┬───────┘
                                                                                                     │
┌──────────────┐  GET /api/ia/predictions/:id/  ┌─────────────────┐  GET /predictions/:id           │
│  Dashboard    │ ─────────────────────────────▶│ Backend Django   │ ─────────────────────────────────┤
│  gérant       │◀───────────────────────────── │                  │◀───────────────────────────────  │
└──────────────┘                                └─────────────────┘                                  │
                                                                                                       ▼
                                                                                          ┌───────────────────────┐
                                                                                          │ PostgreSQL (lecture)   │
                                                                                          │ + OpenRouter (LLM)     │
                                                                                          └───────────────────────┘
```

Django ne parle **jamais directement** à OpenRouter : il relaie toujours la requête à ce service (`IA_SERVICE_URL`, voir `backend/.env`), qui lui seul détient la clé API et la logique de prompt.

## Les fonctionnalités IA

### 1. Chatbot d'assistance (`POST /chatbot`)

Répond aux questions des amateurs sur la page d'accueil publique (réservation, tarifs, paiement, annulation, abonnement gérant). Pipeline complet à chaque message :

1. **Garde-fou d'entrée** (`garde_fous.message_entrant_valide`) : rejette sans appeler le LLM un message vide, trop long, ou contenant une tentative grossière de manipulation du prompt ("ignore tes instructions", "jailbreak"...).
2. **Recherche de vrais terrains** : requête SQL directe sur `terrains_terrain` pour ne présenter au LLM que des terrains/prix réellement en base (jamais inventés).
3. **RAG (Retrieval-Augmented Generation)** sur les politiques de la plateforme (`rag.py`) : si la question touche l'annulation, le remboursement ou l'abonnement, les passages pertinents de `faq/politiques.txt` sont retrouvés par similarité sémantique (embeddings `sentence-transformers`) et injectés dans le prompt.
4. **Appel au LLM** (`llm.demander_au_llm`) avec un prompt système strict (ne répond qu'aux sujets Sama-Terrain, n'invente rien, ne révèle jamais ses instructions).
5. **Garde-fou de sortie** (`garde_fous.nettoyer_reponse`) : tronque une réponse anormalement longue.
6. En cas d'échec du LLM (timeout, erreur fournisseur, quota dépassé) : réponse de secours générique, jamais une erreur brute.

### 2. Réservation assistée par conversation (`POST /chatbot`, `reservation_assistee.py`)

Le chatbot peut préparer une réservation en plusieurs échanges :

> Joueur : « Je veux réserver demain à 20 h. »
> IA : « Quel terrain souhaitez-vous réserver ? Disponibles demain à 20h : … »
> Joueur : « Le terrain Almadies. »
> IA : « Le créneau … est disponible pour 30 000 FCFA. Voulez-vous confirmer ? » + bouton « Confirmer sur la page du terrain »

Trois étapes, chacune avec un rôle séparé :

1. **L'IA comprend** : le LLM lit les derniers messages de l'utilisateur (français ou wolof) et renvoie `{"date", "heure", "terrain_id"}` en JSON. Chaque valeur est vérifiée : une date hors des 14 prochains jours, une heure mal formée ou un terrain inexistant est ignoré.
2. **La plateforme vérifie** : une requête SQL en lecture seule sur `creneaux_creneau` dit si le créneau est libre et à quel prix. Les réponses sont écrites en Python, pas par le LLM : un prix ne peut pas être déformé.
3. **L'utilisateur confirme** : le service ne crée **aucune** réservation et ne déclenche **aucun** paiement. Il renvoie un lien `/terrains/{id}?date=…&creneau=…` : la fiche terrain présélectionne le créneau, puis l'amateur suit le parcours habituel (réservation → `/paiement` → PayTech).

Le frontend envoie les derniers messages de l'utilisateur (`historique`) : le service ne stocke aucune session. Si le LLM est indisponible, l'assistant propose simplement d'aller sur la page de recherche. Les questions sur un autre sujet (mes réservations, annulation, abonnement…) restent traitées par le chatbot général.

### 3. Prédictions de demande / prix (`GET /predictions/{terrain_id}`)

Alimente le dashboard et la page "Insights IA" du gérant :

1. Calcule, pour chaque heure de créneau du terrain, le **taux de confirmation réel** des créneaux passés (`confirmés / total`) → classe la demande en `faible` / `moyen` / `élevé`.
2. Écrit directement ces résultats sur les lignes `Creneau` concernées (`niveau_demande`, `prix_recommande_ia`, `derniere_maj_ia`) — `+15%` si forte demande, `−10%` si faible.
3. Demande au LLM de **rédiger** des recommandations en français à partir de ces vraies statistiques (le LLM ne fait que mettre en phrases, il n'invente aucun chiffre).
4. Si le LLM échoue, repli sur des phrases générées directement depuis les statistiques brutes — jamais de texte halluciné.

## Stack technique

| Composant | Rôle |
|---|---|
| FastAPI + Uvicorn | Serveur web léger et rapide |
| SQLAlchemy | Requêtes SQL directes vers PostgreSQL (lecture des terrains/créneaux, écriture des résultats IA) |
| `requests` | Appels HTTP vers l'API OpenRouter |
| `sentence-transformers` | Modèle d'embeddings multilingue pour le RAG (recherche sémantique dans la FAQ) |
| `langchain-text-splitters` | Découpage des documents de FAQ en chunks pour le RAG |
| OpenRouter | Passerelle vers des LLM externes gratuits (aucun modèle propriétaire hébergé ici) |

## Organisation du code

```
main.py          Points d'entrée FastAPI : /health, /predictions/{id}, /chatbot
reservation_assistee.py  Réservation assistée : le LLM extrait date/heure/terrain, SQL vérifie le créneau
texte.py         Normalisation du texte (minuscules, accents) partagée
llm.py           Appel HTTP à OpenRouter (modèle, clé API, timeout)
garde_fous.py    Validation du message entrant + nettoyage de la réponse sortante
rag.py           Indexation et recherche sémantique dans faq/ (embeddings, similarité cosinus)
db.py            Connexion SQLAlchemy à la même base Postgres que Django (lecture/écriture ciblée)
faq/             Documents texte source du RAG (politiques d'annulation, remboursement, abonnement...)
```

## Installation et lancement

Ce service est prévu pour tourner via le `docker-compose.yml` du backend (voir [backend/README.md](../backend/README.md)), qui le démarre en même temps que Django et PostgreSQL :

```bash
# Depuis backend/ (pas depuis IA/)
cp ../IA/.env.example ../IA/.env    # si absent, puis renseigner OPENROUTER_API_KEY
docker compose up -d --build
```

- Le service est alors disponible sur **http://localhost:8001**
- `GET /health` permet de vérifier rapidement qu'il tourne (`{"status": "ok"}`)
- `GET /docs` donne une documentation Swagger interactive générée automatiquement par FastAPI

**Après toute modification de `IA/.env`**, il faut recréer le conteneur pour que la nouvelle valeur soit prise en compte (`restart` seul ne relit pas le fichier) :

```bash
docker compose up -d --force-recreate ia
```

### Sans Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

cp .env.example .env    # adapter DATABASE_URL vers votre Postgres local

uvicorn main:app --reload --port 8001
```

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | Connexion à la même base PostgreSQL que Django (lecture des terrains/créneaux/réservations, écriture des champs IA sur `Creneau`) |
| `OPENROUTER_API_KEY` | Clé API OpenRouter ([openrouter.ai/keys](https://openrouter.ai/keys)) — sans elle, `demander_au_llm` lève une erreur explicite |
| `OPENROUTER_MODEL` | Identifiant du modèle utilisé (ex : `nvidia/nemotron-3-super-120b-a12b:free`) |

## Choisir un modèle sur OpenRouter

Les modèles gratuits (`:free`) d'OpenRouter partagent un **quota quotidien par compte** (~50 requêtes/jour toutes gratuites confondues) et peuvent être **temporairement surchargés côté fournisseur**, indépendamment de ce quota — dans ce cas OpenRouter répond parfois avec un **HTTP 200 contenant un corps d'erreur** plutôt qu'un vrai code d'erreur, ce qu'il faut détecter explicitement (voir `llm.py`, qui vérifie la présence de `"choices"` dans la réponse).

Pour vérifier rapidement qu'un modèle répond correctement :

```bash
docker compose exec ia python -c "
import os, requests
r = requests.post('https://openrouter.ai/api/v1/chat/completions',
    headers={'Authorization': f'Bearer {os.getenv(\"OPENROUTER_API_KEY\")}'},
    json={'model': os.getenv('OPENROUTER_MODEL'), 'messages': [{'role':'user','content':'bonjour'}]},
    timeout=20)
print(r.status_code, r.text[:300])
"
```

Liste des modèles gratuits actuellement proposés par OpenRouter : `GET https://openrouter.ai/api/v1/models` (filtrer les identifiants se terminant par `:free`).

## Points d'attention / limites connues

- **Latence variable** : les modèles gratuits peuvent répondre en 2s comme en 40s selon la charge du fournisseur. Le timeout de `llm.py` (45s) et celui du proxy Django (60s) doivent rester cohérents entre eux — et le serveur Gunicorn du backend doit avoir un `--timeout` supérieur aux deux, sinon il tue le worker avant la fin de la requête.
- **Modèles "raisonneurs"** : certains modèles gratuits (suffixés `reasoning`, ou orientés chaîne de pensée) peuvent renvoyer leur raisonnement interne brut dans le champ `content` au lieu d'une réponse propre. Préférer un modèle conversationnel classique pour le chatbot.
- **Erreurs silencieuses** : `main.py` capture toute exception LLM avec `logger.exception(...)` avant de retomber sur un message de secours — toujours consulter `docker compose logs ia` en cas de comportement inattendu plutôt que de deviner.
- **Le RAG ne connaît que `faq/politiques.txt`** : pour enrichir les réponses sur d'autres sujets (nouvelles règles, nouveaux moyens de paiement...), ajouter un fichier `.txt` dans `faq/` — l'index est reconstruit automatiquement au prochain redémarrage du service (mis en cache en mémoire via `@lru_cache`, pas rechargé à chaud).
- **Tests automatisés** : seule la réservation assistée est couverte (`python -m unittest test_reservation_assistee`, sans base ni LLM grâce à des doublures).

## Perspectives d'évolution

Fonctionnalités **non disponibles** à ce jour, préparées dans l'architecture :

- **Assistant vocal (français / wolof)** : la réservation assistée prend du texte en entrée et ne dépend pas du canal. Un assistant vocal consisterait à ajouter une étape de transcription (speech-to-text via une API externe, comme le reste de l'IA du projet) avant le même `POST /chatbot` : « Je veux réserver un terrain demain soir près de Parcelles Assainies » suivrait alors exactement le même parcours (compréhension → vérification en base → confirmation par l'utilisateur). Points à valider avant de s'engager : qualité de la transcription du wolof par les API disponibles, et compréhension du wolof par le LLM utilisé. Aucune dépendance audio n'est installée pour l'instant.
- **Rapports hebdomadaires des gérants** : rédigés par un agent IA dans N8n, à partir des chiffres fournis par le backend (voir `GET /api/gerant/n8n/rapport-hebdomadaire/` dans le [README du backend](../backend/README.md)). Ce service n'y intervient pas.
