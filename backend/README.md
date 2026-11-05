# NewsFoundry Backend

API FastAPI (Python 3.13, uv, SQLModel, PostgreSQL, PydanticAI).

Démarrage rapide, depuis ce dossier :

```bash
cp .env.example .env     # renseigner JWT_SECRET (openssl rand -hex 32)
uv sync
uv run --env-file .env src/main.py     # API sur http://localhost:8000, doc sur /docs
uv run pytest                          # tests
```

La base PostgreSQL se lance avec Docker : voir [`../docs/developpement.md`](../docs/developpement.md).

- Installation, variables d'environnement, tests, CI, MLflow : [`../docs/developpement.md`](../docs/developpement.md)
- Architecture et routes : [`../docs/architecture.md`](../docs/architecture.md)
- Déploiement sur Railway : [`../docs/deploiement.md`](../docs/deploiement.md)
- Choix techniques : [`../docs/decisions.md`](../docs/decisions.md)
