"""
tests/test_localization_coverage.py

TICKET-053 — garde-fou de couverture i18n.

Garantit que toute langue déclarée dans SUPPORTED_LANGUAGES est *complète* par
rapport à la référence EN (aucune clé manquante), et que les placeholders de
formatage `{...}` sont identiques d'une langue à l'autre (sinon `tr()` casserait
au runtime via str.format). Empêche de publier une langue partiellement traduite.
"""

import re

import pytest

from core.localization import compute_coverage, SUPPORTED_LANGUAGES, get_translations_dict

_PLACEHOLDER = re.compile(r"{[^{}]+}")


class TestCoverage:
    def test_no_language_has_missing_keys(self) -> None:
        """Chaque langue couvre 100 % des clés de la référence EN."""
        report = compute_coverage("en")
        incomplete = {
            lang: data["missing"]
            for lang, data in report.items()
            if data["missing"]
        }
        assert not incomplete, f"Langues incomplètes : { {k: len(v) for k, v in incomplete.items()} }"

    def test_no_language_has_extra_keys(self) -> None:
        """Aucune langue n'a de clé absente de la référence EN (typo / clé orpheline)."""
        report = compute_coverage("en")
        extras = {lang: data["extra"] for lang, data in report.items() if data["extra"]}
        assert not extras, f"Clés en trop : {extras}"

    def test_every_language_file_loads(self) -> None:
        """Les 10 langues déclarées ont une table non vide chargée depuis leur TOML."""
        translations = get_translations_dict()
        for lang in SUPPORTED_LANGUAGES:
            assert translations.get(lang), f"Table vide ou absente pour '{lang}'"


class TestPlaceholders:
    def test_format_placeholders_match_english(self) -> None:
        """Les placeholders {..} de chaque traduction correspondent à ceux de l'EN."""
        translations = get_translations_dict()
        en = translations["en"]
        mismatches = []
        for lang in SUPPORTED_LANGUAGES:
            if lang == "en":
                continue
            d = translations[lang]
            for key, en_text in en.items():
                en_ph = set(_PLACEHOLDER.findall(en_text))
                if not en_ph:
                    continue
                tr_ph = set(_PLACEHOLDER.findall(d.get(key, "")))
                if en_ph != tr_ph:
                    mismatches.append(f"{lang}/{key}: EN={en_ph} vs {tr_ph}")
        assert not mismatches, "Placeholders incohérents :\n" + "\n".join(mismatches)
