from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, UniqueConstraint
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
    # la discussion. Sert à retrouver les sources consultées (et, plus tard, à indexer leur
    # contenu pour de la recherche sémantique) sans relire tout l'historique.
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


class ChatArticle(SQLModel, table=True):
    """Texte d'un article trouvé par search_news dans une discussion.

    Alimente la recherche sémantique de la revue de presse (index en mémoire, jamais persisté).
    Table à part plutôt qu'une clé de `Chat.loaded_articles` : le texte (jusqu'à 6 000 caractères
    par article) serait relu à chaque affichage de la discussion. Jamais exposée par l'API :
    seule la revue de presse, après vérification du propriétaire du chat, la lit.
    """

    __table_args__ = (UniqueConstraint("chat_id", "url"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    chat_id: int = Field(foreign_key="chat.id", index=True)
    url: str
    title: str
    text: str
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
