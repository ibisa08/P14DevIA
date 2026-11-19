import logging

from fastapi import APIRouter, Depends, HTTPException, status
from llama_index.core.base.embeddings.base import BaseEmbedding
from sqlmodel import Session, col, select

from agents.history import load_history, to_display_messages, to_transcript
from agents.review_agent import generate_review
from auth.dependencies import get_current_user
from database import get_session
from models import PressReview, User
from routers.auth import UNAUTHORIZED_RESPONSE
from routers.chats import (
    LLM_ERROR,
    LLM_ERROR_RESPONSE,
    NOT_FOUND_RESPONSE,
    get_owned_chat,
    load_owned_chat_articles,
)
from schemas import PressReviewRead, ReviewCreate
from services.rag import ArticleText, get_embed_model, select_relevant_articles

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reviews"])

EMPTY_CHAT = "Envoie au moins un message dans la discussion avant de générer une revue de presse."


@router.post(
    "/chats/{chat_id}/reviews",
    response_model=PressReviewRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        **UNAUTHORIZED_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **LLM_ERROR_RESPONSE,
        400: {
            "description": "Discussion sans message",
            "content": {"application/json": {"example": {"detail": EMPTY_CHAT}}},
        },
    },
)
async def create_review(
    chat_id: int,
    request: ReviewCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    embed_model: BaseEmbedding | None = Depends(get_embed_model),
) -> PressReview:
    chat = get_owned_chat(session, chat_id, current_user)
    messages = to_display_messages(load_history(chat.messages))
    if not messages:
        # Sans matière, l'agent ne pourrait qu'inventer une revue
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=EMPTY_CHAT)
    # Textes lus après le contrôle du propriétaire ci-dessus, et filtrés par lui une seconde fois
    articles = [
        ArticleText(url=row.url, title=row.title, text=row.text)
        for row in load_owned_chat_articles(session, chat_id, current_user)
    ]
    # Libère la connexion pendant les appels externes (voir send_message)
    session.commit()

    # Jamais bloquant : sans clé, sans article pertinent ou en cas de panne, la liste est vide
    # et la revue repose sur la discussion seule
    sources = await select_relevant_articles(request.topic, articles, embed_model)

    try:
        output = await generate_review(request.topic, to_transcript(messages), sources)
    except Exception:
        logger.exception("Échec de l'agent de revue de presse (chat %s)", chat_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=LLM_ERROR)

    review = PressReview(
        user_id=current_user.id,
        chat_id=chat_id,
        topic=request.topic,
        title=output.title,
        content=output.model_dump(mode="json"),
        # Vrai seulement si des articles retenus par le RAG ont nourri la revue
        rag_used=bool(sources),
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    return review


@router.get("/reviews", response_model=list[PressReviewRead], responses=UNAUTHORIZED_RESPONSE)
def list_reviews(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[PressReview]:
    statement = (
        select(PressReview)
        .where(PressReview.user_id == current_user.id)
        .order_by(col(PressReview.created_at).desc(), col(PressReview.id).desc())
    )
    return list(session.exec(statement).all())
