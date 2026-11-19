"""Recherche sémantique (RAG) dans les articles d'une discussion, avec LlamaIndex.

À la génération d'une revue de presse, on indexe en mémoire le texte des articles trouvés par
`search_news`, on retrouve les extraits qui parlent du sujet demandé et on ne garde que les
articles pertinents. L'index n'est jamais persisté : il est reconstruit à chaque revue puis jeté.

Le module ne lève jamais d'exception à l'appelant : RAG désactivé, modèle indisponible, délai dépassé,
aucun article pertinent… tous ces cas renvoient une liste vide et la revue est alors générée à
partir de la discussion seule, comme avant l'ajout du RAG.
"""

import asyncio
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import SentenceSplitter
from pydantic import PrivateAttr

from config import get_settings

logger = logging.getLogger(__name__)

# Découpage en extraits, compté en mots (voir `_words`). Le modèle par défaut (MiniLM multilingue)
# tronque à 128 tokens : en français, ~1,5 token par mot, donc 70 mots ≈ 105 tokens, sans perte.
# À réduire si on choisit un modèle encore plus court, à augmenter pour un modèle à 512 tokens.
CHUNK_SIZE_WORDS = 70
CHUNK_OVERLAP_WORDS = 10
# Extraits gardés au maximum par article dans le prompt de l'agent de revue
MAX_EXCERPTS_PER_ARTICLE = 3


class EmbeddingModelUnavailable(Exception):
    """Le modèle d'embeddings n'a pas pu être chargé (téléchargement, fichier, mémoire)."""


class FastEmbedEmbedding(BaseEmbedding):
    """Embeddings locaux avec fastembed (ONNX, sans PyTorch) derrière l'interface LlamaIndex.

    Le paquet `llama-index-embeddings-fastembed` n'est pas utilisé : il limite sa dépendance à
    fastembed à Python < 3.13. Le modèle est chargé à la PREMIÈRE vectorisation, jamais à
    l'import de l'app ni à la construction : une instance inutilisée ne coûte aucune RAM.
    """

    _model: Any = PrivateAttr(default=None)
    _load_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def __init__(self, model_name: str) -> None:
        super().__init__(model_name=model_name)

    def _loaded_model(self) -> Any:
        # Verrou : deux revues simultanées ne chargent pas le modèle deux fois (~800 Mo chacune)
        with self._load_lock:
            if self._model is None:
                # Import ici : fastembed (et onnxruntime) ne sont chargés que si le RAG sert
                from fastembed import TextEmbedding

                logger.info("Chargement du modèle d'embeddings %s", self.model_name)
                try:
                    self._model = TextEmbedding(self.model_name)
                except Exception as exc:
                    # Nom inconnu, téléchargement impossible, mémoire insuffisante… : un seul type
                    # d'erreur pour l'appelant, qui sait ainsi que c'est le modèle et non l'index
                    raise EmbeddingModelUnavailable(f"{type(exc).__name__}: {exc}") from exc
            return self._model

    def _get_query_embedding(self, query: str) -> list[float]:
        return next(iter(self._loaded_model().query_embed([query]))).tolist()

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embeddings([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._loaded_model().passage_embed(texts)]

    # Variantes asynchrones exigées par LlamaIndex : le calcul est fait dans un thread, voir
    # `select_relevant_articles` qui exécute déjà tout le flux hors de la boucle d'événements.
    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await asyncio.to_thread(self._get_query_embedding, query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._get_text_embedding, text)


@lru_cache
def _shared_embed_model(model_name: str) -> FastEmbedEmbedding:
    # Une seule instance par processus : le modèle est chargé une fois puis réutilisé
    return FastEmbedEmbedding(model_name)


def get_embed_model() -> BaseEmbedding | None:
    """Modèle d'embeddings, ou None si RAG_ENABLED est faux (mode dégradé, rien n'est chargé)."""
    settings = get_settings()
    if not settings.rag_enabled:
        return None
    return _shared_embed_model(settings.embedding_model)


@dataclass(frozen=True)
class ArticleText:
    """Article d'une discussion (ligne de ChatArticle) à indexer."""

    url: str
    title: str
    text: str


@dataclass(frozen=True)
class RelevantArticle:
    """Article jugé pertinent pour le sujet, avec ses meilleurs extraits (du plus au moins proche)."""

    url: str
    title: str
    excerpts: list[str]
    score: float


def _words(text: str) -> list[str]:
    # Découpage par mots plutôt que par tokens du modèle : le tokenizer par défaut de LlamaIndex
    # (tiktoken) télécharge son vocabulaire au premier usage, ce qui échouerait hors ligne
    return text.split()


def _retrieve(
    topic: str,
    articles: list[ArticleText],
    embed_model: BaseEmbedding,
    min_score: float,
    top_k: int,
) -> list[RelevantArticle]:
    """Indexe les articles en mémoire, récupère les extraits proches du sujet, filtre au seuil."""
    # L'URL sert d'identifiant du document : on retrouve l'article depuis un extrait sans la
    # mettre dans le texte vectorisé. Le titre, lui, aide la recherche.
    documents = [
        Document(text=article.text, doc_id=article.url, metadata={"title": article.title})
        for article in articles
    ]
    splitter = SentenceSplitter(
        chunk_size=CHUNK_SIZE_WORDS, chunk_overlap=CHUNK_OVERLAP_WORDS, tokenizer=_words
    )
    # Index par défaut de LlamaIndex : en mémoire, non persisté
    index = VectorStoreIndex.from_documents(
        documents, embed_model=embed_model, transformations=[splitter]
    )
    nodes = index.as_retriever(similarity_top_k=top_k).retrieve(topic)

    titles = {article.url: article.title for article in articles}
    excerpts: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for node in nodes:
        score = node.score or 0.0
        if score >= min_score and node.node.ref_doc_id in titles:
            excerpts[node.node.ref_doc_id].append((score, node.node.get_content().strip()))

    relevant = []
    for url, scored in excerpts.items():
        scored.sort(key=lambda item: item[0], reverse=True)
        relevant.append(
            RelevantArticle(
                url=url,
                title=titles[url],
                excerpts=[text for _, text in scored[:MAX_EXCERPTS_PER_ARTICLE]],
                score=scored[0][0],
            )
        )
    return sorted(relevant, key=lambda article: article.score, reverse=True)


async def select_relevant_articles(
    topic: str,
    articles: list[ArticleText],
    embed_model: BaseEmbedding | None,
    *,
    min_score: float | None = None,
    top_k: int | None = None,
    timeout_seconds: float | None = None,
) -> list[RelevantArticle]:
    """Articles pertinents pour `topic`, les plus proches d'abord ; liste vide dans tous les cas dégradés.

    Les paramètres non fournis viennent de la configuration (RAG_MIN_SCORE, RAG_TOP_K,
    RAG_TIMEOUT_SECONDS).
    """
    if embed_model is None:
        logger.info("RAG désactivé (RAG_ENABLED=false), revue générée sans recherche")
        return []
    if not articles:
        return []

    settings = get_settings()
    min_score = settings.rag_min_score if min_score is None else min_score
    top_k = settings.rag_top_k if top_k is None else top_k
    timeout_seconds = settings.rag_timeout_seconds if timeout_seconds is None else timeout_seconds

    try:
        # Appels réseau synchrones : dans un thread, pour ne pas bloquer les autres requêtes
        relevant = await asyncio.wait_for(
            asyncio.to_thread(_retrieve, topic, articles, embed_model, min_score, top_k),
            timeout=timeout_seconds,
        )
    # Chaque repli journalise un WARNING avec sa cause (sans texte d'article, sujet ni clé)
    except TimeoutError:
        logger.warning("RAG en repli [timeout] : délai de %s s dépassé", timeout_seconds)
        return []
    except EmbeddingModelUnavailable as exc:
        logger.warning("RAG en repli [modèle indisponible] : %s", exc)
        return []
    except Exception as exc:
        logger.warning("RAG en repli [erreur d'index] : %s : %s", type(exc).__name__, exc)
        return []

    logger.info("RAG : %s article(s) pertinent(s) sur %s", len(relevant), len(articles))
    return relevant
