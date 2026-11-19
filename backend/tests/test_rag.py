"""Recherche sémantique des articles (LlamaIndex) : aucun appel réseau, faux embeddings."""

import asyncio
import logging
import time

import pytest
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.embeddings import MockEmbedding
from pydantic import PrivateAttr

from config import get_settings
from rag_fakes import FailingEmbedding, KeywordEmbedding
from services.rag import (
    MAX_EXCERPTS_PER_ARTICLE,
    ArticleText,
    FastEmbedEmbedding,
    _shared_embed_model,
    get_embed_model,
    select_relevant_articles,
)

RETRAITES = ArticleText(
    "https://a.fr/retraites", "Retraites : le projet", "La réforme des retraites divise. " * 5
)
INFLATION = ArticleText(
    "https://b.fr/inflation", "Prix alimentaires", "L'inflation alimentaire ralentit. " * 5
)
GAZA = ArticleText("https://c.fr/gaza", "Négociations", "Cessez-le-feu à Gaza, pourparlers. " * 5)


def select(topic: str, articles: list[ArticleText], model: BaseEmbedding | None, **kwargs):
    kwargs.setdefault("min_score", 0.3)
    return asyncio.run(select_relevant_articles(topic, articles, model, **kwargs))


# --- Sélection ------------------------------------------------------------------------


def test_keeps_only_relevant_articles_with_their_excerpts():
    model = KeywordEmbedding()

    result = select("réforme des retraites", [INFLATION, RETRAITES, GAZA], model)

    assert [article.url for article in result] == [RETRAITES.url]
    assert result[0].title == RETRAITES.title
    assert "retraites" in result[0].excerpts[0]
    # La requête est vectorisée comme une requête, les articles comme des textes
    assert model.queries == ["réforme des retraites"]
    # L'URL n'est pas dans le texte vectorisé (elle sert seulement d'identifiant)
    assert not any("a.fr" in text for text in model.texts)


def test_articles_sorted_by_relevance_and_excerpts_capped():
    long_on_topic = ArticleText(
        "https://d.fr/long", "Dossier retraites", " ".join(["retraites"] * 600)
    )
    mixed = ArticleText("https://e.fr/mixte", "Mixte", "retraites " + "météo " * 400)

    result = select("retraites", [mixed, long_on_topic], KeywordEmbedding())

    assert result[0].url == long_on_topic.url
    assert len(result[0].excerpts) == MAX_EXCERPTS_PER_ARTICLE
    assert result[0].score >= result[-1].score


def test_no_relevant_article_returns_empty():
    assert select("vaccin grippe", [RETRAITES, INFLATION], KeywordEmbedding(), min_score=0.5) == []


def test_mock_embedding_runs_offline():
    # MockEmbedding de LlamaIndex : vecteurs constants, tout est « proche » : on vérifie surtout
    # que l'indexation et la récupération tournent de bout en bout sans réseau ni clé
    result = select("n'importe quoi", [RETRAITES, GAZA], MockEmbedding(embed_dim=8), min_score=0.5)

    assert {article.url for article in result} == {RETRAITES.url, GAZA.url}


# --- Cas dégradés : jamais d'exception -------------------------------------------------


def test_without_embedding_model_returns_empty(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)

    assert select("retraites", [RETRAITES], None) == []
    assert "RAG_ENABLED=false" in caplog.text


def test_without_articles_returns_empty():
    model = KeywordEmbedding()

    assert select("retraites", [], model) == []
    assert model.queries == []


def test_embedding_failure_returns_empty_and_logs_no_content(caplog: pytest.LogCaptureFixture):
    assert select("retraites", [RETRAITES], FailingEmbedding()) == []

    assert "panne simulée" in caplog.text
    assert [(r.levelname, "[erreur d'index]" in r.message) for r in caplog.records if "repli" in r.message] == [
        ("WARNING", True)
    ]
    # Ni le texte des articles ni le sujet dans les logs
    assert "divise" not in caplog.text and "réforme" not in caplog.text


class SlowEmbedding(KeywordEmbedding):
    _delay: float = PrivateAttr(default=0.3)

    def _get_text_embedding(self, text: str) -> list[float]:
        time.sleep(self._delay)
        return super()._get_text_embedding(text)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        time.sleep(self._delay)
        return [super(SlowEmbedding, self)._vector(text) for text in texts]


def test_timeout_returns_empty(caplog: pytest.LogCaptureFixture):
    assert select("retraites", [RETRAITES], SlowEmbedding(), timeout_seconds=0.05) == []
    assert [r.levelname for r in caplog.records if "repli" in r.message] == ["WARNING"]
    assert "[timeout]" in caplog.text


# --- Modèle local fastembed (chargement à la demande, rien n'est téléchargé) --------------


class FakeNumpyVector(list):
    """Imite un vecteur numpy : fastembed renvoie des tableaux avec `.tolist()`."""

    def tolist(self) -> list[float]:
        return list(self)


class FakeTextEmbedding:
    """Remplace `fastembed.TextEmbedding` : compte les chargements, aucun téléchargement."""

    loaded: list[str] = []

    def __init__(self, model_name: str) -> None:
        FakeTextEmbedding.loaded.append(model_name)

    def query_embed(self, texts: list[str]):
        return (FakeNumpyVector([1.0, 0.0]) for _ in texts)

    def passage_embed(self, texts: list[str]):
        return (FakeNumpyVector([0.0, 1.0]) for _ in texts)


@pytest.fixture
def fake_fastembed(monkeypatch: pytest.MonkeyPatch):
    import fastembed

    FakeTextEmbedding.loaded = []
    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)
    _shared_embed_model.cache_clear()
    yield FakeTextEmbedding
    _shared_embed_model.cache_clear()


def test_fastembed_model_is_loaded_on_demand_and_only_once(fake_fastembed):
    model = FastEmbedEmbedding("modele-multilingue")
    # Construire l'instance ne charge rien
    assert fake_fastembed.loaded == []

    assert model.get_query_embedding("question") == [1.0, 0.0]
    assert model.get_text_embedding_batch(["un", "deux"]) == [[0.0, 1.0], [0.0, 1.0]]
    assert model.get_text_embedding("trois") == [0.0, 1.0]

    assert fake_fastembed.loaded == ["modele-multilingue"]


def test_fastembed_runs_through_the_llamaindex_pipeline(fake_fastembed):
    model = FastEmbedEmbedding("modele-multilingue")

    # Vecteurs orthogonaux : similarité nulle, aucun article retenu, mais le flux complet tourne
    assert select("retraites", [RETRAITES], model, min_score=0.5) == []
    assert fake_fastembed.loaded == ["modele-multilingue"]


def test_unavailable_model_logs_a_warning_with_the_cause(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    import fastembed

    def broken(model_name: str):
        raise OSError("téléchargement impossible")

    monkeypatch.setattr(fastembed, "TextEmbedding", broken)

    assert select("retraites", [RETRAITES], FastEmbedEmbedding("modele-multilingue")) == []

    repli = [r for r in caplog.records if "repli" in r.message]
    assert [r.levelname for r in repli] == ["WARNING"]
    assert "[modèle indisponible]" in repli[0].message and "téléchargement impossible" in repli[0].message
    # Ni le texte des articles ni le sujet dans le log
    assert "divise" not in caplog.text and "réforme" not in caplog.text


def test_rag_disabled_by_default_loads_nothing(fake_fastembed):
    get_settings.cache_clear()
    try:
        assert get_settings().rag_enabled is False
        assert get_embed_model() is None
        assert fake_fastembed.loaded == []
    finally:
        get_settings.cache_clear()


def test_rag_enabled_builds_one_shared_lazy_model(monkeypatch: pytest.MonkeyPatch, fake_fastembed):
    monkeypatch.setenv("RAG_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_MODEL", "autre/modele-multilingue")
    get_settings.cache_clear()
    try:
        model = get_embed_model()

        assert isinstance(model, FastEmbedEmbedding) and model.model_name == "autre/modele-multilingue"
        # Même instance d'une requête à l'autre : le modèle n'est chargé qu'une fois par processus
        assert get_embed_model() is model
        # get_embed_model ne charge pas le modèle : seul le premier calcul de vecteur le fait
        assert fake_fastembed.loaded == []
    finally:
        monkeypatch.delenv("RAG_ENABLED")
        monkeypatch.delenv("EMBEDDING_MODEL")
        get_settings.cache_clear()


def test_importing_the_app_does_not_load_fastembed():
    # Sous-processus : le test principal a déjà pu importer fastembed (fixture fake_fastembed)
    import subprocess
    import sys

    code = "import sys, main; sys.exit(1 if any(m.startswith('fastembed') or m.startswith('onnxruntime') for m in sys.modules) else 0)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd="src",
        env={"PATH": "", "JWT_SECRET": "x" * 40, "DATABASE_URL": "sqlite://", "LLM_MODEL": "test"},
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()[-500:]
