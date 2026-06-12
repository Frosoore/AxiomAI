# CHANGELOG — TICKET-056 : messages user-facing du moteur en anglais

## 2026-06-12 — livré

Suite de TICKET-055. Le moteur publié (`axiomai-engine`) dit désormais **en anglais** tout ce qu'il
expose à l'utilisateur. Périmètre : **messages d'exception** + **events** (`axiom dev`) + **statuts
surfacés**. Hors périmètre (laissés FR, chantier à part) : commentaires/docstrings internes, logs
`logger.*`, et les messages côté **app** (`workers/`, ex. `db_tasks.py "Populate preview annulé."`).

### Méthode
- Recensement **exhaustif des `raise`** (45) plutôt que grep d'accents : le français **sans accent**
  (« invalide », « introuvable », « impossible ») y échappe (même piège qu'au CLI).
- Traduction par **fragments** (préserve les placeholders `{...}` et la structure des f-strings).

### Exceptions traduites (FR → EN)
- `compile.py` (6 : TOML invalide, champ requis manquant, fichier/dossier/universe.toml introuvable,
  frontmatter invalide), `decompile.py` (1), `dev.py` (1 raise).
- `library.py` (4 : univers introuvable, déjà un univers-dossier, dossier existe déjà, conversion).
- `package.py` (6 : arbo source invalide, base univers introuvable, décompilation, format non reconnu,
  v1 corrompu, archive illisible).
- `saves.py` (correction/import impossible, sauvegarde introuvable ×3, save_state.toml invalide,
  at_turn/at_minute), `savestore.py` (6 : save introuvable ×3, archives invalide/illisible, db déjà
  existante, « cette save vient d'un autre univers » + « utiliser force »).
- `backends/gemini.py` (message d'exception quota mixte FR/EN → tout EN).
- Déjà EN (laissés) : `backends/base`, `backends/universal`, `memory`, `modifiers`, `rules`, `schema`.

### Events / statuts traduits
- `dev.py` : « Définition compilée » / « Modification détectée — définition rechargée » → EN ;
  event d'erreur « Source invalide (en attente de correction) » → « Invalid source (awaiting fix) ».
- `populate.py` : messages d'annulation/reprise (« Populate annulé… conservée(s) », « déjà
  insérée(s)… relancer reprendra ici… ») → EN.
- `saves.py` : libellé de journal `"Save importée"` → `"Save imported"` (donnée écrite dans la timeline).

### Tests
- Assertions FR mises à jour (mises à jour, pas suppressions) : `test_dev_hotreload`
  (compiled/reloaded), `test_populate_resume` (already inserted ×2), `test_generation_cancel`
  (match="kept"), `test_savestore` (not found — fait en TICKET-055). `test_generation_cancel`
  L218 (`got == ["annulé"]`) **laissé** : « annulé » est défini par le fake interne du test, pas par
  le moteur.
- Validation (offscreen) : **166 passed** sur les 9 suites impactées. 1 flaky **préexistant et non lié**
  (`test_registre_cancel_active_generations` : test threadé, passe 3/3 en isolation, flanche sous
  charge ; n'exécute aucun code modifié ici).
- Smoke : `compile_universe(...)` → `CompileError("Source folder not found: …")` ; scan final = zéro
  message FR user-facing (raise/event) dans `axiom/`.

### Reste hors périmètre (non traité, signalé)
- Logs `logger.*` du moteur (encore FR par endroits) — diagnostic, pas « user-facing » au sens surfacé ;
  chantier distinct si souhaité.
- Français côté **app** (`workers/`, certains messages) — l'app est la couche localisée (i18n), à
  traiter dans le chantier doc/UI si besoin.
