# CHANGELOG — QA post-merge (Companion Mode + génération d'images)

## 2026-06-10 — session de contrôle qualité

### Vérifications passées (rien à signaler)
- Aucun marqueur de conflit résiduel dans le repo.
- `compileall` sur `axiom/ core/ workers/ ui/ database/ main.py` : OK.
- `debug/startup_check.py` : OK (signaux DbWorker, schéma, imports Qt/genai/moteur).
- Frontière headless intacte (`test_engine_headless` vert, `axiom/image_generator.py` zéro Qt).
- Résolution de conflit `axiom/config.py` saine : champs TICKET-031 (quota LLM) **et** champs
  image coexistent ; cache mtime de `load_config` (TICKET-042) préservé ; le dialogue Réglages
  reconstruit l'`AppConfig` **sans perdre aucun champ** (vérifié programmatiquement).
- API `intents=` : tous les appelants prod alignés (arbitrator, session, multiplayer,
  regenerate, CLI play, workers). Suppression de `debug/test_audio_logic.py` honorée.
- GUI : affichage des images branché (tour courant + rebuild d'historique avec
  `assets_dir`), sélecteur de joueur, événements `hero_intent` relus correctement.

### Bug corrigé (seul code modifié)
- **`tests/test_engine_port_b4.py`** : le `FakeArbitrator` de
  `test_action_queue_sequentielle_et_stop` gardait l'ancienne signature
  (`user_message=`/`player_entity_id=`) alors que le merge a migré
  `axiom/multiplayer.py::ActionQueue.run_loop` vers `intents=`. Le `TypeError` était avalé
  par le `except` de la boucle → l'assert échouait après 5 s **et** le thread non-daemon
  restait bloqué sur `queue.get()`, ce qui **gelait pytest à la sortie** (c'est ce qui
  faisait « pendre » toute suite contenant ce fichier). Fake aligné sur `intents=` ;
  10/10 verts, plus aucun blocage.

### Tests (par sous-ensembles, TICKET-008 oblige)
- 115 verts : arbitrator, session, prompt_builder, image_generator, llm_base.
- 269 verts : UaC, savestore, schema, event_sourcing, checkpoint, chronicler, rules,
  modifiers, lore, localization, config, persona, backup, chat_buffer…
- 20 verts : workers (narrative, db_worker ×2, hardcore, generation_cancel).
- 14 + 1 + 1 + 28 verts : cli_play, engine_headless, settings_dialog, dev_hotreload.
- 10 verts : engine_port_b4 (après fix).
- 66 verts : populate ×2, gemini_client, ollama_client.
- 56 verts : lot Qt/vector séparé (vector_memory, vector_threading, phase6, ambiance).
- **Total : 580 verts, 0 échec.** `git status` propre après les runs (pas de fuite de
  fichiers de test dans le repo).

### Tickets ouverts dans PENDING.md
- **TICKET-043** — `"player"` en dur dans `session.py` (contexte Héros + images vide si
  l'id joueur réel diffère). Priorité moyenne-haute.
- **TICKET-044** — artefacts du merge à supprimer (3 scripts regex jetables à la racine,
  2 PNG 1×1 commités dans `assets/`). Feu vert utilisateur requis pour suppression.
- **TICKET-045** — échec backend image → mock 1×1 affichée au lieu de rien.
- **TICKET-046** — onglet Illustration hors i18n (`_tr_img` en dur).
- **TICKET-047** — historique : format « SIMULTANEOUS ACTIONS » sur action solo.
- **TICKET-048** — cycle de vie des images vs saves (fork/suppression/.axiomsave/rewind/
  multijoueur).
