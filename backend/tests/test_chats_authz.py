"""Isolation des discussions : un utilisateur ne voit ni ne modifie jamais celles d'un autre."""

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents.chat_agent import chat_agent

NOT_FOUND = {"detail": "Discussion introuvable"}
UNKNOWN_ID = 999_999


def must_not_be_called(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    raise AssertionError("le modèle ne doit pas être appelé pour le chat d'un autre utilisateur")


@pytest.fixture
def alice_chat(client: TestClient, alice: dict[str, str]) -> dict:
    """Chat d'Alice contenant déjà un échange."""
    chat_id = client.post("/chats", headers=alice).json()["id"]
    client.post(f"/chats/{chat_id}/messages", json={"content": "Secret d'Alice"}, headers=alice)
    return client.get(f"/chats/{chat_id}", headers=alice).json()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/chats"),
        ("post", "/chats"),
        ("get", "/chats/1"),
        ("post", "/chats/1/messages"),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer pas-un-jwt"}])
def test_routes_require_authentication(
    client: TestClient, method: str, path: str, headers: dict[str, str]
):
    response = client.request(method, path, json={"content": "x"}, headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_other_user_list_never_contains_foreign_chats(
    client: TestClient, alice_chat: dict, bob: dict[str, str]
):
    assert client.get("/chats", headers=bob).json() == []

    bob_chat = client.post("/chats", headers=bob).json()

    assert [chat["id"] for chat in client.get("/chats", headers=bob).json()] == [bob_chat["id"]]


def test_other_user_cannot_read_chat(client: TestClient, alice_chat: dict, bob: dict[str, str]):
    response = client.get(f"/chats/{alice_chat['id']}", headers=bob)

    # Même réponse qu'un id inexistant : on ne révèle pas que le chat existe
    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert "Secret d'Alice" not in response.text


def test_other_user_cannot_write_in_chat(
    client: TestClient, alice: dict[str, str], alice_chat: dict, bob: dict[str, str]
):
    with chat_agent.override(model=FunctionModel(must_not_be_called)):
        response = client.post(
            f"/chats/{alice_chat['id']}/messages", json={"content": "Intrusion"}, headers=bob
        )

    assert response.status_code == 404
    assert response.json() == NOT_FOUND
    assert client.get(f"/chats/{alice_chat['id']}", headers=alice).json() == alice_chat


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", f"/chats/{UNKNOWN_ID}"), ("post", f"/chats/{UNKNOWN_ID}/messages")],
)
def test_unknown_chat_returns_404(
    client: TestClient, alice: dict[str, str], method: str, path: str
):
    response = client.request(method, path, json={"content": "x"}, headers=alice)

    assert response.status_code == 404
    assert response.json() == NOT_FOUND
