"""Ajout automatique de la colonne `rag_used` sur une base créée avant son introduction."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from database import init_db
from models import PressReview


def test_init_db_adds_rag_used_to_an_existing_table():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    # Table `pressreview` telle qu'elle existait en production, sans `rag_used`
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE pressreview (id INTEGER PRIMARY KEY, user_id INTEGER, chat_id INTEGER, "
                "topic VARCHAR, title VARCHAR, content JSON, created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO pressreview (user_id, chat_id, topic, title, content) "
                "VALUES (1, 1, 'ancien', 'Ancienne revue', '{}')"
            )
        )

    init_db(engine)
    init_db(engine)  # idempotent : un second démarrage ne fait rien

    assert "rag_used" in {column["name"] for column in inspect(engine).get_columns("pressreview")}
    with Session(engine) as session:
        # Les revues existantes valent False, et une nouvelle revue s'enregistre normalement
        assert session.get(PressReview, 1).rag_used is False
        session.add(PressReview(user_id=1, chat_id=1, topic="t", title="t", content={}, rag_used=True))
        session.commit()


# --- PostgreSQL réel (optionnel) ---------------------------------------------------------
# La CI tourne sur SQLite. Ce test ne s'exécute que si TEST_POSTGRES_URL est définie, par exemple :
#   docker run -d -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=t -p 55432:5432 postgres:17
#   TEST_POSTGRES_URL=postgresql+psycopg2://postgres:pw@localhost:55432/t uv run pytest tests/test_database_migration.py
# Il travaille dans un schéma temporaire, supprimé à la fin : la base indiquée n'est pas modifiée.

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL non définie")
def test_postgres_startup_twice_and_with_stale_check(monkeypatch: pytest.MonkeyPatch):
    import database

    schema = f"test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(POSTGRES_URL, connect_args={"options": f"-csearch_path={schema}"})
    try:
        SQLModel.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE pressreview DROP COLUMN rag_used"))

        statements: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().startswith("ALTER"):
                statements.append(statement.strip())

        database.init_db(engine)
        database.init_db(engine)
        assert statements == [
            'ALTER TABLE "pressreview" ADD COLUMN IF NOT EXISTS "rag_used" BOOLEAN NOT NULL DEFAULT false'
        ]

        # Deux instances qui démarrent ensemble : la seconde a lu le schéma AVANT l'ajout de la
        # colonne et relance l'ALTER. Sans IF NOT EXISTS, PostgreSQL répondrait « already exists ».
        class StaleInspector:
            def has_table(self, name: str) -> bool:
                return True

            def get_columns(self, name: str) -> list[dict]:
                return []

        monkeypatch.setattr(database, "inspect", lambda engine: StaleInspector())
        database.add_missing_columns(engine)
        assert len(statements) > 1
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
