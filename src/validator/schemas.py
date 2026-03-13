"""
Pydantic v2 schemas for raw and validated lottery draw data.

``RawDrawResult`` represents unprocessed input from scrapers or file imports.
``ValidatedDraw`` enforces game-specific rules (number count, range, uniqueness)
via a Pydantic model validator.
"""

from __future__ import annotations

import logging
from datetime import date

from pydantic import BaseModel, model_validator

from src.config.constants import GAME_REGISTRY, GameDefinition

logger = logging.getLogger(__name__)


class RawDrawResult(BaseModel):
    """Unprocessed draw result as received from a scraper or file parser.

    All fields are kept as raw strings so that the normalizer can handle
    the full variety of formats found in Dominican lottery data sources.

    Attributes:
        date_str: The draw date in its original string format
                  (e.g. ``"15-01-2024"``, ``"15 de enero de 2024"``).
        numbers: The drawn numbers as raw strings (not yet parsed/validated).
        bonus: Optional bonus number as a raw string.
        source: Free-text identifier of where this data came from.
    """

    date_str: str
    numbers: list[str]
    bonus: str | None = None
    source: str = ""


class ValidatedDraw(BaseModel):
    """A fully validated and normalised draw result ready for persistence.

    The ``model_validator`` ensures all game-specific constraints are met
    before a draw can be constructed.

    Attributes:
        game_type: Game identifier matching a key in ``GAME_REGISTRY``.
        draw_date: Calendar date of the draw.
        numbers: Sorted list of main numbers drawn (ascending).
        bonus_number: The bonus number, or ``None`` for games without one.
        source: Origin label (e.g. ``"scraper"``, ``"csv"``).
    """

    game_type: str
    draw_date: date
    numbers: list[int]
    bonus_number: int | None = None
    source: str = ""

    @model_validator(mode="after")
    def _validate_against_game_rules(self) -> ValidatedDraw:
        """Validate draw data against the game definition rules.

        Checks performed:
        1. ``game_type`` exists in ``GAME_REGISTRY``.
        2. ``numbers`` count matches ``GameDefinition.number_count``.
        3. All numbers are unique.
        4. All numbers fall within ``[pool_min, pool_max]``.
        5. If the game has a bonus, ``bonus_number`` is within bonus range.
        6. If the game has no bonus, ``bonus_number`` must be ``None``.
        """
        # --- Game existence ---
        game_def: GameDefinition | None = GAME_REGISTRY.get(self.game_type)
        if game_def is None:
            valid_types = ", ".join(sorted(GAME_REGISTRY.keys()))
            raise ValueError(
                f"Unknown game_type '{self.game_type}'. "
                f"Valid types: {valid_types}"
            )

        # --- Number count ---
        if len(self.numbers) != game_def.number_count:
            raise ValueError(
                f"Game '{self.game_type}' requires exactly "
                f"{game_def.number_count} numbers, got {len(self.numbers)}."
            )

        # --- Uniqueness ---
        if len(set(self.numbers)) != len(self.numbers):
            duplicates = sorted({n for n in self.numbers if self.numbers.count(n) > 1})
            raise ValueError(
                f"Numbers must be unique. Duplicates found: {duplicates}"
            )

        # --- Range check ---
        out_of_range = sorted(
            n for n in self.numbers
            if n < game_def.pool_min or n > game_def.pool_max
        )
        if out_of_range:
            raise ValueError(
                f"Numbers out of range [{game_def.pool_min}, {game_def.pool_max}]: "
                f"{out_of_range}"
            )

        # --- Bonus number ---
        if game_def.has_bonus:
            if self.bonus_number is not None:
                if not game_def.validate_bonus(self.bonus_number):
                    raise ValueError(
                        f"Bonus number {self.bonus_number} out of range "
                        f"[{game_def.bonus_min}, {game_def.bonus_max}] "
                        f"for game '{self.game_type}'."
                    )
        else:
            if self.bonus_number is not None:
                raise ValueError(
                    f"Game '{self.game_type}' does not have a bonus number, "
                    f"but bonus_number={self.bonus_number} was provided."
                )

        return self
