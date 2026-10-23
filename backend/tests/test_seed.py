import bcrypt
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import User


def test_seed_user_password_is_verifiable(client: TestClient, session: Session):
    # Le lifespan du client a seedé l'utilisateur de test : son hash doit être un str
    # bcrypt exploitable (régression du bug bytes stockés dans une colonne str).
    user = session.exec(select(User).where(User.email == "test@test.com")).one()

    assert user.hashed_password.startswith("$2")
    assert bcrypt.checkpw(b"test", user.hashed_password.encode("utf-8"))
