# TICKET-030 — Populate × Universe-as-Code — CHANGELOG

## 2026-06-09 — implémentation complète (session Claude)

Périmètre validé par l'utilisateur en début de session : Populate ciblé + prévisualisation
du diff texte + canonisation depuis la partie (authoring LLM→texte direct §7.9 écarté).

**Moteur (zéro Qt) :**
- `axiom/library.py` : + `diff_source_trees(before, after)` (diff unifié par fichier,
  zones protégées exclues) et `apply_staged_source(staged, src, db)` (miroir de l'arbre
  validé vers la source + `refresh_definition` in-place). `_mirror_tree` durci : les zones
  protégées ne sont plus copiées non plus DEPUIS l'arbre source.
- `axiom/prompts.py` : + `CANONIZE_SYSTEM_PROMPT` / `build_canonize_prompt` — extraction
  des éléments canon (entités npc/faction + entrées de lore) d'un transcript de jeu,
  listes d'exclusion (déjà connus, joueur jamais extrait).

**Workers Qt :**
- `workers/db_tasks.py` :
  - `_stage_source_change(universe_db, mutate)` — la sandbox : copie temporaire du `.db`,
    mutation dessus, reconstruction de l'arbre source futur (sync db→texte TICKET-027),
    diff contre une **baseline normalisée** (sync de la copie *avant* mutation : le diff
    ne montre que l'effet de la génération, pas le bruit de reformatage d'une source
    écrite à la main). Rien n'est écrit dans l'univers réel.
  - `PreviewPopulateTask` (enchaîne les Populate* choisis sur la copie),
    `ApplyStagedSourceTask` (applique + nettoie + resync optionnel de la save en cours),
    `CanonizeStoryTask` (LLM → `_insert_canon` idempotent → preview ou application directe
    + `refresh_save_definition`), `discard_staged_source` (annulation).
- `workers/db_worker.py` : signaux `populate_previewed`/`staged_applied`/`story_canonized`
  + méthodes `preview_populate`/`apply_staged`/`canonize_story`.

**GUI :**
- `ui/widgets/diff_preview_dialog.py` (nouveau) : fichiers impactés (+/±/−, couleurs) +
  diff unifié monospace, boutons Appliquer/Annuler. Réutilisé par les deux flux.
- `ui/widgets/populate_tab.py` : case « Prévisualiser le diff avant d'appliquer »
  (cochée par défaut, désactivée sur .db plat via `set_preview_supported`) ; signal
  `populate_requested` étendu à 4 args (preview).
- `ui/creator_studio_view.py` : en mode preview, le lot Populate part en sandbox après le
  save habituel ; dialogue de diff ; Appliquer → source + db + reload des vues.
- `ui/tabletop_view.py` : toggle « Canon auto » (OFF par défaut, jamais persisté) + bouton
  « Canoniser… » dans la barre du haut. Ponctuel = transcript récent (8 entrées) → LLM →
  dialogue de diff → application sur l'UNIVERS + resync de la save en cours. Auto = même
  chose en silence après chaque tour (statut seulement). Erreur claire si la save n'est
  pas liée à un univers-dossier (`uac_folder_required`).
- `axiom/localization.py` : clés EN + FR.

**Tests :** `tests/test_source_preview.py` (nouveau, 10) : diff (ajout/modif/suppression,
zones protégées), apply, sandbox sans effet sur le réel, stage→apply, refus .db plat,
no-op, `_insert_canon` idempotent, résolution de l'univers depuis une save séparée, refus
sans univers-dossier. Smokes offscreen GUI (populate tab, dialogue diff, studio, tabletop).
Suites vertes : phase6/db_worker_atomic/universe_as_code/dev_hotreload/savestore/
localization/prompt_builder (163) + garde-fous collab + startup_check.

**Note d'usage :** appliquer une prévisualisation normalise au passage la source (même
réécriture que toute sauvegarde Studio depuis TICKET-027) ; le diff affiché, lui, ne
montre que l'effet de la génération.

**Reste :** validation GUI réelle par l'utilisateur (les chemins LLM exigent une clé Gemini).
