"""Tests for validator and normalizer modules."""

from __future__ import annotations

import datetime

import pytest


class TestNormalizer:
    """Tests for the data normalizer."""

    def test_normalize_valid_draw(self):
        from src.validator.normalizer import Normalizer
        from src.validator.schemas import RawDrawResult

        normalizer = Normalizer()
        raw = RawDrawResult(
            date_str="15-01-2024",
            numbers=["5", "12", "23", "31", "7", "2"],
            source="test",
        )
        validated, errors = normalizer.normalize_batch([raw], game_type="loto")
        assert len(validated) == 1
        assert len(errors) == 0
        assert validated[0].numbers == [2, 5, 7, 12, 23, 31]  # Sorted

    def test_normalize_invalid_number_rejected(self):
        from src.validator.normalizer import Normalizer
        from src.validator.schemas import RawDrawResult

        normalizer = Normalizer()
        raw = RawDrawResult(
            date_str="15-01-2024",
            numbers=["5", "12", "23", "31", "7", "99"],  # 99 is out of range for 6/38
            source="test",
        )
        validated, errors = normalizer.normalize_batch([raw], game_type="loto")
        assert len(validated) == 0
        assert len(errors) == 1

    def test_normalize_spanish_date(self):
        from src.validator.normalizer import Normalizer
        from src.validator.schemas import RawDrawResult

        normalizer = Normalizer()
        raw = RawDrawResult(
            date_str="15 de enero de 2024",
            numbers=["1", "8", "15", "22", "29", "36"],
            source="test",
        )
        validated, errors = normalizer.normalize_batch([raw], game_type="loto")
        assert len(validated) == 1
        assert validated[0].draw_date == datetime.date(2024, 1, 15)

    def test_normalize_wrong_count_rejected(self):
        from src.validator.normalizer import Normalizer
        from src.validator.schemas import RawDrawResult

        normalizer = Normalizer()
        raw = RawDrawResult(
            date_str="15-01-2024",
            numbers=["1", "2", "3"],  # Too few for 6/38
            source="test",
        )
        validated, errors = normalizer.normalize_batch([raw], game_type="loto")
        assert len(validated) == 0
        assert len(errors) == 1


class TestValidatedDraw:
    """Tests for ValidatedDraw model validation."""

    def test_valid_draw(self):
        from src.validator.schemas import ValidatedDraw

        draw = ValidatedDraw(
            game_type="loto",
            draw_date=datetime.date(2024, 1, 15),
            numbers=[2, 5, 7, 12, 23, 31],
        )
        assert draw.numbers == [2, 5, 7, 12, 23, 31]

    def test_out_of_range_raises(self):
        from src.validator.schemas import ValidatedDraw

        with pytest.raises(ValueError, match="out of range"):
            ValidatedDraw(
                game_type="loto",
                draw_date=datetime.date(2024, 1, 15),
                numbers=[2, 5, 7, 12, 23, 99],  # 99 out of range
            )

    def test_duplicate_numbers_raises(self):
        from src.validator.schemas import ValidatedDraw

        with pytest.raises(ValueError, match="unique"):
            ValidatedDraw(
                game_type="loto",
                draw_date=datetime.date(2024, 1, 15),
                numbers=[2, 2, 7, 12, 23, 31],  # Duplicate 2
            )

    def test_unknown_game_raises(self):
        from src.validator.schemas import ValidatedDraw

        with pytest.raises(ValueError, match="Unknown game_type"):
            ValidatedDraw(
                game_type="nonexistent",
                draw_date=datetime.date(2024, 1, 15),
                numbers=[2, 5, 7, 12, 23, 31],
            )
