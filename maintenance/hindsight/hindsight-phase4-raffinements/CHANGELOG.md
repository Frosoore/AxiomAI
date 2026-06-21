# CHANGELOG — Phase 4 (B-3 missions + prompt caching)

## 2026-06-18 — Démarrage
- Création de l'étape (DOC/TODO/CHANGELOG). Investigation : stockage missions = `Universe_Meta`
  (round-trip `[extra]` lossless, zéro schéma) ; SDK genai 2.8 supporte le cache explicite mais nos
  prompts sont petits → cache guardé + fallback gracieux.

### B-3 — mission de croyance par personnage ✅
- `axiom/missions.py` (nouveau) : lecture `Universe_Meta` — **`belief_mission`** (défaut univers) +
  **`belief_missions`** JSON `{nom: mission}`. Helpers `get_universe_mission`, `get_belief_missions`,
  `get_belief_missions_from_value`, `parse_missions_text`/`missions_to_text` (round-trip GUI), tous
  **dégradation gracieuse**. Stockage en `Universe_Meta` → **zéro changement de schéma**, round-trip
  lossless via `[extra]` (une colonne `Entities` aurait touché 6-7 listes de colonnes synchronisées).
- `axiom/consolidate.py` : section **« Character memory styles »** dans le prompt, limitée aux persos
  **présents dans le lot** (sujets des croyances + entités/who des faits), insensible à la casse +
  mission d'univers par défaut. Signature `consolidate(..., missions=…)`.
- `workers/fact_worker.py` : charge mission d'univers + missions par perso depuis `db_path`, passe à
  `consolidate`.
- **GUI** : champ **« Character memory styles »** (`QPlainTextEdit`, « Nom: ce qu'il retient » par ligne)
  dans l'onglet Metadata du Studio → sérialisé en `meta["belief_missions"]` JSON (le `meta` y est déjà
  persité en `Universe_Meta` via `save_full_universe`, donc round-trip `[extra]` + copie save + package
  gratuits). `doc()`-é (`creator_meta.belief_missions` + détail `_d`).
- i18n ×10 : `belief_missions_title/placeholder` + `doc_creator_meta_belief_missions(_t/_d)`.
- Tests : `tests/test_missions.py` (lecture, JSON malformé, round-trip texte, **prompt enrichi** des
  styles présents, exclusion des absents).

### B-4 — prompt caching (Gemini) ✅ (guardé, honnête)
- **Investigation** : `google-genai` 2.8 expose `client.caches` + `GenerateContentConfig(cached_content=…)`.
  **Mais** le cache **explicite** exige un préfixe assez gros ; nos system prompts (factextract/consolidate)
  sont petits → souvent rejetés. Le cache **implicite** (auto) couvre déjà ce cas sans code.
- `GeminiClient` : **cache explicite opt-in, guardé** — seuil `_PROMPT_CACHE_MIN_CHARS=8000` (on ne tente
  même pas en dessous), **mémoïsation des échecs** (jamais de re-tentative `create` qui échoue),
  **fallback gracieux** vers le `system_instruction` inline (jamais de régression). Config bâtie
  **par modèle** dans la lambda de retry (cache keyé sur le modèle réellement utilisé, fallback inclus).
  N'affecte que `complete()` (les appels de fond Vivant ; le streaming narratif est inchangé).
- `config.memory_prompt_cache_enabled` (off) + branché dans `build_llm_from_config` (Gemini) + **toggle GUI**
  onglet Mémoire (i18n + doc ×10).
- **Honnêteté** : pour nos prompts actuels (petits) le cache explicite **no-op** sans risque ; il prend
  effet pour de gros prompts/modèles. Les vrais leviers de coût restent le batch N tours (Phase 2) + le
  modèle d'extraction moins cher + la consolidation gatée.
- Tests : `tests/test_gemini_prompt_cache.py` (désactivé/petit/gros-réutilisé/échec-mémoïsé/make_config).

### Phase 4 (B-3 + prompt caching) COMPLÈTE. **Suite 884 ✅.** Rien commité.
Restent (non demandés) : modèles mentaux, directives/persona, extraction temporelle (§7.5/7.8/7.9).

### Doc Sphinx du moteur mise à jour (TICKET-058) — couvre tout le chantier mémoire (2026-06-18)
- `docs/api/memory.md` : ajout des automodules **`axiom.observations`, `axiom.consolidate`,
  `axiom.missions`** (Phases 3-4) à côté des Phase 1-2 déjà présents ; intro réécrite (recherche →
  faits → croyances → missions).
- `docs/guides/memory.md` : table des modes enrichie (ligne croyances), nouvelles sections **Beliefs**
  (observations, consolidation CREATE/UPDATE/DELETE, hiérarchie de rappel), **Belief rollback**
  (clé `sources`/turn), **Per-character memory styles** (B-3), **Prompt caching** (B-4, honnête sur le
  no-op des petits prompts). Les nouveaux champs de config sont auto-documentés (`automodule axiom.config`).
- **4 docstrings reST corrigées** (ligne vide avant les listes à puces : `factextract`, `consolidate`,
  `reranker` ; littéral `` ``fact_id`` `` mal fermé dans `facts.insert_facts`) — elles auraient fait
  **échouer le build strict `-W` de la CI**.
- **Build vérifié en local : `sphinx -W` EXIT=0, zéro warning** (intersphinx neutralisé le temps du
  build — la machine bloque sur le fetch réseau `docs.python.org`, la CI a le réseau ; `conf.py`
  restauré à l'identique).
