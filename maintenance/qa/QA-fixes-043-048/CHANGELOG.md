# CHANGELOG — QA-fixes 043→048

## 2026-06-10 — correction en lot (feu vert utilisateur)

### TICKET-044 — artefacts du merge supprimés
- Supprimés : `fix_tests.py`, `fix_tests2.py`, `refactor_tests.py` (racine — scripts regex
  one-shot de migration de tests, déjà appliqués) ; `assets/57f249e1-…/turn_1.png` et
  `assets/8815be43-…/turn_1.png` (PNG 1×1 de dev commités par accident). `assets/` ne garde
  que les vrais assets de l'app (icônes, captures).

### TICKET-047 — `axiom/session.py::_load_history`
- Le format `[SIMULTANEOUS ACTIONS FOR THIS TICK]` ne s'applique plus que si le tour
  contient **plusieurs** intentions ; une action solo garde son texte brut quel que soit
  le nom du joueur (avant : seul un acteur nommé « Player » y échappait).

### TICKET-043 — `axiom/session.py` : id joueur résolu, plus de `"player"` en dur
- `resolve_tick` (contexte image) : `player_entity_id = next(aid for aid in intents
  if aid != hero_entity_id)` — même règle que `arbitrator.py:163` ; localisation joueur
  et exclusion de la liste des personnages utilisent l'id résolu.
- `_get_hero_decision` : idem depuis `current_intents` ; stats/localisation du joueur et
  fallback nom (`id_to_name`) sur l'id résolu.

### TICKET-045 — `axiom/image_generator.py::generate_image`
- L'image mock est réservée au backend configuré `"mock"`. Backend inconnu → warning +
  `None`. Échec SD/ComfyUI (réseau, HTTP, réponse vide) → `None` — plus jamais de carré
  gris 1×1 dans le chat ni de fichier parasite dans `assets/`.
- Tests : les 2 tests « falls back to mock » inversés en « returns None » + nouveau test
  backend inconnu.

### TICKET-046 — onglet Illustration localisé proprement
- `ui/settings_dialog.py` : helper `_tr_img` (map fr en dur) supprimé ; tout passe par
  `tr()`. Clés ajoutées à `axiom/localization.py` (blocs en + fr) : `tab_image`,
  `image_enable`, `image_backend`, `image_api_url`, `image_width`, `image_height`,
  `image_steps`, `image_cfg_scale`, `image_workflow` (autres langues → fallback en).

### TICKET-048 — cycle de vie des illustrations
- `axiom/paths.py` : nouveau `get_assets_dir()` (honore data_dir injecté/env).
- `axiom/savestore.py` : section assets — `assets_dir_for_save`, `copy_save_assets`,
  `delete_save_assets`, `truncate_save_assets`/`truncate_assets_in`. Branchés :
  - `duplicate_save` → images copiées (save séparée **et** fork legacy embarquée) ;
  - `delete_save` / `delete_universe_saves` → images purgées ;
  - `pack_save` → entrées `assets/turn_*.png` dans le zip `.axiomsave` ;
  - `unpack_save` → images extraites sous l'id final (ré-identification comprise) ;
    noms filtrés (`turn_*.png` plats uniquement). Format compatible dans les deux sens.
- `axiom/session.py::rewind` → `truncate_assets_in(data_root/assets/save_id, turn_id)` :
  les illustrations des tours annulés ne réapparaissent plus.
- `workers/hardcore_worker.py` (mort hardcore) → purge des illustrations (étape 4b).
- `ui/tabletop_view.py` → utilise `paths.get_assets_dir()`.
- **Décision actée** : seul le chemin `Session` génère des images ; la file multijoueur
  (`ActionQueue`, arbitrator direct) n'en produit pas.

### Tests
- 8 nouveaux : 5 cycle de vie assets (`test_savestore.py::TestAssetsLifecycle`),
  2 session (043 id joueur nommé, 047 texte brut solo), 1 image (backend inconnu).
- Suites rejouées par sous-ensembles : 185 + 173 + 182 + 32 + 16 + 8 verts (et le lot
  Qt/vector, 56 verts, inchangé depuis la QA du matin). `startup_check` OK.
  `git status` sans fuite de fichiers.

### Doc
- Tickets 043→048 archivés dans `DONE.md`, retirés de `PENDING.md` (index compris).
- `maintenance/README.md` : ligne d'étape ajoutée.
