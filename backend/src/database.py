import logging
from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy import Engine, inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from auth.security import hash_password
from config import get_settings
from models import User

logger = logging.getLogger(__name__)


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


def add_missing_columns(engine: Engine) -> None:
    """Ajoute à une table existante les colonnes apparues depuis sa création.

    `create_all` crée les tables absentes mais ne modifie jamais une table existante : sans cette
    étape, la colonne `rag_used` manquerait en production et chaque création de revue échouerait.
    Seules les colonnes avec une valeur par défaut serveur sont ajoutées (additif, sans perte).
    Une vraie migration (Alembic) reste une piste d'amélioration, voir docs/ameliorations.md (B8).
    """
    inspector = inspect(engine)
    for table in SQLModel.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing or column.server_default is None:
                continue
            column_type = column.type.compile(dialect=engine.dialect)
            default = column.server_default.arg.compile(dialect=engine.dialect)
            # PostgreSQL : IF NOT EXISTS rend l'ordre idempotent même si deux instances démarrent en
            # même temps (déploiement qui se chevauche) et voient toutes deux la colonne manquante.
            # SQLite (tests) ne connaît pas cette clause ; la vérification ci-dessus lui suffit.
            if_not_exists = "IF NOT EXISTS " if engine.dialect.name == "postgresql" else ""
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f'ALTER TABLE "{table.name}" ADD COLUMN {if_not_exists}"{column.name}" '
                        f"{column_type} NOT NULL DEFAULT {default}"
                    )
                )
            logger.info("Colonne %s.%s ajoutée", table.name, column.name)


def init_db(engine: Engine) -> None:
    """Crée les tables manquantes et l'utilisateur de test sur l'engine fourni."""
    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)
    logger.info("Base de données initialisée (tables créées si absentes)")

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
                    hashed_password=hash_password(default_password),
                )
            )
            session.commit()
