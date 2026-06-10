# B3 — Migration Populate* vers le moteur — TODO

Dernier morceau « non migré » d'ARCHITECTURE.md côté authoring : l'authoring LLM
d'univers (`Populate*`, carte) vivait dans `workers/db_tasks.py` (Qt).

- [x] `axiom/populate.py` (zéro Qt) : `populate_meta/stats/rules/events/entities/lore/map`
      — LLM injectable (tests), statut via callback optionnel, sync source (TICKET-027)
      après chaque écriture, commit par chunk conservé pour les entités (TICKET-031),
      registre `POPULATE_TARGETS`
- [x] `workers/db_tasks.py` : les 7 `Populate*Task` deviennent des coquilles fines
      (classe commune `_BasePopulateTask`, API/signaux inchangés) ;
      `PreviewPopulateTask` appelle le moteur directement
- [x] CLI : sous-commande `axiom populate <univers> -t <cible> [...] [--text ...]`
- [x] `ARCHITECTURE.md` : la ligne « non migré » Populate* retirée
- [x] Tests : `tests/test_populate_engine.py` (11 : un par générateur + sync source +
      CLI), `tests/test_populate_resume.py` toujours vert (reprise par chunk)
- [x] Validation : suites affectées (118 + 14) + garde-fous collab + startup_check + smoke
      sandbox de preview de bout en bout
