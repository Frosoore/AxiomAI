"""
tests/test_localization.py

Unit tests for axiom.localization — the tr() translation helper, the supported
language table, and number formatting.

Migrated (TICKET-001) from the print-only debug script debug/test_translations.py
into proper assertion-based pytest coverage; localization had no tests/ coverage.
"""

import pytest

from axiom.localization import (
    SUPPORTED_LANGUAGES,
    fmt_num,
    get_translations_dict,
    tr,
)


# A handful of keys that the UI relies on across the app.
_CORE_KEYS = ["app_title", "settings_title", "play", "stats"]


class TestTranslationsDict:
    def test_english_table_present(self) -> None:
        """The translations dict always contains the 'en' baseline."""
        assert "en" in get_translations_dict()

    def test_every_supported_language_has_a_table(self) -> None:
        """Each language advertised in SUPPORTED_LANGUAGES has a translation table."""
        translations = get_translations_dict()
        for lang_code in SUPPORTED_LANGUAGES:
            assert lang_code in translations, f"missing table for '{lang_code}'"

    def test_core_keys_present_in_english(self) -> None:
        """The English baseline defines the core UI keys."""
        en = get_translations_dict()["en"]
        for key in _CORE_KEYS:
            assert key in en, f"core key '{key}' missing from English table"


class TestTr:
    def test_known_key_returns_translation(self) -> None:
        """tr() returns a non-empty translated string for a known key."""
        result = tr("app_title")
        assert isinstance(result, str) and result != ""

    def test_unknown_key_falls_back_to_key_itself(self) -> None:
        """An unknown key returns the key verbatim rather than raising."""
        assert tr("this_key_does_not_exist_anywhere") == "this_key_does_not_exist_anywhere"

    def test_keyword_formatting_is_applied(self) -> None:
        """Numeric kwargs are formatted into the placeholder via fmt_num."""
        # 'turn_fmt' is a parametrised key used by the turn label.
        formatted = tr("turn_fmt", count=3)
        assert "3" in formatted


class TestFmtNum:
    def test_whole_float_renders_without_decimal(self) -> None:
        """A whole-valued number renders without a trailing '.0'."""
        assert fmt_num(10.0) == "10"

    def test_integer_renders_as_integer(self) -> None:
        """An int renders as its plain integer string."""
        assert fmt_num(42) == "42"
