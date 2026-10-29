"""Client WorldNewsAPI : aucun appel réseau, toutes les réponses passent par httpx.MockTransport."""

import asyncio
import logging
from datetime import UTC, datetime

import httpx
import pytest

from config import Settings
from services.news_api import (
    SEARCH_MAX_RESULTS,
    SUMMARY_MAX_CHARS,
    TOP_NEWS_LIMIT,
    InvalidResponseError,
    MissingApiKeyError,
    NewsApiError,
    NewsApiTimeoutError,
    QuotaExceededError,
)
from news_fakes import (
    API_KEY,
    FakeApi,
    FakeClock,
    article,
    make_client,
    ok,
    search_payload,
    top_news_payload,
)


# --- Simplification -------------------------------------------------------------------


def test_top_news_simplified():
    long_summary = "mot " * 200
    api = FakeApi(
        ok(
            top_news_payload(
                [
                    [article(1, summary=long_summary)],
                    # Sans résumé : début du texte intégral à la place
                    [article(2, summary=None)],
                    # Sans URL http(s) : sujet ignoré
                    [article(3, url="javascript:alert(1)")],
                    [article(4, publish_date="date invalide")],
                ]
            )
        )
    )

    articles = asyncio.run(make_client(api).get_top_news())

    assert [a.title for a in articles] == ["Titre 1", "Titre 2", "Titre 4"]
    first = articles[0]
    assert len(first.summary) <= SUMMARY_MAX_CHARS + 1 and first.summary.endswith("…")
    assert first.source == "media1.fr"
    assert first.url == "https://www.media1.fr/article"
    assert first.published_at == datetime(2026, 10, 29, 8, 30, tzinfo=UTC)
    assert articles[1].summary == "Texte intégral 2"
    assert articles[2].published_at is None
    # Jamais la réponse brute : ni texte intégral, ni image, ni auteurs
    assert set(first.model_dump()) == {"title", "summary", "url", "source", "published_at"}


def test_top_news_request_and_limit():
    api = FakeApi(ok(top_news_payload([[article(i)] for i in range(20)])))

    articles = asyncio.run(make_client(api, country="fr", language="fr").get_top_news())

    assert len(articles) == TOP_NEWS_LIMIT
    request = api.requests[0]
    assert request.url.path == "/top-news"
    assert request.url.params["source-country"] == "fr"
    assert request.url.params["language"] == "fr"
    assert request.url.params["max-news-per-cluster"] == "1"
    # Clé dans le header, jamais dans l'URL (qui finit dans les logs)
    assert request.headers["x-api-key"] == API_KEY
    assert API_KEY not in str(request.url)


def test_search_news_request():
    api = FakeApi(ok(search_payload([article(1), article(2)])))

    articles = asyncio.run(make_client(api).search_news("  élections  ", language="fr", number=50))

    assert [a.title for a in articles] == ["Titre 1", "Titre 2"]
    params = api.requests[0].url.params
    assert api.requests[0].url.path == "/search-news"
    assert params["text"] == "élections"
    assert params["language"] == "fr"
    # Nombre de résultats borné, quel que soit ce que demande l'appelant
    assert params["number"] == str(SEARCH_MAX_RESULTS)
    assert params["sort"] == "publish-time"


@pytest.mark.parametrize("query", ["ab", "   ", "x" * 101])
def test_search_news_rejects_invalid_query(query: str):
    api = FakeApi(ok({"news": []}))

    with pytest.raises(ValueError):
        asyncio.run(make_client(api).search_news(query))
    assert api.requests == []


# --- Erreurs ------------------------------------------------------------------------


def test_missing_key_makes_no_request():
    api = FakeApi(ok(top_news_payload([])))
    client = make_client(api, api_key=None)

    with pytest.raises(MissingApiKeyError):
        asyncio.run(client.get_top_news())
    with pytest.raises(MissingApiKeyError):
        asyncio.run(client.search_news("élections"))
    assert api.requests == []


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (402, QuotaExceededError),
        (429, QuotaExceededError),
        (401, NewsApiError),
        (500, NewsApiError),
    ],
)
def test_http_errors(status_code: int, error_type: type[NewsApiError]):
    api = FakeApi(lambda request: httpx.Response(status_code, json={"message": "erreur"}))

    with pytest.raises(error_type):
        asyncio.run(make_client(api).search_news("élections"))


def test_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("trop long", request=request)

    with pytest.raises(NewsApiTimeoutError):
        asyncio.run(make_client(FakeApi(handler)).search_news("élections"))


def test_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connexion refusée", request=request)

    with pytest.raises(NewsApiError):
        asyncio.run(make_client(FakeApi(handler)).get_top_news())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>pas du JSON</html>"),
        httpx.Response(200, json={"inattendu": True}),
        httpx.Response(200, json={"top_news": "pas une liste"}),
    ],
)
def test_invalid_response(response: httpx.Response):
    api = FakeApi(lambda request: response)

    with pytest.raises(InvalidResponseError):
        asyncio.run(make_client(api).get_top_news())


def test_api_key_never_logged(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)
    # httpx compris (ses logs d'URL sont coupés par l'app, on les réactive pour le test)
    caplog.set_level(logging.DEBUG, logger="httpx")
    responses = iter(
        [
            httpx.Response(
                200,
                json=top_news_payload([[article(1)]]),
                headers={"X-API-Quota-Request": "1.01", "X-API-Quota-Left": "48.99"},
            ),
            httpx.Response(402, json={"message": "quota"}),
        ]
    )
    client = make_client(FakeApi(lambda request: next(responses)))

    async def scenario() -> None:
        await client.get_top_news()
        with pytest.raises(QuotaExceededError) as exc_info:
            await client.search_news("élections")
        assert API_KEY not in str(exc_info.value)

    asyncio.run(scenario())

    # Les logs existent bien (quota, erreur, requêtes httpx)… sans jamais contenir la clé
    assert "1.01 point(s), reste 48.99" in caplog.text
    assert "Quota quotidien WorldNewsAPI épuisé" in caplog.text
    assert API_KEY not in caplog.text


# --- Cache et limitation de débit ---------------------------------------------------------


def test_top_news_cached_until_ttl():
    api = FakeApi(ok(top_news_payload([[article(1)]])))
    clock = FakeClock()
    client = make_client(api, clock, cache_ttl_seconds=3600)

    async def scenario() -> None:
        first = await client.get_top_news()
        clock.advance(3599)
        assert await client.get_top_news() == first
        assert len(api.requests) == 1
        clock.advance(2)
        await client.get_top_news()

    asyncio.run(scenario())
    assert len(api.requests) == 2


def test_concurrent_top_news_single_request():
    api = FakeApi(ok(top_news_payload([[article(1)]])))
    client = make_client(api)

    async def scenario() -> None:
        await asyncio.gather(client.get_top_news(), client.get_top_news())

    asyncio.run(scenario())
    assert len(api.requests) == 1


def test_top_news_failure_cached_briefly():
    responses = iter(
        [
            httpx.Response(402, json={"message": "quota"}),
            httpx.Response(200, json=top_news_payload([[article(1)]])),
        ]
    )
    api = FakeApi(lambda request: next(responses))
    clock = FakeClock()
    client = make_client(api, clock, failure_ttl_seconds=300)

    async def scenario() -> None:
        with pytest.raises(QuotaExceededError):
            await client.get_top_news()
        clock.advance(299)
        # Échec encore en cache : même erreur, sans nouvel appel
        with pytest.raises(QuotaExceededError):
            await client.get_top_news()
        assert len(api.requests) == 1
        clock.advance(2)
        assert len(await client.get_top_news()) == 1

    asyncio.run(scenario())
    assert len(api.requests) == 2


def test_requests_spaced_by_one_second():
    api = FakeApi(ok({"news": []}))
    clock = FakeClock()
    client = make_client(api, clock)

    async def scenario() -> None:
        await client.search_news("élections")
        clock.advance(0.3)
        await client.search_news("climat")

    asyncio.run(scenario())
    assert clock.sleeps == [pytest.approx(0.7)]


# --- Configuration -------------------------------------------------------------------


def test_settings_key_optional_and_hidden():
    base = {"jwt_secret": "x" * 32, "llm_model": "test"}

    assert Settings(_env_file=None, **base, worldnews_api_key="").worldnews_api_key is None
    settings = Settings(_env_file=None, **base, worldnews_api_key=API_KEY)
    assert settings.worldnews_api_key.get_secret_value() == API_KEY
    assert API_KEY not in repr(settings)
