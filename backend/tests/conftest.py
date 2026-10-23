from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from database import get_engine, get_session
from main import app


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
    # Le `with` déclenche le lifespan, donc init_db(engine de test)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
