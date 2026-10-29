"""Étape 6 : outil search_news de l'agent de chat (FunctionModel, WorldNewsAPI simulée)."""

import logging
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from sqlmodel import Session

from agents.chat_agent import MAX_SEARCHES_PER_MESSAGE, chat_agent, chat_model
from agents.review_agent import review_agent
from models import Chat
from news_fakes import FakeApi, article, make_client, ok, search_payload
from services.news_api import NewsClient

# Dans ces tests, le chat est créé avec le client par défaut (sans clé, sans actualités) et le
# faux WorldNewsAPI n'est installé qu'ensuite : il ne reçoit donc que les recherches.
InstallNewsClient = Callable[[NewsClient], None]


def create_chat(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post("/chats", headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def send(client: TestClient, chat_id: int, headers: dict[str, str]) -> httpx.Response:
    body = {"content": "Quoi de neuf ?"}
    return client.post(f"/chats/{chat_id}/messages", json=body, headers=headers)


def last_tool_results(messages: list[ModelMessage]) -> list[ToolReturnPart | RetryPromptPart]:
    """Résultats d'outils renvoyés au modèle dans la dernière requête."""
    last = messages[-1]
    assert isinstance(last, ModelRequest)
    return [part for part in last.parts if isinstance(part, ToolReturnPart | RetryPromptPart)]


def searching_model(*calls: dict, seen: list | None = None) -> FunctionModel:
    """Modèle qui lance les recherches `calls` (une par tour), puis répond avec ce qu'il a reçu.

    `seen` collecte les résultats d'outils renvoyés au modèle (succès, échecs, retries).
    """

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # Tours de l'échange en cours uniquement : l'historique contient les échanges précédents
        current = messages[current_exchange_start(messages) :]
        if len(current) > 1 and seen is not None:
            seen.extend(last_tool_results(current))
        tool_turns = sum(isinstance(m, ModelResponse) and bool(m.tool_calls) for m in current)
        if tool_turns < len(calls):
            call = ToolCallPart("search_news", calls[tool_turns], tool_call_id=f"t{tool_turns}")
            return ModelResponse(parts=[TextPart("Je cherche…"), call])
        results = last_tool_results(current)
        return ModelResponse(parts=[TextPart(f"Synthèse : {results[0].model_response_str()}")])

    return FunctionModel(model)


def current_exchange_start(messages: list[ModelMessage]) -> int:
    """Index de la requête qui porte le dernier message du journaliste."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, ModelRequest) and any(
            isinstance(part, UserPromptPart) for part in message.parts
        ):
            return index
    return 0


def test_agent_calls_search_news_and_uses_results(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    api = FakeApi(ok(search_payload([article(1), article(2, url="https://lemonde.fr/b")])))
    chat_id = create_chat(client, alice)
    use_news_client(make_client(api))

    model = searching_model({"query": "réforme des retraites", "language": "fr", "max_results": 2})
    with chat_agent.override(model=model):
        response = send(client, chat_id, alice)

    assert response.status_code == 200
    messages = response.json()["messages"]
    # Seule la réponse finale est affichée, pas l'étape intermédiaire « Je cherche… »
    assert [m["role"] for m in messages] == ["user", "assistant"]
    answer = messages[1]["content"]
    assert "Titre 1" in answer and "lemonde.fr" in answer
    # Sortie compacte : jamais le texte intégral ni les champs bruts de l'API
    assert "Texte intégral" not in answer and "image" not in answer

    params = api.requests[0].url.params
    assert params["text"] == "réforme des retraites"
    assert params["language"] == "fr"
    assert params["number"] == "2"

    session.expire_all()
    assert session.get(Chat, chat_id).loaded_articles == [
        {"url": "https://www.media1.fr/article", "title": "Titre 1"},
        {"url": "https://lemonde.fr/b", "title": "Titre 2"},
    ]


def test_search_query_never_logged(
    client: TestClient,
    alice: dict[str, str],
    use_news_client: InstallNewsClient,
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.INFO)
    chat_id = create_chat(client, alice)
    use_news_client(make_client(FakeApi(ok(search_payload([article(1)])))))

    with chat_agent.override(model=searching_model({"query": "dossier confidentiel"})):
        assert send(client, chat_id, alice).status_code == 200

    # Ni la recherche (dans l'URL appelée par httpx) ni le contenu des messages
    assert "confidentiel" not in caplog.text
    assert "Quoi de neuf" not in caplog.text


def test_loaded_articles_accumulate_without_duplicates(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    responses = iter(
        [
            httpx.Response(200, json=search_payload([article(1), article(2)])),
            httpx.Response(200, json=search_payload([article(2), article(3)])),
        ]
    )
    chat_id = create_chat(client, alice)
    use_news_client(make_client(FakeApi(lambda request: next(responses))))

    for query in ("climat", "énergie"):
        with chat_agent.override(model=searching_model({"query": query})):
            assert send(client, chat_id, alice).status_code == 200

    session.expire_all()
    titles = [found["title"] for found in session.get(Chat, chat_id).loaded_articles]
    assert titles == ["Titre 1", "Titre 2", "Titre 3"]


def test_api_error_reported_to_model_not_502(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client: InstallNewsClient
):
    api = FakeApi(lambda request: httpx.Response(402, json={"message": "quota"}))
    chat_id = create_chat(client, alice)
    use_news_client(make_client(api))
    seen: list = []

    with chat_agent.override(model=searching_model({"query": "élections"}, seen=seen)):
        response = send(client, chat_id, alice)

    # Le message aboutit : le modèle a reçu l'échec et a pu répondre quand même
    assert response.status_code == 200
    [result] = seen
    assert isinstance(result, ToolReturnPart) and result.outcome == "failed"
    assert "Quota quotidien WorldNewsAPI épuisé" in result.content
    assert "signale au journaliste" in result.content
    # Un seul appel : l'échec n'invite pas le modèle à réessayer
    assert len(api.requests) == 1
    session.expire_all()
    assert session.get(Chat, chat_id).loaded_articles == []


def test_missing_key_reported_to_model(client: TestClient, alice: dict[str, str]):
    # Client par défaut des tests : sans clé
    chat_id = create_chat(client, alice)
    seen: list = []

    with chat_agent.override(model=searching_model({"query": "élections"}, seen=seen)):
        response = send(client, chat_id, alice)

    assert response.status_code == 200
    assert "clé WorldNewsAPI non configurée" in seen[0].content


def test_invalid_arguments_ask_model_to_retry(
    client: TestClient, alice: dict[str, str], use_news_client: InstallNewsClient
):
    api = FakeApi(ok(search_payload([article(1)])))
    chat_id = create_chat(client, alice)
    use_news_client(make_client(api))
    seen: list = []

    model = searching_model({"query": "ab", "max_results": 50}, seen=seen)
    with chat_agent.override(model=model):
        response = send(client, chat_id, alice)

    assert response.status_code == 200
    # Arguments refusés avant tout appel réseau, avec un message de correction pour le modèle
    assert seen[0].outcome == "retried" and seen[0].retry.cause == "validation_error"
    assert api.requests == []


def test_searches_limited_per_message(
    client: TestClient, alice: dict[str, str], use_news_client: InstallNewsClient
):
    api = FakeApi(ok(search_payload([article(1)])))
    chat_id = create_chat(client, alice)
    use_news_client(make_client(api))
    seen: list = []
    calls = [{"query": f"recherche {index}"} for index in range(MAX_SEARCHES_PER_MESSAGE + 1)]

    with chat_agent.override(model=searching_model(*calls, seen=seen)):
        response = send(client, chat_id, alice)

    assert response.status_code == 200
    assert len(api.requests) == MAX_SEARCHES_PER_MESSAGE
    assert "Limite de 3 recherches" in seen[-1].content


def test_test_model_never_calls_tools(
    client: TestClient, alice: dict[str, str], use_news_client: InstallNewsClient
):
    # LLM_MODEL=test (forcé par conftest) : TestModel configuré pour ne lancer aucun outil
    model = chat_model()
    assert isinstance(model, TestModel) and model.call_tools == []

    api = FakeApi(ok(search_payload([article(1)])))
    chat_id = create_chat(client, alice)
    use_news_client(make_client(api))

    assert send(client, chat_id, alice).status_code == 200
    # Aucune recherche réelle : le quota n'est pas consommé en développement
    assert api.requests == []


def test_other_user_cannot_trigger_search(
    client: TestClient,
    alice: dict[str, str],
    bob: dict[str, str],
    use_news_client: InstallNewsClient,
):
    api = FakeApi(ok(search_payload([article(1)])))
    chat_id = create_chat(client, alice)
    use_news_client(make_client(api))

    with chat_agent.override(model=searching_model({"query": "élections"})):
        response = send(client, chat_id, bob)

    assert response.status_code == 404
    assert api.requests == []


def test_review_agent_has_no_tools(client: TestClient, alice: dict[str, str]):
    chat_id = create_chat(client, alice)
    with chat_agent.override(model=TestModel(custom_output_text="Voici l'actualité.")):
        assert send(client, chat_id, alice).status_code == 200
    tools_seen: list[list[str]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tools_seen.append([tool.name for tool in info.function_tools])
        output_tool = info.output_tools[0].name
        args = {"title": "Revue", "summary": "Synthèse", "articles": []}
        return ModelResponse(parts=[ToolCallPart(output_tool, args)])

    with review_agent.override(model=FunctionModel(model)):
        response = client.post(
            f"/chats/{chat_id}/reviews", json={"topic": "Actualité"}, headers=alice
        )

    assert response.status_code == 201
    assert tools_seen == [[]]
