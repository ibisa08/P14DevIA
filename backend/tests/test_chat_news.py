"""Étape 5 : actualités du jour injectées et figées dans le prompt système des discussions."""

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlmodel import Session

from agents.chat_agent import NEWSFOUNDRY_SYSTEM_PROMPT, chat_agent
from models import Chat
from news_fakes import FakeApi, article, make_client, ok, top_news_payload
from services.news_api import NewsClient

InstallNewsClient = Callable[[NewsClient], None]


def create_chat(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post("/chats", headers=headers)
    assert response.status_code == 201
    return response.json()


def stored_prompt(session: Session, chat_id: int) -> str:
    session.expire_all()
    return session.get(Chat, chat_id).system_prompt


def test_top_news_injected_in_system_prompt(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    api = FakeApi(ok(top_news_payload([[article(1)], [article(2, summary="Grève à la SNCF")]])))
    use_news_client(make_client(api))

    chat = create_chat(client, alice)

    prompt = stored_prompt(session, chat["id"])
    assert prompt.startswith(NEWSFOUNDRY_SYSTEM_PROMPT)
    today = datetime.now(ZoneInfo("Europe/Paris"))
    assert f"Actualités du {today:%d/%m/%Y}" in prompt
    # Titres, résumés, sources et liens, avec la consigne de citer les sources
    assert "1. Titre 1 (media1.fr, 29/10/2026)" in prompt
    assert "Grève à la SNCF" in prompt
    assert "https://www.media2.fr/article" in prompt
    assert "cite le média et le lien" in prompt
    # Jamais le texte intégral de l'article
    assert "Texte intégral" not in prompt
    # Le front ne voit pas le prompt
    assert "system_prompt" not in chat


def test_system_prompt_frozen_across_messages(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    use_news_client(make_client(FakeApi(ok(top_news_payload([[article(1)]])))))
    chat = create_chat(client, alice)
    prompt_at_creation = stored_prompt(session, chat["id"])

    # Les actualités changent ensuite (nouveau jour, cache expiré…)
    use_news_client(make_client(FakeApi(ok(top_news_payload([[article(99)]])))))
    received_instructions: list[str | None] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        received_instructions.append(info.instructions)
        return ModelResponse(parts=[TextPart("Réponse")])

    with chat_agent.override(model=FunctionModel(model)):
        for content in ("Premier message", "Second message"):
            response = client.post(
                f"/chats/{chat['id']}/messages", json={"content": content}, headers=alice
            )
            assert response.status_code == 200

    # Le chat garde les actualités de sa création, en base comme dans ce que reçoit le modèle
    assert stored_prompt(session, chat["id"]) == prompt_at_creation
    # (PydanticAI retire les espaces de début et de fin des instructions)
    assert received_instructions == [prompt_at_creation.strip()] * 2
    assert "Titre 99" not in prompt_at_creation
    # Un nouveau chat, lui, reçoit les nouvelles actualités
    assert "Titre 99" in stored_prompt(session, create_chat(client, alice)["id"])


def test_two_chats_single_top_news_call(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    api = FakeApi(ok(top_news_payload([[article(1)]])))
    use_news_client(make_client(api))

    first = create_chat(client, alice)
    second = create_chat(client, alice)

    # Cache : un seul appel à WorldNewsAPI, mêmes actualités dans les deux chats
    assert len(api.requests) == 1
    assert "Titre 1" in stored_prompt(session, first["id"])
    assert "Titre 1" in stored_prompt(session, second["id"])


def test_news_api_down_chat_still_created(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    api = FakeApi(lambda request: httpx.Response(503, text="Service Unavailable"))
    use_news_client(make_client(api))

    chat = create_chat(client, alice)
    second = create_chat(client, alice)

    prompt = stored_prompt(session, chat["id"])
    assert prompt.startswith(NEWSFOUNDRY_SYSTEM_PROMPT)
    assert "Actualités indisponibles" in prompt
    # Échec gardé en cache : pas de nouvel appel voué à l'échec pour le chat suivant
    assert len(api.requests) == 1
    assert "Actualités indisponibles" in stored_prompt(session, second["id"])


def test_missing_key_chat_created_without_news(
    client: TestClient, session: Session, alice: dict[str, str]
):
    # Client par défaut des tests : sans clé, aucune requête possible
    chat = create_chat(client, alice)

    assert "Actualités indisponibles" in stored_prompt(session, chat["id"])


def test_unexpected_client_error_does_not_block(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    class BrokenClient(NewsClient):
        async def get_top_news(self):
            raise RuntimeError("bug inattendu")

    use_news_client(BrokenClient("cle"))

    chat = create_chat(client, alice)

    assert "Actualités indisponibles" in stored_prompt(session, chat["id"])
