from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from sqlmodel import Session, select

from agents.chat_agent import chat_agent
from agents.review_agent import review_agent
from models import PressReview

REVIEW_OUTPUT = {
    "title": "Revue de presse : l'IA dans la santé",
    "summary": "Les usages de l'IA progressent à l'hôpital.",
    "articles": [
        {
            "title": "Diagnostic assisté",
            "summary": "Des outils d'aide au diagnostic en test.",
            "source": "Le Monde",
            "url": "https://example.com/article",
        },
        {"title": "Formation des soignants", "summary": "Un enjeu majeur.", "source": None, "url": None},
    ],
}


@pytest.fixture
def chat_id(client: TestClient, alice: dict[str, str]) -> int:
    """Chat d'Alice contenant un échange."""
    chat_id = client.post("/chats", headers=alice).json()["id"]
    with chat_agent.override(model=TestModel(custom_output_text="L'IA aide au diagnostic.")):
        client.post(
            f"/chats/{chat_id}/messages", json={"content": "Parle-moi de l'IA en santé"}, headers=alice
        )
    return chat_id


def generate(client: TestClient, headers: dict[str, str], chat_id: int, topic: str = "IA et santé"):
    return client.post(f"/chats/{chat_id}/reviews", json={"topic": topic}, headers=headers)


def test_generate_review_with_structured_output(
    client: TestClient, session: Session, alice: dict[str, str], chat_id: int
):
    with review_agent.override(model=TestModel(custom_output_args=REVIEW_OUTPUT)):
        response = generate(client, alice, chat_id)

    assert response.status_code == 201
    body = response.json()
    assert body["chat_id"] == chat_id
    assert body["topic"] == "IA et santé"
    assert body["title"] == REVIEW_OUTPUT["title"]
    assert body["content"] == REVIEW_OUTPUT
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None

    saved = session.exec(select(PressReview)).one()
    assert (saved.id, saved.chat_id, saved.topic) == (body["id"], chat_id, "IA et santé")
    assert saved.content == REVIEW_OUTPUT


def test_review_agent_receives_topic_and_chat_history(
    client: TestClient, alice: dict[str, str], chat_id: int
):
    prompts: list[str] = []

    def recording_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts.append(str(messages[-1].parts[-1].content))
        # Sortie structurée : le modèle « appelle » l'outil de sortie avec les données attendues
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, REVIEW_OUTPUT)])

    with review_agent.override(model=FunctionModel(recording_model)):
        generate(client, alice, chat_id, topic="Santé numérique")

    [prompt] = prompts
    assert "Santé numérique" in prompt
    assert "Parle-moi de l'IA en santé" in prompt
    assert "L'IA aide au diagnostic." in prompt


def test_unsafe_article_url_is_dropped(client: TestClient, alice: dict[str, str], chat_id: int):
    output = {**REVIEW_OUTPUT, "articles": [{**REVIEW_OUTPUT["articles"][0], "url": "javascript:alert(1)"}]}

    with review_agent.override(model=TestModel(custom_output_args=output)):
        response = generate(client, alice, chat_id)

    assert response.json()["content"]["articles"][0]["url"] is None


def test_list_reviews_newest_first(client: TestClient, alice: dict[str, str], chat_id: int):
    with review_agent.override(model=TestModel(custom_output_args=REVIEW_OUTPUT)):
        first = generate(client, alice, chat_id, topic="Premier sujet").json()
        second = generate(client, alice, chat_id, topic="Second sujet").json()

    response = client.get("/reviews", headers=alice)

    assert response.status_code == 200
    assert [review["id"] for review in response.json()] == [second["id"], first["id"]]


def test_empty_topic_returns_422(client: TestClient, alice: dict[str, str], chat_id: int):
    for topic in ["", "   ", "x" * 201]:
        assert generate(client, alice, chat_id, topic=topic).status_code == 422


def test_chat_without_messages_returns_400(
    client: TestClient, session: Session, alice: dict[str, str]
):
    empty_chat_id = client.post("/chats", headers=alice).json()["id"]

    response = generate(client, alice, empty_chat_id)

    assert response.status_code == 400
    assert session.exec(select(PressReview)).all() == []


def test_model_error_returns_502_and_saves_nothing(
    client: TestClient, session: Session, alice: dict[str, str], chat_id: int
):
    def failing_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError("fournisseur indisponible")

    with review_agent.override(model=FunctionModel(failing_model)):
        response = generate(client, alice, chat_id)

    assert response.status_code == 502
    assert response.json() == {"detail": "L'assistant n'a pas pu répondre, réessaie."}
    assert session.exec(select(PressReview)).all() == []


def test_invalid_model_output_returns_502(
    client: TestClient, session: Session, alice: dict[str, str], chat_id: int
):
    # Un modèle qui ne respecte jamais le format structuré épuise ses tentatives
    def text_only_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("Pas de JSON ici")])

    with review_agent.override(model=FunctionModel(text_only_model)):
        response = generate(client, alice, chat_id)

    assert response.status_code == 502
    assert session.exec(select(PressReview)).all() == []
