from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import get_engine, init_db

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def hello():
    return {"message": "👋"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
