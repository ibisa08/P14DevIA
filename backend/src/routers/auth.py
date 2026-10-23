from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from auth.dependencies import get_current_user, unauthorized
from auth.jwt import create_access_token
from auth.security import dummy_password_hash, verify_password
from database import get_session
from models import User
from schemas import LoginRequest, TokenResponse, UserRead

router = APIRouter(tags=["auth"])

# Documente la réponse 401 dans le schéma OpenAPI (/docs)
UNAUTHORIZED_RESPONSE = {
    401: {
        "description": "Non authentifié",
        "content": {"application/json": {"example": {"detail": "Identifiants invalides"}}},
    }
}


@router.post("/login", response_model=TokenResponse, responses=UNAUTHORIZED_RESPONSE)
def login(credentials: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.exec(select(User).where(User.email == credentials.email)).first()

    # Email inconnu et mauvais mot de passe donnent la même réponse, et un checkpw est
    # toujours exécuté (hash factice) : ni le message ni le temps de réponse ne révèlent
    # si le compte existe.
    hashed_password = user.hashed_password if user else dummy_password_hash()
    password_ok = verify_password(credentials.password, hashed_password)
    if user is None or not password_ok:
        raise unauthorized("Identifiants invalides")

    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead, responses=UNAUTHORIZED_RESPONSE)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
