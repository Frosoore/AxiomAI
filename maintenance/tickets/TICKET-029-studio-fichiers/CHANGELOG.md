# TICKET-029 — Creator Studio : onglet « Fichiers » — CHANGELOG

## 2026-06-09 — implémentation complète (session Claude)

**Moteur (zéro Qt) :**
- `axiom/library.py` : + `LibraryError` + `convert_flat_db_to_folder(db_path)` —
  conversion d'un `.db` plat en univers-dossier : saves embarquées extraites en fichiers
  séparés (`saves/<clé>/`, clé inchangée = stem) puis reliées à la nouvelle source
  (`Save_Meta` : universe_db/universe_source/definition_hash → resync §7.6 à l'ouverture),
  définition décompilée vers `<parent>/<stem>/`, cache compilé, original renommé en
  `.db.bak` (récupérable, sorti de la découverte du Hub — pas de doublon). Conversion
  rejouable : une save déjà extraite n'est jamais écrasée.

**Workers Qt (coquilles fines) :**
- `workers/db_tasks.py` : + `RefreshDefinitionTask` (source texte → `.db` in-place,
  sémantique `axiom dev` : source malformée = CompileError remontée en signal, db intacte)
  et `ConvertFlatDbTask`.
- `workers/db_worker.py` : signaux `definition_refreshed` / `universe_converted` +
  méthodes `refresh_definition_from(src_dir)` / `convert_flat_to_folder()`.

**GUI :**
- `ui/widgets/universe_files_tab.py` (nouveau) : arbo des fichiers texte de l'univers
  (.toml/.md/.txt/.json, zones `.axiom-cache/` et `.git/` masquées), éditeur monospace,
  bouton « Enregistrer le fichier » (activé sur modification, garde-fou sur changement
  de fichier non sauvé), page alternative « .db plat » avec proposition de conversion.
- `ui/creator_studio_view.py` : onglet « Fichiers » (10e onglet) ; à l'enregistrement
  d'un fichier → `refresh_definition` en thread puis rechargement des vues classiques ;
  l'onglet se relit à chaque activation (la source est réécrite après chaque save
  Studio, TICKET-027) ; conversion → `load_universe(nouveau cache)`.
- `axiom/localization.py` : clés EN + FR (autres langues → fallback EN).

**Tests :** `tests/test_savestore.py` (+3 conversion : complète avec save migrée/reliée,
refus cache d'univers-dossier, refus dossier existant). Smokes offscreen : widget complet
(arbo, édition, save → signal, refresh task → db, source cassée → erreur propre,
mode .db plat → conversion → mode arbo), CreatorStudioView avec le nouvel onglet.
Suites vertes : phase6/dev_hotreload/universe_as_code/db_worker_atomic/localization (90),
garde-fous collab (engine_headless + cli_play + startup_check).

**Reste :** validation GUI réelle par l'utilisateur.
