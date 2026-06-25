# CHANGELOG — Pilier 8 (fiabilité Arbitrator)

## 2026-06-23 — Lot 1, item 1 : fix bug « plot armor » Companion

**Constat (audit).** Dans `ArbitratorEngine._validate_change`, le cas Companion où le
héros passerait sous 0 retournait `(True, "")` → le delta négatif était appliqué tel
quel (ex. HP 10, delta -20 → HP = -10). Le commentaire promettait pourtant « cap at 0
… the hero survives ». Le héros pouvait donc finir à HP négatif (et déclencher les
règles de mort), à l'opposé du « plot armor » revendiqué.

**Fix.**
- `_validate_change` renvoie désormais un **3-uplet** `(valid, reason, clamp_value)`.
  `clamp_value` vaut `None` en temps normal, et `0` dans le cas plot-armor (signal
  « applique un plancher absolu de 0 au lieu du delta brut »).
- La boucle d'application de `process_turn` honore ce signal : le changement est
  converti en `stat_set value=0` (toujours **appliqué**, pas rejeté) → le héros reste
  à 0 au lieu de plonger en négatif.
- Seul appelant de `_validate_change` = la boucle interne (aucun appel direct dans les
  tests), donc le changement de signature est contenu.

**Tests.**
- `test_plot_armor_prevents_rejection` (existant) reste vert : le changement est
  toujours appliqué et non rejeté.
- Ajout `test_plot_armor_clamps_hero_to_zero` : après le tour, HP du héros == 0 (et non
  négatif) dans le State_Cache.

**Décision utilisateur (2026-06-23).** Choix **plancher à 0** confirmé (vs 1 / ignorer).
Aucun changement de code requis : le comportement déjà implémenté est retenu et figé.

## 2026-06-23 — Lot 1, item 2 : bornes / énums / légalité spatiale (❹)

**Constat (audit).** `_validate_change` ne vérifiait que : entité connue, stat ∈
`Stat_Definitions`, non-négativité. Donc `Health = 9999` passait, un téléport vers un
lieu inexistant passait, et **toute** valeur non-numérique passait (« always valid »).

**Fix (durcissement déterministe gratuit, ON, non-togglable).** Les bornes vivent dans
la colonne JSON `Stat_Definitions.parameters` (zéro migration de schéma — la convention
`{ min, max }` existait déjà dans Myria ; ajout de `allowed = [...]` pour les énums) :
- **Borne haute `max`** : une affectation/delta qui dépasse `max` est **clampée** au
  plafond (appliquée, pas rejetée — l'action aboutit mais ne peut pas gonfler la stat
  au-delà de sa limite de design). Réutilise le signal `clamp_value` de l'item 1.
- **Borne basse `min`** : généralise la non-négativité. Sous `min` (sinon plancher
  implicite 0) → **rejet** (hint narrateur), sauf héros Companion → clamp au plancher.
- **Énums `allowed`** : une affectation hors de la liste déclarée est **rejetée**.
- **Légalité spatiale** : affecter `Location` à un lieu absent de la table `Locations`
  est **rejeté** (désactivé si l'univers ne déclare aucun lieu → rétro-compatible).

Détails d'implémentation :
- `_load_defined_stats()` (nom seul) remplacé par `_load_stat_defs()` (name→{value_type,
  params}) + nouveau `_load_known_locations()` ; les deux chargés **une fois par tour**
  (pas de N+1). `_validate_change` prend désormais `(…, stat_defs, known_locations)` et
  renvoie toujours le 3-uplet `(valid, reason, clamp_value)`.
- Helper module `_as_number()` : tolère bornes string/malformées (borne ignorée plutôt
  que crash). Les clamps entiers sont stockés en int (`"100"`, pas `"100.0"`).
- **Rétro-compat** : une stat sans `parameters` déclarés garde le comportement d'avant
  (vérifié par `test_unbounded_stat_accepts_large_value` : `HP = 9999` accepté).

**Tests.** +7 (`TestDeterministicBounds`) : clamp max (assign + delta), rejet sous min,
rejet/accept énum, rejet lieu inconnu, rétro-compat stat non bornée. Suite
`test_arbitrator.py` **55 verte** ; garde-fous `test_engine_headless`+`test_cli_play`
(15) + `event_sourcing`/`rules_engine`/`port_b4` (74) verts ; `startup_check` OK.

## 2026-06-23 — Lot 1, item 3 : sortie structurée / `response_schema` (❸)

**Constat (audit).** Le `tool_call` est extrait par **regex** d'un bloc ```` ```json ````
du flux brut → JSON malformé/absent = zéro changement, silencieusement. Surtout, le
backend **Gemini** (seul backend de l'utilisateur) **ignorait totalement**
`response_format` : *tous* les appels pur-JSON (Timekeeper, populate, consolidate,
factextract) tombaient sur le parsing regex sans aucune garantie de JSON valide.

**Contrainte d'architecture (importante).** Le **tour narratif** entrelace de la prose
**streamée** et un bloc JSON inline → on **ne peut pas** le forcer en JSON pur sans
casser le streaming (ce serait « résoudre puis raconter », Lot 3). La sortie structurée
s'applique donc aux **appels pur-JSON**, et `parse_tool_call` reste le filet pour le tour
narratif et les fournisseurs sans JSON garanti.

**Fix.**
- **Contrat backend** (`axiom/backends/base.py`) : nouveau paramètre
  `response_schema: dict | None` (un JSON Schema agnostique) sur `complete()` et
  `stream_tokens()` ; docstrings + note de protocole mises à jour.
- **Gemini** (`gemini.py`) : honore enfin `response_format="json"` →
  `response_mime_type="application/json"` ; avec un schéma →
  `response_json_schema` (SDK google-genai 2.8.0, champ vérifié présent). Helper
  `_json_output_kwargs` **gardé par capability-check** (`model_fields`) → un SDK plus
  ancien dégrade en JSON simple au lieu de crasher. **Gros gain** : les appels
  populate/consolidate/factextract existants (déjà `response_format="json"`) sont
  désormais réellement contraints côté Gemini, sans toucher leurs call-sites.
- **Ollama** (`ollama.py`) : `format` accepte le schéma quand fourni (structured
  output natif), sinon `"json"`.
- **UniversalClient** (`universal.py`) : reste en `json_object` (valide JSON garanti,
  accepté par les 6 fournisseurs OpenAI-compat) — le type `json_schema` n'est **pas**
  uniformément supporté (notamment Fireworks bêta) → choix conservateur documenté pour
  éviter les 400 ; le schéma est threadé mais non câblé au wire.
- **Arbitrator** : le **Timekeeper** (seul appel pur-JSON côté arbitrator) passe
  désormais `response_format="json"` + `_TIMEKEEPER_SCHEMA`
  (`{elapsed_minutes:int>=0}`) → fin du scrape regex sur ce point.

**Tests.** +9 : Gemini (mime+schema posés / tour narratif non affecté), Ollama
(format=json / format=schema), UniversalClient (json_object, schéma sans casse, absence
hors json), Arbitrator (le Timekeeper demande bien la sortie structurée). Tous les fakes
de test utilisent `**kwargs` → signature rétro-compatible. Suites : `test_arbitrator`
(57), `test_gemini_client`/`test_ollama_client`/`test_llm_base`/`test_reasoning_models`,
+ consumers (populate/consolidate/factextract/reflect/missions/fact_worker) + garde-fous
(`engine_headless`/`cli_play`/`gemini_prompt_cache`/`port_b4`) **verts** ; `startup_check` OK.

**Lot 1 terminé.** Suite → Lot 2 (détecteur de divergence prose↔état, heuristique zéro
LLM, §23.4), puis Lot 3 (« résoudre puis raconter », après §24/flags).
