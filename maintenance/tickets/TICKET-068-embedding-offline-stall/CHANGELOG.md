# CHANGELOG — TICKET-068 (embedding offline)

## 2026-06-12 — modèle d'embedding chargé hors-ligne quand déjà caché

### `axiom/memory.py`
- `_EmbeddingSingleton.get()` : charge `all-MiniLM-L6-v2` avec
  `local_files_only=True` (chemin rapide, aucun HEAD réseau vers HF Hub).
  En cas d'échec (modèle pas encore en cache, 1ᵉʳ lancement), fallback sur un
  chargement en ligne unique. Supprime le stall ~87 s du premier tour sur les
  hôtes à IPv6 cassée vers huggingface.co (même cause racine que le fix Gemini
  `IPv4FirstTransport`).

### `tests/test_vector_memory.py` (+3 tests)
- `TestEmbeddingSingletonOffline` : `local_files_only=True` bien passé ;
  fallback online si l'offline lève (modèle non caché) ; singleton réutilisé.
- Fixture `vm` et patches recalés sur
  `chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction`
  (l'ancien patch sur `axiom.memory.…` ne touchait pas l'import local de `get()`).

### Vérifications
- Sonde isolée : `SentenceTransformerEmbeddingFunction(local_files_only=True)`
  → 3,2 s vs 86,7 s sans (modèle déjà caché).
- Tour complet réel sur Myria (fireworks/gpt-oss-20b, clé bêta) : 1ᵉʳ token à
  3,9 s, fini en 7,2 s, narration streamée correcte.
- `pytest tests/test_vector_memory.py tests/test_vector_threading.py
  tests/test_reasoning_models.py tests/test_builtin_keys.py` → 62 verts.
