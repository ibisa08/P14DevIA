# Développement local

Prérequis : Docker, Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js 22.19 (`.nvmrc`).

## Installation

### 1. Base de données

```bash
docker run --name newsfoundry_db -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=newsfoundry -p 5432:5432 -d postgres:17
```

Si le port 5432 est déjà pris (Postgres Homebrew, autre conteneur), publie le conteneur sur un autre
port, par exemple `-p 5434:5432`, et reporte-le dans `DATABASE_URL`
(`postgresql://user:password@localhost:5434/newsfoundry`).

### 2. Backend

```bash
cd backend
cp .env.example .env     # puis renseigner JWT_SECRET : openssl rand -hex 32
uv sync
uv run --env-file .env src/main.py     # API sur http://localhost:8000
```

Au démarrage, l'application crée les tables manquantes et le compte de test
`test@test.com` / `test`. Sans `JWT_SECRET` (ou avec moins de 32 caractères), elle refuse de démarrer
avec un message explicite.

> `create_all` n'ajoute pas de colonne à une table existante. Après une évolution du modèle, une
> base locale existante doit être migrée à la main ou recréée (ce qui efface ses données : à ne
> faire qu'en connaissance de cause).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev              # http://localhost:3000
```

L'URL de l'API se règle avec `NEXT_PUBLIC_API_URL` (défaut : `http://localhost:8000`). Cette valeur
est figée au build.

## Variables d'environnement du backend

Le modèle est `backend/.env.example`. Les variables sont lues par `config.py` ; un `.env` n'est jamais
commité.

| Variable | Obligatoire | Défaut | Rôle |
|---|---|---|---|
| `DATABASE_URL` | oui | — | Connexion PostgreSQL |
| `JWT_SECRET` | oui | — | Secret de signature des JWT, 32 caractères minimum |
| `LLM_MODEL` | oui | — | Modèle des agents, au format `fournisseur:modèle`, ou `test` |
| `ANTHROPIC_API_KEY` | si `LLM_MODEL` ≠ `test` | — | Clé Anthropic, lue par le SDK au premier appel |
| `WORLDNEWS_API_KEY` | non | — | Clé WorldNewsAPI ; sans elle, l'application fonctionne sans actualités |
| `JWT_EXPIRE_MINUTES` | non | `60` | Durée de validité d'un token |
| `FRONTEND_ORIGINS` | non | `http://localhost:3000` | Origines autorisées par CORS, séparées par des virgules |
| `PORT` | non | `8000` | Port d'écoute (Railway fournit le sien) |
| `SQL_ECHO` | non | `false` | Affiche les requêtes SQL dans les logs |
| `NEWS_COUNTRY` | non | `fr` | Pays des actualités du jour |
| `NEWS_LANGUAGE` | non | `fr` | Langue des actualités du jour |
| `TOP_NEWS_CACHE_TTL_SECONDS` | non | `3600` | Durée du cache des actualités du jour |
| `TOP_NEWS_FAILURE_TTL_SECONDS` | non | `300` | Durée pendant laquelle un échec est retenu avant de retenter |
| `MLFLOW_TRACKING_URI` | non | — | Active le traçage MLflow (développement local uniquement) |

Frontend : `NEXT_PUBLIC_API_URL` seulement.

### Travailler sans clé : `LLM_MODEL=test`

Avec `LLM_MODEL=test` (valeur de `.env.example`), les agents utilisent le `TestModel` de PydanticAI :
réponses factices, aucun appel réseau, aucune clé. L'agent de chat n'appelle alors aucun outil, pour
ne pas consommer le quota WorldNewsAPI. Pour essayer le vrai modèle, utilise
`LLM_MODEL=anthropic:claude-haiku-5-5` et renseigne `ANTHROPIC_API_KEY`.

Le plan gratuit de WorldNewsAPI offre 50 points par jour : garde les essais réels sobres (le coût
de chaque appel est journalisé).

## Tests

```bash
cd backend
uv run pytest            # 99 tests
uv run pytest tests/test_chats_authz.py -v     # un fichier
```

- Chaque test reçoit une base SQLite en mémoire neuve (`conftest.py`) : la base de développement
  n'est jamais touchée et aucun service Postgres n'est nécessaire.
- Aucun appel externe : WorldNewsAPI est simulée par `httpx.MockTransport` ; les agents utilisent
  `TestModel` et `FunctionModel`. `conftest.py` force `LLM_MODEL=test` et retire les clés, même si
  elles sont présentes dans le shell ou le `.env`.
- Les tests d'autorisation (`test_auth.py`, `test_chats_authz.py`, `test_reviews_authz.py`)
  vérifient notamment qu'un utilisateur reçoit 404 sur la discussion d'un autre, sur toutes les
  routes, et que le modèle n'est jamais appelé dans ce cas.

## Intégration continue

`.github/workflows/ci.yml` s'exécute à chaque push et pull request sur `main` : installation de
`uv`, `uv sync --frozen` (échoue si `uv.lock` n'est pas à jour), puis `uv run pytest -v`. Railway
est configuré pour n'attendre que la CI soit verte avant de redéployer (voir
[`deploiement.md`](deploiement.md)).

## Observabilité : traçage MLflow

Le traçage des agents est réservé au développement local ; MLflow est dans le groupe de
dépendances `observability`, absent de l'image de production.

```bash
cd backend
uv sync --group observability
uv run mlflow server --port 5001        # interface sur http://localhost:5001
# puis dans .env : MLFLOW_TRACKING_URI=http://localhost:5001
uv run --env-file .env src/main.py
```

Le banc d'essai `scripts/benchmark_reviews.py` (hors de l'image Docker) mesure le temps de génération
d'une revue selon la longueur de la discussion ; il n'appelle jamais WorldNewsAPI. Lance-le
d'abord avec `--dry-run` (estimation, aucun appel) :

```bash
cd backend
uv run --env-file .env python ../scripts/benchmark_reviews.py --dry-run
```

Chaque échange apparaît dans l'expérience `newsfoundry` avec ses étapes : appels au modèle, appel de
l'outil `search_news`, durées et tokens. Une trace contient les messages complets : ne pointe que vers
un serveur MLflow local. Les mesures obtenues avec cet outil sont dans
[`ameliorations.md`](ameliorations.md).
