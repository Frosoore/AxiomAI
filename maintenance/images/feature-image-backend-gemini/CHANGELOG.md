# Changelog — Backend Gemini pour la génération d'images

## 2026-06-10 — implémentation complète (session unique)

- `axiom/config.py` : + `image_gemini_model` (défaut `gemini-2.5-flash-image`), persistance
  automatique via le dataclass (clé inconnue ignorée par les vieux settings.json).
- `axiom/backends/gemini.py` : + `GeminiClient.generate_image_bytes(prompt, aspect_ratio)` —
  `generate_content` avec `response_modalities=["TEXT","IMAGE"]` + `ImageConfig(aspect_ratio=…)`
  (omis si SDK trop ancien), extraction du premier part `inline_data` (bytes, tolère base64 str).
  Passe par `_call_with_quota_retry` → pacing req/min, retry 429 au délai suggéré, compte à
  rebours `on_status` et annulation `cancel_event` réutilisés tels quels (TICKET-031/033).
- `axiom/image_generator.py` : + branche backend `"gemini"` (`_generate_gemini`) — clé
  `gemini_api_key` absente → None sans appel réseau ; hooks statut/annulation propagés depuis
  le backend texte de la session ; échec réel → None (TICKET-045). + `closest_aspect_ratio()`
  et `GEMINI_ASPECT_RATIOS` (l'API prend un ratio, pas des pixels — mapping depuis
  `image_width`/`image_height`).
- `ui/settings_dialog.py` : onglet Illustration — entrée « Google Gemini (cloud) » dans le
  combo backend + champ « Modèle d'image Gemini » (load/collect/retranslate).
- `axiom/localization.py` : + clé `image_gemini_model` (en + fr).
- Tests : +5 dans `tests/test_image_generator.py` (succès avec vérif modèle/contents/
  modalities/ratio 16:9, clé absente, échec API, réponse sans image, mapping ratio) ;
  `tests/test_settings_dialog.py` étendu (champ modèle + backend gemini sélectionnable,
  champ vide → défaut).
- Coordination : `maintenance/collab/claude/EN_COURS.md` purgé des lignes mergées (Pilier 2 →
  QA 048) et rempli avec ce chantier.

### Validation

- `test_image_generator.py` 32 ✅, `test_settings_dialog.py` 2 ✅, contrat partagé
  (`test_engine_headless.py` + `test_cli_play.py`) 15 ✅, `debug/startup_check.py` ✅,
  suite large 518 ✅, lot vector/Qt (`test_vector_*`, `test_phase6`, `test_ambiance_*`) 56 ✅.
- 21 échecs **préexistants et sans rapport** (`test_universe_as_code.py`,
  `test_source_preview.py::test_stage_puis_apply`) : `Path.read_text(newline=)` exige
  Python 3.13, le venv recréé est sur le 3.12 système → **TICKET-049** dans PENDING.md.

### Notes environnement

- Le venv `.venv/` du repo avait disparu — recréé (Python 3.12.3 système,
  `google-genai` 2.8.0, qui supporte bien `ImageConfig`/`response_modalities`).
- ⚠ Validation GUI utilisateur en attente (tour réel avec clé Gemini).
