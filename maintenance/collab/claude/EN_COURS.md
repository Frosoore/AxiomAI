# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `dev-documentation`
**Chantier :** TICKET-057 — doc intégrée à l'app GUI (tooltips, « expliquer cette page », quick tour, annuaire). Le TICKET-058 (site Sphinx) est livré, en attente d'activation Pages.

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| `docs/` (nouveau dossier racine) | site Sphinx (EN + FR) — **fait, en attente de merge** | 2026-06-12 | nouveau, zéro conflit possible |
| `.github/workflows/docs.yml` (nouveau) | build + déploiement GitHub Pages — **fait** | 2026-06-12 | nouveau |
| **docstrings de `axiom/*.py`** (19 fichiers) | traduction FR→EN des **docstrings publiques** — **fait** | 2026-06-12 | **aucune ligne de code touchée**, que des docstrings (621 tests verts) ; règle désormais : docstring publique = anglais |
| `requirements-dev.txt`, `.gitignore` | + outillage doc (sphinx, furo, myst-parser, sphinx-intl ; ignore `docs/_build/`, `*.mo`) | 2026-06-12 | |
| `axiom/__init__.py` | TICKET-060 : `axiom.help` (`_HELP_TEXT`) traduit FR→EN — **fait** | 2026-06-12 | texte/docstrings seuls, zéro ligne de code |
| `ui/` (vues principales + nouveaux modules `help_system`/`help_dialogs`) | TICKET-057 : doc intégrée (tooltips, bouton « ? », tour, annuaire) + **toggle des tooltips** (settings, `install_tooltip_gate`) + fixes retranslate `setup_view` — **fait, en attente de validation GUI + commit** | 2026-06-12 | ajouts ciblés (helpers + boutons) ; préviens si tu touches `ui/` |
| `core/locales/*.toml` | TICKET-057 : clés `doc_*` + 9 clés persona/toggle ×10 langues — **fait** (+ correction de clés préexistantes mal traduites : `chronicler_interval_label`, `univ_params`, `image_api_url` ko) | 2026-06-12 | ajouts en fin de fichier + ~14 lignes existantes corrigées |
| `axiom/config.py` | TICKET-057 : champ `doc_tooltips_enabled` (bool, défaut True) — **fait** | 2026-06-12 | ajout pur (dataclass + docstring), zéro logique touchée |

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
