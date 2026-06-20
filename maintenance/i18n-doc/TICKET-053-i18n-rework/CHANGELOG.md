# CHANGELOG — TICKET-053 : rework i18n

## 2026-06-12 — rework complet livré (code) — ⚠ validation GUI en attente

### Audit de départ
- EN/FR complets (295 clés) ; 8 autres langues incomplètes (es=84, autres=85 clés manquantes
  chacune → fallback EN → UI mi-traduite). Fichier monolithe `axiom/localization.py` de 2419 lignes.
- `load_config` déjà mis en cache par mtime (perf de `tr()` OK, rien à faire côté perf).
- Décisions utilisateur : rework complet, TOML par langue, API `tr()` inchangée.

### Externalisation (TOML par langue)
- Nouveau dossier `axiom/locales/` avec `en/fr/es/de/it/pt/ru/zh/ja/ko.toml`.
- Génération initiale par script one-shot depuis le `_TRANSLATIONS` littéral → **round-trip
  vérifié strictement identique** au dict d'origine (0 corruption sur les 10 langues).
- `axiom/localization.py` réécrit : table littérale supprimée, remplacée par `_load_translations()`
  (lecture `tomllib`, **chargement paresseux + caché**). Ajout `reload_translations()` (vide le cache).
  API publique inchangée : `tr`, `fmt_num`, `SUPPORTED_LANGUAGES`, `canonical_verbosity`,
  `get_translations_dict`. Fichier passé de 2419 → ~165 lignes. Aucun des ~25 `from axiom.localization
  import tr` de l'UI n'a eu besoin d'être modifié.

### Complétion de la couverture
- 679 clés traduites/ajoutées (es +84, les 7 autres +85) → **10 langues à 295/295**.
- Placeholders de formatage `{path}`/`{turn}`/`{count}`/`{name}`/`{entities}`/`{lore}` :
  cohérence EN ↔ chaque langue vérifiée (aucune divergence → pas de casse `str.format` au runtime).
- Style maison respecté : « save » gardé comme emprunt dans les langues latines (comme le FR) ;
  de/ru/zh/ja/ko traduits proprement. ⚠ qualité zh/ja/ko/ru non vérifiable par l'utilisateur (assumé).

### Outil de contrôle
- Nouvelle commande **`axiom i18n-check`** (`axiom/cli/i18n_cmd.py` + subparser dans `cli/main.py`) :
  compteurs manquantes/en trop par langue, exit≠0 si trou, options `--show-keys`/`--strict`/`--reference`.
  Logique partagée `compute_coverage()` réutilisée par le test.
- Nouveau test `tests/test_localization_coverage.py` : 0 clé manquante, 0 clé orpheline, cohérence
  des placeholders, 10 tables non vides.

### Packaging
- `pyproject.toml` : ajout `[tool.setuptools.package-data]` → `axiom = ["locales/*.toml"]`.
- Wheel construit (`axiomai_engine-0.1.2`) et inspecté : les **10 `.toml` sont embarqués** +
  `localization.py` allégé. `export_engine.py` OK sans modif (copytree complet de `axiom/`).

### Validation
- Tests verts (offscreen) : `test_localization` (11) + `test_localization_coverage` (4) +
  `test_config` + `test_arbitrator` + `test_settings_dialog` → 60 passed.
- Découverte env : sous ce sandbox headless, **toute** la suite pytest abortait (Qt `QApplication`
  du conftest sans serveur d'affichage, Python 3.14) → contournement `QT_QPA_PLATFORM=offscreen`
  (toute la suite repasse). Non lié à la modif ; noté dans la mémoire `project_test_env`.

### Reste
- ⚠ Validation GUI réelle par l'utilisateur : changer la langue dans Settings et parcourir une
  langue non-EN/FR (es/de/it/pt/ru/zh/ja/ko) pour confirmer l'absence de texte anglais résiduel.
- Script one-shot conservé pour trace : `maintenance/TICKET-053-i18n-rework/_fill_locales.py`.
