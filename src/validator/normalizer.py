"""
Normalizer that converts ``RawDrawResult`` instances into ``ValidatedDraw``
objects, applying date parsing, type coercion, sorting, and validation
against the game definition.

Supports the diverse date formats and Spanish month names commonly found
in Dominican Republic lottery data sources.
"""

from __future__ import annotations

import datetime
import logging
import re

from src.config.constants import get_game
from src.validator.schemas import RawDrawResult, ValidatedDraw

logger = logging.getLogger(__name__)

# ── Date parsing helpers ─────────────────────────────────────────────────

# Common date formats found on Dominican lottery sites and spreadsheets.
_DATE_FORMATS: list[str] = [
    "%d-%m-%Y",     # 15-01-2024
    "%Y-%m-%d",     # 2024-01-15
    "%d/%m/%Y",     # 15/01/2024
]

# Spanish month names -> month numbers for manual fallback parsing.
_SPANISH_MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

# Pre-compiled regex for Spanish date patterns like "15 de enero de 2024"
# or "15 enero 2024".
_SPANISH_DATE_RE = re.compile(
    r"(\d{1,2})\s+(?:de\s+)?(\w+)\s+(?:de\s+)?(\d{4})",
    re.IGNORECASE,
)


class NormalizationError(Exception):
    """Raised when a raw draw result cannot be normalised."""


class Normalizer:
    """Stateless transformer from raw scraped data to validated draws.

    Usage::

        normalizer = Normalizer()
        validated = normalizer.normalize(raw_result, game_type="loto")
    """

    @staticmethod
    def normalize(raw: RawDrawResult, game_type: str) -> ValidatedDraw:
        """Normalise a single raw draw result into a validated draw.

        Processing steps:
        1. Parse the date string into a ``datetime.date``.
        2. Parse number strings, strip whitespace, convert to ``int``.
        3. Sort numbers ascending.
        4. Parse optional bonus number.
        5. Construct a ``ValidatedDraw`` which validates against game rules.

        Args:
            raw: The unprocessed draw result from a scraper or file reader.
            game_type: Game identifier (e.g. ``"loto"``, ``"loto_pool"``).

        Returns:
            A fully validated ``ValidatedDraw`` instance.

        Raises:
            ValueError: If the data cannot be parsed or fails validation,
                with a descriptive message indicating the root cause.
        """
        # Ensure the game_type is valid early for a clear error message.
        game_def = get_game(game_type)

        # --- Parse date ---
        draw_date = Normalizer._parse_date(raw.date_str)

        # --- Parse numbers ---
        numbers = Normalizer._parse_numbers(raw.numbers)

        # --- Sort ascending ---
        numbers.sort()

        # --- Parse bonus ---
        bonus_number: int | None = None
        if raw.bonus is not None:
            bonus_number = Normalizer._parse_single_number(raw.bonus, label="bonus")

        # --- Build ValidatedDraw (triggers model_validator) ---
        return ValidatedDraw(
            game_type=game_type,
            draw_date=draw_date,
            numbers=numbers,
            bonus_number=bonus_number,
            source=raw.source,
        )

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str) -> datetime.date:
        """Parse a date string in one of the supported formats.

        Supported formats:
        - ``DD-MM-YYYY``
        - ``YYYY-MM-DD``
        - ``DD/MM/YYYY``
        - Spanish month names: ``"15 de enero de 2024"``, ``"15 enero 2024"``

        Args:
            date_str: Raw date string from the source.

        Returns:
            Parsed ``datetime.date``.

        Raises:
            ValueError: If the date cannot be parsed in any known format.
        """
        text = date_str.strip()

        # Try standard strptime formats first.
        for fmt in _DATE_FORMATS:
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue

        # Fallback: Spanish date like "15 de enero de 2024" or "15 enero 2024".
        match = _SPANISH_DATE_RE.match(text)
        if match:
            day_str, month_name, year_str = match.groups()
            month_num = _SPANISH_MONTHS.get(month_name.lower())
            if month_num is not None:
                try:
                    return datetime.date(int(year_str), month_num, int(day_str))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid date components day={day_str}, month={month_name}, "
                        f"year={year_str}: {exc}"
                    ) from exc

        raise ValueError(
            f"Cannot parse date '{date_str}'. Supported formats: "
            f"DD-MM-YYYY, YYYY-MM-DD, DD/MM/YYYY, Spanish month names "
            f"(e.g. '15 de enero de 2024')."
        )

    @staticmethod
    def _parse_numbers(raw_numbers: list[str]) -> list[int]:
        """Parse a list of raw number strings into integers.

        Args:
            raw_numbers: List of number strings from the source.

        Returns:
            List of parsed integers (not yet sorted).

        Raises:
            ValueError: If any element cannot be converted to int.
        """
        parsed: list[int] = []
        for idx, raw_val in enumerate(raw_numbers):
            parsed.append(
                Normalizer._parse_single_number(raw_val, label=f"number[{idx}]")
            )
        return parsed

    @staticmethod
    def _parse_single_number(raw_val: str, label: str = "number") -> int:
        """Parse a single raw string value into an integer.

        Args:
            raw_val: The raw string value.
            label: Descriptive label for error messages.

        Returns:
            The parsed integer.

        Raises:
            ValueError: If the value cannot be converted.
        """
        cleaned = raw_val.strip()
        try:
            return int(cleaned)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid {label}: '{raw_val}' cannot be converted to int."
            ) from exc

    # ── Batch processing ──────────────────────────────────────────────

    def normalize_batch(
        self,
        raw_results: list[RawDrawResult],
        game_type: str,
    ) -> tuple[list[ValidatedDraw], list[tuple[int, str]]]:
        """Normalise a list of raw draw results, collecting errors per row.

        Args:
            raw_results: List of unprocessed draw results.
            game_type: Game identifier to apply to all draws.

        Returns:
            A tuple of (validated_draws, errors) where errors is a list
            of (row_index, error_message) tuples for rows that failed.
        """
        validated: list[ValidatedDraw] = []
        errors: list[tuple[int, str]] = []

        for idx, raw in enumerate(raw_results):
            try:
                draw = self.normalize(raw, game_type=game_type)
                validated.append(draw)
            except (ValueError, NormalizationError) as exc:
                errors.append((idx, str(exc)))
                logger.debug("Row %d failed normalisation: %s", idx, exc)

        logger.info(
            "Batch normalisation: %d valid, %d errors out of %d total.",
            len(validated),
            len(errors),
            len(raw_results),
        )
        return validated, errors
