FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Contexte de build = backend/ (Root Directory Railway) : chemins relatifs à ce dossier.
COPY pyproject.toml uv.lock ./
# --no-dev : pytest/httpx ne servent qu'aux tests, inutile de les embarquer en prod
RUN uv sync --frozen --no-dev

COPY src/ ./src/

# Indicatif : le port réel est lu depuis la variable PORT (config.py)
EXPOSE 8000

# --no-sync : sinon `uv run` réinstallerait le groupe dev au démarrage du conteneur
CMD ["uv", "run", "--no-sync", "python", "src/main.py"]
