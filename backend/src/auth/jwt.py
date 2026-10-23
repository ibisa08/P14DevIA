from datetime import UTC, datetime, timedelta

import jwt

from config import get_settings

ALGORITHM = "HS256"


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        # La RFC 7519 impose un `sub` de type chaîne (PyJWT le vérifie au décodage)
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """Vérifie signature et expiration, puis renvoie l'id utilisateur.

    Lève `jwt.InvalidTokenError` (dont `ExpiredSignatureError`) si le token est invalide.
    """
    payload = jwt.decode(
        token,
        get_settings().jwt_secret,
        # Liste blanche explicite : empêche un token forgé avec "alg": "none" ou un autre algo
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp", "iat"]},
    )
    try:
        return int(payload["sub"])
    except ValueError as exc:
        raise jwt.InvalidTokenError("Le claim sub n'est pas un identifiant") from exc
