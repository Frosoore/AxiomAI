# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `dev-documentation`
**Chantier :** TICKET-058 — site de doc Sphinx de la lib `axiomai-engine` (nouveau dossier `docs/`, GitHub Pages).

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| `docs/` (nouveau dossier racine) | site Sphinx (EN + FR) — **fait, en attente de merge** | 2026-06-12 | nouveau, zéro conflit possible |
| `.github/workflows/docs.yml` (nouveau) | build + déploiement GitHub Pages — **fait** | 2026-06-12 | nouveau |
| **docstrings de `axiom/*.py`** (19 fichiers) | traduction FR→EN des **docstrings publiques** — **fait** | 2026-06-12 | **aucune ligne de code touchée**, que des docstrings (621 tests verts) ; règle désormais : docstring publique = anglais |
| `requirements-dev.txt`, `.gitignore` | + outillage doc (sphinx, furo, myst-parser, sphinx-intl ; ignore `docs/_build/`, `*.mo`) | 2026-06-12 | |
| `axiom/__init__.py` | TICKET-060 : `axiom.help` (`_HELP_TEXT`) traduit FR→EN — **fait** | 2026-06-12 | texte/docstrings seuls, zéro ligne de code |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- **Rework i18n complet** (TICKET-053/054/055/056, commit `f1e95f4` sur `dev-documentation`) :
  l'i18n a **quitté le moteur** → `core/localization.py` + `core/locales/*.toml` (10 langues).
  ⚠ `from axiom.localization import …` n'existe plus → `from core.localization import …`.
  Le moteur publié (CLI, exceptions, events) parle **anglais** ; `fmt_num` vit dans
  `axiom/textfmt.py` ; le temps GUI s'affiche via `core.localization.format_time(...)`.
- Tout le tableau précédent (Pilier 2 + UX 028→033 + B3 + B4 + QA 034→048) est **mergé**
  (`9814896`, `2a52332`) — lignes retirées.
- **Packaging pip du moteur** (TICKET-009 clos : `pyproject.toml` racine, package PyPI
  `axiomai-engine`, `export_engine.py`, `axiom.help`) — **mergé dans `main`** (`fbe8b6e`).
- **Génération d'images** (branche `image-gen`, **mergée dans `main` le 2026-06-11**) :
  backend Gemini cloud (`image_gemini_model`), fiabilisation SD WebUI/ComfyUI
  (`image_timeout`, 404 → message --api, fix workflow ComfyUI : checkpoint auto via
  `/object_info` + VAEDecode `samples`), filtre streaming étendu aux fences ```` ```json ````
  (`ui/widgets/chat_display.py` : `_JSON_FENCES` — préviens si tu touches le buffer de stream).
