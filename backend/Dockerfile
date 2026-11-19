FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Contexte de build = backend/ (Root Directory Railway) : chemins relatifs à ce dossier.
COPY pyproject.toml uv.lock ./
# --no-dev : pytest/httpx ne servent qu'aux tests, inutile de les embarquer en prod.
# UV_LINK_MODE=copy : uv installe par défaut en liens durs depuis son cache, et LlamaIndex refuse
# de lire ses fichiers de données multi-liens (« Security Violation », CWE-59) : le RAG échouerait
# en production. --no-cache : le cache de uv ne reste pas dans la couche de l'image.
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-cache

# Modèle d'embeddings du RAG, téléchargé À LA CONSTRUCTION de l'image : sans cela, chaque
# redémarrage du conteneur le retélécharge (~220 Mo) dans un dossier temporaire, et la première
# revue dépasserait le délai du RAG. Doit rester identique à EMBEDDING_MODEL au runtime.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV FASTEMBED_CACHE_PATH=/app/.fastembed
RUN uv run --no-sync python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}')"

COPY src/ ./src/

# Indicatif : le port réel est lu depuis la variable PORT (config.py)
EXPOSE 8000

# --no-sync : sinon `uv run` réinstallerait le groupe dev au démarrage du conteneur
CMD ["uv", "run", "--no-sync", "python", "src/main.py"]
