"""
Async HTTP client for scraping Dominican lottery websites.

Provides retry logic with exponential backoff and jitter, automatic
User-Agent header injection, and a clean async context-manager lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; LeidsaOracle/1.0)"


class ScraperError(Exception):
    """Raised when a page fetch fails after exhausting all retries."""


class ScraperClient:
    """Reusable async HTTP client with retry semantics.

    The underlying ``httpx.AsyncClient`` is created lazily on first use
    and should be released by calling :meth:`close` (or using this object
    as an async context manager).

    Args:
        base_url: Root URL prepended to every *path* passed to :meth:`fetch_page`.
        timeout: Per-request timeout in seconds.
        max_retries: Total attempts before giving up (includes the initial try).
        delay: Base delay in seconds for the first backoff interval.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 3,
        delay: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._delay = delay
        self._client: httpx.AsyncClient | None = None

    # ── Async context-manager protocol ────────────────────────────────

    async def __aenter__(self) -> ScraperClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    # ── Internal helpers ──────────────────────────────────────────────

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create and return the shared ``httpx.AsyncClient``."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-DO,es;q=0.9,en;q=0.5",
                },
                follow_redirects=True,
            )
            logger.debug("HTTP client created for %s", self._base_url)
        return self._client

    # ── Public API ────────────────────────────────────────────────────

    async def fetch_page(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> str:
        """Fetch an HTML page, retrying on transient failures.

        Uses **exponential backoff with jitter** to avoid thundering-herd
        effects when multiple scrapers run concurrently.

        Args:
            path: URL path relative to the base URL (e.g. ``"/leidsa/loto-mas"``).
            params: Optional query-string parameters.

        Returns:
            The response body as a string.

        Raises:
            ScraperError: After all retry attempts are exhausted.
        """
        client = await self._ensure_client()
        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                logger.debug(
                    "Fetching %s%s (attempt %d/%d)",
                    self._base_url,
                    path,
                    attempt,
                    self._max_retries,
                )
                response = await client.get(path, params=params)
                response.raise_for_status()
                logger.info(
                    "Fetched %s%s (%d bytes, status %d)",
                    self._base_url,
                    path,
                    len(response.text),
                    response.status_code,
                )
                return response.text

            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "Timeout fetching %s%s (attempt %d/%d): %s",
                    self._base_url, path, attempt, self._max_retries, exc,
                )

            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                # Don't retry on client errors (4xx) except 429 Too Many Requests.
                if 400 <= status < 500 and status != 429:
                    raise ScraperError(
                        f"HTTP {status} for {self._base_url}{path}: {exc}"
                    ) from exc
                logger.warning(
                    "HTTP %d fetching %s%s (attempt %d/%d)",
                    status, self._base_url, path, attempt, self._max_retries,
                )

            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "Network error fetching %s%s (attempt %d/%d): %s",
                    self._base_url, path, attempt, self._max_retries, exc,
                )

            # Exponential backoff with full jitter.
            if attempt < self._max_retries:
                backoff = self._delay * (2 ** (attempt - 1))
                jitter = random.uniform(0, backoff)  # noqa: S311
                wait_time = backoff + jitter
                logger.debug("Retrying in %.2f seconds...", wait_time)
                await asyncio.sleep(wait_time)

        raise ScraperError(
            f"Failed to fetch {self._base_url}{path} after "
            f"{self._max_retries} attempts: {last_error}"
        )

    async def close(self) -> None:
        """Close the underlying HTTP client and release resources."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("HTTP client closed for %s", self._base_url)
            self._client = None
