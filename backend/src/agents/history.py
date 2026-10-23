"""Conversion entre l'historique PydanticAI stocké en base et ce qu'en voit le front."""

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    UserPromptPart,
)

from schemas import ChatMessageRead


def load_history(raw: list[dict[str, Any]]) -> list[ModelMessage]:
    return ModelMessagesTypeAdapter.validate_python(raw)


def dump_history(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    # mode="json" : dates en ISO 8601, contenu binaire en base64, stockable en colonne JSON
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")


def to_display_messages(messages: list[ModelMessage]) -> list[ChatMessageRead]:
    """Ne garde que les messages lisibles : questions du journaliste et réponses texte.

    Instructions, appels de tools et métadonnées du fournisseur restent internes.
    """
    display: list[ChatMessageRead] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    display.append(
                        ChatMessageRead(role="user", content=part.content, created_at=part.timestamp)
                    )
        elif isinstance(message, ModelResponse) and message.text:
            display.append(
                ChatMessageRead(role="assistant", content=message.text, created_at=message.timestamp)
            )
    return display

