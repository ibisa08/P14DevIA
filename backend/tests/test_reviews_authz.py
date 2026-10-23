"""Isolation des revues de presse : un utilisateur ne voit ni ne génère jamais chez un autre."""

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlmodel import Session, select

from agents.review_agent import review_agent
from models import PressReview

UNKNOWN_ID = 999_999


def must_not_be_called(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    raise AssertionError("le modèle ne doit pas être appelé pour le chat d'un autre utilisateur")


@pytest.fixture
def alice_chat_id(client: TestClient, alice: dict[str, str]) -> int:
    """Chat d'Alice avec un échange et une revue déjà générée (TestModel par défaut)."""
    chat_id = client.post("/chats", headers=alice).json()["id"]
    client.post(f"/chats/{chat_id}/messages", json={"content": "Bonjour"}, headers=alice)
    assert client.post(
        f"/chats/{chat_id}/reviews", json={"topic": "Sujet d'Alice"}, headers=alice
    ).status_code == 201
    return chat_id


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/chats/1/reviews"), ("get", "/reviews")],
)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer pas-un-jwt"}])
def test_routes_require_authentication(
    client: TestClient, method: str, path: str, headers: dict[str, str]
):
    response = client.request(method, path, json={"topic": "x"}, headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_other_user_list_never_contains_foreign_reviews(
    client: TestClient, alice: dict[str, str], alice_chat_id: int, bob: dict[str, str]
):
    assert len(client.get("/reviews", headers=alice).json()) == 1
    assert client.get("/reviews", headers=bob).json() == []


def test_other_user_cannot_generate_review_on_chat(
    client: TestClient, session: Session, alice_chat_id: int, bob: dict[str, str]
):
    with review_agent.override(model=FunctionModel(must_not_be_called)):
        response = client.post(
            f"/chats/{alice_chat_id}/reviews", json={"topic": "Intrusion"}, headers=bob
        )

    # Même 404 qu'un chat inexistant, et rien n'est créé
    assert response.status_code == 404
    assert response.json() == {"detail": "Discussion introuvable"}
    assert [review.topic for review in session.exec(select(PressReview)).all()] == ["Sujet d'Alice"]


def test_unknown_chat_returns_404(client: TestClient, alice: dict[str, str]):
    response = client.post(f"/chats/{UNKNOWN_ID}/reviews", json={"topic": "x"}, headers=alice)

    assert response.status_code == 404
    assert response.json() == {"detail": "Discussion introuvable"}
