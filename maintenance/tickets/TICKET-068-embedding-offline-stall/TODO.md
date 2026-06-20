# TICKET-068 — Le 1ᵉʳ tour fige ~90 s : le modèle d'embedding ping HF Hub

**Statut : ✅ CORRIGÉ + vérifié en réel (2026-06-12).**

## Le vrai bug derrière « la réponse n'arrive pas »

Découvert en reprenant TICKET-066 (gpt-oss-20b « Generating » interminable). Le
backend de raisonnement n'était **pas** en cause : sondé en réel, gpt-oss-20b
répond en streaming en ~2 s, et un **tour complet sur Myria** (API `Session`,
exactement ce que la GUI exécute) produit bien la narration streamée.

Le blocage est dans **`axiom/memory.py`** : `_EmbeddingSingleton.get()` charge
`all-MiniLM-L6-v2` via `SentenceTransformerEmbeddingFunction` **sans**
`local_files_only`. Même quand le modèle est déjà en cache disque,
sentence-transformers envoie un **HEAD réseau vers huggingface.co** à chaque
chargement pour vérifier les mises à jour. Sur cette machine (IPv6 cassée vers
Google/HF — cf. [[project-test-env]], même cause racine que le fix Gemini
`IPv4FirstTransport`), ce HEAD **stalle ~87 s** par intermittence.

Comme le singleton se charge au **premier tour de chaque session** (1ʳᵉ query
vector), le joueur voit « Generating… » sans fin et abandonne. Indépendant du
backend LLM (toucherait Gemini pareil) — d'où le faux procès fait à gpt-oss.

### Mesure (clé bêta, save Myria, process froid)
- Sans offline : `load+encode` = **86,7 s** (+ warning « sending
  unauthenticated requests to the HF Hub »).
- Avec `local_files_only=True` : **3,2 s**, plus aucun appel réseau.
- Tour complet Myria après fix : 1ᵉʳ token à **3,9 s**, fini en **7,2 s**.

## Fix

`_EmbeddingSingleton.get()` essaie d'abord `local_files_only=True` (chemin
rapide, modèle déjà caché → zéro réseau) ; en cas d'échec (1ᵉʳ lancement / cache
vidé, le modèle n'est pas sur disque) il retombe sur un chargement en ligne **une
seule fois**, puis toutes les sessions suivantes reprennent le chemin offline.

## Reste à faire

- [ ] Validation GUI utilisateur : lancer l'app, jouer un 1ᵉʳ tour
  (fireworks/gpt-oss ou Gemini) → la narration s'affiche en quelques secondes,
  plus de « Generating… » qui traîne.

## Repères

- `axiom/memory.py` — `_EmbeddingSingleton.get()` (try offline → fallback online).
- `tests/test_vector_memory.py::TestEmbeddingSingletonOffline` (3 tests :
  `local_files_only=True` passé, fallback online si non caché, singleton mis en
  cache).
