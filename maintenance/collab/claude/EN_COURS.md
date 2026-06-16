# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main`
**Chantier :** TICKET-062 (préparation bêta) — items 1, 2 et 4 (diagnostic CLI+GUI)
**VALIDÉS GUI le 2026-06-13** + CI GitHub Actions + fixes TICKET-050/066/068, le tout
**en attente de commit utilisateur** (rien de bloquant côté code). Restent hors-commit :
item 3 (check Windows) et item 5 (screens/GIF). TICKET-057 (doc intégrée) rouvert : contenu
trop succinct, à enrichir.

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| `universes/Myria/` (nouveau) + `.gitignore` | TICKET-062 : univers par défaut (Universe-as-Code, EN) — **créé, compile OK, en attente de relecture utilisateur + commit** | 2026-06-12 | dossier nouveau, zéro conflit ; gitignore : `universes/` → `universes/*` + `!universes/Myria/` |
| `core/bundled_universes.py` (nouveau) + `main.py` | TICKET-062 : installation de l'univers embarqué au 1ᵉʳ lancement — fait, VALIDÉ GUI le 2026-06-13, en attente de commit | 2026-06-12 | `main.py` : 4 lignes ajoutées juste avant `QApplication` ; préviens si tu touches la séquence de démarrage |
| `ui/creator_studio_view.py` | Fix crash Studio « Edit » : `_meta_float` tolérant sur tension/température/top_p — fait, VALIDÉ GUI le 2026-06-13, en attente de commit | 2026-06-12 | + fix données `universes/Myria/universe.toml` (`world_tension_level` 0.6) ; ⚠ TICKET-065 ouvert : clé tension en 2 casses (Chronicler vs Studio/compile) |
| `axiom/backends/universal.py` + `axiom/config.py` + `core/builtin_keys.py` (nouveau) + `ui/settings_dialog.py` + `workers/model_list_worker.py` (nouveau) + `core/locales/*.toml` | TICKET-062 item 2 : clés bêta Fireworks (rotation multi-clés, registre, sélecteur de modèles avec prix) — fait, VALIDÉ GUI le 2026-06-13, en attente de commit | 2026-06-12 | ⚠ défaut `fireworks_model` changé (`deepseek-v3p1` mort → `gpt-oss-120b`) ; +8 clés i18n ×10 langues (`browse_models`…) ; si tu touches `UniversalClient`, préserve `_send_with_rotation` |
| `axiom/backends/transport.py` (nouveau) + `gemini.py` + `universal.py` | QA-test-connexion-gemini : transport `IPv4FirstTransport` (IPv4 d'abord, fallback dual-stack, connect timeout 5 s) — fait, VALIDÉ GUI le 2026-06-13, en attente de commit | 2026-06-12 | le « Test Connection » bloquait des minutes (IPv6 cassée + SDK genai sans timeout), maintenant 0,27 s ; si tu touches la construction des clients httpx/genai, préserve ce transport (les deux clients le partagent) |
| `axiom/backends/universal.py` + `tests/test_reasoning_models.py` (nouveau) | TICKET-066 : modèles de raisonnement (gpt-oss, deepseek-v4, o-series…) — floor `max_tokens=2048`, `reasoning_effort: low` pour gpt-oss, `content` absent toléré dans `complete()` — **VALIDÉ GUI le 2026-06-13** (l'échec du 06-12 était TICKET-068, pas le backend), en attente de commit | 2026-06-12 | le Timekeeper crashait (`KeyError: 'content'`) et la narration sortait vide avec gpt-oss ; si tu touches `_get_payload`, préserve le floor et `_is_reasoning_model` |
| `axiom/memory.py` + `ui/diagnostic_dialog.py` + `workers/diagnostic_worker.py` (nouveaux) + `ui/main_window.py` + `.github/workflows/tests.yml` (nouveau) | TICKET-068 (embedding `local_files_only`), diagnostic GUI (Aide→Diagnostic), CI GitHub Actions — **VALIDÉS GUI le 2026-06-13**, en attente de commit | 2026-06-13 | `main.py`/`main_window.py` : action menu Aide ajoutée ; CI = 2 lots (contourne segfault TICKET-067) ; si tu touches le chargement de l'embedding, préserve `local_files_only=True` |
| `run.bat` + `test.bat` + `tools/diagnostic.py` + `run.sh` | TICKET-062 item 3 (audit Windows) : `run.bat` plancher 3.10→3.11, `#`→`REM`/emoji dans les `.bat`, garde-fou UTF-8 stdout du diagnostic CLI, **+ nettoyage code mort `run.sh`** (`check_lib`/`MISSING_LIBS`) — fait, en attente de commit | 2026-06-13 | audit statique only (pas de machine Windows) ; moteur déjà Windows-safe ; reste = **TICKET-069** (test machine réelle) ; détail `maintenance/TICKET-062-windows-support/` |
| `ui/widgets/entity_editor.py` | fix-entity-category-type : allow changing entity category/type in Creator Studio | 2026-06-16 | changing read-only table widget item to QComboBox and syncing it |


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
