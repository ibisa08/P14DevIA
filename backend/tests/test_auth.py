from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from auth.jwt import ALGORITHM, create_access_token, decode_access_token
from auth.security import hash_password
from config import get_settings
from models import User

# Utilisateur seedé par init_db (lifespan du client de test)
SEED_EMAIL = "test@test.com"
SEED_PASSWORD = "test"


def seeded_user(session: Session) -> User:
    return session.exec(select(User).where(User.email == SEED_EMAIL)).one()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- POST /login ---------------------------------------------------------------


def test_login_ok_returns_token_with_user_id_as_sub(client: TestClient, session: Session):
    response = client.post("/login", json={"email": SEED_EMAIL, "password": SEED_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"]) == seeded_user(session).id


def test_login_wrong_password_returns_401(client: TestClient):
    response = client.post("/login", json={"email": SEED_EMAIL, "password": "mauvais"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Identifiants invalides"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_unknown_email_returns_same_401_as_wrong_password(client: TestClient):
    unknown = client.post("/login", json={"email": "inconnu@test.com", "password": "x"})
    wrong_password = client.post("/login", json={"email": SEED_EMAIL, "password": "x"})

    # Réponses indiscernables : on ne révèle pas quels comptes existent
    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "pas-un-email", "password": "test"},
        {"email": SEED_EMAIL},
        {"password": "test"},
        {},
    ],
    ids=["email-mal-forme", "password-manquant", "email-manquant", "body-vide"],
)
def test_login_invalid_body_returns_422_with_readable_detail(client: TestClient, payload: dict):
    response = client.post("/login", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    # Format d'erreur homogène : une chaîne lisible, pas la liste brute de Pydantic
    assert isinstance(detail, str)
    assert detail.startswith("Requête invalide")


# --- GET /me -------------------------------------------------------------------


def test_me_without_token_returns_401(client: TestClient):
    response = client.get("/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "detail" in response.json()


@pytest.mark.parametrize(
    "token",
    [
        "pas.un.jwt",
        # Signature valide en forme mais avec un autre secret
        jwt.encode(
            {"sub": "1", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(hours=1)},
            "un-autre-secret-de-plus-de-32-caracteres!!",
            algorithm=ALGORITHM,
        ),
    ],
    ids=["malforme", "mauvaise-signature"],
)
def test_me_with_invalid_token_returns_401(client: TestClient, token: str):
    response = client.get("/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_with_expired_token_returns_401(client: TestClient, session: Session):
    past = datetime.now(UTC) - timedelta(hours=2)
    expired_token = jwt.encode(
        {"sub": str(seeded_user(session).id), "iat": past, "exp": past + timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm=ALGORITHM,
    )

    response = client.get("/me", headers=bearer(expired_token))

    assert response.status_code == 401


def test_me_with_token_of_deleted_user_returns_401(client: TestClient, session: Session):
    user = User(email="supprime@test.com", hashed_password=hash_password("x"))
    session.add(user)
    session.commit()
    token = create_access_token(user.id)
    session.delete(user)
    session.commit()

    response = client.get("/me", headers=bearer(token))

    assert response.status_code == 401


def test_me_with_valid_token_returns_user_without_password(client: TestClient, session: Session):
    user = seeded_user(session)

    response = client.get("/me", headers=bearer(create_access_token(user.id)))

    assert response.status_code == 200
    assert response.json() == {"id": user.id, "email": SEED_EMAIL}
    assert "hashed_password" not in response.text
