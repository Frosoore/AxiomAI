# A2 — Bugs logiques

Corrections de comportements incorrects (pas de crash, mais logique défaillante).

- **2.1** Performance : déduplication O(N²) → O(1) dans la boucle de chaining du RulesEngine.
- **2.2** Fiabilité Qt : connexion/déconnexion répétée du signal `rewind_complete` → connexion permanente + flag `_rewind_in_progress`.
- **2.3** Typage Qt : slot `_on_rewind_done` sans param pour un `Signal(dict)` → `@Slot(dict)`.
