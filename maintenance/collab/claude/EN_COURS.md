# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main`
**Chantier :** TICKET-056 — messages user-facing du moteur (exceptions + events) en anglais. _(053/054 i18n + 055 CLI anglais terminés juste avant, même session.)_

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| **`axiom/localization.py`, `axiom/locales/`, `axiom/cli/i18n_cmd.py`** | **SUPPRIMÉS** (feu vert user) — l'i18n quitte le moteur | 2026-06-12 | ⚠ si tu utilisais `from axiom.localization import …`, c'est désormais `from core.localization import …` |
| `axiom/textfmt.py`      | nouveau : `fmt_num` (langue-neutre) reste côté moteur | 2026-06-12 | `from axiom.textfmt import fmt_num` |
| `axiom/time_system.py`  | `get_time_components()` (données + clé de phase) ; `get_time_string()` = anglais par défaut, zéro i18n | 2026-06-12 | le moteur n'émet plus de texte traduit |
| `axiom/modifiers.py`, `axiom/arbitrator.py` | `fmt_num` ← `axiom.textfmt` | 2026-06-12 | |
| `axiom/cli/main.py`, `pyproject.toml` | retrait `i18n-check` + `package-data` locales | 2026-06-12 | |
| `core/localization.py` + `core/locales/*.toml` | **nouveau foyer i18n** (tr, SUPPORTED_LANGUAGES, canonical_verbosity, format_time, 10 langues) | 2026-06-12 | nouvelle source de vérité des traductions GUI |
| ~30 fichiers `ui/*`, `workers/db_tasks.py` | bascule import `axiom.localization` → `core.localization` | 2026-06-12 | imports seulement, comportement inchangé |
| `axiom/cli/*.py` (main, play, compile_cmd, populate_cmd, saves_cmd) | traduction FR→EN du texte user-facing (help/print) | 2026-06-12 | strings seulement, aucune logique changée |
| `axiom/{compile,decompile,dev,library,package,saves,savestore,populate}.py` + `axiom/backends/gemini.py` | messages d'exception/events FR→EN (TICKET-056) | 2026-06-12 | **strings seulement** (placeholders préservés) — si tu assertes un message d'exception, il est désormais en anglais |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- Tout le tableau précédent (Pilier 2 + UX 028→033 + B3 + B4 + QA 034→048) est **mergé**
  (`9814896`, `2a52332`) — lignes retirées.
- **Packaging pip du moteur** (TICKET-009 clos : `pyproject.toml` racine, package PyPI
  `axiomai-engine`, `export_engine.py`, `axiom.help`) — **mergé dans `main`** (`fbe8b6e`).
- **Génération d'images** (branche `image-gen`, **mergée dans `main` le 2026-06-11**) :
  backend Gemini cloud (`image_gemini_model`), fiabilisation SD WebUI/ComfyUI
  (`image_timeout`, 404 → message --api, fix workflow ComfyUI : checkpoint auto via
  `/object_info` + VAEDecode `samples`), filtre streaming étendu aux fences ```` ```json ````
  (`ui/widgets/chat_display.py` : `_JSON_FENCES` — préviens si tu touches le buffer de stream).
