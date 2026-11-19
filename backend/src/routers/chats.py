import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, col, select

from agents.chat_agent import ChatDeps, build_system_prompt, generate_reply
from agents.history import dump_history, load_history, to_display_messages
from auth.dependencies import get_current_user
from database import get_session
from models import Chat, ChatArticle, User, utc_now
from routers.auth import UNAUTHORIZED_RESPONSE
from schemas import ChatRead, ChatSummary, MessageCreate
from services.news_api import NewsApiError, NewsArticle, NewsClient, get_news_client

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


def merge_articles(
    known: list[dict[str, str]], found: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Ajoute les articles trouvés à ceux déjà chargés, sans doublon d'URL (nouvelle liste)."""
    known_urls = {article["url"] for article in known}
    return [*known, *(article for article in found if article["url"] not in known_urls)]


# Garde-fou : texte stocké pour au plus ce nombre d'articles par discussion (les premiers trouvés)
MAX_STORED_ARTICLES_PER_CHAT = 50


def store_article_texts(session: Session, chat: Chat, deps: ChatDeps) -> None:
    """Ajoute à la session les textes des articles trouvés pendant l'échange (sans doublon d'URL).

    Ils serviront à la recherche sémantique de la revue de presse. La ligne est rattachée au chat
    que l'appelant vient de charger avec `get_owned_chat` : jamais à un chat d'un autre utilisateur.
    """
    known_urls = set(
        session.exec(select(ChatArticle.url).where(ChatArticle.chat_id == chat.id)).all()
    )
    for article in deps.found_articles:
        url = article["url"]
        if len(known_urls) >= MAX_STORED_ARTICLES_PER_CHAT:
            break
        text = deps.found_texts.get(url)
        if text and url not in known_urls:
            known_urls.add(url)
            session.add(
                ChatArticle(chat_id=chat.id, url=url, title=article["title"], text=text)
            )


def load_owned_chat_articles(session: Session, chat_id: int, user: User) -> list[ChatArticle]:
    """Articles d'une discussion de `user`, ou liste vide si elle appartient à un autre.

    Le filtre sur le propriétaire est dans la requête SQL (jointure), comme `get_owned_chat` :
    même un appel avec un mauvais couple (chat, utilisateur) ne peut pas lire les textes d'autrui.
    """
    statement = (
        select(ChatArticle)
        .join(Chat, col(Chat.id) == col(ChatArticle.chat_id))
        .where(ChatArticle.chat_id == chat_id, Chat.user_id == user.id)
        .order_by(col(ChatArticle.id))
    )
    return list(session.exec(statement).all())


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


async def fetch_top_news(news_client: NewsClient) -> list[NewsArticle] | None:
    """Actualités du jour, ou None si indisponibles : jamais bloquant pour la création du chat."""
    try:
        return await news_client.get_top_news()
    except NewsApiError as exc:
        logger.warning("Nouvelle discussion sans actualités du jour : %s", exc)
    except Exception:
        # Bug inattendu du client : la discussion doit être créée quand même
        logger.exception("Nouvelle discussion sans actualités du jour (erreur inattendue)")
    return None


@router.post(
    "",
    response_model=ChatRead,
    status_code=status.HTTP_201_CREATED,
    responses=UNAUTHORIZED_RESPONSE,
)
async def create_chat(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    news_client: NewsClient = Depends(get_news_client),
) -> ChatRead:
    user_id = current_user.id
    # Connexion rendue au pool pendant l'appel à WorldNewsAPI (jusqu'au timeout du client)
    session.commit()
    top_news = await fetch_top_news(news_client)

    now = utc_now()
    local_now = now.astimezone(TITLE_TIMEZONE)
    chat = Chat(
        user_id=user_id,
        title=f"Discussion du {local_now:%d/%m/%Y}",
        # Figé ici : un chat repris plus tard garde les actualités du jour de sa création
        system_prompt=build_system_prompt(top_news, local_now.date()),
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
    news_client: NewsClient = Depends(get_news_client),
) -> ChatRead:
    chat = get_owned_chat(session, chat_id, current_user)
    history = load_history(chat.messages)
    system_prompt = chat.system_prompt
    # Termine la transaction de lecture : la connexion retourne au pool pendant l'appel au
    # modèle (plusieurs secondes) au lieu de rester « idle in transaction » côté Postgres.
    session.commit()

    deps = ChatDeps(news_client=news_client)
    try:
        updated_history = await generate_reply(message.content, history, system_prompt, deps)
    except Exception:
        # Détail (fournisseur, quota, clé manquante...) dans les logs uniquement ;
        # l'historique n'est pas modifié, le message pourra être renvoyé tel quel.
        logger.exception("Échec de l'agent de chat (chat %s)", chat_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=LLM_ERROR)

    chat.messages = dump_history(updated_history)
    chat.loaded_articles = merge_articles(chat.loaded_articles, deps.found_articles)
    store_article_texts(session, chat, deps)
    chat.updated_at = utc_now()
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return to_chat_read(chat)
