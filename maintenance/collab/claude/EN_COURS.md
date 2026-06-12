# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main` (TICKET-057/058 mergés — PR #3 `916079f` + PR #4 `33088e3`)
**Chantier :** rien en cours. TICKET-058 (site Sphinx) livré, en attente d'activation Pages.

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| _(rien)_ | | | |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- **Doc intégrée à l'app + site Sphinx** (TICKET-057/058/060, **mergés dans `main`** le
  2026-06-12, PR #3 `916079f` + PR #4 `33088e3`) : nouveaux modules `ui/help_system.py` /
  `ui/help_dialogs.py` (tooltips partout via `doc()`, bouton « ? »/F1, quick tour, annuaire),
  toggle settings `doc_tooltips_enabled`, `docs/` (Sphinx EN+FR, Pages à activer),
  ~250 clés ajoutées par langue dans `core/locales/*.toml`. ⚠ Si tu ajoutes un widget
  interactif dans `ui/`, documente-le (`doc(widget, "page.el")` + 2 clés ×10 langues) —
  sinon `tests/test_help_system.py` échoue ; `python tools/doc_check.py` liste les trous.
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
