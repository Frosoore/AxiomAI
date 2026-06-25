# Pilier 8 — Fiabilité de l'Arbitrator (cohérence prose↔état)

Réf. plan : `maintenance/AXIOM_AI_UPGRADE_DETAILS.md` §23 (PARTIE VIII).
Issu de l'audit du 2026-06-23 (lecture intégrale de `axiom/arbitrator.py`).

Principe : le **durcissement déterministe gratuit est ON et non-togglable** (socle) ;
seuls les mécanismes à appel LLM supplémentaire seront togglables (§24, plus tard).

## Lot 1 — durcissement déterministe gratuit (en cours)

- [x] **1. Bug « plot armor » Companion (❺).** Clamp réel à 0. **Décision user 2026-06-23 :
  plancher à 0 confirmé** (vs 1 / ignorer). Figé.
- [x] **2. Bornes / énums / légalité dans `_validate_change` (❹).** min/max + énums
  (`allowed`) déclarés dans `Stat_Definitions.parameters` (JSON, zéro migration) ;
  `Location` ∈ lieux connus. max → clamp, min/énum/lieu → rejet. +7 tests. Fait 2026-06-23.
- [x] **3. Sortie structurée / `response_schema` (❸).** Param `response_schema` ajouté au
  contrat backend ; Gemini honore enfin `response_format="json"` + `response_json_schema`
  (gros gain : populate/consolidate/factextract enfin contraints) ; Ollama `format`=schéma ;
  UniversalClient reste `json_object` (sûr cross-provider) ; Timekeeper passe en JSON+schéma.
  Tour narratif **non concerné** (prose streamée + fence inline). +9 tests. Fait 2026-06-23.

## Lot 2 — détecteur de divergence (heuristique, zéro LLM) — plus tard
## Lot 3 — « résoudre puis raconter » (option Fidélité, +1 appel LLM) — après §24

## Questions ouvertes (pour l'utilisateur)
- Plot armor : clamp à **0** (comportement documenté, retenu) vs **1** (survie garantie
  si une règle tue à HP<=0) vs **ignorer** la réduction (HP inchangé) ? À trancher.

---

## ▶ PROCHAINE SESSION — commencer ici

État : **Lot 1 COMPLET** (items 1 plot armor, 2 bornes/énums/légalité, 3 sortie
structurée), testé (`test_arbitrator` 57 verte + backends + consumers + garde-fous),
**non commité**. On passe au **Lot 2**.

1. **Lot 2 — détecteur de divergence prose↔état (§23.4)** : sans 2ᵉ appel LLM, après
   parsing, scanner `narrative_text` pour des **affirmations chiffrées / d'inventaire**
   (« +N or », « tu perds X PV », « tu trouves <item> ») **sans** `state_change`/
   `inventory_change` correspondant. Écart → marquer le tour `unreliable` (exploitable
   par le harnais §10 + UI) et/ou re-prompt léger. Heuristique imparfaite mais zéro token.
   → flag `divergence_detector_enabled`, **ON par défaut, togglable** (cf. §24).
   - emplacement : dans `process_turn` après le parsing du tool_call (`axiom/arbitrator.py`) ;
   - `ArbitratorResult` : ajouter un champ `unreliable: bool` (+ raisons) ;
   - ⚠ heuristique multilingue (le jeu tourne en 10 langues) — commencer simple (chiffres
     + mots-clés EN), ne pas sur-ajuster ; documenter les limites.
2. Après Lot 2 → Lot 3 (« résoudre puis raconter », +1 appel LLM, OFF par défaut, **après**
   §24 qui régit les flags/presets de budget).

### Rappels d'exécution
- Garde-fous : `.venv/bin/python -m pytest tests/test_engine_headless.py tests/test_cli_play.py -q`
  + `debug/startup_check.py`. **Ne pas** lancer `pytest tests/` en entier → segfault
  préexistant (TICKET-067, torch+Qt) ; tester par lots.
- Tenir à jour CHANGELOG.md + `AXIOM_STATUS.md` (ligne `engine`) + `collab/claude/EN_COURS.md`.
- Pas de commit sans feu vert utilisateur.

### En suspens (hors Pilier 8, à ne pas oublier)
- **Phase « vol de techno » (§25)** : l'utilisateur veut la lancer (un agent par cible,
  domaines A→H) → trouvailles à consigner dans `PENDING.md`.
- **Pré-existant à signaler** : marqueur de conflit `<<<<<<< HEAD` dans
  `maintenance/README.md` (~ligne 231) — résolution git côté utilisateur.
