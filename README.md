# NewsFoundry

Outil de revue de presse assisté par IA pour journalistes pigistes : un assistant conversationnel
qui s'appuie sur l'actualité du jour (WorldNewsAPI) et sait chercher des articles, puis une
génération de revues de presse structurées, sauvegardées et consultables.

## Application déployée

| | URL |
|---|---|
| Frontend (Vercel) | https://p14-dev-ia-olive.vercel.app |
| API (Railway) | https://p14devia-production-67a4.up.railway.app |
| Documentation de l'API (Swagger) | https://p14devia-production-67a4.up.railway.app/docs |

**Compte de test** (il n'y a pas d'inscription) : `test@test.com` / `test`

### Disponibilité

Le frontend reste en ligne en permanence. Le backend (et sa base Postgres) est actif pendant les
périodes d'évaluation seulement : hors de ces périodes, la connexion affichera « Le service est
momentanément indisponible ». Pour le remettre en ligne, suivre la procédure « Redéployer » de
[`docs/deploiement.md`](docs/deploiement.md#redéployer).

## Besoins fonctionnels

- L'utilisateur peut se connecter.
- L’utilisateur peut voir la liste de ses discussions passées.
- L’utilisateur peut démarrer une nouvelle discussion ou reprendre une ancienne discussion.
- Un utilisateur n’est pas autorisé à accéder aux discussions d’un autre utilisateur.
- Le LLM répond aux messages envoyés par l’utilisateur.
- L'utilisateur peut faire générer une revue de presse à partir d'une discussion.
- L'application doit afficher des messages d'erreur à l'utilisateur final en cas d'erreur.

## Choix technologiques

### Frontend

**Next.js**

### Backend

- **Python** pour bénéficier de son écosystème de librairies IA
- **FastAPI** pour le développement de l'API
- Connection avec des **JWT**
- **SQLModel** comme ORM : fait pour bien marcher avec FastAPI.
  - Branché à une base de données **PostgreSQL**
- **PydanticAI** comme client qui s'intégrera aussi bien avec les autres outils de la stack backend
- Attention à la **sécurité des données**. On ne veut pas qu’un utilisateur puisse accéder aux chats d’un autre utilisateur ou les modifier.
  - Le produit aura rapidement beaucoup d’utilisateurs professionnels il est donc crucial de garantir le fonctionnement correct de cette fonctionnalité par l'**implémentation de tests automatisés qui s'exécutent par une Github Action**.
- Pour les sources de news, on utilisera l’API [**WorldNewsAPI**](https://worldnewsapi.com/).
- Pour déployer on mettra le frontend sur **Vercel** et le backend sur **Railway**.

Les justifications détaillées de chaque choix sont dans [`docs/decisions.md`](docs/decisions.md).

## Démarrage rapide

Prérequis : Docker, Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js 22.19.

```bash
# 1. Base de données (port 5434 si 5432 est déjà pris, voir docs/developpement.md)
docker run --name newsfoundry_db -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=newsfoundry -p 5432:5432 -d postgres:17

# 2. API sur http://localhost:8000
cd backend
cp .env.example .env        # puis renseigner JWT_SECRET (openssl rand -hex 32)
uv sync
uv run --env-file .env src/main.py

# 3. Frontend sur http://localhost:3000 (dans un autre terminal)
cd frontend
npm install
npm run dev
```

Avec `LLM_MODEL=test` (valeur de `.env.example`), l'assistant répond par des textes factices : ni clé
Anthropic ni clé WorldNewsAPI ne sont nécessaires pour essayer l'interface.

## Tests

```bash
cd backend && uv run pytest
```

99 tests, sur SQLite en mémoire, sans appel réseau (aucune clé requise). Ils incluent les tests
d'autorisation : un utilisateur ne peut ni lire, ni écrire, ni générer une revue sur la discussion
d'un autre. La CI GitHub Actions (`.github/workflows/ci.yml`) les lance à chaque push et pull
request sur `main`.

## Documentation

| Document | Contenu |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Schéma d'ensemble, arborescences, modèle de données, routes, déroulé d'un message, authentification et gestion d'erreurs |
| [`docs/developpement.md`](docs/developpement.md) | Installation locale, variables d'environnement, tests, CI, observabilité (MLflow) |
| [`docs/deploiement.md`](docs/deploiement.md) | Déploiement Vercel et Railway, variables de production, procédure pour redéployer |
| [`docs/decisions.md`](docs/decisions.md) | Choix techniques regroupés par thème, avec leur justification |
| [`docs/ameliorations.md`](docs/ameliorations.md) | Pistes d'amélioration de la partie IA, chacune avec une mesure, une implémentation et un objectif |

Les README de [`backend/`](backend/README.md) et [`frontend/`](frontend/README.md) renvoient vers ces documents.
