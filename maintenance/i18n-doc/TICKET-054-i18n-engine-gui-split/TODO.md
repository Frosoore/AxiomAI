# TODO — TICKET-054 : séparation i18n moteur / GUI

Suite directe de TICKET-053. Décision utilisateur (2026-06-12) : **le moteur ne traduit pas**.
Tout l'i18n (les 295 clés, dont les phases horaires) part côté app ; le moteur n'émet que des
**données / clés stables / anglais par défaut**.

## Moteur `axiom/` — devient sans traduction
- [x] `axiom/textfmt.py` : `fmt_num` (langue-neutre).
- [x] `axiom/time_system.py` : `get_time_components()` (données + clé de phase) ;
      `get_time_string()` = anglais par défaut, zéro i18n (sortie EN identique à avant).
- [x] `axiom/modifiers.py`, `axiom/arbitrator.py` : `fmt_num` ← `axiom.textfmt`.
- [x] Supprimés : `axiom/localization.py`, `axiom/locales/`, `axiom/cli/i18n_cmd.py` ;
      `i18n-check` retiré de `cli/main.py` ; `package-data` retiré du `pyproject.toml`.

## App — reçoit tout l'i18n
- [x] `core/localization.py` : `tr`, `fmt_num`, `SUPPORTED_LANGUAGES`, `canonical_verbosity`,
      `format_time`, `compute_coverage`, `reload_translations`.
- [x] 10 TOML déplacés `axiom/locales/*` → `core/locales/*`.
- [x] 26 fichiers app : import `axiom.localization` → `core.localization` (comportement inchangé).
- [x] 4 appels GUI `get_time_string` → `format_time` localisé.
- [x] `canonical_verbosity` importé de `core.localization` (creator_studio_view, tabletop_view).

## Tests
- [x] `test_localization.py` + `test_localization_coverage.py` → `core.localization`.
- [x] Outil de couverture app `tools/i18n_check.py` (remplace `axiom i18n-check`).

## Validation
- [x] Contrat moteur : aucune ref i18n importée dans `axiom/` (seuls des commentaires pointent vers
      core.localization) ; wheel reconstruit **sans** locales ni localization.py.
- [x] Tests verts (offscreen) : 60 passed ; collecte complète 565 tests → 0 import cassé.
- [ ] ⚠ Validation GUI réelle (changement de langue, affichage du temps localisé).
