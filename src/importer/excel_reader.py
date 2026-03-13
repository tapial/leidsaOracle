"""
Excel and CSV file reader for importing historical lottery draw data.

Supports two common spreadsheet layouts:

1. **Wide format**: Each number in its own column.
   ``Date | N1 | N2 | N3 | N4 | N5 | N6``

2. **CSV-in-cell format**: All numbers in a single column separated by
   commas, dashes, or spaces.
   ``Date | Numbers ("03,10,15,22,31,38")``

Column detection is case-insensitive and supports both English and
Spanish header names.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Union

import pandas as pd

from src.validator.schemas import RawDrawResult

logger = logging.getLogger(__name__)

# ── Column name mappings (case-insensitive) ───────────────────────────────

# Patterns that indicate a date column.
_DATE_PATTERNS: set[str] = {
    "fecha", "date", "draw_date", "drawdate", "fecha_sorteo",
    "fecha sorteo", "sorteo", "dia",
}

# Patterns that indicate a combined numbers column (CSV-in-cell format).
_COMBINED_NUMBER_PATTERNS: set[str] = {
    "numeros", "numbers", "nums", "resultado", "resultados",
    "combinacion", "combinaci\u00f3n", "winning_numbers",
}

# Patterns for individual number columns: "n1", "numero1", "number1", etc.
_INDIVIDUAL_NUMBER_RE = re.compile(
    r"^(?:n(?:umero|umber)?|num|#|ball|bola)?\s*(\d+)$",
    re.IGNORECASE,
)

# Bonus column patterns.
_BONUS_PATTERNS: set[str] = {
    "bonus", "extra", "mas", "m\u00e1s", "loto_mas", "mega",
    "bonus_number", "numero_extra",
}


class ExcelReadError(Exception):
    """Raised when an Excel/CSV file cannot be read or parsed."""


class ExcelReader:
    """Reads lottery draw data from Excel (.xlsx, .xls) and CSV files.

    The reader auto-detects column roles using header names and
    supports both wide and CSV-in-cell layouts.
    """

    def read_file(
        self,
        file: Union[Path, BytesIO],
        game_type: str = "loto",
    ) -> list[RawDrawResult]:
        """Read a file and return a list of raw draw results.

        Args:
            file: Path to an Excel/CSV file, or an in-memory BytesIO.
            game_type: The game type to tag each result with.

        Returns:
            A list of :class:`RawDrawResult` objects, one per row.

        Raises:
            ExcelReadError: If the file cannot be read or column detection fails.
        """
        try:
            df = self._load_dataframe(file)
        except Exception as exc:
            raise ExcelReadError(f"Failed to read file: {exc}") from exc

        if df.empty:
            logger.warning("File is empty, returning no results.")
            return []

        # Normalise column names for matching.
        df.columns = [str(c).strip() for c in df.columns]

        date_col = self._find_date_column(df)
        if date_col is None:
            raise ExcelReadError(
                f"Could not detect a date column. "
                f"Columns found: {list(df.columns)}"
            )

        # Determine the format: combined or wide.
        combined_col = self._find_combined_numbers_column(df)
        if combined_col is not None:
            return self._parse_combined_format(
                df, date_col, combined_col, game_type
            )

        number_cols = self._find_individual_number_columns(df)
        if number_cols:
            return self._parse_wide_format(
                df, date_col, number_cols, game_type
            )

        raise ExcelReadError(
            f"Could not detect number columns. "
            f"Columns found: {list(df.columns)}"
        )

    # ── File loading ──────────────────────────────────────────────────

    def _load_dataframe(self, file: Union[Path, BytesIO]) -> pd.DataFrame:
        """Load a DataFrame from an Excel or CSV file."""
        if isinstance(file, BytesIO):
            # Try Excel first, then CSV.
            try:
                file.seek(0)
                return pd.read_excel(file, engine="openpyxl")
            except Exception:
                file.seek(0)
                return pd.read_csv(file)

        path = Path(file)
        suffix = path.suffix.lower()

        if suffix in (".xlsx", ".xls"):
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            return pd.read_excel(path, engine=engine)
        elif suffix == ".csv":
            return pd.read_csv(path)
        else:
            # Try Excel, then CSV as fallback.
            try:
                return pd.read_excel(path, engine="openpyxl")
            except Exception:
                return pd.read_csv(path)

    # ── Column detection ──────────────────────────────────────────────

    def _find_date_column(self, df: pd.DataFrame) -> str | None:
        """Find the column that holds draw dates."""
        for col in df.columns:
            normalised = col.lower().strip().replace(" ", "_")
            if normalised in _DATE_PATTERNS:
                logger.debug("Detected date column: '%s'", col)
                return col

        # Heuristic: first column with date-like values.
        for col in df.columns:
            sample = df[col].dropna().head(5)
            date_count = 0
            for val in sample:
                try:
                    pd.to_datetime(val)
                    date_count += 1
                except Exception:
                    pass
            if date_count >= 3:
                logger.debug("Inferred date column by content: '%s'", col)
                return col

        return None

    def _find_combined_numbers_column(self, df: pd.DataFrame) -> str | None:
        """Find a column containing all numbers as a delimited string."""
        for col in df.columns:
            normalised = col.lower().strip().replace(" ", "_")
            if normalised in _COMBINED_NUMBER_PATTERNS:
                logger.debug("Detected combined numbers column: '%s'", col)
                return col

        # Heuristic: look for columns with comma-separated digit strings.
        for col in df.columns:
            if col == self._find_date_column(df):
                continue
            sample = df[col].dropna().head(5).astype(str)
            csv_count = sum(
                1 for v in sample
                if re.match(r"^\d{1,2}[\s,\-;|]+\d{1,2}", v.strip())
            )
            if csv_count >= 3:
                logger.debug("Inferred combined column by content: '%s'", col)
                return col

        return None

    def _find_individual_number_columns(self, df: pd.DataFrame) -> list[str]:
        """Find columns representing individual draw numbers (wide format)."""
        number_cols: list[tuple[int, str]] = []  # (sort_key, col_name)

        for col in df.columns:
            normalised = col.lower().strip()
            match = _INDIVIDUAL_NUMBER_RE.match(normalised)
            if match:
                idx = int(match.group(1))
                number_cols.append((idx, col))
                continue

            # Also match plain "N1", "N2", etc. or "Numero 1".
            match2 = re.match(r"^(?:n|numero|number|#|ball|bola)\s*(\d+)$", normalised, re.IGNORECASE)
            if match2:
                idx = int(match2.group(1))
                number_cols.append((idx, col))

        if number_cols:
            # Sort by the numeric suffix to preserve correct order.
            number_cols.sort(key=lambda x: x[0])
            cols = [c[1] for c in number_cols]
            logger.debug("Detected %d individual number columns: %s", len(cols), cols)
            return cols

        # Heuristic: all-numeric columns after the date column.
        date_col = self._find_date_column(df)
        numeric_cols: list[str] = []
        past_date = False
        for col in df.columns:
            if col == date_col:
                past_date = True
                continue
            if not past_date:
                continue
            # Check if this column is numeric with lottery-range values.
            try:
                vals = pd.to_numeric(df[col].dropna().head(10), errors="coerce")
                if vals.notna().sum() >= 5 and vals.min() >= 1 and vals.max() <= 99:
                    numeric_cols.append(col)
            except Exception:
                pass

        if len(numeric_cols) >= 3:
            logger.debug("Inferred %d number columns by content: %s", len(numeric_cols), numeric_cols)
            return numeric_cols

        return []

    def _find_bonus_column(self, df: pd.DataFrame, exclude: set[str]) -> str | None:
        """Find a bonus number column (not in *exclude*)."""
        for col in df.columns:
            if col in exclude:
                continue
            normalised = col.lower().strip().replace(" ", "_")
            if normalised in _BONUS_PATTERNS:
                logger.debug("Detected bonus column: '%s'", col)
                return col
        return None

    # ── Row parsing ───────────────────────────────────────────────────

    def _parse_wide_format(
        self,
        df: pd.DataFrame,
        date_col: str,
        number_cols: list[str],
        game_type: str,
    ) -> list[RawDrawResult]:
        """Parse a wide-format DataFrame (one number per column)."""
        bonus_col = self._find_bonus_column(
            df, exclude={date_col, *number_cols}
        )

        results: list[RawDrawResult] = []
        for idx, row in df.iterrows():
            try:
                draw_date = self._coerce_date(row[date_col])
                numbers = [str(row[c]) for c in number_cols]

                bonus = None
                if bonus_col is not None and pd.notna(row.get(bonus_col)):
                    bonus = str(row[bonus_col])

                results.append(
                    RawDrawResult(
                        draw_date=draw_date,
                        numbers=numbers,
                        bonus_number=bonus,
                        game_type=game_type,
                        source="excel",
                    )
                )
            except Exception as exc:
                logger.warning("Skipping row %s: %s", idx, exc)

        logger.info("Parsed %d rows in wide format.", len(results))
        return results

    def _parse_combined_format(
        self,
        df: pd.DataFrame,
        date_col: str,
        numbers_col: str,
        game_type: str,
    ) -> list[RawDrawResult]:
        """Parse CSV-in-cell format (all numbers in one column)."""
        bonus_col = self._find_bonus_column(
            df, exclude={date_col, numbers_col}
        )

        results: list[RawDrawResult] = []
        for idx, row in df.iterrows():
            try:
                draw_date = self._coerce_date(row[date_col])
                raw_numbers = str(row[numbers_col])
                numbers = re.split(r"[\s,\-;|]+", raw_numbers.strip())
                numbers = [n.strip() for n in numbers if n.strip().isdigit()]

                bonus = None
                if bonus_col is not None and pd.notna(row.get(bonus_col)):
                    bonus = str(row[bonus_col])

                results.append(
                    RawDrawResult(
                        draw_date=draw_date,
                        numbers=numbers,
                        bonus_number=bonus,
                        game_type=game_type,
                        source="excel",
                    )
                )
            except Exception as exc:
                logger.warning("Skipping row %s: %s", idx, exc)

        logger.info("Parsed %d rows in combined format.", len(results))
        return results

    @staticmethod
    def _coerce_date(value: object) -> str:
        """Coerce a cell value to a date string for downstream parsing."""
        if pd.isna(value):
            raise ValueError("Date cell is empty")

        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d")

        # Let the normalizer handle string parsing.
        return str(value).strip()
