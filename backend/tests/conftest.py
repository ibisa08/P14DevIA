import os
from collections.abc import Callable, Generator

# Doit précéder l'import de l'app : la config est validée dès l'import de `main`.
# Affectation (et non setdefault) : les tests utilisent toujours ce secret, jamais celui du .env.
os.environ["JWT_SECRET"] = "secret-de-test-uniquement-pour-pytest-0123456789"
# TestModel de PydanticAI par défaut : aucun test ne peut appeler un vrai modèle (ni coûter,
# ni exiger de clé). Les tests qui ont besoin d'une réponse précise utilisent agent.override().
os.environ["LLM_MODEL"] = "test"
# Ceinture et bretelles : même avec des clés réelles dans le shell ou le .env, aucun test
# n'appelle Anthropic ni WorldNewsAPI. Le SDK Anthropic lit l'environnement : on retire la clé.
# WORLDNEWS_API_KEY est forcée à vide (et non retirée) : une variable d'environnement prime
# sur le .env, que la config lit aussi.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["WORLDNEWS_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from auth.jwt import create_access_token
from database import get_engine, get_session
from main import app
from models import User
from services.news_api import NewsClient, get_news_client


@pytest.fixture
def engine() -> Generator[Engine, None, None]:
    """Base SQLite en mémoire, neuve à chaque test : jamais de contact avec la base de dev.

    StaticPool force une connexion unique partagée : sans lui, chaque connexion SQLite
    « :memory: » ouvrirait une base vide différente et les tables créées disparaîtraient.
    """
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},  # TestClient exécute l'app dans un autre thread
        poolclass=StaticPool,
    )
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    """Session directe sur la base de test, pour préparer ou vérifier des données."""
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture
def client(engine: Engine) -> Generator[TestClient, None, None]:
    """Client HTTP branché sur la base de test (tables + user seedé via le lifespan)."""

    def get_session_override() -> Generator[Session, None, None]:
        with Session(engine) as db_session:
            yield db_session

    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_session] = get_session_override
    # Client WorldNewsAPI sans clé par défaut : aucun appel réseau possible, les discussions
    # sont créées sans actualités. Les tests d'actualités installent un faux via use_news_client.
    keyless_news_client = NewsClient(None)
    app.dependency_overrides[get_news_client] = lambda: keyless_news_client
    # Le `with` déclenche le lifespan, donc init_db(engine de test)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_user_headers(session: Session, email: str) -> dict[str, str]:
    """Crée un utilisateur et renvoie ses headers d'authentification."""
    # Hash factice : ces utilisateurs ne passent jamais par /login (évite un bcrypt lent par test)
    user = User(email=email, hashed_password="non-utilise")
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def alice(client: TestClient, session: Session) -> dict[str, str]:
    """Headers d'un premier utilisateur (dépend de `client` : les tables doivent exister)."""
    return create_user_headers(session, "alice@test.com")


@pytest.fixture
def bob(client: TestClient, session: Session) -> dict[str, str]:
    """Headers d'un second utilisateur, pour les tests d'isolation."""
    return create_user_headers(session, "bob@test.com")


@pytest.fixture
def use_news_client(client: TestClient) -> Callable[[NewsClient], None]:
    """Installe un client WorldNewsAPI (branché sur un faux transport) pour la suite du test."""

    def install(news_client: NewsClient) -> None:
        app.dependency_overrides[get_news_client] = lambda: news_client

    return install
