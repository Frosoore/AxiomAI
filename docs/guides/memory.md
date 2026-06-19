# Narrative memory

Axiom remembers the story so the world stays coherent across hundreds of turns.
Memory has a search layer and a cognitive layer, and a mode toggle that decides
how much of it is used.

- A **search layer** (always on, fully offline and deterministic) that recalls
  the most relevant past narrative for the current turn.
- A **cognitive layer** (opt-in *living* mode) that distils the narrative into
  structured **facts** and, optionally, into evolving **beliefs** the world's
  characters remember and revise.

The design is adapted from the
[Hindsight](https://github.com/vectorize-io/hindsight) memory system,
reimplemented on Axiom's offline stack (ChromaDB + SQLite + a pluggable
`LLMBackend`) while preserving its core invariant: everything is keyed by
`turn_id`, so a rewind rolls the whole memory back in lockstep with the events.

## The two modes

The mode is a per-save preference, read from
{py:attr}`axiom.config.AppConfig.memory_mode`:

| | **lite** (default) | **living** (opt-in) |
|---|---|---|
| Hybrid search | yes | yes |
| LLM fact extraction | no | yes (background) |
| Evolving beliefs | no | optional ({py:attr}`~axiom.config.AppConfig.memory_beliefs_enabled`) |
| Network required | no | yes (LLM) |
| Determinism | total | tested with a mocked LLM |
| Cost | none | bounded (every *N* turns) |

`lite` is the safe default: it never touches an LLM or the network, so the game
loop runs anywhere and the test-suite stays deterministic. Use
{py:func}`axiom.config.memory_mode_is_living` to branch on the mode (any value
other than the explicit `"living"` opt-in resolves to `lite`).

## Search layer (both modes)

Long-term narrative is embedded into a local
[ChromaDB](https://www.trychroma.com/) store, one collection per save, with the
offline `all-MiniLM-L6-v2` model. Each chunk is tagged with the `turn_id` that
produced it, which makes rollback surgical: rewinding to turn *N* deletes every
chunk from a later turn.

{py:meth}`axiom.memory.VectorMemory.query` runs a **hybrid search**:

1. **Semantic arm** — ChromaDB approximate-nearest-neighbour over the embeddings
   (meaning-based recall).
2. **Lexical arm** — BM25 over the save's chunks ([`rank_bm25`](https://pypi.org/project/rank-bm25/)),
   which rescues an *exact* token the embeddings miss (a proper noun, an item).
3. **Rank fusion** — the two ranked lists are merged with Reciprocal Rank Fusion
   ({py:func}`axiom.retrieval.fusion.reciprocal_rank_fusion`); the normalised RRF
   score is the base relevance.
4. **Recency modulation** — turn-age nudges the score by a small factor
   (±10%) so a relevant-but-old memory is ranked down, never crushed.
5. **Focus boost** — chunks that mention the current scene get a flat additive
   bump via the `focus_terms` argument: the player's current location *and* the
   names of the characters sharing it, so memories about who and where you are
   surface more readily.
6. **Optional reranker** — when
   {py:attr}`axiom.config.AppConfig.memory_reranker_enabled` is set, a
   cross-encoder ({py:class}`axiom.retrieval.reranker.CrossEncoderReranker`)
   re-scores the fused candidates jointly against the query for the most precise
   ordering. It is **off by default** (it needs a ~90 MB torch model) and
   degrades to a no-op when its runtime is unavailable.

Every step is offline and deterministic; the reranker is the only optional
dependency and it always has a safe fallback.

## Lore Book retrieval

A universe's **Lore Book** is static, authored world knowledge (factions, places,
history) — separate from the per-turn narrative. Each turn the engine surfaces the
entries relevant to the player's input in two steps:

1. **Semantic match** — the Lore Book is embedded into the same per-save store
   (tagged `chunk_type="lore"`, at turn 0 so it survives any rewind) and matched by
   *meaning*, so "betrayal" can surface an entry about a "coup" even without the
   exact word. The embedding is refreshed once per session (and after a hot reload).
2. **Link expansion** — the semantic hits are then expanded with a few *related*
   entries (same category, or shared keywords), an idea adapted from Hindsight's
   link expansion. It is computed at query time over the small lore table (no
   precomputed graph), giving the narrator associative context, not just direct hits.

When the embedding runtime is unavailable (e.g. Windows without the torch runtime),
retrieval falls back to a deterministic keyword overlap on the structured table, so
the lore never disappears.

## Cognitive layer (living mode)

In `living` mode the engine additionally distils the narrative into atomic
**facts** — a who/what/when/where/why model adapted from the
[Hindsight](https://github.com/vectorize-io/hindsight) memory system.

A fact ({py:class}`axiom.facts.Fact`) carries a canonical `statement`, a
`fact_type` (`world` / `experience` / `assistant`), the structured fields, and a
list of `entities`. Facts are produced by
{py:func}`axiom.factextract.extract_facts` (an LLM call, run off the turn loop)
and stored with {py:func}`axiom.facts.insert_facts`, tagged with their `turn_id`.

```python
from axiom import facts, factextract

new_facts = factextract.extract_facts(llm, narrative_text, when_hint="dusk")
facts.insert_facts("MyWorld.db", save_id, turn_id, new_facts)
```

Because facts are turn-tagged, rollback stays trivial: a rewind drops every fact
from a later turn, atomically with the events it deletes (handled inside
{py:meth}`axiom.checkpoint.CheckpointManager.rewind`). Extraction is **fire and
forget** — any failure (LLM offline, bad output) yields no facts and never
interrupts play.

At prompt-building time the Arbitrator surfaces the most relevant facts (those
about the on-scene characters, then the most recent) as additional memory lines,
so the narrator can stay consistent with what the world has learned.

### Cost control

Fact extraction is batched: {py:attr}`axiom.config.AppConfig.memory_fact_interval`
sets how many turns pass between extractions (`0` disables periodic extraction
entirely). {py:attr}`axiom.config.AppConfig.memory_fact_model` overrides the
model used (empty = reuse the configured game backend), so a cheaper, faster
model can do the extraction.

## Beliefs (living mode, opt-in)

Facts are immutable observations of single moments. On top of them, Axiom can
maintain **beliefs** — synthetic, *evolving* opinions a character or the world
holds — when {py:attr}`axiom.config.AppConfig.memory_beliefs_enabled` is set
(use {py:func}`axiom.config.memory_beliefs_active` to branch; it requires living
mode *and* the opt-in). This is what lets an NPC hold a grudge hundreds of turns
after you wronged them.

A belief ({py:class}`axiom.observations.Observation`) carries a canonical
`statement`, the `subject` it is about, a `proof_count`, and — crucially — its
`sources`: the facts that back it, as `{fact_id, turn_id}` pairs.

After a batch of facts is stored, {py:func}`axiom.consolidate.consolidate` asks
the LLM how the beliefs should change and returns CREATE / UPDATE / DELETE
actions; {py:func}`axiom.observations.apply_consolidation` applies them
deterministically (a new belief, a reinforced one with merged sources, or a
contradicted one removed). Like extraction, consolidation is background and
fire-and-forget.

At prompt-building time the Arbitrator surfaces memory as a **hierarchy**, most
synthetic first: relevant *beliefs*, then *facts*, then raw narrative chunks — so
the narrator leads with what the world has concluded, backed by the specifics.

### Belief rollback

Beliefs derive from several turns, so they cannot be dropped by a single
`turn_id`. The `sources` turn ids are the rollback key
({py:func}`axiom.observations.rollback_observations`, run inside
{py:meth}`axiom.checkpoint.CheckpointManager.rewind`'s transaction): rewinding to
turn *N* deletes every belief *created* after *N* and, for the survivors, keeps
only the sources at turns `<= N`, recomputing `proof_count`. Beliefs thus roll
back atomically with the facts and events they were built from.

### Per-character memory styles

Different characters remember differently: a rancorous NPC dwells on betrayals, a
merchant on debts. A **belief mission** biases what the consolidator records
about each subject. Missions live in `Universe_Meta` (so they round-trip with the
Universe-as-Code source and travel with saves) and are read by
{py:mod}`axiom.missions`:

- `belief_mission` — the universe-wide default;
- `belief_missions` — a JSON `{entity_name: mission}` of per-character overrides,
  editable in the Creator Studio's *Metadata* tab as `Name: what they remember`
  lines.

The consolidator includes the styles of the characters in play, so each forms
beliefs in character.

### Prompt caching

For the background living-mode calls on the Gemini backend, optional explicit
context caching ({py:attr}`axiom.config.AppConfig.memory_prompt_cache_enabled`)
caches a large, stable system prompt to cut input-token cost. It is **off by
default**, guarded by a minimum size and a graceful fallback: when the prompt is
too small to qualify (the common case — Gemini's implicit caching already covers
that) or caching is unavailable, it safely does nothing.
