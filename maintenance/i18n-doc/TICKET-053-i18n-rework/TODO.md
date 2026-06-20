# TODO — TICKET-053 : rework i18n

Objectif : assainir le système de traduction **avant** d'y déverser la doc intégrée.
Décisions utilisateur (2026-06-12) : **rework complet**, format **TOML par langue**, API `tr()` inchangée.

## 1. Externalisation des traductions
- [x] Créer `axiom/locales/<lang>.toml` (10 fichiers) générés depuis le `_TRANSLATIONS` actuel
      (script one-shot via tomlkit → round-trip vérifié identique au dict d'origine).
- [x] Réécrire `axiom/localization.py` : chargement paresseux + caché depuis `axiom/locales/*.toml`
      (lecture `tomllib`). Dict littéral de 2400 lignes supprimé (fichier 2419 → ~165 lignes).
- [x] **API publique inchangée** : `tr`, `fmt_num`, `SUPPORTED_LANGUAGES`,
      `canonical_verbosity`, `get_translations_dict` (+ ajout `reload_translations`).

## 2. Compléter la couverture
- [x] Remplir les ~85 clés manquantes pour es, de, it, pt, ru, zh, ja, ko
      (679 clés ajoutées). Les 10 langues sont à 295/295. Placeholders `{..}` cohérents (vérifié).

## 3. Outil de contrôle
- [x] Commande CLI `axiom i18n-check` (manquantes / en trop par langue, exit≠0 si trou ; `--show-keys`, `--strict`).
- [x] Test `tests/test_localization_coverage.py` : 0 clé manquante + cohérence des placeholders.

## 4. Packaging
- [x] `pyproject.toml` : `[tool.setuptools.package-data]` `axiom = ["locales/*.toml"]`.
      Wheel construit et vérifié : les 10 `.toml` sont embarqués.
- [x] `export_engine.py` : OK sans modif (`copytree` complet de `axiom/`, locales/ inclus).

## 5. Validation
- [x] Tests verts (offscreen) : `test_localization` + `test_localization_coverage` +
      échantillon moteur (`test_config`, `test_arbitrator`) + `test_settings_dialog` → 60 passed.
- [x] Smoke : `tr()` rend identique avant/après (round-trip TOML == dict d'origine).
- [ ] ⚠ Validation GUI réelle par l'utilisateur (changement de langue dans Settings, langues non-EN/FR).
