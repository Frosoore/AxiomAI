---
name: project-test-env
description: Environnement d'exécution/test d'AxiomAI côté utilisateur — Gemini only, pas de LLM local
metadata:
  type: project
---

L'utilisateur teste AxiomAI sur une machine à **carte AMD** : il ne fait **pas tourner de LLM local**
(Ollama/universal indisponible en pratique). Le seul backend exploitable est **Gemini**, avec une clé
configurée valide.

**Modèle qui marche (2026-06-04) : `gemini-2.5-flash-lite`** (seul avec du quota free-tier sur la clé).
`gemini-2.0-flash` et `-flash-lite` renvoient **429 RESOURCE_EXHAUSTED, `limit: 0`** (zéro quota gratuit,
y compris par jour — attendre ne sert à rien) ; `gemini-1.5-flash`/`-8b` → 404 (retirés) ; `gemini-2.5-flash`
se connecte mais renvoie un texte vide (`None` → `LLMParseError`, structure « thinking » non gérée).
`settings.json` (`~/.config/AxiomAI/`) a été basculé sur `gemini-2.5-flash-lite`.

**Why:** pour valider un tour de jeu réel, on dépend de Gemini ; les chemins qui supposaient un modèle
local (`extraction_model = llama3.1:8b`) cassaient en Gemini (cf. [[—]] TICKET-007). Les validations
« run réel » peuvent échouer pour cause de quota, pas de bug.

**How to apply:**
- Pour tester le moteur en headless sans GUI : `PYTHONPATH=. .venv/bin/python debug/run_step7_live.py`
  (construit Session + exécute le vrai NarrativeWorker, tape sur le backend configuré).
- Univers de test dispo : `~/AxiomAI/universes/Myria.db` (le restaurer à 0 save/0 event après test).
- Ne pas supposer qu'un modèle local est disponible ; préférer Gemini ou des stubs.
- Le venv du projet est `.venv/` (le `python` système n'a pas les deps).
- **Tests (2026-06-07) :** `pytest` est installé dans le `.venv`. Mais lancer la **suite complète**
  (`pytest` sans cible) **segfault** : c'est le bug pré-existant TICKET-008 (torch `dlopen`
  `libtriton.so` sur un QThread, sans le `preload_embedding_runtime()` de `main.py` qui n'existe pas
  sous pytest). → **lancer par sous-ensembles de fichiers** (`pytest tests/test_arbitrator.py …`).
  Les tests moteur non-Qt passent ainsi sans souci. Éviter de regrouper avec les tests
  vectoriels/Qt (`test_vector_*`, `test_phase6`, `test_ambiance_*`).
