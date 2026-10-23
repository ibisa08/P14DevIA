from collections.abc import Generator
from functools import lru_cache

import bcrypt
from fastapi import Depends
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from config import get_settings
from models import User


@lru_cache
def get_engine() -> Engine:
    """Engine PostgreSQL de l'application, créé au premier appel puis réutilisé.

    Utilisé comme dépendance FastAPI : les tests le remplacent via
    `app.dependency_overrides[get_engine]` pour pointer vers SQLite en mémoire.
    """
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL n'est pas définie (voir backend/.env.example)")
    return create_engine(settings.database_url, echo=settings.sql_echo)


def get_session(engine: Engine = Depends(get_engine)) -> Generator[Session, None, None]:
    """Dépendance FastAPI : une session par requête, fermée automatiquement."""
    with Session(engine) as session:
        yield session


def init_db(engine: Engine) -> None:
    """Crée les tables manquantes et l'utilisateur de test sur l'engine fourni."""
    SQLModel.metadata.create_all(engine)
    print("Database initialized successfully")

    # Création de l'utilisateur de test (pas d'inscription dans l'application)
    default_email = "test@test.com"
    default_password = "test"

    with Session(engine) as session:
        statement = select(User).where(User.email == default_email)
        user = session.exec(statement).first()

        if not user:
            session.add(
                User(
                    email=default_email,
                    # hashpw renvoie des bytes : on stocke la chaîne décodée dans la colonne str,
                    # sinon la valeur enregistrée devient la représentation "b'...'" et checkpw échoue.
                    hashed_password=bcrypt.hashpw(
                        default_password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8"),
                )
            )
            session.commit()
