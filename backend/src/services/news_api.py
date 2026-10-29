"""Client WorldNewsAPI (/top-news, /search-news) aux sorties simplifiées pour le LLM.

Plan gratuit : 50 points par jour, 1 requête par seconde, 1 requête simultanée. Le client
sérialise donc ses appels, les espace d'au moins une seconde et garde les actualités du jour
en cache. Les réponses brutes (texte intégral, images, auteurs…) ne sortent jamais d'ici :
on ne renvoie que titre, résumé tronqué, URL, source et date, pour limiter les tokens.
"""

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.worldnewsapi.com"
# Court : la création d'un chat attend /top-news, mieux vaut un chat sans actus qu'une attente
TIMEOUT_SECONDS = 5.0
# Limite du plan gratuit : 1 requête par seconde
MIN_INTERVAL_SECONDS = 1.0
# Nombre d'actualités du jour retenues (une par sujet) et longueur max d'un résumé :
# environ 1 000 tokens au total, assez pour couvrir l'actualité sans alourdir chaque appel
TOP_NEWS_LIMIT = 8
SUMMARY_MAX_CHARS = 300
# /search-news : bornes de la doc pour `text`, nombre de résultats volontairement bas (quota)
QUERY_MIN_LENGTH = 3
QUERY_MAX_LENGTH = 100
SEARCH_MAX_RESULTS = 5


# --- Erreurs ------------------------------------------------------------------------
# Les messages sont lisibles par un humain comme par le modèle, et ne contiennent jamais la clé.


class NewsApiError(Exception):
    """Échec d'un appel à WorldNewsAPI (clé refusée, panne, erreur réseau…)."""


class MissingApiKeyError(NewsApiError):
    """WORLDNEWS_API_KEY n'est pas configurée : aucun appel n'est tenté."""


class QuotaExceededError(NewsApiError):
    """Quota quotidien épuisé (402) ou trop de requêtes (429)."""


class NewsApiTimeoutError(NewsApiError):
    """WorldNewsAPI n'a pas répondu à temps."""


class InvalidResponseError(NewsApiError):
    """Réponse illisible ou au format inattendu."""


# --- Sorties simplifiées -------------------------------------------------------------


class NewsArticle(BaseModel):
    """Article réduit à ce dont le LLM a besoin."""

    title: str
    summary: str
    url: str
    source: str
    published_at: datetime | None


# --- Format brut de l'API (validé, jamais exposé) -------------------------------------
# Tous les champs d'un article sont facultatifs dans la doc : un article incomplet est
# écarté à la simplification au lieu de faire échouer toute la réponse.


class _RawArticle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    summary: str | None = None
    text: str | None = None
    url: str | None = None
    publish_date: str | None = None


class _RawCluster(BaseModel):
    news: list[_RawArticle]


class _TopNewsResponse(BaseModel):
    top_news: list[_RawCluster]


class _SearchNewsResponse(BaseModel):
    news: list[_RawArticle]


def _truncate(text: str, max_chars: int) -> str:
    """Espaces normalisés, coupe au dernier mot entier avant la limite."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


def _parse_publish_date(value: str | None) -> datetime | None:
    # Format de la doc « YYYY-MM-DD HH:MM:SS », sans fuseau : on le lit en UTC
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _simplify(raw: _RawArticle) -> NewsArticle | None:
    """Article simplifié, ou None s'il manque un titre ou une URL http(s)."""
    title = (raw.title or "").strip()
    url = (raw.url or "").strip()
    parts = urlsplit(url)
    if not title or parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    # Résumé absent de certains articles : début du texte intégral à la place
    summary = _truncate(raw.summary or raw.text or "", SUMMARY_MAX_CHARS)
    return NewsArticle(
        title=_truncate(title, SUMMARY_MAX_CHARS),
        summary=summary or "Résumé indisponible.",
        url=url,
        # L'API ne donne pas le nom du média : on affiche son domaine (ex. lemonde.fr)
        source=parts.hostname.removeprefix("www."),
        published_at=_parse_publish_date(raw.publish_date),
    )


# --- Client --------------------------------------------------------------------------


class NewsClient:
    """Client WorldNewsAPI avec limitation de débit et cache des actualités du jour.

    Une instance pour toute l'application (voir `get_news_client`) : le cache et la
    limitation de débit vivent en mémoire, dans un seul processus.
    """

    def __init__(
        self,
        api_key: str | None,
        *,
        country: str = "fr",
        language: str = "fr",
        cache_ttl_seconds: float = 3600,
        failure_ttl_seconds: float = 300,
        min_interval_seconds: float = MIN_INTERVAL_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._api_key = api_key
        self._country = country
        self._language = language
        self._cache_ttl = cache_ttl_seconds
        self._failure_ttl = failure_ttl_seconds
        self._min_interval = min_interval_seconds
        # Injectés par les tests : transport simulé (aucun appel réseau) et horloge contrôlée
        self._transport = transport
        self._clock = clock
        self._sleep = sleep

        # Une seule requête à la fois vers l'API (1 requête simultanée sur le plan gratuit)
        self._request_lock = asyncio.Lock()
        self._last_request_at: float | None = None
        # Deux créations de chat simultanées ne déclenchent qu'un appel à /top-news
        self._top_news_lock = asyncio.Lock()
        # (expiration, actualités) en cas de succès, (expiration, erreur) en cas d'échec
        self._top_news_cache: tuple[float, list[NewsArticle] | NewsApiError] | None = None

    async def get_top_news(self) -> list[NewsArticle]:
        """Actualités du jour du pays configuré, un article par sujet (les plus couverts d'abord).

        Les succès sont gardés en cache `cache_ttl_seconds`. Les échecs (quota, panne) le sont
        `failure_ttl_seconds` : inutile de retenter à chaque création de chat un appel voué à
        l'échec, qui consommerait du quota ou ferait attendre l'utilisateur jusqu'au timeout.
        """
        self._require_key()
        async with self._top_news_lock:
            if self._top_news_cache and self._clock() < self._top_news_cache[0]:
                cached = self._top_news_cache[1]
                if isinstance(cached, NewsApiError):
                    # Traceback remis à zéro : sinon elle s'allonge à chaque nouvelle levée
                    raise cached.with_traceback(None)
                return cached

            try:
                payload = await self._get(
                    "/top-news",
                    {
                        "source-country": self._country,
                        "language": self._language,
                        # Un article par sujet suffit : réponse plus légère
                        "max-news-per-cluster": 1,
                    },
                )
                response = self._parse(_TopNewsResponse, payload, "/top-news")
            except NewsApiError as exc:
                self._top_news_cache = (self._clock() + self._failure_ttl, exc)
                raise

            articles: list[NewsArticle] = []
            for cluster in response.top_news:
                article = next(filter(None, map(_simplify, cluster.news)), None)
                if article:
                    articles.append(article)
                if len(articles) == TOP_NEWS_LIMIT:
                    break
            self._top_news_cache = (self._clock() + self._cache_ttl, articles)
            return articles

    async def search_news(
        self, query: str, *, language: str | None = None, number: int = SEARCH_MAX_RESULTS
    ) -> list[NewsArticle]:
        """Articles correspondant à `query`, les plus récents d'abord (pas de cache)."""
        self._require_key()
        query = query.strip()
        if not QUERY_MIN_LENGTH <= len(query) <= QUERY_MAX_LENGTH:
            raise ValueError(
                f"La recherche doit faire de {QUERY_MIN_LENGTH} à {QUERY_MAX_LENGTH} caractères."
            )
        params: dict[str, str | int] = {
            "text": query,
            "number": max(1, min(number, SEARCH_MAX_RESULTS)),
            "sort": "publish-time",
            "sort-direction": "DESC",
        }
        if language:
            params["language"] = language
        payload = await self._get("/search-news", params)
        response = self._parse(_SearchNewsResponse, payload, "/search-news")
        return [article for article in map(_simplify, response.news) if article]

    def _require_key(self) -> None:
        if not self._api_key:
            raise MissingApiKeyError(
                "Actualités indisponibles : clé WorldNewsAPI non configurée."
            )

    async def _get(self, path: str, params: dict[str, str | int]) -> object:
        """Requête GET authentifiée, sérialisée et espacée ; renvoie le JSON décodé."""
        async with self._request_lock:
            if self._last_request_at is not None:
                wait = self._last_request_at + self._min_interval - self._clock()
                if wait > 0:
                    await self._sleep(wait)
            try:
                # Clé dans le header (recommandation de la doc) : elle n'apparaît ni dans l'URL
                # ni, donc, dans les logs de httpx qui journalisent chaque URL appelée.
                async with httpx.AsyncClient(
                    base_url=BASE_URL,
                    headers={"x-api-key": self._api_key or ""},
                    timeout=TIMEOUT_SECONDS,
                    transport=self._transport,
                ) as client:
                    response = await client.get(path, params=params)
            except httpx.TimeoutException as exc:
                error = NewsApiTimeoutError("WorldNewsAPI ne répond pas (délai dépassé).")
                raise self._fail(path, error) from exc
            except httpx.HTTPError as exc:
                raise self._fail(path, NewsApiError("WorldNewsAPI est injoignable.")) from exc
            finally:
                self._last_request_at = self._clock()

        self._log_quota(path, response)
        if response.status_code == 402:
            raise self._fail(path, QuotaExceededError("Quota quotidien WorldNewsAPI épuisé."))
        if response.status_code == 429:
            error = QuotaExceededError("Trop de requêtes vers WorldNewsAPI, réessaie plus tard.")
            raise self._fail(path, error)
        if response.status_code in (401, 403):
            raise self._fail(path, NewsApiError("Clé WorldNewsAPI refusée."))
        if response.is_error:
            raise self._fail(
                path, NewsApiError(f"WorldNewsAPI a renvoyé une erreur {response.status_code}.")
            )
        try:
            return response.json()
        except ValueError as exc:
            error = InvalidResponseError("Réponse illisible de WorldNewsAPI.")
            raise self._fail(path, error) from exc

    def _parse[T: BaseModel](self, model: type[T], payload: object, path: str) -> T:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            error = InvalidResponseError("Réponse inattendue de WorldNewsAPI.")
            raise self._fail(path, error) from exc

    @staticmethod
    def _fail(path: str, error: NewsApiError) -> NewsApiError:
        # Seuls l'endpoint et le message sont journalisés : ni clé, ni paramètres, ni réponse
        logger.warning("WorldNewsAPI %s : %s", path, error)
        return error

    @staticmethod
    def _log_quota(path: str, response: httpx.Response) -> None:
        # Headers documentés par WorldNewsAPI : coût réel de chaque appel et points restants
        cost = response.headers.get("X-API-Quota-Request")
        left = response.headers.get("X-API-Quota-Left")
        if cost is not None or left is not None:
            logger.info("WorldNewsAPI %s : %s point(s), reste %s", path, cost, left)


@lru_cache
def get_news_client() -> NewsClient:
    """Instance unique (dépendance FastAPI) : le cache est partagé entre les requêtes."""
    settings = get_settings()
    api_key = settings.worldnews_api_key
    return NewsClient(
        api_key.get_secret_value() if api_key else None,
        country=settings.news_country,
        language=settings.news_language,
        cache_ttl_seconds=settings.top_news_cache_ttl_seconds,
        failure_ttl_seconds=settings.top_news_failure_ttl_seconds,
    )
