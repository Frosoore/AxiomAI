# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main` (working tree, commit en attente de feu vert)
**Chantier :** feature-cloud-text-providers — onglet « Cloud » des paramètres avec menu
déroulant de fournisseur texte (Gemini / Claude / Venice AI / Fireworks AI / OpenAI).

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| `axiom/config.py`       | nouveaux champs clé/modèle par fournisseur + table providers + build | 2026-06-12 | nouvelles valeurs `llm_backend` : claude/venice/fireworks/openai |
| `axiom/backends/universal.py` | + `extra_headers`, `max_stop_sequences` (rétro-compatible) | 2026-06-12 | signature constructeur étendue, défauts inchangés |
| `ui/settings_dialog.py` | onglet Gemini → onglet « Cloud » générique | 2026-06-12 | widgets `_gemini_key/_gemini_model` renommés `_cloud_key/_cloud_model` |
| `core/locales/*.toml`   | + `tab_cloud`, `cloud_provider` ; − `cloud_gemini` | 2026-06-12 | 10 langues |
| `tests/test_config.py`, `tests/test_settings_dialog.py` | + tests providers | 2026-06-12 | |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- **Doc Sphinx + i18n rework** (TICKET-053→058/060) — **mergé dans `main`** (`916079f`) :
  l'i18n a quitté le moteur → `core/localization.py` + `core/locales/*.toml` (10 langues).
  ⚠ `from axiom.localization import …` n'existe plus → `from core.localization import …`.
  Le moteur publié (CLI, exceptions, events, `axiom.help`) parle **anglais**.
- **Packaging pip du moteur** (TICKET-009 clos) — mergé dans `main` (`fbe8b6e`).
- **Génération d'images** (mergée 2026-06-11) : backend Gemini cloud, fiabilisation
  SD WebUI/ComfyUI, filtre streaming `_JSON_FENCES` (`ui/widgets/chat_display.py` —
  préviens si tu touches le buffer de stream).
