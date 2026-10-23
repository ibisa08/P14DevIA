from functools import lru_cache
from typing import Annotated

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application, lue depuis les variables d'environnement (et `.env`)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Optionnelle à l'import pour que l'app soit importable sans base (tests, CI) ;
    # get_engine() lève une erreur explicite si elle manque au moment de s'en servir.
    database_url: str | None = None
    port: int = 8000
    sql_echo: bool = False
    # NoDecode : on accepte une simple liste séparée par des virgules
    # (ex. "http://localhost:3000,https://app.vercel.app") au lieu d'imposer du JSON.
    frontend_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Obligatoire, sans valeur par défaut : un secret par défaut finirait tôt ou tard en prod.
    # 32 caractères minimum, recommandation pour une clé HMAC-SHA256.
    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = Field(default=60, gt=0)

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        # Message lisible au démarrage plutôt qu'une trace Pydantic brute (détail conservé via `from`)
        problems = "; ".join(
            f"{str(error['loc'][0]).upper()} : {error['msg']}" for error in exc.errors()
        )
        raise RuntimeError(
            f"Configuration invalide ({problems}). Voir backend/.env.example."
        ) from exc
