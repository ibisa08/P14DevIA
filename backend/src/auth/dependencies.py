import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from auth.jwt import decode_access_token
from database import get_session
from models import User

# auto_error=False : on gère nous-mêmes l'absence de header pour renvoyer un 401 homogène.
# HTTPBearer ajoute aussi le bouton « Authorize » dans la doc Swagger (/docs).
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized(detail: str) -> HTTPException:
    # Le header WWW-Authenticate est exigé par la RFC 7235 sur une réponse 401
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Dépendance des routes protégées : renvoie l'utilisateur du token, sinon 401."""
    if credentials is None:
        raise unauthorized("Authentification requise")

    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized("Token invalide ou expiré")

    # Token valide mais utilisateur supprimé depuis son émission
    user = session.get(User, user_id)
    if user is None:
        raise unauthorized("Token invalide ou expiré")
    return user
