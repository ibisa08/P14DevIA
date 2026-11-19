"""RAG dans le parcours API : revue avec sources, cas dégradés, isolation entre utilisateurs."""

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlmodel import Session, select

from agents.review_agent import review_agent
from main import app
from models import PressReview, User
from rag_fakes import FailingEmbedding, KeywordEmbedding
from services.rag import get_embed_model
from test_chat_articles import RETRAITES_TEXT, add_article, make_chat_with_message, user_by_email

REVIEW_OUTPUT = {"title": "Revue", "summary": "Synthèse.", "articles": []}
INFLATION_TEXT = "L'inflation alimentaire ralentit selon l'Insee. " * 8


class ReviewPrompts:
    """Modèle de revue factice qui enregistre le prompt reçu."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.prompts.append(str(messages[-1].parts[-1].content))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, REVIEW_OUTPUT)])


def use_embedding(model) -> None:
    app.dependency_overrides[get_embed_model] = lambda: model


def review(client: TestClient, headers: dict[str, str], chat_id: int, topic: str = "retraites"):
    prompts = ReviewPrompts()
    with review_agent.override(model=FunctionModel(prompts)):
        response = client.post(f"/chats/{chat_id}/reviews", json={"topic": topic}, headers=headers)
    return response, prompts.prompts


# --- Revue avec sources ------------------------------------------------------------------------


def test_review_receives_only_relevant_articles(
    client: TestClient, session: Session, alice: dict[str, str]
):
    chat_id = make_chat_with_message(client, alice)
    add_article(session, chat_id, "retraites", RETRAITES_TEXT)
    add_article(session, chat_id, "inflation", INFLATION_TEXT)
    model = KeywordEmbedding()
    use_embedding(model)

    response, [prompt] = review(client, alice, chat_id, "réforme des retraites")

    assert response.status_code == 201
    assert "<sources>" in prompt
    assert "https://retraites.fr/a" in prompt and "partenaires sociaux" in prompt
    # L'article hors sujet n'est pas dans le prompt (il n'y a pas non plus ses extraits)
    assert "inflation.fr" not in prompt and "Insee" not in prompt
    # Les deux articles ont été indexés, la requête est le sujet demandé
    assert len(model.texts) == 2 and model.queries == ["réforme des retraites"]
    # La revue indique qu'elle a utilisé le RAG, dans la réponse et dans la liste des revues
    assert response.json()["rag_used"] is True
    assert [item["rag_used"] for item in client.get("/reviews", headers=alice).json()] == [True]


@pytest.mark.parametrize(
    "embedding",
    [None, FailingEmbedding(), KeywordEmbedding()],
    ids=["sans-cle", "embeddings-en-panne", "aucun-article-pertinent"],
)
def test_degraded_cases_generate_review_as_before(
    client: TestClient, session: Session, alice: dict[str, str], embedding
):
    chat_id = make_chat_with_message(client, alice)
    add_article(session, chat_id, "retraites", RETRAITES_TEXT)
    use_embedding(embedding)

    # « grippe » : aucun article n'en parle ; les autres cas ne tentent même pas la recherche
    response, [prompt] = review(client, alice, chat_id, "vaccin grippe")

    assert response.status_code == 201
    assert "<sources>" not in prompt
    assert "vaccin grippe" in prompt and "Réponse." in prompt
    assert session.exec(select(PressReview)).one().title == "Revue"
    # Repli : la revue le dit, elle n'a pas utilisé le RAG
    assert response.json()["rag_used"] is False
    assert session.exec(select(PressReview)).one().rag_used is False


def test_review_without_any_article_never_calls_embeddings(
    client: TestClient, alice: dict[str, str]
):
    chat_id = make_chat_with_message(client, alice)
    model = KeywordEmbedding()
    use_embedding(model)

    response, [prompt] = review(client, alice, chat_id)

    assert response.status_code == 201 and "<sources>" not in prompt
    assert model.texts == [] and model.queries == []


def test_llm_failure_still_returns_502_with_sources(
    client: TestClient, session: Session, alice: dict[str, str]
):
    chat_id = make_chat_with_message(client, alice)
    add_article(session, chat_id, "retraites", RETRAITES_TEXT)
    use_embedding(KeywordEmbedding())

    def failing(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError("panne du modèle")

    with review_agent.override(model=FunctionModel(failing)):
        response = client.post(
            f"/chats/{chat_id}/reviews", json={"topic": "retraites"}, headers=alice
        )

    assert response.status_code == 502
    assert session.exec(select(PressReview)).all() == []


# --- Isolation entre utilisateurs --------------------------------------------------------------


def user_by_email(session: Session, email: str) -> User:
    return session.exec(select(User).where(User.email == email)).one()


def test_cannot_index_another_users_articles(
    client: TestClient, session: Session, alice: dict[str, str], bob: dict[str, str]
):
    alice_chat = make_chat_with_message(client, alice)
    add_article(session, alice_chat, "retraites", RETRAITES_TEXT)
    model = KeywordEmbedding()
    use_embedding(model)

    response, prompts = review(client, bob, alice_chat)

    # Même 404 qu'un chat inexistant, et rien n'a été indexé, appelé ni sauvegardé
    assert response.status_code == 404
    assert response.json() == {"detail": "Discussion introuvable"}
    assert prompts == []
    assert model.texts == [] and model.queries == []
    assert session.exec(select(PressReview)).all() == []


def test_own_review_never_includes_another_users_articles(
    client: TestClient, session: Session, alice: dict[str, str], bob: dict[str, str]
):
    alice_chat = make_chat_with_message(client, alice)
    add_article(session, alice_chat, "retraites", RETRAITES_TEXT)
    bob_chat = make_chat_with_message(client, bob)
    model = KeywordEmbedding()
    use_embedding(model)

    response, [prompt] = review(client, bob, bob_chat, "réforme des retraites")

    assert response.status_code == 201
    # Bob n'a aucun article : rien d'Alice n'est indexé ni cité, malgré un sujet identique
    assert model.texts == []
    assert "<sources>" not in prompt and "retraites.fr" not in prompt


