"""
Scraper orchestration service.

Coordinates the HTTP client, site-specific parsers, normalizer, and
database repositories to scrape lottery results from Dominican lottery
websites and persist them.

Supports:
- Scraping the latest results.
- Scraping historical results with pagination.
- Full-history backfill.
- Automatic fallback from primary to secondary data source.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.constants import get_game
from src.config.settings import Settings
from src.database.models import Draw
from src.database.repository import DrawRepository, ImportLogRepository
from src.scraper.base_parser import BaseDrawParser
from src.scraper.client import ScraperClient, ScraperError
from src.scraper.conectate_parser import ConectateParser
from src.scraper.loterias_dom_parser import LoteriasDomParser
from src.validator.normalizer import Normalizer, NormalizationError
from src.validator.schemas import RawDrawResult, ValidatedDraw

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Summary of a single scrape/import operation."""

    draws_found: int = 0
    draws_imported: int = 0
    draws_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def merge(self, other: ImportResult) -> None:
        """Accumulate counts from another result into this one."""
        self.draws_found += other.draws_found
        self.draws_imported += other.draws_imported
        self.draws_skipped += other.draws_skipped
        self.errors.extend(other.errors)


class ScraperService:
    """High-level facade for scraping lottery data from the web.

    Tries the **primary** source (loteriasdominicanas.com) first; if it
    fails, automatically retries against the **fallback** source
    (conectate.com.do).

    Args:
        settings: Application settings (provides URLs, timeouts, etc.).
        normalizer: The shared normalizer instance for data cleaning.
    """

    def __init__(self, settings: Settings, normalizer: Normalizer) -> None:
        self._settings = settings
        self._normalizer = normalizer

    # ── Public API ────────────────────────────────────────────────────

    async def scrape_latest(
        self,
        game_type: str,
        session: AsyncSession,
    ) -> ImportResult:
        """Scrape the most recent draw results for a game.

        Fetches the results page, parses it, normalises the data, and
        inserts any new draws into the database.

        Args:
            game_type: Game identifier (e.g. ``"loto"``).
            session: Active async database session.

        Returns:
            An :class:`ImportResult` summarising what happened.
        """
        game_def = get_game(game_type)

        # Create an import log entry.
        import_log = await ImportLogRepository.create_log(
            session,
            source_type="scraper",
            source_identifier=f"latest:{game_type}",
            status="running",
        )

        result = ImportResult()

        try:
            raw_results = await self._fetch_with_fallback(
                game_def.scraper_path,
                game_type,
                historical=False,
            )
            result = await self._process_and_store(
                raw_results, game_type, session, import_log.id
            )

            await ImportLogRepository.update_log(
                session,
                import_log.id,
                status="completed",
                draws_found=result.draws_found,
                draws_imported=result.draws_imported,
                draws_skipped=result.draws_skipped,
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )

        except Exception as exc:
            error_msg = f"Scrape latest failed for {game_type}: {exc}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            await ImportLogRepository.update_log(
                session,
                import_log.id,
                status="failed",
                error_message=error_msg[:1000],
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )

        return result

    async def scrape_historical(
        self,
        game_type: str,
        session: AsyncSession,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
    ) -> ImportResult:
        """Scrape historical results, optionally filtered by date range.

        Iterates through paginated pages until no more data is available
        or the date range is exhausted.

        Args:
            game_type: Game identifier.
            session: Active async database session.
            date_from: Earliest draw date to include (inclusive).
            date_to: Latest draw date to include (inclusive).

        Returns:
            An :class:`ImportResult` with aggregate counts.
        """
        game_def = get_game(game_type)

        import_log = await ImportLogRepository.create_log(
            session,
            source_type="scraper",
            source_identifier=f"historical:{game_type}",
            status="running",
        )

        result = ImportResult()
        page = 1
        max_pages = 200  # Safety limit.

        try:
            while page <= max_pages:
                raw_results, has_more = await self._fetch_historical_page(
                    game_def.scraper_path,
                    game_type,
                    page=page,
                )

                if not raw_results:
                    logger.info("No results on page %d, stopping.", page)
                    break

                # Filter by date range if specified.
                if date_from or date_to:
                    raw_results = self._filter_by_date_range(
                        raw_results, date_from, date_to
                    )

                page_result = await self._process_and_store(
                    raw_results, game_type, session, import_log.id
                )
                result.merge(page_result)

                if not has_more:
                    logger.info("No more pages after page %d.", page)
                    break

                # Check if we've gone past the date range.
                if date_from and raw_results:
                    oldest = self._get_oldest_date(raw_results)
                    if oldest and oldest < date_from:
                        logger.info("Reached date_from boundary, stopping.")
                        break

                page += 1

                # Polite delay between page fetches.
                await asyncio.sleep(self._settings.scraper.delay)

            await ImportLogRepository.update_log(
                session,
                import_log.id,
                status="completed",
                draws_found=result.draws_found,
                draws_imported=result.draws_imported,
                draws_skipped=result.draws_skipped,
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )

        except Exception as exc:
            error_msg = f"Scrape historical failed for {game_type}: {exc}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            await ImportLogRepository.update_log(
                session,
                import_log.id,
                status="failed",
                draws_found=result.draws_found,
                draws_imported=result.draws_imported,
                draws_skipped=result.draws_skipped,
                error_message=error_msg[:1000],
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )

        return result

    async def scrape_full_history(
        self,
        game_type: str,
        session: AsyncSession,
    ) -> ImportResult:
        """Scrape the entire available history for a game.

        Convenience wrapper that calls :meth:`scrape_historical` with no
        date bounds.

        Args:
            game_type: Game identifier.
            session: Active async database session.

        Returns:
            An :class:`ImportResult` with aggregate counts.
        """
        logger.info("Starting full history scrape for %s", game_type)
        return await self.scrape_historical(
            game_type, session, date_from=None, date_to=None
        )

    # ── Fetch with fallback ───────────────────────────────────────────

    async def _fetch_with_fallback(
        self,
        path: str,
        game_type: str,
        *,
        historical: bool,
        page: int = 1,
    ) -> list[RawDrawResult]:
        """Try primary source, fall back to secondary on failure.

        Returns raw (unparsed) results from whichever source succeeds.
        """
        game_def = get_game(game_type)

        # Primary: loteriasdominicanas.com
        try:
            return await self._fetch_and_parse(
                base_url=self._settings.scraper.base_url,
                path=path,
                game_def=game_def,
                parser_cls=LoteriasDomParser,
                historical=historical,
                page=page,
            )
        except ScraperError as exc:
            logger.warning(
                "Primary source failed for %s: %s. Trying fallback.", game_type, exc
            )

        # Fallback: conectate.com.do
        fallback_path = ConectateParser.translate_path(path)
        return await self._fetch_and_parse(
            base_url=self._settings.scraper.fallback_url,
            path=fallback_path,
            game_def=game_def,
            parser_cls=ConectateParser,
            historical=historical,
            page=page,
        )

    async def _fetch_historical_page(
        self,
        path: str,
        game_type: str,
        page: int,
    ) -> tuple[list[RawDrawResult], bool]:
        """Fetch a single historical page with fallback support.

        Returns (raw_results, has_more_pages).
        """
        game_def = get_game(game_type)

        # Primary.
        try:
            return await self._fetch_and_parse_historical(
                base_url=self._settings.scraper.base_url,
                path=path,
                game_def=game_def,
                parser_cls=LoteriasDomParser,
                page=page,
            )
        except ScraperError as exc:
            logger.warning(
                "Primary historical fetch failed (page %d): %s. Trying fallback.",
                page, exc,
            )

        # Fallback.
        fallback_path = ConectateParser.translate_path(path)
        return await self._fetch_and_parse_historical(
            base_url=self._settings.scraper.fallback_url,
            path=fallback_path,
            game_def=game_def,
            parser_cls=ConectateParser,
            page=page,
        )

    async def _fetch_and_parse(
        self,
        base_url: str,
        path: str,
        game_def: object,
        parser_cls: type[BaseDrawParser],
        *,
        historical: bool,
        page: int = 1,
    ) -> list[RawDrawResult]:
        """Fetch HTML and parse it using the given parser class."""
        scraper_settings = self._settings.scraper
        async with ScraperClient(
            base_url=base_url,
            timeout=scraper_settings.timeout,
            max_retries=scraper_settings.max_retries,
            delay=scraper_settings.delay,
        ) as client:
            params: dict[str, str] | None = None
            if page > 1:
                params = {"page": str(page)}

            html = await client.fetch_page(path, params=params)

        parser = parser_cls(game_def)  # type: ignore[arg-type]

        if historical:
            results, _ = parser.parse_historical_page(html)
            return results
        else:
            return parser.parse_results_page(html)

    async def _fetch_and_parse_historical(
        self,
        base_url: str,
        path: str,
        game_def: object,
        parser_cls: type[BaseDrawParser],
        page: int,
    ) -> tuple[list[RawDrawResult], bool]:
        """Fetch and parse a historical page, returning (results, has_more)."""
        scraper_settings = self._settings.scraper
        async with ScraperClient(
            base_url=base_url,
            timeout=scraper_settings.timeout,
            max_retries=scraper_settings.max_retries,
            delay=scraper_settings.delay,
        ) as client:
            params: dict[str, str] | None = None
            if page > 1:
                params = {"page": str(page)}

            html = await client.fetch_page(path, params=params)

        parser = parser_cls(game_def)  # type: ignore[arg-type]
        return parser.parse_historical_page(html)

    # ── Processing pipeline ───────────────────────────────────────────

    async def _process_and_store(
        self,
        raw_results: list[RawDrawResult],
        game_type: str,
        session: AsyncSession,
        import_log_id: int,
    ) -> ImportResult:
        """Normalise, deduplicate, and bulk-insert raw results.

        Args:
            raw_results: Raw parsed results.
            game_type: Game identifier.
            session: Active database session.
            import_log_id: FK to the import log tracking this operation.

        Returns:
            An ImportResult describing what was processed.
        """
        result = ImportResult()
        result.draws_found = len(raw_results)

        if not raw_results:
            return result

        # Normalise.
        validated, norm_errors = self._normalizer.normalize_batch(
            raw_results, game_type=game_type
        )
        for idx, msg in norm_errors:
            result.errors.append(f"Row {idx}: {msg}")

        if not validated:
            logger.warning("No valid results after normalization for %s.", game_type)
            return result

        # Deduplicate against existing DB records.
        dates = [v.draw_date for v in validated]
        existing_dates = await DrawRepository.draw_exists(
            session, game_type, dates[0]
        ) if len(dates) == 1 else set()

        # For batch dedup, get all existing dates at once.
        if len(dates) > 1:
            existing_dates_set: set[datetime.date] = set()
            # Check in batches to avoid huge IN clauses.
            batch_size = 500
            for i in range(0, len(dates), batch_size):
                batch_dates = dates[i: i + batch_size]
                for d in batch_dates:
                    if await DrawRepository.draw_exists(session, game_type, d):
                        existing_dates_set.add(d)
            existing_dates = existing_dates_set
        else:
            existing_dates = set()
            if dates and await DrawRepository.draw_exists(session, game_type, dates[0]):
                existing_dates.add(dates[0])

        # Filter to only new draws.
        new_draws: list[ValidatedDraw] = []
        seen_dates: set[datetime.date] = set()  # De-dup within this batch.

        for v in validated:
            if v.draw_date in existing_dates:
                result.draws_skipped += 1
                continue
            if v.draw_date in seen_dates:
                result.draws_skipped += 1
                continue
            seen_dates.add(v.draw_date)
            new_draws.append(v)

        if not new_draws:
            result.draws_skipped = len(validated)
            logger.info("All %d draws already exist for %s.", len(validated), game_type)
            return result

        # Build ORM objects and bulk insert.
        draw_models = [
            Draw(
                game_type=v.game_type,
                draw_date=v.draw_date,
                numbers=v.numbers,
                bonus_number=v.bonus_number,
                source=v.source or "scraper",
                import_log_id=import_log_id,
            )
            for v in new_draws
        ]

        inserted = await DrawRepository.bulk_insert_draws(session, draw_models)
        result.draws_imported = inserted
        result.draws_skipped = len(validated) - inserted - len(norm_errors)

        logger.info(
            "Processed %d results for %s: %d imported, %d skipped, %d errors.",
            result.draws_found, game_type,
            result.draws_imported, result.draws_skipped, len(result.errors),
        )

        return result

    # ── Utility ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_date_str(date_str: str) -> datetime.date | None:
        """Best-effort parse of a date_str to a date object."""
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _filter_by_date_range(
        results: list[RawDrawResult],
        date_from: datetime.date | None,
        date_to: datetime.date | None,
    ) -> list[RawDrawResult]:
        """Filter raw results by date bounds (best-effort, skips unparseable dates)."""
        filtered: list[RawDrawResult] = []
        for r in results:
            parsed = ScraperService._parse_date_str(r.date_str)
            if parsed is None:
                # Can't parse date — include it and let normalization handle it.
                filtered.append(r)
                continue
            if date_from and parsed < date_from:
                continue
            if date_to and parsed > date_to:
                continue
            filtered.append(r)
        return filtered

    @staticmethod
    def _get_oldest_date(results: list[RawDrawResult]) -> datetime.date | None:
        """Find the oldest date among raw results (best-effort)."""
        dates: list[datetime.date] = []
        for r in results:
            parsed = ScraperService._parse_date_str(r.date_str)
            if parsed is not None:
                dates.append(parsed)
        return min(dates) if dates else None
