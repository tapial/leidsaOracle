"""
Excel / CSV import service.

Orchestrates file reading, deduplication (by file hash and by draw date),
normalisation, and bulk insertion of lottery draw data from uploaded files.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from io import BytesIO
from pathlib import Path
from typing import Union

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Draw
from src.database.repository import DrawRepository, ImportLogRepository
from src.importer.excel_reader import ExcelReader, ExcelReadError
from src.scraper.scraper_service import ImportResult
from src.validator.normalizer import Normalizer
from src.validator.schemas import ValidatedDraw

logger = logging.getLogger(__name__)

# Chunk size for reading file bytes when computing the hash.
_HASH_CHUNK_SIZE = 8192


class ImporterService:
    """Service for importing lottery data from Excel/CSV files.

    Handles the full pipeline: file hash check, reading, normalisation,
    deduplication, bulk insert, and import log creation.

    Args:
        normalizer: Shared normalizer for data cleaning.
    """

    def __init__(self, normalizer: Normalizer) -> None:
        self._normalizer = normalizer
        self._reader = ExcelReader()

    async def import_excel(
        self,
        file: Union["UploadFile", Path],
        game_type: str,
        session: AsyncSession,
    ) -> ImportResult:
        """Import draws from an uploaded Excel/CSV file.

        Pipeline steps:
        1. Compute SHA-256 hash of the file contents.
        2. Check ``ImportLogRepository`` for a previous import with the same hash.
        3. Read the file via :class:`ExcelReader`.
        4. Normalise all rows via :class:`Normalizer`.
        5. Deduplicate against existing draws in the database.
        6. Bulk-insert new draws.
        7. Create/update an :class:`ImportLog` entry.

        Args:
            file: A FastAPI ``UploadFile``, or a local filesystem ``Path``.
            game_type: The game type to assign to all imported draws.
            session: Active async database session (caller manages the
                     transaction boundary).

        Returns:
            An :class:`ImportResult` summarising the import.
        """
        result = ImportResult()

        # ── Step 1: Read file bytes and compute hash ──────────────────
        file_bytes, file_name = await self._read_file_bytes(file)
        file_hash = self._compute_sha256(file_bytes)

        logger.info(
            "Importing file '%s' (SHA-256: %s, %d bytes) for game %s.",
            file_name, file_hash[:16], len(file_bytes), game_type,
        )

        # ── Step 2: Check for duplicate import ────────────────────────
        existing_log = await ImportLogRepository.find_by_hash(session, file_hash)
        if existing_log is not None:
            logger.info(
                "File already imported (import_log_id=%d, hash=%s). Skipping.",
                existing_log.id, file_hash[:16],
            )
            result.errors.append(
                f"File already imported on "
                f"{existing_log.started_at.isoformat() if existing_log.started_at else 'unknown date'} "
                f"(import log #{existing_log.id})."
            )
            return result

        # ── Step 3: Create import log ─────────────────────────────────
        import_log = await ImportLogRepository.create_log(
            session,
            source_type="excel",
            source_identifier=file_name,
            file_hash=file_hash,
            status="running",
        )

        try:
            # ── Step 4: Read file ─────────────────────────────────────
            raw_results = self._reader.read_file(
                BytesIO(file_bytes), game_type=game_type
            )
            result.draws_found = len(raw_results)

            if not raw_results:
                logger.warning("No rows found in file '%s'.", file_name)
                await ImportLogRepository.update_log(
                    session,
                    import_log.id,
                    status="completed",
                    draws_found=0,
                    completed_at=datetime.datetime.now(datetime.timezone.utc),
                )
                return result

            # ── Step 5: Normalise ─────────────────────────────────────
            validated, norm_errors = self._normalizer.normalize_batch(
                raw_results, game_type=game_type
            )
            for idx, msg in norm_errors:
                result.errors.append(f"Row {idx}: {msg}")

            if not validated:
                logger.warning(
                    "No valid rows after normalisation for file '%s'.", file_name
                )
                await ImportLogRepository.update_log(
                    session,
                    import_log.id,
                    status="completed",
                    draws_found=result.draws_found,
                    draws_skipped=result.draws_found,
                    error_message="; ".join(result.errors[:5]),
                    completed_at=datetime.datetime.now(datetime.timezone.utc),
                )
                return result

            # ── Step 6: Deduplicate ───────────────────────────────────
            new_draws = await self._deduplicate(validated, game_type, session)
            result.draws_skipped = len(validated) - len(new_draws)

            if not new_draws:
                logger.info(
                    "All %d draws from '%s' already exist.", len(validated), file_name
                )
                await ImportLogRepository.update_log(
                    session,
                    import_log.id,
                    status="completed",
                    draws_found=result.draws_found,
                    draws_skipped=result.draws_skipped,
                    completed_at=datetime.datetime.now(datetime.timezone.utc),
                )
                return result

            # ── Step 7: Bulk insert ───────────────────────────────────
            draw_models = [
                Draw(
                    game_type=v.game_type,
                    draw_date=v.draw_date,
                    numbers=v.numbers,
                    bonus_number=v.bonus_number,
                    source=v.source or "excel",
                    import_log_id=import_log.id,
                )
                for v in new_draws
            ]

            inserted = await DrawRepository.bulk_insert_draws(session, draw_models)
            result.draws_imported = inserted

            logger.info(
                "File '%s': found=%d, imported=%d, skipped=%d, errors=%d.",
                file_name, result.draws_found, result.draws_imported,
                result.draws_skipped, len(result.errors),
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

        except ExcelReadError as exc:
            error_msg = f"Failed to read file '{file_name}': {exc}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            await ImportLogRepository.update_log(
                session,
                import_log.id,
                status="failed",
                draws_found=result.draws_found,
                error_message=error_msg[:1000],
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )

        except Exception as exc:
            error_msg = f"Unexpected error importing '{file_name}': {exc}"
            logger.error(error_msg, exc_info=True)
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

    # ── Internal helpers ──────────────────────────────────────────────

    async def _read_file_bytes(
        self,
        file: Union["UploadFile", Path],
    ) -> tuple[bytes, str]:
        """Read all bytes from a file and return (bytes, filename).

        Supports both FastAPI UploadFile objects and pathlib Paths.
        """
        if isinstance(file, Path):
            file_bytes = file.read_bytes()
            file_name = file.name
        else:
            # FastAPI UploadFile.
            file_bytes = await file.read()
            file_name = getattr(file, "filename", "uploaded_file") or "uploaded_file"
            # Reset position in case caller needs to re-read.
            await file.seek(0)

        return file_bytes, file_name

    @staticmethod
    def _compute_sha256(data: bytes) -> str:
        """Compute the SHA-256 hex digest of raw bytes."""
        hasher = hashlib.sha256()
        # Process in chunks for memory efficiency on large files.
        offset = 0
        while offset < len(data):
            chunk = data[offset: offset + _HASH_CHUNK_SIZE]
            hasher.update(chunk)
            offset += _HASH_CHUNK_SIZE
        return hasher.hexdigest()

    async def _deduplicate(
        self,
        validated: list[ValidatedDraw],
        game_type: str,
        session: AsyncSession,
    ) -> list[ValidatedDraw]:
        """Remove draws that already exist in the database or are duplicated within the batch."""
        # Collect all dates and check existence in one pass.
        all_dates = [v.draw_date for v in validated]

        existing_dates: set[datetime.date] = set()
        batch_size = 500
        for i in range(0, len(all_dates), batch_size):
            batch = all_dates[i: i + batch_size]
            for d in batch:
                if await DrawRepository.draw_exists(session, game_type, d):
                    existing_dates.add(d)

        # Filter, also removing intra-batch duplicates.
        new_draws: list[ValidatedDraw] = []
        seen_dates: set[datetime.date] = set()

        for v in validated:
            if v.draw_date in existing_dates:
                continue
            if v.draw_date in seen_dates:
                continue
            seen_dates.add(v.draw_date)
            new_draws.append(v)

        return new_draws
