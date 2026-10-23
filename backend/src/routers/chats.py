import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, select

from agents.chat_agent import NEWSFOUNDRY_SYSTEM_PROMPT, generate_reply
from agents.history import dump_history, load_history, to_display_messages
from auth.dependencies import get_current_user
from database import get_session
from models import Chat, User, utc_now
from routers.auth import UNAUTHORIZED_RESPONSE
from schemas import ChatRead, ChatSummary, MessageCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chats"])

# Fuseau des utilisateurs (pigistes francophones) pour la date du titre
TITLE_TIMEZONE = ZoneInfo("Europe/Paris")
CHAT_NOT_FOUND = "Discussion introuvable"
LLM_ERROR = "L'assistant n'a pas pu répondre, réessaie."

NOT_FOUND_RESPONSE = {
    404: {
        "description": "Discussion inexistante ou appartenant à un autre utilisateur",
        "content": {"application/json": {"example": {"detail": CHAT_NOT_FOUND}}},
    }
}
LLM_ERROR_RESPONSE = {
    502: {
        "description": "Le modèle n'a pas répondu (rien n'est sauvegardé)",
        "content": {"application/json": {"example": {"detail": LLM_ERROR}}},
    }
}


def get_owned_chat(session: Session, chat_id: int, user: User) -> Chat:
    """Chat de l'utilisateur, sinon 404.

    Le filtre sur user_id est dans la requête SQL elle-même : le chat d'un autre utilisateur
    n'est jamais chargé, et la réponse est la même que pour un id inexistant (on ne révèle
    pas qu'il existe).
    """
    chat = session.exec(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)).first()
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CHAT_NOT_FOUND)
    return chat


def to_chat_read(chat: Chat) -> ChatRead:
    return ChatRead(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=to_display_messages(load_history(chat.messages)),
    )


@router.get("", response_model=list[ChatSummary], responses=UNAUTHORIZED_RESPONSE)
def list_chats(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[Chat]:
    statement = (
        select(Chat)
        .where(Chat.user_id == current_user.id)
        # id en second critère : ordre stable si deux chats ont la même date
        .order_by(col(Chat.updated_at).desc(), col(Chat.id).desc())
    )
    return list(session.exec(statement).all())


@router.post(
    "",
    response_model=ChatRead,
    status_code=status.HTTP_201_CREATED,
    responses=UNAUTHORIZED_RESPONSE,
)
def create_chat(
    current_user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> ChatRead:
    now = utc_now()
    chat = Chat(
        user_id=current_user.id,
        title=f"Discussion du {now.astimezone(TITLE_TIMEZONE):%d/%m/%Y}",
        system_prompt=NEWSFOUNDRY_SYSTEM_PROMPT,
        created_at=now,
        updated_at=now,
    )
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return to_chat_read(chat)


@router.get(
    "/{chat_id}",
    response_model=ChatRead,
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE},
)
def read_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChatRead:
    return to_chat_read(get_owned_chat(session, chat_id, current_user))


@router.post(
    "/{chat_id}/messages",
    response_model=ChatRead,
    responses={**UNAUTHORIZED_RESPONSE, **NOT_FOUND_RESPONSE, **LLM_ERROR_RESPONSE},
)
async def send_message(
    chat_id: int,
    message: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChatRead:
    chat = get_owned_chat(session, chat_id, current_user)
    history = load_history(chat.messages)
    system_prompt = chat.system_prompt
    # Termine la transaction de lecture : la connexion retourne au pool pendant l'appel au
    # modèle (plusieurs secondes) au lieu de rester « idle in transaction » côté Postgres.
    session.commit()

    try:
        updated_history = await generate_reply(message.content, history, system_prompt)
    except Exception:
        # Détail (fournisseur, quota, clé manquante...) dans les logs uniquement ;
        # l'historique n'est pas modifié, le message pourra être renvoyé tel quel.
        logger.exception("Échec de l'agent de chat (chat %s)", chat_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=LLM_ERROR)

    chat.messages = dump_history(updated_history)
    chat.updated_at = utc_now()
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return to_chat_read(chat)
