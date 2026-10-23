"""Schémas d'entrée/sortie de l'API, séparés des modèles de table.

Les réponses ne passent que par ces schémas : `hashed_password` ne peut pas fuiter, et
l'historique brut PydanticAI d'un chat n'est jamais exposé.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, StringConstraints

MESSAGE_MAX_LENGTH = 4000
TOPIC_MAX_LENGTH = 200


def ensure_utc(value: datetime) -> datetime:
    # SQLite (tests) relit les dates sans fuseau : on les marque UTC pour que le JSON porte
    # toujours un décalage explicite, sinon le navigateur les lirait en heure locale.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str


# --- Discussions ----------------------------------------------------------------


class MessageCreate(BaseModel):
    # Espaces retirés avant contrôle : un message fait uniquement d'espaces est refusé (422)
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MESSAGE_MAX_LENGTH)
    ]


class ChatMessageRead(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: UtcDatetime


class ChatSummary(BaseModel):
    id: int
    title: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ChatRead(ChatSummary):
    messages: list[ChatMessageRead]


# --- Revues de presse -------------------------------------------------------------


class ReviewCreate(BaseModel):
    topic: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TOPIC_MAX_LENGTH)
    ]


class ArticleRead(BaseModel):
    title: str
    summary: str
    source: str | None = None
    url: str | None = None


class ReviewContent(BaseModel):
    title: str
    summary: str
    articles: list[ArticleRead]


class PressReviewRead(BaseModel):
    id: int
    chat_id: int
    topic: str
    title: str
    content: ReviewContent
    created_at: UtcDatetime
