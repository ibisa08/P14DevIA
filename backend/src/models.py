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
    # Figé à la création puis réutilisé tel quel à chaque échange (contexte d'actualité à l'étape 5)
    system_prompt: str
    # Historique PydanticAI complet, sérialisé via ModelMessagesTypeAdapter.
    # Le type JSON générique de SQLAlchemy fonctionne sur Postgres comme sur SQLite (tests).
    # Toujours réaffecter une nouvelle liste : une modification en place ne serait pas détectée.
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))

