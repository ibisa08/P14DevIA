"""Stockage du texte des articles par discussion (ChatArticle) : jamais exposé, borné, isolé."""

import httpx
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from sqlmodel import Session, select

from agents.chat_agent import chat_agent
from models import Chat, ChatArticle, User
from news_fakes import FakeApi, article, make_client, ok, search_payload
from routers.chats import MAX_STORED_ARTICLES_PER_CHAT, load_owned_chat_articles
from services.news_api import ARTICLE_TEXT_MAX_CHARS
from test_search_news_tool import create_chat, searching_model, send

RETRAITES_TEXT = "La réforme des retraites divise les partenaires sociaux. " * 8


def add_article(session: Session, chat_id: int, name: str, text: str) -> None:
    session.add(
        ChatArticle(chat_id=chat_id, url=f"https://{name}.fr/a", title=f"Article {name}", text=text)
    )
    session.commit()


def make_chat_with_message(client: TestClient, headers: dict[str, str]) -> int:
    chat_id = create_chat(client, headers)
    with chat_agent.override(model=TestModel(custom_output_text="Réponse.")):
        send(client, chat_id, headers)
    return chat_id


def user_by_email(session: Session, email: str) -> User:
    return session.exec(select(User).where(User.email == email)).one()


# --- Stockage des textes pendant la discussion ---------------------------------------------


def test_search_stores_article_texts_without_exposing_them(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client
):
    api = FakeApi(ok(search_payload([article(1, text=RETRAITES_TEXT), article(2, text="")])))
    chat_id = create_chat(client, alice)
    use_news_client(make_client(api))

    with chat_agent.override(model=searching_model({"query": "retraites"})):
        response = send(client, chat_id, alice)

    assert response.status_code == 200
    # Le texte intégral ne sort jamais par l'API ni vers le modèle
    assert "partenaires sociaux" not in response.text
    assert "partenaires sociaux" not in client.get(f"/chats/{chat_id}", headers=alice).text
    rows = session.exec(select(ChatArticle)).all()
    assert {(row.chat_id, row.url, row.title) for row in rows} == {
        (chat_id, "https://www.media1.fr/article", "Titre 1"),
        (chat_id, "https://www.media2.fr/article", "Titre 2"),
    }
    by_title = {row.title: row.text for row in rows}
    assert by_title["Titre 1"].startswith("La réforme des retraites")
    # Sans texte intégral, le résumé de l'API sert de texte à indexer
    assert by_title["Titre 2"] == "Résumé 2"


def test_texts_not_duplicated_and_truncated(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client
):
    huge = "mot " * 5000
    responses = iter(
        [
            httpx.Response(200, json=search_payload([article(1, text=huge)])),
            httpx.Response(200, json=search_payload([article(1, text=huge), article(2)])),
        ]
    )
    chat_id = create_chat(client, alice)
    use_news_client(make_client(FakeApi(lambda request: next(responses))))

    with chat_agent.override(model=searching_model({"query": "climat"}, {"query": "énergie"})):
        assert send(client, chat_id, alice).status_code == 200

    rows = session.exec(select(ChatArticle).order_by(ChatArticle.id)).all()
    assert [row.title for row in rows] == ["Titre 1", "Titre 2"]
    assert len(rows[0].text) <= ARTICLE_TEXT_MAX_CHARS


def test_stored_articles_per_chat_are_capped(
    client: TestClient, session: Session, alice: dict[str, str], use_news_client
):
    chat_id = create_chat(client, alice)
    for index in range(MAX_STORED_ARTICLES_PER_CHAT):
        session.add(ChatArticle(chat_id=chat_id, url=f"https://x.fr/{index}", title="t", text="x"))
    session.commit()
    use_news_client(make_client(FakeApi(ok(search_payload([article(1)])))))

    with chat_agent.override(model=searching_model({"query": "retraites"})):
        assert send(client, chat_id, alice).status_code == 200

    assert len(session.exec(select(ChatArticle)).all()) == MAX_STORED_ARTICLES_PER_CHAT


# --- Isolation entre utilisateurs --------------------------------------------------------------


def test_articles_of_another_users_chat_cannot_be_read(
    client: TestClient, session: Session, alice: dict[str, str], bob: dict[str, str]
):
    alice_chat = make_chat_with_message(client, alice)
    add_article(session, alice_chat, "retraites", RETRAITES_TEXT)
    alice_user = user_by_email(session, "alice@test.com")
    bob_user = user_by_email(session, "bob@test.com")

    assert [row.url for row in load_owned_chat_articles(session, alice_chat, alice_user)] == [
        "https://retraites.fr/a"
    ]
    # Mauvais couple (chat d'Alice, utilisateur Bob) : la requête SQL elle-même ne renvoie rien
    assert load_owned_chat_articles(session, alice_chat, bob_user) == []



def test_cannot_add_articles_to_another_users_chat(
    client: TestClient, session: Session, alice: dict[str, str], bob: dict[str, str], use_news_client
):
    alice_chat = create_chat(client, alice)
    use_news_client(make_client(FakeApi(ok(search_payload([article(1, text=RETRAITES_TEXT)])))))

    with chat_agent.override(model=searching_model({"query": "retraites"})):
        response = send(client, alice_chat, bob)

    assert response.status_code == 404
    assert session.exec(select(ChatArticle)).all() == []
    assert session.get(Chat, alice_chat).loaded_articles == []
