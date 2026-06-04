# maintenance/

Ce dossier centralise le suivi de toutes les étapes de refactorisation et d'évolution du projet Axiom AI.

## Structure

Chaque étape (feature, bugfix, refacto, pilier du plan d'upgrade) reçoit son propre sous-dossier :

```
maintenance/
└── <nom-etape>/
    ├── TODO.md       — tâches à accomplir pour cette étape
    ├── CHANGELOG.md  — ce qui a été fait, commit par commit ou par session
    └── DOC.md        — documentation : objectif, décisions techniques, usage
```

## Règle

Avant de commencer à coder une étape, créer son dossier avec les trois fichiers.
Mettre à jour TODO.md et CHANGELOG.md au fil du travail.
Ne pas mélanger les étapes entre elles.

## Étapes

| Dossier | Statut | Description |
|---------|--------|-------------|
| `A1-bugs-bloquants` | ✅ terminé | Phase A §1 — corriger les crashs latents |
| `A2-bugs-logiques` | ✅ terminé | Phase A §2 — corriger les comportements incorrects |
| `A3-optimisations` | ✅ terminé | Phase A §3 — optimisations chirurgicales (perf + logs) |
| `A4-nettoyage-code-mort` | ✅ terminé | Phase A §4 — suppression code mort |
| `A5-hotfix-import-circulaire` | ✅ terminé | Hotfix — cycle d'import introduit par A3.4 (démarrage cassé) |
| `B1-pilier1-engine-headless` | ✅ fonctionnel (reste packaging) | Phase B §5 — Pilier 1 : moteur extrait dans `axiom/` (zéro Qt). Étapes 1 (copie) ✅, 2 (bascule app+tests) ✅, 3 (paths/config) absorbée→TICKET-004, 4 (API `Session`/`Universe`) ✅. Plan révisé §5.3-bis : 5 (injection chemins) ✅, 6 (parité `Session`) ✅, 7 (worker = coquille threading) ✅ + **validé run réel GUI**, 8 (CLI `axiom play`) ✅. Bugs résolus en chemin : TICKET-007 (Gemini), TICKET-008 (segfault torch+Qt). **Reste packaging** : split physique `axiom-engine/` + `pyproject.toml` pip-installable → TICKET-009 (dépend de TICKET-003). |
