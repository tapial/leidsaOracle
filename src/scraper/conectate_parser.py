"""
HTML parser for **conectate.com.do/loterias/leidsa**.

Secondary / fallback data source.  The site uses a different HTML
structure and CSS class naming convention compared to
loteriasdominicanas.com, but the overall layout (date + number balls)
is similar.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from src.config.constants import GameDefinition
from src.scraper.base_parser import BaseDrawParser
from src.validator.schemas import RawDrawResult

logger = logging.getLogger(__name__)

# ── Date parsing ──────────────────────────────────────────────────────────

_SPANISH_MONTHS: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


def _parse_conectate_date(text: str) -> date | None:
    """Parse a date string using Conectate's typical formats."""
    text = text.strip()

    # Standard formats.
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # Spanish month names: "15 de enero de 2024", "Enero 15, 2024".
    match = re.search(
        r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text, re.IGNORECASE
    )
    if match:
        day_s, month_name, year_s = match.groups()
        month = _SPANISH_MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year_s), month, int(day_s))
            except ValueError:
                pass

    # "Enero 15, 2024" variant.
    match = re.search(
        r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", text, re.IGNORECASE
    )
    if match:
        month_name, day_s, year_s = match.groups()
        month = _SPANISH_MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year_s), month, int(day_s))
            except ValueError:
                pass

    # Embedded dd/mm/yyyy.
    match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", text)
    if match:
        d, m, y = match.groups()
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            pass

    return None


def _extract_numbers_from_element(element: Tag) -> list[str]:
    """Extract number strings from a Conectate result element."""
    numbers: list[str] = []

    # Conectate-specific selectors.
    selectors = [
        ".num", ".number", ".ball", ".numero",
        "span.lottery-number", ".result-num",
        ".circle-number", ".bolita",
        "li.num", "div.num",
    ]
    for selector in selectors:
        found = element.select(selector)
        if found:
            nums = [el.get_text(strip=True) for el in found]
            nums = [n for n in nums if n.isdigit()]
            if nums:
                return nums

    # Combined text element with separators.
    combined_selectors = [".numbers", ".numeros", ".resultado", ".nums"]
    for selector in combined_selectors:
        el = element.select_one(selector)
        if el:
            raw = el.get_text(strip=True)
            parts = re.split(r"[\s,\-|]+", raw)
            nums = [p for p in parts if p.isdigit()]
            if nums:
                return nums

    # Generic: collect all numeric text in child elements.
    for child in element.find_all(["span", "td", "li", "div", "strong"]):
        txt = child.get_text(strip=True)
        if txt.isdigit() and 1 <= int(txt) <= 99:
            numbers.append(txt)

    return numbers


class ConectateParser(BaseDrawParser):
    """Parser for **conectate.com.do** LEIDSA result pages.

    The Conectate site uses a different DOM structure from
    loteriasdominicanas.com but follows a similar pattern of date headers
    followed by number elements.

    URL patterns:
    - ``/loterias/leidsa/loto-mas`` for Loto / Loto Mas
    - ``/loterias/leidsa/loto-pool`` for Loto Pool
    """

    # Conectate uses different URL paths than loteriasdominicanas.com.
    _PATH_MAP: dict[str, str] = {
        "/leidsa/loto": "/loterias/leidsa/loto",
        "/leidsa/loto-mas": "/loterias/leidsa/loto-mas",
        "/leidsa/loto-pool": "/loterias/leidsa/loto-pool",
    }

    def __init__(self, game_def: GameDefinition) -> None:
        super().__init__(game_def)

    @classmethod
    def translate_path(cls, original_path: str) -> str:
        """Convert a loteriasdominicanas.com path to a Conectate path.

        Args:
            original_path: The scraper_path from the game definition.

        Returns:
            The equivalent path on conectate.com.do.
        """
        return cls._PATH_MAP.get(original_path, original_path)

    def parse_results_page(self, html: str) -> list[RawDrawResult]:
        """Parse the latest-results page from Conectate."""
        soup = BeautifulSoup(html, "lxml")
        results = self._extract_results(soup)
        logger.info(
            "Conectate: parsed %d results from latest page for %s",
            len(results), self._game_def.code,
        )
        return results

    def parse_historical_page(
        self,
        html: str,
    ) -> tuple[list[RawDrawResult], bool]:
        """Parse a historical/paginated page from Conectate."""
        soup = BeautifulSoup(html, "lxml")
        results = self._extract_results(soup)
        has_more = self._detect_next_page(soup)
        logger.info(
            "Conectate: parsed %d historical results for %s (has_more=%s)",
            len(results), self._game_def.code, has_more,
        )
        return results, has_more

    # ── Internal extraction ───────────────────────────────────────────

    def _extract_results(self, soup: BeautifulSoup) -> list[RawDrawResult]:
        """Try card-based, then table-based extraction."""
        results: list[RawDrawResult] = []

        # Card-based layout.
        blocks = self._find_result_blocks(soup)
        for block in blocks:
            raw = self._parse_block(block)
            if raw is not None:
                results.append(raw)

        if results:
            return results

        # Table fallback.
        results = self._parse_table_layout(soup)
        return results

    def _find_result_blocks(self, soup: BeautifulSoup) -> list[Tag]:
        """Locate result blocks using Conectate-specific selectors."""
        selectors = [
            ".result-card",
            ".sorteo",
            ".lottery-result",
            ".draw-result",
            ".resultado-item",
            ".result-block",
            "div.result",
            "article.sorteo",
            ".card-result",
        ]
        for selector in selectors:
            blocks = soup.select(selector)
            if blocks:
                logger.debug(
                    "Conectate: found %d blocks with '%s'",
                    len(blocks), selector,
                )
                return blocks
        return []

    def _parse_block(self, block: Tag) -> RawDrawResult | None:
        """Parse a single result block into a RawDrawResult."""
        # Date extraction.
        draw_date: date | None = None
        date_selectors = [
            ".date", ".fecha", ".draw-date",
            "h3", "h4", "h5", ".title",
            "time", "span.date", ".sorteo-fecha",
        ]
        for sel in date_selectors:
            el = block.select_one(sel)
            if el:
                draw_date = _parse_conectate_date(el.get_text())
                if draw_date:
                    break

        if draw_date is None:
            draw_date = _parse_conectate_date(block.get_text())

        if draw_date is None:
            logger.debug("Conectate: skipping block, no date found.")
            return None

        # Number extraction.
        numbers = _extract_numbers_from_element(block)
        if len(numbers) < self._game_def.number_count:
            logger.debug(
                "Conectate: skipping block for %s, got %d numbers (need %d).",
                draw_date, len(numbers), self._game_def.number_count,
            )
            return None

        main_numbers = numbers[: self._game_def.number_count]
        bonus: str | None = None

        if self._game_def.has_bonus and len(numbers) > self._game_def.number_count:
            bonus = numbers[self._game_def.number_count]

        # Check for dedicated bonus element.
        if self._game_def.has_bonus and bonus is None:
            bonus_selectors = [
                ".bonus", ".extra", ".mas", ".mega",
                ".bonus-number", ".loto-mas",
            ]
            for sel in bonus_selectors:
                el = block.select_one(sel)
                if el:
                    txt = el.get_text(strip=True)
                    if txt.isdigit():
                        bonus = txt
                        break

        return RawDrawResult(
            date_str=draw_date.isoformat(),
            numbers=main_numbers,
            bonus=bonus,
            source="scraper",
        )

    def _parse_table_layout(self, soup: BeautifulSoup) -> list[RawDrawResult]:
        """Fallback: extract results from HTML tables."""
        results: list[RawDrawResult] = []

        for table in soup.select("table"):
            rows = table.select("tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) < 2:
                    continue

                draw_date = _parse_conectate_date(cells[0].get_text())
                if draw_date is None:
                    continue

                numbers: list[str] = []
                for cell in cells[1:]:
                    txt = cell.get_text(strip=True)
                    if txt.isdigit():
                        numbers.append(txt)

                if len(numbers) < self._game_def.number_count:
                    continue

                main_numbers = numbers[: self._game_def.number_count]
                bonus: str | None = None
                if (
                    self._game_def.has_bonus
                    and len(numbers) > self._game_def.number_count
                ):
                    bonus = numbers[self._game_def.number_count]

                results.append(
                    RawDrawResult(
                        date_str=draw_date.isoformat(),
                        numbers=main_numbers,
                        bonus=bonus,
                        source="scraper",
                    )
                )

        return results

    def _detect_next_page(self, soup: BeautifulSoup) -> bool:
        """Check if a pagination next-page link exists."""
        next_selectors = [
            "a.next", ".pagination a[rel='next']",
            "li.next a", "a.next-page",
            ".pager .next a",
        ]
        for selector in next_selectors:
            try:
                if soup.select_one(selector):
                    return True
            except Exception:
                continue

        for link in soup.find_all("a"):
            link_text = link.get_text(strip=True).lower()
            if link_text in ("siguiente", "next", ">>", ">"):
                return True

        return False
