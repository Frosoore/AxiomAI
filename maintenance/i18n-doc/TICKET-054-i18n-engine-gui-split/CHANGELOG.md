# CHANGELOG — TICKET-054 : séparation i18n moteur / GUI

## 2026-06-12 — livré (code) — ⚠ validation GUI en attente

Suite directe de TICKET-053. Décision utilisateur : **le moteur ne traduit pas** — il émet des
données / clés stables / de l'anglais par défaut ; tout l'i18n vit côté frontend.

### Constat qui rend la séparation propre
- Seules 2 fonctions du moteur traduisaient, et **toutes deux n'étaient appelées que par le GUI** :
  `TimeSystem.get_time_string` (affichage du temps) et `canonical_verbosity` (rustine : le Studio
  stockait le texte traduit d'un combo). Aucune logique interne du moteur ne dépend des traductions.
- Le CLI n'utilisait déjà PAS le catalogue (messages en français codés en dur).

### Moteur `axiom/` — devient sans traduction
- **`axiom/textfmt.py`** (nouveau) : `fmt_num` (formatage de nombres, langue-neutre) reste côté moteur.
  `axiom/modifiers.py` et `axiom/arbitrator.py` l'importent désormais de là.
- **`axiom/time_system.py`** : nouvelle `get_time_components(total_minutes) -> TimeComponents`
  (année, mois, jour, h, min, **clé de phase** stable `dawn/morning/afternoon/dusk/night`) — données
  brutes, zéro i18n. `get_time_string()` conservée mais **rendu anglais par défaut** (dev/CLI/lib),
  sans aucune dépendance de localisation. Sortie EN identique à avant.
- **Supprimés** (feu vert utilisateur) : `axiom/localization.py`, `axiom/locales/` (les 10 TOML),
  `axiom/cli/i18n_cmd.py`. Retirés : la commande `axiom i18n-check` (`cli/main.py`) et le bloc
  `[tool.setuptools.package-data]` du `pyproject.toml`.
- **Wheel reconstruit et vérifié** : `axiomai-engine` n'embarque plus aucun `locales/` ni
  `localization.py` — la lib publiée est redevenue propre (que `axiom/`, zéro habillage GUI).

### App — reçoit tout l'i18n
- **`core/localization.py`** (nouveau, couche partagée sous `ui/` et `workers/`) : `tr`,
  `fmt_num` (ré-export de `axiom.textfmt`), `SUPPORTED_LANGUAGES`, `canonical_verbosity`,
  `compute_coverage`, `reload_translations`, et **`format_time(time_system, minutes)`** qui lit les
  données du moteur et traduit phase + gabarit selon la langue courante.
- **`core/locales/*.toml`** : les 10 langues déménagées depuis `axiom/locales/` (295 clés, dont les
  phases horaires).
- **`tools/i18n_check.py`** (nouveau) : remplace `axiom i18n-check` (audit de couverture côté app).
- **26 fichiers app** (`ui/*`, `workers/db_tasks.py`) : bascule `from axiom.localization import …`
  → `from core.localization import …` (imports seulement, comportement inchangé).
- **4 appels GUI** à `get_time_string` → `format_time(...)` localisé (`scheduled_events_editor` ×3,
  `tabletop_view` ×1). `canonical_verbosity` réimporté de `core.localization` (Studio + tabletop).

### Tests
- `tests/test_localization.py` + `tests/test_localization_coverage.py` → importent `core.localization`
  (et `compute_coverage` y est désormais).
- Validation (offscreen) : 60 passed (i18n + couverture + settings_dialog + config + arbitrator).
- **Collecte pytest complète** (565 tests, hors 4 fichiers vector/torch) : **0 import cassé**.
- Smokes : moteur s'importe seul (`get_time_string` EN par défaut, `get_time_components`, `fmt_num`),
  `format_time` rend « An 1, … (Aube) » en FR, `tools/i18n_check.py` → 10/10 langues OK.

### Reste
- ⚠ Validation GUI réelle : changer de langue + vérifier l'affichage du temps localisé en jeu.
