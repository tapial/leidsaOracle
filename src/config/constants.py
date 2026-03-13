"""
Game definitions and registry for all supported LEIDSA lottery products.

Each game is described by a frozen dataclass that captures its rules,
drawing schedule, and scraper endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GameDefinition:
    """Immutable specification of a LEIDSA lottery game.

    Attributes:
        code: Internal identifier used as the ``game_type`` key everywhere.
        display_name: Human-readable name for UI and reports.
        number_count: How many main numbers are drawn per game.
        pool_min: Lowest selectable main number (inclusive).
        pool_max: Highest selectable main number (inclusive).
        has_bonus: Whether the game includes a separate bonus number.
        bonus_min: Lowest bonus number (inclusive), or ``None``.
        bonus_max: Highest bonus number (inclusive), or ``None``.
        draw_days: Weekday names when draws take place.
        draw_time: Scheduled draw time as an ``"HH:MM"`` string.
        scraper_path: URL path appended to the base URL for scraping results.
    """

    code: str
    display_name: str
    number_count: int
    pool_min: int
    pool_max: int
    has_bonus: bool
    bonus_min: int | None
    bonus_max: int | None
    draw_days: tuple[str, ...]
    draw_time: str
    scraper_path: str

    # ── Convenience helpers ──────────────────────────────────────────

    @property
    def pool_size(self) -> int:
        """Total count of numbers in the main pool."""
        return self.pool_max - self.pool_min + 1

    @property
    def bonus_pool_size(self) -> int | None:
        """Total count of numbers in the bonus pool, or ``None``."""
        if not self.has_bonus or self.bonus_min is None or self.bonus_max is None:
            return None
        return self.bonus_max - self.bonus_min + 1

    def validate_numbers(self, numbers: list[int]) -> bool:
        """Return True if *numbers* is a valid main-number selection."""
        if len(numbers) != self.number_count:
            return False
        if len(set(numbers)) != self.number_count:
            return False
        return all(self.pool_min <= n <= self.pool_max for n in numbers)

    def validate_bonus(self, bonus: int) -> bool:
        """Return True if *bonus* is a valid bonus number for this game."""
        if not self.has_bonus or self.bonus_min is None or self.bonus_max is None:
            return False
        return self.bonus_min <= bonus <= self.bonus_max


# ── Game Registry ────────────────────────────────────────────────────────

GAME_REGISTRY: dict[str, GameDefinition] = {
    "loto": GameDefinition(
        code="loto",
        display_name="Loto",
        number_count=6,
        pool_min=1,
        pool_max=38,
        has_bonus=False,
        bonus_min=None,
        bonus_max=None,
        draw_days=("Wednesday", "Saturday"),
        draw_time="20:55",
        scraper_path="/leidsa/loto-mas",
    ),
    "loto_mas": GameDefinition(
        code="loto_mas",
        display_name="Loto M\u00e1s",
        number_count=6,
        pool_min=1,
        pool_max=38,
        has_bonus=True,
        bonus_min=1,
        bonus_max=12,
        draw_days=("Wednesday", "Saturday"),
        draw_time="20:55",
        scraper_path="/leidsa/loto-mas",
    ),
    "loto_pool": GameDefinition(
        code="loto_pool",
        display_name="Loto Pool",
        number_count=5,
        pool_min=1,
        pool_max=31,
        has_bonus=False,
        bonus_min=None,
        bonus_max=None,
        draw_days=(
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ),
        draw_time="20:55",
        scraper_path="/leidsa/loto-pool",
    ),
}


def get_game(game_type: str) -> GameDefinition:
    """Look up a game by its code, raising ``KeyError`` if not found."""
    try:
        return GAME_REGISTRY[game_type]
    except KeyError:
        valid = ", ".join(sorted(GAME_REGISTRY))
        raise KeyError(f"Unknown game type '{game_type}'. Valid types: {valid}") from None
