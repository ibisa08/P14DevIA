"""Faux WorldNewsAPI partagés par les tests : réponses simulées par httpx.MockTransport."""

from collections.abc import Callable

import httpx

from services.news_api import NewsClient

API_KEY = "cle-secrete-de-test-0123456789"


class FakeClock:
    """Horloge contrôlée par le test : le temps n'avance que via advance() ou sleep()."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeApi:
    """Transport simulé qui enregistre les requêtes reçues."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make_client(api: FakeApi, clock: FakeClock | None = None, **kwargs) -> NewsClient:
    clock = clock or FakeClock()
    return NewsClient(
        kwargs.pop("api_key", API_KEY),
        transport=api.transport,
        clock=clock,
        sleep=clock.sleep,
        **kwargs,
    )


def article(index: int, **overrides) -> dict:
    """Article au format brut de WorldNewsAPI."""
    return {
        "id": index,
        "title": f"Titre {index}",
        "text": f"Texte intégral {index}",
        "summary": f"Résumé {index}",
        "url": f"https://www.media{index}.fr/article",
        "image": "https://img.fr/a.jpg",
        "publish_date": "2026-10-29 08:30:00",
        "authors": ["Jean Dupont"],
        **overrides,
    }


def top_news_payload(clusters: list[list[dict]]) -> dict:
    return {"top_news": [{"news": news} for news in clusters], "language": "fr", "country": "fr"}


def search_payload(news: list[dict]) -> dict:
    return {"offset": 0, "number": len(news), "available": len(news), "news": news}


def ok(payload: dict) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json=payload)
