# collab/ — Coordination du dev parallèle à deux

Ce dossier sert à ce que **deux développeurs travaillant en parallèle sur des branches Git
séparées** (tout le code écrit par des **agents CLI** : Claude Code d'un côté, Gemini CLI de
l'autre) **voient ce que l'autre est en train de faire** et **ne se marchent pas sur les pieds**.

Ce n'est **pas** une hiérarchie : `main` appartient aux deux à parts égales. C'est juste un point
de rendez-vous d'information + quelques règles.

## Répartition actuelle des chantiers

| Dev          | Agent        | Chantier                                   | Doc       |
|--------------|--------------|--------------------------------------------|-----------|
| Utilisateur  | Claude Code  | **Pilier 2 — Universe-as-Code**            | §7 + C.1  |
| Pote         | Gemini CLI   | **Pilier 5 — Le Temps comme substrat causal** | §6 + C.2  |

---

## Comment marche ce dossier

```
maintenance/collab/
├── README.md          ← CE fichier : les règles + la table des fichiers chauds. Stable, lu par les deux.
├── claude/
│   └── EN_COURS.md     ← écrit UNIQUEMENT par Claude (l'utilisateur). Ce que je touche en ce moment.
└── gemini/
    └── EN_COURS.md     ← écrit UNIQUEMENT par Gemini (le pote). Ce qu'il touche en ce moment.
```

**Règle d'or du dossier : chaque agent n'écrit QUE dans son propre sous-dossier, et LIT celui de
l'autre.** Comme ça, jamais deux agents n'éditent le même fichier de coordination → zéro conflit sur
la coordination elle-même.

- **Avant** de commencer à modifier du code dans `axiom/` (ou un autre fichier partagé), l'agent :
  1. lit le `EN_COURS.md` **de l'autre** pour voir s'il y a chevauchement ;
  2. déclare dans **son propre** `EN_COURS.md` les fichiers/modules qu'il s'apprête à toucher.
- **Après** avoir mergé / fini un lot : l'agent **vide ou met à jour** sa section dans son `EN_COURS.md`
  (on ne laisse pas une réservation périmée, sinon l'autre s'auto-bloque pour rien).

---

## Les règles (lues par les deux agents)

### 1. Branches courtes, intégration fréquente
Merger `main` dans sa branche **souvent** (idéalement chaque jour / à chaque fin d'étape). Beaucoup
de petits conflits frais et compréhensibles >>> un seul énorme conflit après des semaines de
divergence.

### 2. `main` est toujours vert
On ne merge dans `main` **que si** les garde-fous passent :
```bash
.venv/bin/python -m pytest tests/test_engine_headless.py tests/test_cli_play.py -q
.venv/bin/python debug/startup_check.py
```
C'est le **contrat partagé** : git ne détecte PAS un conflit *sémantique* (l'un change une fonction,
l'autre son appelant → « pas de conflit » mais code cassé). Seuls les tests l'attrapent.

### 3. Édition ciblée — mais pas timide
Modifier ce que le travail demande, **y compris de grosses refontes quand c'est justifié**. Ce qu'on
évite, c'est le bruit **gratuit hors-scope** : reformater/réindenter/réordonner les imports/renommer
des variables **sur des lignes qui n'ont rien à voir avec la tâche**. Ce bruit-là transforme une modif
d'1 ligne en conflit de 40 lignes avec le boulot de l'autre. La grosse modif utile est bienvenue ; le
diff cosmétique parasite, non.

### 4. Pas deux refontes de format concurrentes
On **ne fait jamais deux refontes en même temps** du même format/schéma (`.axiom`, `axiom/schema.py`).
Avant de toucher lourdement un fichier que l'autre chantier vise aussi : le déclarer dans `EN_COURS.md`
et/ou se parler. (Une table de « propriété » des fichiers chauds n'est **pas** en place pour le moment —
on la définira seulement si le besoin s'en fait sentir.)

### 5. Fichiers-index partagés = une ligne par item
`maintenance/README.md` (table d'étapes), `ARCHITECTURE.md` (table « code non migré »),
`Changelog.md`, `maintenance/PENDING.md`, `maintenance/DONE.md` : structurés **une ligne par entrée**,
chacun n'édite que **sa** ligne → conflits triviaux.

### 6. Qui résout un conflit de merge ?
Celui qui **merge en second** (donc celui qui intègre l'autre dans sa branche, ou qui ouvre sa PR
après). En cas de doute sur la bonne résolution, se parler.

---

## À coller dans le prompt de départ de chaque agent

> Avant de modifier du code dans `axiom/` ou tout fichier partagé : lis
> `maintenance/collab/README.md` (les règles) et le `EN_COURS.md` de
> l'AUTRE dev (`maintenance/collab/gemini/EN_COURS.md` si tu es Claude,
> `maintenance/collab/claude/EN_COURS.md` si tu es Gemini). Vérifie aussi le travail en vol avec
> `git fetch && git log --oneline main..origin/<branche-de-l-autre>`. Déclare les fichiers que tu vas
> toucher dans TON `EN_COURS.md` (claude/ ou gemini/ selon qui tu es). N'écris jamais dans le
> sous-dossier de l'autre.
