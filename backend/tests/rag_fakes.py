"""Faux embeddings pour les tests du RAG : aucun appel réseau, résultats déterministes."""

import re

from llama_index.core.base.embeddings.base import BaseEmbedding
from pydantic import PrivateAttr

# Un axe par thème : deux textes sont proches s'ils parlent du même thème
THEMES = ["retraites", "inflation", "gaza", "grippe", "météo"]


class KeywordEmbedding(BaseEmbedding):
    """Vecteur = nombre d'occurrences de chaque thème : similarité cosinus > 0 ssi thème commun.

    Enregistre tout ce qu'on lui envoie, pour vérifier quels textes ont été indexés.
    """

    _texts: list[str] = PrivateAttr(default_factory=list)
    _queries: list[str] = PrivateAttr(default_factory=list)

    @property
    def texts(self) -> list[str]:
        return self._texts

    @property
    def queries(self) -> list[str]:
        return self._queries

    @staticmethod
    def _vector(text: str) -> list[float]:
        words = re.findall(r"\w+", text.lower())
        vector = [float(sum(word.startswith(theme) for word in words)) for theme in THEMES]
        # Jamais un vecteur nul (cosinus indéfini) : composante constante très faible
        return [*vector, 0.001]

    def _get_query_embedding(self, query: str) -> list[float]:
        self._queries.append(query)
        return self._vector(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        self._texts.append(text)
        return self._vector(text)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)


class FailingEmbedding(KeywordEmbedding):
    """Embeddings en panne (clé refusée, quota, réseau…)."""

    def _get_text_embedding(self, text: str) -> list[float]:
        raise RuntimeError("panne simulée")

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("panne simulée")
