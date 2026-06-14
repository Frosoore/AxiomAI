"""
core/localization.py

Système d'internationalisation (i18n) **côté application** d'Axiom AI.

Depuis TICKET-054, l'i18n ne vit plus dans le moteur (`axiom/`) : le moteur émet des
données / clés stables / de l'anglais par défaut, et c'est ici — côté frontend — que tout
est traduit. Les traductions vivent dans `core/locales/<lang>.toml` (chargement paresseux,
mis en cache).

API :
    tr(key, **kwargs)        -> str   (traduction + formatage)
    fmt_num(val)             -> str   (ré-exporté du moteur : axiom.textfmt)
    SUPPORTED_LANGUAGES      -> dict[str, str]
    canonical_verbosity(v)   -> str
    format_time(time_system, total_minutes) -> str   (affichage du temps localisé)
    get_translations_dict()  -> dict[str, dict[str, str]]
    compute_coverage(ref)    -> dict   (audit i18n, cf. tools/i18n_check.py)
"""

from __future__ import annotations
import tomllib
from pathlib import Path

from axiom.logger import logger
from axiom.textfmt import fmt_num  # ré-export : formatage de nombres (langue-neutre, moteur)

__all__ = [
    "tr", "fmt_num", "SUPPORTED_LANGUAGES", "canonical_verbosity",
    "format_time", "get_translations_dict", "compute_coverage", "reload_translations",
]

# Supported languages with their native names
SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
    "zh": "简体中文",
    "ja": "日本語",
    "ko": "한국어"
}

# Répertoire des fichiers de traduction (côté app, plus dans le wheel du moteur).
_LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# Cache des traductions chargées : {lang: {key: text}}. Rempli à la 1ʳᵉ demande.
_TRANSLATIONS_CACHE: dict[str, dict[str, str]] | None = None

# Cache de la langue courante. `tr()` est appelé des centaines de fois par rendu
# d'UI ; sans ça chaque appel repassait par load_config() (un os.stat de cache
# mtime). La langue ne change qu'au save des réglages → `reload_translations()`
# (appelé par MainWindow à ce moment) vide ce cache.
_CURRENT_LANG: str | None = None


def _load_translations() -> dict[str, dict[str, str]]:
    """Charge (une seule fois) et met en cache les tables de toutes les langues.

    Un fichier manquant ou invalide donne une table vide (le fallback EN de `tr()`
    prend alors le relais), sans casser l'app.
    """
    global _TRANSLATIONS_CACHE
    if _TRANSLATIONS_CACHE is None:
        data: dict[str, dict[str, str]] = {}
        for lang in SUPPORTED_LANGUAGES:
            path = _LOCALES_DIR / f"{lang}.toml"
            try:
                data[lang] = tomllib.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                logger.warning(f"Locale file missing: {path}")
                data[lang] = {}
            except (tomllib.TOMLDecodeError, OSError) as exc:
                logger.error(f"Locale file invalid ({lang}): {exc}")
                data[lang] = {}
        _TRANSLATIONS_CACHE = data
    return _TRANSLATIONS_CACHE


def reload_translations() -> None:
    """Vide les caches i18n (traductions + langue courante).

    À appeler après un changement de langue (save des réglages) ou en hot
    reload / tests.
    """
    global _TRANSLATIONS_CACHE, _CURRENT_LANG
    _TRANSLATIONS_CACHE = None
    _CURRENT_LANG = None


def _current_language() -> str:
    global _CURRENT_LANG
    if _CURRENT_LANG is not None:
        return _CURRENT_LANG
    try:
        from axiom.config import load_config
        _CURRENT_LANG = getattr(load_config(), "language", "en")
    except Exception:
        _CURRENT_LANG = "en"
    return _CURRENT_LANG


def tr(key: str, **kwargs) -> str:
    """Translate a key into the current language with optional formatting.

    If any values in kwargs are numbers, they are formatted via fmt_num().
    """
    lang = _current_language()
    translations = _load_translations()
    lang_dict = translations.get(lang, translations.get("en", {}))
    text = lang_dict.get(key)

    if text is None:
        text = translations.get("en", {}).get(key)
        if text is None:
            logger.warning(f"Localization key missing: '{key}' (lang: {lang})")
            return key

    if kwargs:
        formatted_kwargs = {k: (fmt_num(v) if isinstance(v, (int, float)) else v) for k, v in kwargs.items()}
        try:
            return text.format(**formatted_kwargs)
        except (KeyError, ValueError) as exc:
            logger.error(f"Localization format error for key '{key}': {exc}")
            return text
    return text


def format_time(time_system, total_minutes: int) -> str:
    """Affichage du temps localisé à partir des données brutes du moteur.

    Le moteur (`TimeSystem.get_time_components`) fournit année/mois/jour/h/min + une clé
    de phase stable ; on traduit ici la phase et le gabarit selon la langue courante.
    """
    c = time_system.get_time_components(total_minutes)
    return tr(
        "time_fmt",
        year=c.year, month=c.month_name, day=c.day,
        hour=f"{c.hour:02d}", minute=f"{c.minute:02d}",
        phase=tr(c.phase_key),
    )


def get_translations_dict() -> dict[str, dict[str, str]]:
    """Expose le dictionnaire interne (debug / tests / couverture)."""
    return _load_translations()


_VERBOSITY_LEVELS = ("short", "balanced", "talkative")


def canonical_verbosity(value: str) -> str:
    """Normalise un niveau de verbosité vers sa valeur canonique.

    TICKET-032 : le Creator Studio a historiquement stocké dans `Universe_Meta`
    le TEXTE AFFICHÉ du combo (« équilibré », « locuaz », …) au lieu de la
    valeur canonique attendue partout ailleurs (`short`/`balanced`/`talkative`).
    Accepte les deux : canonique tel quel, sinon recherche inverse dans toutes
    les langues (migration douce des univers déjà enregistrés). Inconnu →
    'balanced'.
    """
    v = (value or "").strip().lower()
    if v in _VERBOSITY_LEVELS:
        return v
    for lang_dict in _load_translations().values():
        for level in _VERBOSITY_LEVELS:
            if lang_dict.get(level, "").lower() == v:
                return level
    return "balanced"


def compute_coverage(reference: str = "en") -> dict[str, dict[str, list[str]]]:
    """Couverture i18n de chaque langue vs la référence (clés manquantes / en trop).

    Retourne `{lang: {"missing": [...], "extra": [...]}}`. Utilisé par
    `tools/i18n_check.py` et `tests/test_localization_coverage.py`.
    """
    translations = get_translations_dict()
    ref_keys = list(translations.get(reference, {}))
    ref_set = set(ref_keys)
    report: dict[str, dict[str, list[str]]] = {}
    for lang in SUPPORTED_LANGUAGES:
        if lang == reference:
            continue
        lang_set = set(translations.get(lang, {}))
        report[lang] = {
            "missing": [k for k in ref_keys if k not in lang_set],
            "extra": sorted(lang_set - ref_set),
        }
    return report
