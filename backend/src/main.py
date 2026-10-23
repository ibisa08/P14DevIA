import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import get_engine, init_db
from errors import register_error_handlers
from routers import auth, chats, reviews

# Sans configuration, les logs INFO des modules de l'app seraient ignorés
# (uvicorn ne configure que ses propres loggers)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")

# Lève une erreur explicite dès le démarrage si la config est incomplète (ex. JWT_SECRET)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Exécuté au démarrage quel que soit le lanceur (script, `uvicorn main:app`, Docker),
    # contrairement à un appel placé dans le bloc `__main__`.
    # Le lifespan ne passe pas par Depends : on résout l'override à la main pour que
    # les tests puissent injecter leur engine SQLite.
    engine_provider = app.dependency_overrides.get(get_engine, get_engine)
    init_db(engine_provider())
    yield


app = FastAPI(title="NewsFoundry API", lifespan=lifespan)

# Avant CORSMiddleware : les réponses d'erreur 500 doivent elles aussi porter les headers CORS
register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    # L'auth passe par le header Authorization (token en localStorage), pas par des cookies :
    # inutile d'autoriser l'envoi de credentials cross-origin, on garde la surface minimale.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(reviews.router)


@app.get("/")
async def hello():
    return {"message": "👋"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
