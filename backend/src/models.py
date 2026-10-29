from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str = Field()


class Chat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str
    # Prompt de base + actualités du jour, figé à la création puis réutilisé à chaque échange
    system_prompt: str
    # Historique PydanticAI complet, sérialisé via ModelMessagesTypeAdapter.
    # Le type JSON générique de SQLAlchemy fonctionne sur Postgres comme sur SQLite (tests).
    # Toujours réaffecter une nouvelle liste : une modification en place ne serait pas détectée.
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    # Articles trouvés par l'outil search_news ({url, title}, sans doublon), cumulés sur toute
    # la discussion : base d'un futur RAG sur les articles consultés (étape 8)
    loaded_articles: list[dict[str, str]] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class PressReview(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    topic: str
    title: str
    # Sortie structurée de l'agent : {title, summary, articles: [{title, summary, source, url}]}
    content: dict[str, Any] = Field(sa_type=JSON)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
