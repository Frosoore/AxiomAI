# B3 — Migration Populate* vers le moteur — CHANGELOG

## 2026-06-10 — migration complète (session Claude)

**`axiom/populate.py` (nouveau, zéro Qt) :** les sept générateurs du Creator Studio
(`populate_meta`, `populate_stats`, `populate_rules`, `populate_events`,
`populate_entities`, `populate_lore`, `populate_map`) portés tels quels depuis
`workers/db_tasks.py` :
- signature commune `(db_path, mode="auto", custom_text=None, llm=None, on_status=…)` —
  LLM injectable (tests/composition), sinon construit depuis la config avec le modèle
  d'extraction ; progression via callback (les tâches Qt le branchent sur leurs signaux) ;
- insertion idempotente conservée (ids/noms connus sautés), parsing JSON résilient
  conservé, sync source TICKET-027 après chaque écriture ;
- `populate_entities` garde le commit **par chunk** (TICKET-031 : reprise après 429) ;
- registre `POPULATE_TARGETS` (clé → fonction) partagé par le Populate tab,
  la sandbox de preview et le CLI.

**`workers/db_tasks.py` :** les 7 `Populate*Task` → coquilles fines (`_BasePopulateTask`
commune, ~510 lignes de logique remplacées par ~60 lignes de wrappers ; API, signatures
et signaux inchangés → `db_worker.py` et le GUI n'ont pas bougé). `PreviewPopulateTask`
appelle le moteur directement (plus de sous-tâches Qt dans la sandbox).

**CLI :** `axiom populate <univers> -t entities -t lore [--text "consigne"]`
(`axiom/cli/populate_cmd.py`) — l'authoring devient pilotable headless, comme le reste
du moteur. `--text` ⇒ mode custom.

**`ARCHITECTURE.md` :** ligne « Authoring LLM d'univers (Populate*, carte) » retirée de
la table « non migré » (règle impérative de la table respectée).

**Différence assumée :** les ids générés collapsent les underscores consécutifs
(« L'éclipse » → `l_clipse` au lieu de `l__clipse`) — cosmétique, nouveaux inserts
uniquement.

**Tests :** `tests/test_populate_engine.py` (nouveau, 11 — fake LLM injecté : meta,
réponse vide, stats/rules/lore idempotents, events, map (parent 'none' → NULL,
connexions bidirectionnelles, nœud inconnu sauté), entités en mode consigne (stats non
définies filtrées), sync source sur univers-dossier, CLI ok + univers introuvable).
`tests/test_populate_resume.py` (reprise par chunk) vert sans modification — il passe
désormais par la coquille → moteur. Suites vertes : source_preview/db_worker_atomic/
phase6/gemini/universe_as_code/savestore (118), garde-fous collab + startup_check.
Smoke offscreen : PreviewPopulateTask → diff → ApplyStagedSourceTask de bout en bout.
