# Phase 4 — Raffinements (chantier Hindsight)

Périmètre demandé par l'utilisateur (2026-06-18) : **B-3 (mission de croyance par personnage)** et
**prompt caching** (réduire le coût du Mode Vivant). Les autres raffinements (modèles mentaux,
directives, extraction temporelle) restent pour plus tard.

## B-3 — Mission de croyance par personnage/univers
Idée : un PNJ « se souvient différemment » selon sa nature (rancunier → trahisons ; cupide →
transactions ; loyal → services rendus). C'est la **mission** déjà acceptée par le consolidateur
(`axiom.consolidate.consolidate(..., mission=…)`), rendue **configurable par entité**.

**Stockage : `Universe_Meta`** (key-value flexible, **round-trip lossless via `[extra]`** de
compile/decompile, copié par `savestore._DEFINITION_COPY`, packagé). **Zéro changement de schéma**
(une colonne `Entities` aurait touché 6-7 listes de colonnes synchronisées = fragile).
- `belief_mission` : mission **par défaut de l'univers** (string).
- `belief_missions` : JSON **{nom d'entité : mission}** (overrides par perso).

Keyé par **nom** (le `subject` d'une croyance est un nom ; authoring trivial « Nom: mission »).

**GUI** : champ dans l'onglet **Metadata** du Studio (le `meta` dict y est déjà persité vers
`Universe_Meta` via `save_full_universe`). Pas de refonte de l'éditeur d'entités (table source-based).

**Consolidateur** : section « Character memory styles » construite depuis les missions des entités
concernées + mission d'univers par défaut.

## Prompt caching
- Le SDK `google-genai` 2.8 expose `client.caches` + `GenerateContentConfig(cached_content=…)`.
- **Caveat vérifié** : le cache **explicite** a un minimum de tokens ; nos system prompts
  (factextract/consolidate) sont **petits** → souvent **rejetés**. Le cache **implicite** (auto sur
  préfixe stable) s'applique déjà sans code.
- **Livrable** : support de cache explicite **guardé + fallback gracieux** dans `GeminiClient`
  (taille minimale, mémoïsation des échecs, jamais de régression), activable par config, branché sur
  les appels de fond du Mode Vivant. Honnête sur le gain réel (surtout gros prompts / gros modèles).

## Refs
- Reconnaissance : `maintenance/hindsight-mining/DOC.md` §14 B-3, B-4 ; §7.12.
- Phase 3 (consolidate/observations) : `maintenance/hindsight-phase3-croyances/`.
