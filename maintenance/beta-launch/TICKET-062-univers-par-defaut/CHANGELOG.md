# CHANGELOG — TICKET-062 item 1 : câblage premier lancement

## Session du 2026-06-12

### Diagnostic du « univers Myria vide »
- L'utilisateur ne trouvait pas l'univers du ticket : `universes/Myria/`
  (créé session précédente) vivait **dans le repo** mais n'était installé
  nulle part. Le « Myria » vide visible dans l'app était son **vieux
  `~/AxiomAI/universes/Myria.db` de test** du 9 juin (0 save / 0 événement,
  cf. mémoire projet : univers de test à remettre à zéro après usage).

### Implémentation
- Nouveau module **`core/bundled_universes.py`** :
  `install_bundled_universes()` copie chaque univers embarqué du repo
  (`universes/<nom>/` contenant `universe.toml`) vers la bibliothèque du Hub
  (`~/AxiomAI/universes/<nom>/`). Une seule offre par univers, mémorisée dans
  `~/.config/AxiomAI/installed_bundles.txt` (un utilisateur qui supprime
  l'univers ne le voit pas revenir à chaque lancement) ; un dossier existant
  n'est **jamais écrasé** ; `.axiom-cache/` exclu de la copie (recompilé par
  la découverte du Hub via `ensure_compiled`) ; ne lève jamais (le démarrage
  ne doit pas mourir à cause du contenu embarqué).
- Branché dans `main.py` avant la création de la fenêtre (donc avant la
  première découverte du Hub).

### Tests
- Nouveau fichier `tests/test_bundled_universes.py` (8 tests) : installation
  sans cache, idempotence, suppression respectée, jamais d'écrasement,
  dossiers non-univers ignorés, bundle absent = no-op, bibliothèque non
  inscriptible = no-op loggé, le repo embarque bien Myria.

### Vérifications
- Réel sur la machine : installation OK, re-run = no-op, la découverte Hub
  compile et liste `Myria` (dossier UaC) — contenu vérifié dans le cache :
  11 entités, 15 lore, 18 lieux, 2 événements programmés.
- ⚠ Deux cartes « Myria » coexistent dans le Hub de l'utilisateur : la
  nouvelle (dossier) + son vieux `Myria.db` de test vide — suppression du
  vieux laissée à sa décision.
- Suites : 620 tests verts (grande suite hors Qt/vector).

## Session du 2026-06-12 — suite : crash du Studio sur « Edit » Myria

Rapport utilisateur : crash au clic sur Edit (log `crash_20260612_164842.log`,
`ValueError: could not convert string to float: 'cold war on many fronts'`).

### Causes (double bug)
1. **Données** : `universes/Myria/universe.toml` (rédigé session précédente)
   mettait du texte libre dans `world_tension_level`, qui doit être un nombre
   0→1 (`axiom/prompts.py`). Le compilateur stringifie sans valider, le moteur
   est défensif (Chronicler → défaut 0.3)… mais pas le Studio.
2. **Robustesse** : `ui/creator_studio_view.py::_on_meta_loaded` faisait
   `float()` sans filet sur 3 méta éditables par l'utilisateur
   (tension, température, top_p) → un univers importé malformé tuait l'app.

### Correctifs
- `universes/Myria/universe.toml` : `world_tension_level = 0.6` (guerre froide
  multi-fronts = tension élevée sans guerre ouverte), le flavour text passe en
  commentaire TOML. **Propagé à la copie installée** de la bibliothèque
  utilisateur ; recompilation vérifiée via la découverte Hub (`'0.6'` en base).
- `ui/creator_studio_view.py` : helper module `_meta_float(meta, key, default)`
  (parse tolérant) appliqué aux 3 champs — un univers malformé ne crashe plus
  le Studio, il retombe sur les défauts.

### Découverte → TICKET-065 (PENDING.md)
La clé tension existe en **deux casses** : `World_Tension_Level` (seed wizard
`db_helpers.py:115`, lecture Chronicler) vs `world_tension_level` (Studio,
compile/decompile) → le curseur de tension du Studio n'a aucun effet réel sur
le Chronicler. Hors scope ici, ticketé.

### Tests
- Nouveau `tests/test_creator_studio_meta.py` (4) : `_meta_float` valide/
  malformé/absent + régression « le Myria embarqué a une tension numérique
  dans [0,1] ».
- Suites : 624 tests verts (grande suite hors Qt/vector).
