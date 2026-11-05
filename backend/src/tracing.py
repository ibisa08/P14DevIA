"""Traçage MLflow des agents PydanticAI, réservé au développement local.

Activé uniquement si MLFLOW_TRACKING_URI est défini. MLflow est une dépendance de dev : elle
est absente de l'image Docker (`uv sync --no-dev`) et de la production, où la variable n'est
jamais posée. Si elle l'est quand même sans que MLflow soit installé, on prévient dans les
logs et l'application démarre sans traçage : le traçage est un outil de mesure, jamais une
condition de démarrage.

Attention : une trace contient les prompts et les réponses complets (messages du journaliste
compris). Ne pointer que vers un serveur MLflow local.
"""

import logging
import os

from config import Settings

logger = logging.getLogger(__name__)

EXPERIMENT_NAME = "newsfoundry"


def setup_tracing(settings: Settings) -> bool:
    """Active le traçage MLflow si demandé. Renvoie True s'il est actif, sans jamais lever."""
    tracking_uri = settings.mlflow_tracking_uri
    if not tracking_uri:
        return False

    # Serveur éteint : échouer vite plutôt que bloquer le démarrage sur les tentatives
    # par défaut du client MLflow (posé avant l'import, que MLflow lit à la configuration)
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "5")

    try:
        import mlflow
    except ImportError:
        logger.warning(
            "MLFLOW_TRACKING_URI est défini mais MLflow n'est pas installé "
            "(dépendance de dev, absente de l'image Docker) : démarrage sans traçage."
        )
        return False

    try:
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(EXPERIMENT_NAME)
        # Instrumente tous les agents PydanticAI : runs, requêtes au modèle (tokens) et tools
        mlflow.pydantic_ai.autolog()
        # Sans instrumentation des agents, MLflow ne voit que le span global `Agent.run` : il
        # crée ses spans « requête au modèle » et « outil » en s'accrochant à la capacité
        # Instrumentation de PydanticAI, présente seulement quand l'agent est instrumenté.
        from pydantic_ai import Agent

        Agent.instrument_all()
    except Exception as exc:
        # Serveur injoignable, version incompatible… : le traçage ne doit pas bloquer l'app
        logger.warning("Traçage MLflow désactivé (%s : %s).", type(exc).__name__, exc)
        return False

    logger.info("Traçage MLflow actif (expérience « %s »).", EXPERIMENT_NAME)
    return True
