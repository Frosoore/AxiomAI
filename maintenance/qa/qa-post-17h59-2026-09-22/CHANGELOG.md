# CHANGELOG — QA post-`cb9e56d` (2026-09-22)

## GUI bloqué au démarrage — corrigé
- **Cause (reproduite)** : `4967506` a remplacé `QApplication` par une sous-classe qui surcharge
  `notify()` en Python (blocage de la molette sur spinbox/combos). `notify()` est appelé pour les
  événements de **tous** les threads ; au premier `QMediaPlayer()` (`ui/ambiance_manager.py:34`), le
  thread interne `QAudioContext` y entre et attend le GIL tenu par le thread principal, lui-même
  bloqué dans le constructeur C++ → interblocage, la fenêtre ne s'affiche jamais. Repro minimale :
  `QApplication` nu → OK en 0,02 s ; sous-classe `notify` → figé (faulthandler).
- **Fix** (`main.py`) : `_make_application_class()` → `_make_wheel_guard()`, même logique mais en
  **filtre d'événements applicatif** (`app.installEventFilter`), qui ne voit que les objets du thread
  principal. Vérifié : fenêtre visible après lancement réel ; molette ignorée sur un spinbox non
  cliqué (le parent défile), active après clic.

## CI i18n — corrigé
- 6 clés ajoutées en EN par `4967506` sans traduction (`infer_temporary`, `temporary`, `dyn_kind`,
  `dyn_timescale`, `dyn_crash`, `memory_extracting`) → traduites dans les 9 autres langues.
  `tools/i18n_check.py` : 780/780 partout ; `test_localization*.py` verts.

## FOREIGN KEY au premier compile — corrigé
- **Cause (reproduite, aussi sous Linux)** : `d491365` a réécrit `universes/Myria/locations/map.toml`
  trié par ordre alphabétique → 7 lieux listés avant leur `parent_id` (`cinderhold`→`continental_heart`,
  `highport`→`western_coasts`…). `compile.py::_populate` insère dans l'ordre du fichier avec des FK
  immédiates → `IntegrityError`. Seule une install **sans cache** passe par ce chemin (Windows neuf) ;
  chez nous un vieux `.axiom-cache` passait par `refresh_definition` et masquait le bug. Et comme
  `library.discover_universes` n'attrape que `CompileError`, l'erreur brute remontait à chaque Hub.
- **Fix** `axiom/compile.py::_populate` : `BEGIN` + `PRAGMA defer_foreign_keys=ON` (FK vérifiées au
  COMMIT → ordre indifférent ; une référence réellement pendante échoue toujours).
  `compile_universe` convertit une `IntegrityError` en `CompileError` (univers ignoré avec warning
  au lieu d'une pop-up en boucle) et nettoie le `.tmp`.
- **Même bug latent** `axiom/dev.py::refresh_definition` : le PRAGMA était posé **avant** `BEGIN`,
  donc sans effet (hors transaction, le COMMIT implicite de l'instruction le remet à OFF) → inversé.
- Tests ajoutés (`tests/test_universe_as_code.py`) : enfant avant parent, parent pendant →
  `CompileError` sans `.tmp` résiduel, Myria livré compilé à neuf.

## Autres correctifs issus de l'audit
- `ui/hub_view.py:369` : `read_universe_card_metadata` renvoie 4 valeurs depuis `c326aa1`, l'export
  d'univers depuis le Hub dépaquetait 3 → `ValueError` à chaque export. Corrigé.
- `main_web.py` `/api/session/canonize/apply` : les chemins `staged_dir`/`src_dir`/`universe_db`
  venaient du client puis servaient à un miroir avec purge d'orphelins + `rmtree` → suppression de
  fichiers arbitraire par simple POST local. Désormais pris uniquement de l'aperçu mémorisé côté
  serveur (`LAST_CANONIZE_PREVIEW`, lié à la save active). Le client web n'utilisait pas ce chemin.
- `web/app.js` : échappement HTML des contenus LLM dans l'inventaire, le panneau stats et la
  timeline ; suppression du doublon `escapeHtml` (le 2ᵉ, qui gagnait, affichait `0` comme `""`).
  Le reste du XSS systémique → TICKET-093.

## Méthodo (commits des autres contributeurs)
- `maintenance/README.md` : `feature-universe-description` et `web-ui-continuation` n'étaient pas
  indexés → ajoutés ; TICKET-092 n'était pas tracé dans `PENDING.md` → ajouté.
- 4 des 5 commits de Frosoore sans ligne `AXIOM_STATUS.md` ; `a11a554` sans aucun dossier d'étape.
  Non rattrapable a posteriori (historique git) — noté ici.
- Nouveaux tickets : TICKET-093 (XSS web), 094 (CORS/CSRF web), 095 (`materialize_state` non
  historique pour inventaire/lore/modificateurs), 096 (verbosité par défaut passée à `talkative` —
  décision), 097 (code mort multijoueur), 098 (clés i18n orphelines).

## Vérifications
- Lancement réel `main.py` : fenêtre visible. Wheel guard testé en offscreen (bloqué non cliqué →
  le parent défile ; actif après clic).
- `pytest tests/ --ignore=tests/test_ambiance_manager.py` (commande CI, Python 3.14) : **1016 passed** ;
  `test_ambiance_manager.py` seul : 7 passed ; `debug/startup_check.py` : OK ; `tools/i18n_check.py` : OK.
- Test ajouté `tests/test_web_server.py::test_canonize_apply_ignores_client_paths` (400, apply jamais
  appelé, fichiers victimes intacts).
- Non vérifié : Python 3.11/3.12 en local (la CI GitHub les couvre) ; test réel sous Windows.
