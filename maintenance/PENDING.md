# PENDING — tickets à étudier

> Règle de vie du fichier : un ticket **terminé** part dans `DONE.md` (trace condensée) et
> **disparaît d'ici**, index compris. Ne restent dans PENDING que les tickets ouverts,
> différés ou en attente d'une validation utilisateur.

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-009| Split physique `axiom-engine/` + `pyproject.toml` (pip-installable)        | ⏸ différé (handover + dev parallèle) |
| TICKET-017| Temps causal : `major_event_description` ignoré + **time-skip Chronicler** (spec §6.4) | ouvert (partiellement couvert par TICKET-018, domaine Pilier 5/Gemini) |

Tickets résolus/clos : voir `DONE.md` (001→008, 010→012, TC1→TC5, 015→033 sauf 017).


---

## TICKET-009 — Split physique `axiom-engine/` + `pyproject.toml` (pip-installable)

**⏸ DIFFÉRÉ (décision 2026-06-04).** Le code va être rendu au possesseur originel, qui ajoute des
features côté GUI (via Gemini CLI) sans se soucier de l'archi, en **parallèle** du travail moteur.
Dans ce contexte, le split physique sert le mauvais besoin (distribution, pas coordination) et
aggrave les risques : il n'empêche pas l'éparpillement de logique côté app, ajoute une frontière
deux-packages + install editable qu'un dev non-archi (et Gemini CLI) cassera, et crée un churn de
merge maximal pendant le dev parallèle. **Décision : rester en mono-repo** avec la séparation
*logique* `axiom/` (déjà en place) — 90 % du bénéfice, zéro du danger. Le split (et le `pip install`)
se fera **plus tard**, quand le repo sera repris en solo et que les features auront été migrées dans
l'engine. La migration des features app→engine est un chantier à part (piliers), cf. ci-dessous.

**Contexte :** le Pilier 1 a extrait le moteur dans `axiom/` (zéro Qt) et l'a rendu pilotable hors
GUI (API `Session`, CLI `axiom play`, étapes 1-8). C'est l'extraction **fonctionnelle**. Reste
l'objectif **packaging** du plan (§5.2, §5.4) : faire de `axiom-engine` un package **pip-installable**
distinct de l'app UI. Le `pyproject.toml` était reporté dès l'étape 1 (« étape de split physique »).

**Ce qui resterait à faire (à ordonnancer, non planifié dans les étapes 1-8) :**
- Déplacer `axiom/` sous un dossier racine dédié `axiom-engine/axiom/` (le nom de package reste
  `axiom` → les imports `from axiom...` ne changent pas, CLI inclus puisqu'il vit dans `axiom/cli/`).
- Écrire `axiom-engine/pyproject.toml` (deps moteur : chromadb, sentence-transformers, google-genai,
  etc. ; **zéro Qt**) + `console_script` `axiom = axiom.cli:main`. README package.
- `axiom-app/pyproject.toml` (l'app actuelle réduite à l'UI) **dépend de** `axiom-engine`.
- Pré-requis : **TICKET-003** (supprimer les anciens modules `core/`/`database/`/`llm_engine/`
  dépréciés, sinon doublons à l'install). Conditions de TICKET-003 désormais réunies côté run réel.

**Finitions de propreté §5.2 (non bloquantes, regroupables ici ou à part) :**
- Splitter `axiom/prompts.py` en sous-modules (`prompts/narrative.py`, `chronicler.py`, `mini_dico.py`,
  `populate.py`). N'impacte que les consommateurs internes (arbitrator/session/chronicler/db_tasks),
  **pas** le CLI ni l'API publique.
- Passer `VectorMemory` en `Protocol` (abstraction d'embedding injectable). Additif.

**Priorité :** moyenne — c'est le dernier cran du Pilier 1, mais l'extraction fonctionnelle (le gros
de la valeur : moteur headless + CLI) est déjà acquise. À faire avant tout projet voulant
`pip install axiom-engine` (mods, UI web, notebooks).

---

## TICKET-017 — Temps causal : `major_event_description` ignoré + time-skip Chronicler non implémenté

**⏳ OUVERT — partiellement couvert (2026-06-07).** Depuis TICKET-018, un grand saut temporel franchit
un palier de minutes et **déclenche bien le Chronicler** (le monde évolue pendant un long voyage), ce qui
couvre l'essentiel de l'intention §6.4. **Reste à faire** : le champ `major_event_description` renvoyé par
le Timekeeper n'est toujours **pas consommé** — soit l'exploiter (ex. forcer un World Turn sur événement
majeur explicite, indépendamment du palier), soit le retirer du prompt pour cesser de payer ces tokens.
Constat d'origine ci-dessous.

**Constat (`axiom/prompts.py:898,902-903` ; `axiom/arbitrator.py:300-311`).** Le prompt Timekeeper
demande au LLM un champ `major_event_description` (« Arrived at Hemlock », « Defeated the Goblin King »…),
mais `process_turn` ne lit que `elapsed_minutes` (l.310-311) : le champ est **parsé puis jeté**. On paie
des tokens pour une sortie inutilisée.

En parallèle, l'**edge case spec §6.4 « Time skip narratif »** (« si `elapsed_minutes > 480` (8h),
déclencher le Chronicler **avant** de retourner le résultat, pour que le monde évolue pendant le
voyage ») **n'est pas implémenté**. Les deux pointent vers la même fonctionnalité manquante : un grand
saut temporel devrait faire évoluer le monde.

**Ce qui serait à faire :**
- Soit **implémenter** le time-skip : si `elapsed_minutes` dépasse un seuil (ou si
  `major_event_description` est non-null), forcer un World Turn (`chronicler.force_trigger`) — ce qui
  redonne du sens au champ.
- Soit **retirer** `major_event_description` du prompt Timekeeper pour cesser de payer des tokens inutiles.

**Priorité :** moyenne (fonctionnalité spec manquante + léger gaspillage tokens). Lié à TICKET-018.

---


