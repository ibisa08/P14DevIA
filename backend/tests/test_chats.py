import re
from datetime import datetime

from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from sqlmodel import Session

from agents.chat_agent import NEWSFOUNDRY_SYSTEM_PROMPT, chat_agent
from models import Chat


def create_chat(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/chats", headers=headers)
    assert response.status_code == 201
    return response.json()


def user_prompts(messages: list[ModelMessage]) -> list[str]:
    return [
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]


def failing_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    raise RuntimeError("fournisseur indisponible")


# --- Création -------------------------------------------------------------------


def test_create_chat(client: TestClient, session: Session, alice: dict[str, str]):
    body = create_chat(client, alice)

    assert re.fullmatch(r"Discussion du \d{2}/\d{2}/\d{4}", body["title"])
    assert body["messages"] == []
    # Dates avec fuseau explicite, sinon le navigateur les lirait en heure locale
    assert datetime.fromisoformat(body["created_at"]).tzinfo is not None
    # Prompt système figé dans le chat dès sa création
    assert session.get(Chat, body["id"]).system_prompt == NEWSFOUNDRY_SYSTEM_PROMPT


# --- Envoi de messages -------------------------------------------------------------


def test_send_message_returns_simplified_history(client: TestClient, alice: dict[str, str]):
    chat = create_chat(client, alice)

    with chat_agent.override(model=TestModel(custom_output_text="Bonjour, que cherches-tu ?")):
        response = client.post(
            f"/chats/{chat['id']}/messages", json={"content": "  Salut  "}, headers=alice
        )

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Salut"),
        ("assistant", "Bonjour, que cherches-tu ?"),
    ]
    # Jamais le format brut PydanticAI (parts, kind, instructions...)
    assert all(set(message) == {"role", "content", "created_at"} for message in messages)


def test_history_is_persisted_and_sent_back_to_the_model(client: TestClient, alice: dict[str, str]):
    chat = create_chat(client, alice)
    prompts_seen: list[list[str]] = []

    def recording_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompts_seen.append(user_prompts(messages))
        return ModelResponse(parts=[TextPart(f"Réponse {len(prompts_seen)}")])

    with chat_agent.override(model=FunctionModel(recording_model)):
        client.post(f"/chats/{chat['id']}/messages", json={"content": "Premier"}, headers=alice)
        client.post(f"/chats/{chat['id']}/messages", json={"content": "Second"}, headers=alice)

    # Le 2e appel au modèle reçoit le 1er échange
    assert prompts_seen == [["Premier"], ["Premier", "Second"]]

    reloaded = client.get(f"/chats/{chat['id']}", headers=alice).json()
    assert [m["content"] for m in reloaded["messages"]] == [
        "Premier",
        "Réponse 1",
        "Second",
        "Réponse 2",
    ]


def test_model_receives_the_prompt_frozen_in_the_chat(
    client: TestClient, session: Session, alice: dict[str, str]
):
    chat_id = create_chat(client, alice)["id"]
    chat = session.get(Chat, chat_id)
    chat.system_prompt = "Prompt figé de ce chat"
    session.add(chat)
    session.commit()
    instructions_seen: list[str | None] = []

    def recording_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        instructions_seen.append(info.instructions)
        return ModelResponse(parts=[TextPart("ok")])

    with chat_agent.override(model=FunctionModel(recording_model)):
        client.post(f"/chats/{chat_id}/messages", json={"content": "Question"}, headers=alice)

    assert instructions_seen == ["Prompt figé de ce chat"]


def test_chats_are_sorted_by_last_activity(client: TestClient, alice: dict[str, str]):
    older = create_chat(client, alice)
    newer = create_chat(client, alice)

    # Avant toute activité : le plus récemment créé en premier
    ids = [chat["id"] for chat in client.get("/chats", headers=alice).json()]
    assert ids == [newer["id"], older["id"]]

    client.post(f"/chats/{older['id']}/messages", json={"content": "Relance"}, headers=alice)

    ids = [chat["id"] for chat in client.get("/chats", headers=alice).json()]
    assert ids == [older["id"], newer["id"]]


def test_list_chats_returns_summaries_only(client: TestClient, alice: dict[str, str]):
    create_chat(client, alice)

    [summary] = client.get("/chats", headers=alice).json()

    assert set(summary) == {"id", "title", "created_at", "updated_at"}


# --- Erreurs -----------------------------------------------------------------------


def test_empty_or_too_long_message_returns_422(client: TestClient, alice: dict[str, str]):
    chat = create_chat(client, alice)

    for content in ["", "   ", "x" * 4001]:
        response = client.post(
            f"/chats/{chat['id']}/messages", json={"content": content}, headers=alice
        )
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)

    assert client.get(f"/chats/{chat['id']}", headers=alice).json()["messages"] == []


def test_model_error_returns_502_and_keeps_history(client: TestClient, alice: dict[str, str]):
    chat = create_chat(client, alice)
    client.post(f"/chats/{chat['id']}/messages", json={"content": "Premier"}, headers=alice)
    before = client.get(f"/chats/{chat['id']}", headers=alice).json()

    with chat_agent.override(model=FunctionModel(failing_model)):
        response = client.post(
            f"/chats/{chat['id']}/messages", json={"content": "Second"}, headers=alice
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "L'assistant n'a pas pu répondre, réessaie."}
    # Ni le message ni la date d'activité ne sont modifiés
    assert client.get(f"/chats/{chat['id']}", headers=alice).json() == before
