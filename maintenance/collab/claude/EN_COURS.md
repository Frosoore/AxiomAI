# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main`
**Chantier :** rien en cours. `feature-cloud-text-providers` commité (`2d798fe`) et mergé
avec la doc intégrée (TICKET-057) — merge résolu côté Claude le 2026-06-12.

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| _(rien)_ | | | |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- **Fournisseurs cloud de texte** (`feature-cloud-text-providers`, `2d798fe`, mergé avec
  ta doc intégrée le 2026-06-12) : l'onglet Réglages « Cloud (Gemini) » est devenu
  **« Cloud »** avec un menu déroulant de fournisseur (Gemini / Claude / Venice /
  Fireworks / OpenAI / OpenRouter), clé+modèle persistés **par fournisseur**
  (`axiom.config.OPENAI_COMPAT_PROVIDERS`, nouvelles valeurs `llm_backend`).
  ⚠ Conséquences pour toi : widgets `_gemini_key/_gemini_model` → `_cloud_key/_cloud_model`,
  refs doc `settings.tab_gemini/gemini_key/gemini_model` → `settings.tab_cloud/cloud_key/
  cloud_model` (+ `settings.cloud_provider`), clés locales `doc_settings_gemini_*` →
  `doc_settings_cloud_*` (10 langues), clé `cloud_gemini` → `tab_cloud` + `cloud_provider`.
  « Test Connection » cloud = probe d'1 token (`ConnectionTestWorker(probe_model=True)`).
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
  Le moteur publié (CLI, exceptions, events, `axiom.help`) parle **anglais**.
- **Packaging pip du moteur** (TICKET-009 clos) — mergé dans `main` (`fbe8b6e`).
- **Génération d'images** (mergée 2026-06-11) : backend Gemini cloud, fiabilisation
  SD WebUI/ComfyUI, filtre streaming `_JSON_FENCES` (`ui/widgets/chat_display.py` —
  préviens si tu touches le buffer de stream).
