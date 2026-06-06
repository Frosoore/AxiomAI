# Changelog - Pilier 5

## En cours
- Initialisation des documents de maintenance.
- Étape 1 : Ajout de `elapsed_minutes` et `scene_pace` au schéma JSON dans `axiom/prompts.py`.
- Étapes 2 & 4 : Parsing des nouveaux champs dans `ArbitratorEngine.process_turn` et passage de `elapsed_minutes` à `tick_modifiers`.
- Étapes 3 & 5 : Remplacement de l'avancée de temps fixe par `elapsed_minutes` dans `ui/tabletop_view.py` et basculement du `Chronicler` sur les minutes.
- Étapes 6 & 7 : Vérification du déclenchement des `Scheduled_Events` et implémentation du fallback `Timekeeper` directement dans le moteur `axiom/arbitrator.py`. Mise à jour de `ARCHITECTURE.md` en retirant la dépendance au TimekeeperWorker.
- Étape finale (Optimisation) : Délégation totale du calcul du temps au `Timekeeper` dans `ArbitratorEngine`, retrait de `elapsed_minutes` du schéma JSON du LLM principal pour alléger son prompt et améliorer la fiabilité.
- Étape 8 : Validation réussie de `debug/run_step7_live.py` prouvant que le moteur est autonome et fonctionnel sans l'UI Qt. Pilier 5 terminé.
