# DOC — QA Hindsight (léger)

**Objectif.** Contrôle qualité du chantier Hindsight (recherche hybride + faits + croyances + lore) :
bugs, micro-opts, problèmes archi, faiblesses ; + recensement des features Hindsight non portées.

**Résultat.** Code jugé de très haute qualité (dégradation gracieuse partout, rollback atomique,
garde-fous LLM solides). Pas de bug de correction. Findings = coût/scaling « living » + robustesse.
Corrigé : TICKET-077 (consolidation bornée), 078 (cache BM25), 079 (lectures plein-table réduites),
080 (alignement fait↔id). Ouverts : 081 (Trend), 082 (modèles mentaux / directives / temporel).

Détail : `CHANGELOG.md`. Tickets : `../PENDING.md` (077→082).
