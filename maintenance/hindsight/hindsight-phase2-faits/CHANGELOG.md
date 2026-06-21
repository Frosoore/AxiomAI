# CHANGELOG — Phase 2 (infra deux modes + faits)

## 2026-06-18 — Démarrage (items 1-2 : fondation déterministe)
- Création de l'étape (DOC/TODO/CHANGELOG).

### Item 1 — toggle `memory_mode` ✅ (volet config)
- `axiom/config.py` : champ **`memory_mode: str = "lite"`** + helper **`memory_mode_is_living(config)`**
  (défensif : tout sauf « living » → `lite`, le LLM n'est jamais engagé par accident).
- Volet **GUI + i18n différé** au panneau « Mémoire » (qui exposera aussi le cross-encoder Phase 1) —
  fait avec le câblage du job de fond (item 4) pour éviter une UI orpheline.

### Item 2 — table `Facts` + stockage + rollback ✅ (déterministe, zéro LLM)
- `axiom/schema.py` : **`_DDL_FACTS`** (fact_id, save_id, turn_id, fact_type, who, what, fact_when,
  fact_where, why, entities JSON, statement ; FK→Saves ON DELETE CASCADE), index `idx_facts_save_turn`,
  ajout à `_ALL_DDL`/`_DDL_INDEXES`/`EXPECTED_TABLES`, helper **`ensure_facts_table(conn)`** (auto-migration
  des save DBs antérieures, idempotent, réutilise la transaction de l'appelant).
- `axiom/facts.py` (nouveau) : dataclass **`Fact`** (who/what/when/where/why + fact_type + entities +
  statement canonique) + `insert_facts` / `get_facts` (filtres `max_turn_id`, `entity`, `limit`, récent
  d'abord) / `count_facts` / `rollback_facts`. Statements vides ignorés, fact_type inconnu → `world`.
- `axiom/checkpoint.py::rewind` : **DELETE Facts turn_id > target dans la même transaction** que
  Event_Log/Snapshots/Timeline → events et faits dérivés rollback **atomiquement**.
- Tests : `tests/test_facts.py` (14) — insert/roundtrip/filtres/ordre/rollback + **rewind couvre les faits**
  + toggle de mode. **Suite : 829 ✅.**
### Décisions utilisateur (2026-06-18)
- **Cadence** : tous les **N tours**, N **réglable et désactivable** (0 = manuel seul) + **bouton « extraire
  maintenant »** (réinitialise le compteur). → config `memory_fact_interval: int = 5`.
- **Modèle** : backend configuré par défaut, **surchargeable**. → config `memory_fact_model: str = ""`.
- **Causal** : plus tard (hors Phase 2).

### Item 3 — extraction de faits par LLM ✅ (Mode Vivant, testé via mock)
- `axiom/config.py` : `memory_fact_interval` (N tours, désactivable) + `memory_fact_model` (override).
- `axiom/factextract.py` (nouveau) : `extract_facts(llm, narrative, known_entities=, when_hint=, max_facts=)`.
  Prompt système adapté de Hindsight (atomique/vérifiable/sans spéculation, who/what/when/where/why +
  type + entities + statement canonique), via `LLMBackend.complete(response_format="json", temperature=0.2)`.
  **Parsing robuste** (tool_call objet `{"facts":[…]}` / liste nue / JSON dans la prose) ;
  **dégradation gracieuse** : entrée vide ou échec backend → `[]`, **jamais de crash** (fire-and-forget).
  Coercition : statements vides ignorés, type inconnu → `world`, entités non-liste tolérées, cap `max_facts`.
- Tests : `tests/test_factextract.py` (11, LLM mocké). **Suite : 840 ✅.**

### Item 5 — faits dans le contexte de l'Arbitrator ✅ (2026-06-18, moteur pur)
- `axiom/arbitrator.py` : nouvelle méthode **`_fetch_relevant_facts(save_id, max_turn_id, on_scene, limit)`**
  — priorise les faits mentionnant un **perso en scène** (`local_character_names`, déjà calculés à l'étape
  prompt), puis complète avec les **faits les plus récents** ; borné par `max_turn_id` (un tour rembobiné
  ne ressort jamais un fait futur) ; dédup + cap ; dégradation gracieuse (erreur → `[]`).
- En mode **`living`** uniquement (`memory_mode_is_living(cfg)`), ces faits sont préfixés `Known fact:` et
  **fusionnés en tête de `rag_chunks`** → rendus comme lignes `[MEMORY]` du prompt. **Mode `lite` : chemin
  inchangé** (rien n'est appelé → déterminisme total préservé).
- Tests : `tests/test_facts.py::TestArbitratorFactInjection` (4 — priorité scène/récence, borne turn, dédup/
  limite, vide). **Suite : 844 ✅.**

### Côté moteur, la Phase 2 est COMPLÈTE.
Reste **item 4 = couche app** (worker QThread + panneau GUI + i18n ×10) → **documenté** dans
`ITEM4_HANDOFF.md` (handoff pour la prochaine passe). Rien commité.

### Item 4 — couche app (worker + GUI + i18n) ✅ (2026-06-18)
- **`workers/fact_worker.py`** (nouveau) : `FactExtractWorker(QThread)` sur le patron de
  `vector_worker.py`. `run()` fait `extract_facts(...)` **puis** `insert_facts(...)` hors thread UI ;
  signals `facts_extracted(int)` / `error_occurred(str)` / `status_update(str)`. Fire-and-forget :
  `extract_facts` rend déjà `[]` sur backend mort → 0 fait, pas de popup, le jeu continue.
- **`ui/tabletop_view.py`** : branchement post-tour dans `_on_turn_complete` via
  `_accumulate_and_maybe_extract()`. En mode **`living` seul** (`memory_mode_is_living`), chaque tour
  est mis dans un **buffer** (`_fact_pending`) ; tous les **N tours** (`memory_fact_interval`, 0 = off)
  on distille **toute la fenêtre** depuis la dernière extraction (zéro tour sauté) via le worker.
  **Mode `lite` = no-op total** (zéro réseau, le LLM n'est jamais touché). Méthode publique
  **`extract_facts_now()`** (bouton manuel) : extrait tout de suite + reset du compteur. LLM
  d'extraction = `self._llm` réutilisé, ou un **override** (`memory_fact_model`) construit à la volée
  (échec de build → repli sur le LLM du jeu). Buffer + compteur **remis à zéro au rewind**
  (`_on_rewind_done`, les faits futurs sont déjà rollback atomiquement) **et au chargement** de session.
- **`ui/settings_dialog.py`** : nouvel onglet **« Mémoire »** — menu Mode (Léger/Vivant), N
  (`QSpinBox`, 0 = « Manuel seulement » via `setSpecialValueText`), modèle d'extraction
  (`QLineEdit`, vide = défaut), **reranking neuronal** (Phase 1, `memory_reranker_enabled`), bouton
  **« Extraire la mémoire maintenant »** (`Signal extract_now_requested`). Contrôles Vivant grisés en
  Léger ; bouton actif seulement en Vivant **avec une session** (`db_path`). Tous documentés `doc()`/
  `doc_tab` (6 éléments ajoutés à `help_system.PAGES["settings"]`).
- **BUGFIX (régression silencieuse)** : `collect_config()` reconstruisait un `AppConfig` neuf **sans**
  reporter `memory_mode` / `memory_fact_interval` / `memory_fact_model` / `memory_reranker_enabled`
  → **toute sauvegarde des réglages réinitialisait la config mémoire de la Phase 2**. Les 4 champs sont
  désormais lus dans `collect_config` et peuplés dans `load_from_config` + `retranslate_ui`.
- **`ui/main_window.py`** : `_show_settings` relie `dialog.extract_now_requested` →
  `tabletop_view.extract_facts_now`.
- **i18n ×10** : 11 clés UI (`tab_memory`, `memory_mode_*`, `memory_fact_*`, `memory_interval_off`,
  `memory_reranker_label`, `extract_now`, `memory_extracted_fmt`) + **12 clés doc intégrée**
  (`doc_settings_*` ×6 éléments) ajoutées aux 10 langues. `i18n_check` 673/673 ✅, `doc_check` aligné ✅.
- Tests : `tests/test_fact_worker.py` (3 — persiste/0 fait/backend mort gracieux) + 3 dans
  `tests/test_settings_dialog.py` (round-trip mémoire **anti-régression**, grisage Léger, émission du
  bouton). **Suite : 850 ✅** (hors `test_ambiance_manager`, segfault Qt préexistant TICKET-067).

### Doc intégrée enrichie — bouton « Information » des Paramètres par onglet (2026-06-18)
- Le bouton « Information » (et F1) des Paramètres était **plat** : il déversait tous les onglets avec
  des descriptions courtes. Rendu **conscient de l'onglet actif** (patron du Creator Studio) :
  `settings_dialog._show_help` lit `self._tabs.currentIndex()` → `help_dialogs.settings_tab_help_html`.
- **7 sous-pages d'intro** ajoutées (`help_system.PAGES` : `settings_llm/cloud/params/personas/image/
  memory/general`, intro seule, sans renommer les refs d'éléments existants) avec des **intros riches +
  exemples concrets** par onglet. La section **Général** (toujours visible sous les onglets) est
  ajoutée en pied. `ExplainPageDialog` généralisé (accepte `html`/`title` préfabriqués).
- **Blocs de détails `_d`** ajoutés aux 3 éléments Mémoire les plus conceptuels (`memory_mode`,
  `memory_interval`, `memory_reranker`) — exemples « avant/après », compromis, le cas reranking
  expliqué pas à pas. Affichés en F1/annuaire seulement (le survol reste court).
- **i18n ×10** : 14 clés d'intro (`doc_page_settings_*`) + 3 clés de détail (`doc_settings_memory_*_d`)
  dans les 10 langues. `i18n_check` 690/690 ✅, `doc_check` 275 clés alignées ✅.
- Tests : +1 dans `test_settings_dialog.py` (tab-aware compose intro + détails + Général). **Suite 851 ✅.**

### Phase 2 COMPLÈTE (moteur + app). Rien commité.
Reste pour les phases suivantes : **Phase 3** (observations/croyances) puis **Phase 4** (modèles
mentaux + causal). Suivi non bloquant : exposer un témoin « N faits » plus visible, batch lu depuis
`Event_Log` plutôt que le buffer in-memory si on veut survivre à un redémarrage en plein milieu d'une
fenêtre N.
</content>
