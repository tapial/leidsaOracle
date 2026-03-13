"""
Abstract base class for lottery draw HTML parsers.

Each supported website gets its own concrete subclass that knows how to
extract draw results from that site's specific HTML structure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.config.constants import GameDefinition
from src.validator.schemas import RawDrawResult


class BaseDrawParser(ABC):
    """Contract that all site-specific HTML parsers must fulfill.

    Subclasses are responsible for extracting :class:`RawDrawResult` objects
    from raw HTML strings.  The ``game_def`` is injected at construction time
    so parsers can validate number counts and ranges inline when convenient.

    Args:
        game_def: The game definition for the lottery product being parsed.
    """

    def __init__(self, game_def: GameDefinition) -> None:
        self._game_def = game_def

    @property
    def game_def(self) -> GameDefinition:
        """The game definition this parser was configured for."""
        return self._game_def

    @abstractmethod
    def parse_results_page(self, html: str) -> list[RawDrawResult]:
        """Extract draw results from a *latest results* page.

        The page typically shows the most recent drawing(s) for the game.

        Args:
            html: Raw HTML string of the results page.

        Returns:
            A list of :class:`RawDrawResult` instances, newest first.
            An empty list is valid if no results were found.
        """

    @abstractmethod
    def parse_historical_page(
        self,
        html: str,
    ) -> tuple[list[RawDrawResult], bool]:
        """Extract draw results from a *historical / paginated* page.

        Historical pages typically list many past drawings and support
        pagination.

        Args:
            html: Raw HTML string of the historical results page.

        Returns:
            A tuple of ``(results, has_more_pages)`` where:

            - **results**: List of :class:`RawDrawResult` from this page.
            - **has_more_pages**: ``True`` if there are additional pages
              of historical data to fetch.
        """
