"""Ajout automatique de la colonne `rag_used` sur une base créée avant son introduction."""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

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
