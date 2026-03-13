"""
HTML parser for **loteriasdominicanas.com**.

Extracts lottery draw results from the site's result pages.  The site
renders results in card/table blocks with date headers and individual
number elements.  Multiple CSS selector strategies are attempted as
fallbacks in case the site's markup changes.
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

# ── Date parsing helpers ──────────────────────────────────────────────────

_SPANISH_MONTHS: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_DATE_PATTERNS: list[str] = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d de %B de %Y",
]


def _parse_date_text(text: str) -> date | None:
    """Try multiple strategies to parse a date string to ``datetime.date``."""
    text = text.strip()

    # Standard formats first.
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # Spanish: "15 de enero de 2024" or "Miercoles 15 de enero de 2024"
    match = re.search(
        r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text, re.IGNORECASE
    )
    if match:
        day_str, month_name, year_str = match.groups()
        month = _SPANISH_MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year_str), month, int(day_str))
            except ValueError:
                pass

    # Fallback: any date-like pattern dd/mm/yyyy embedded in text.
    match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", text)
    if match:
        d, m, y = match.groups()
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            pass

    return None


def _extract_numbers(element: Tag) -> list[str]:
    """Pull number strings from an element using multiple strategies."""
    numbers: list[str] = []

    # Strategy 1: Individual number elements (spans, lis, divs with class "ball", "numero", etc.)
    selectors = [
        ".ball", ".numero", ".num", ".number",
        "span.result-number", "li.result-number",
        ".lottery-ball", ".result-ball",
        "td.number", "span.ball-number",
    ]
    for selector in selectors:
        found = element.select(selector)
        if found:
            numbers = [el.get_text(strip=True) for el in found]
            # Filter to only digit strings.
            numbers = [n for n in numbers if n.isdigit()]
            if numbers:
                return numbers

    # Strategy 2: A single element with comma / dash / space-separated numbers.
    text_selectors = [
        ".numbers", ".numeros", ".resultado", ".result-numbers",
    ]
    for selector in text_selectors:
        found = element.select_one(selector)
        if found:
            raw = found.get_text(strip=True)
            parts = re.split(r"[\s,\-]+", raw)
            numbers = [p for p in parts if p.isdigit()]
            if numbers:
                return numbers

    # Strategy 3: Walk all child spans/tds and collect numeric text.
    for child in element.find_all(["span", "td", "li", "div"]):
        txt = child.get_text(strip=True)
        if txt.isdigit() and 1 <= int(txt) <= 99:
            numbers.append(txt)

    return numbers


class LoteriasDomParser(BaseDrawParser):
    """Parser for **loteriasdominicanas.com** result pages.

    The site typically renders results in blocks (divs or table rows)
    each containing:
    - A date header (in Spanish)
    - Individual number elements (balls)
    - Optionally a bonus number element
    """

    def __init__(self, game_def: GameDefinition) -> None:
        super().__init__(game_def)

    def parse_results_page(self, html: str) -> list[RawDrawResult]:
        """Parse the latest-results page and return raw draw results."""
        soup = BeautifulSoup(html, "lxml")
        results = self._extract_results(soup)
        logger.info(
            "LoteriasDom: parsed %d results from latest page for %s",
            len(results), self._game_def.code,
        )
        return results

    def parse_historical_page(
        self,
        html: str,
    ) -> tuple[list[RawDrawResult], bool]:
        """Parse a historical/paginated results page.

        Returns:
            (results, has_more_pages)
        """
        soup = BeautifulSoup(html, "lxml")
        results = self._extract_results(soup)
        has_more = self._detect_next_page(soup)
        logger.info(
            "LoteriasDom: parsed %d historical results for %s (has_more=%s)",
            len(results), self._game_def.code, has_more,
        )
        return results, has_more

    # ── Internal extraction logic ─────────────────────────────────────

    def _extract_results(self, soup: BeautifulSoup) -> list[RawDrawResult]:
        """Try multiple extraction strategies to find result blocks."""
        results: list[RawDrawResult] = []

        # Strategy 1: Card-based layout.
        blocks = self._find_result_blocks(soup)
        for block in blocks:
            raw = self._parse_single_block(block)
            if raw is not None:
                results.append(raw)

        if results:
            return results

        # Strategy 2: Table-based layout.
        results = self._parse_table_layout(soup)
        if results:
            return results

        # Strategy 3: Generic fallback - look for any clustered numbers.
        results = self._parse_generic_layout(soup)
        return results

    def _find_result_blocks(self, soup: BeautifulSoup) -> list[Tag]:
        """Locate individual result blocks using multiple selectors."""
        selectors = [
            ".result-card",
            ".draw-result",
            ".lottery-result",
            ".resultado",
            ".result-item",
            "div.result",
            "article.result",
            ".sorteo-result",
        ]
        for selector in selectors:
            blocks = soup.select(selector)
            if blocks:
                logger.debug("Found %d blocks with selector '%s'", len(blocks), selector)
                return blocks
        return []

    def _parse_single_block(self, block: Tag) -> RawDrawResult | None:
        """Extract a single draw result from a result block element."""
        # Find the date.
        draw_date: date | None = None
        date_selectors = [
            ".date", ".fecha", ".draw-date", ".result-date",
            "h3", "h4", "h5", ".title", ".sorteo-date",
            "time", "span.date",
        ]
        for sel in date_selectors:
            el = block.select_one(sel)
            if el:
                draw_date = _parse_date_text(el.get_text())
                if draw_date:
                    break

        # If no date found in a specific element, search the whole block text.
        if draw_date is None:
            draw_date = _parse_date_text(block.get_text())

        if draw_date is None:
            logger.debug("Skipping block: could not extract date.")
            return None

        # Extract numbers.
        numbers = _extract_numbers(block)
        if not numbers:
            logger.debug("Skipping block for %s: no numbers found.", draw_date)
            return None

        # Separate main numbers from potential bonus.
        main_numbers: list[str]
        bonus: str | None = None

        if self._game_def.has_bonus and len(numbers) > self._game_def.number_count:
            main_numbers = numbers[: self._game_def.number_count]
            bonus = numbers[self._game_def.number_count]
        elif len(numbers) >= self._game_def.number_count:
            main_numbers = numbers[: self._game_def.number_count]
        else:
            logger.debug(
                "Skipping block for %s: expected %d numbers, got %d.",
                draw_date, self._game_def.number_count, len(numbers),
            )
            return None

        # Also check for a dedicated bonus element.
        if self._game_def.has_bonus and bonus is None:
            bonus_selectors = [".bonus", ".extra", ".mega", ".mas", ".loto-mas"]
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
        """Extract results from HTML table rows."""
        results: list[RawDrawResult] = []

        tables = soup.select("table")
        for table in tables:
            rows = table.select("tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) < 2:
                    continue

                # First cell is typically the date.
                draw_date = _parse_date_text(cells[0].get_text())
                if draw_date is None:
                    continue

                # Remaining cells contain numbers.
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

    def _parse_generic_layout(self, soup: BeautifulSoup) -> list[RawDrawResult]:
        """Last-resort parser: look for date + number clusters anywhere."""
        results: list[RawDrawResult] = []

        # Find all date-like strings in the page.
        text = soup.get_text()
        date_pattern = re.compile(
            r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})"
        )
        number_pattern = re.compile(
            r"\b(\d{1,2})\b"
        )

        # Split by date occurrences and try to find nearby numbers.
        for match in date_pattern.finditer(text):
            d, m, y = match.groups()
            try:
                draw_date = date(int(y), int(m), int(d))
            except ValueError:
                continue

            # Look at the text following the date match for numbers.
            following_text = text[match.end(): match.end() + 200]
            nums = number_pattern.findall(following_text)
            valid_nums = [
                n for n in nums
                if self._game_def.pool_min <= int(n) <= self._game_def.pool_max
            ]

            if len(valid_nums) >= self._game_def.number_count:
                main_numbers = valid_nums[: self._game_def.number_count]
                bonus: str | None = None
                if (
                    self._game_def.has_bonus
                    and len(valid_nums) > self._game_def.number_count
                ):
                    bonus = valid_nums[self._game_def.number_count]

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
        """Determine whether a pagination *next* link exists."""
        next_selectors = [
            "a.next", "a.page-next", ".pagination a[rel='next']",
            "a:contains('Siguiente')", "a:contains('siguiente')",
            "a:contains('Next')", ".pagination .next",
            "li.next a", "a.next-page",
        ]
        for selector in next_selectors:
            try:
                el = soup.select_one(selector)
                if el:
                    return True
            except Exception:
                # Some CSS pseudo-selectors may not be supported.
                continue

        # Fallback: search for link text.
        for link in soup.find_all("a"):
            link_text = link.get_text(strip=True).lower()
            if link_text in ("siguiente", "next", ">>", ">"):
                return True

        return False
