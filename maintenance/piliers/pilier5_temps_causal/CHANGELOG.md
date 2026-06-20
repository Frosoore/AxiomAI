# Changelog - Pilier 5

## En cours
- Initialisation des documents de maintenance.
- Étape 1 : Ajout de `elapsed_minutes` et `scene_pace` au schéma JSON dans `axiom/prompts.py`.
- Étapes 2 & 4 : Parsing des nouveaux champs dans `ArbitratorEngine.process_turn` et passage de `elapsed_minutes` à `tick_modifiers`.
- Étapes 3 & 5 : Remplacement de l'avancée de temps fixe par `elapsed_minutes` dans `ui/tabletop_view.py` et basculement du `Chronicler` sur les minutes.
- Étapes 6 & 7 : Vérification du déclenchement des `Scheduled_Events` et implémentation du fallback `Timekeeper` directement dans le moteur `axiom/arbitrator.py`. Mise à jour de `ARCHITECTURE.md` en retirant la dépendance au TimekeeperWorker.
- Étape finale (Optimisation) : Délégation totale du calcul du temps au `Timekeeper` dans `ArbitratorEngine`, retrait de `elapsed_minutes` du schéma JSON du LLM principal pour alléger son prompt et améliorer la fiabilité.
- Étape 8 : Validation réussie de `debug/run_step7_live.py` prouvant que le moteur est autonome et fonctionnel sans l'UI Qt. Pilier 5 terminé.

## Review 2026-06-07 (relecture par un tiers)
- Revue de code complète du pilier (développé par un autre contributeur). Le pilier **fonctionne**,
  mais l'implémentation **inverse la cible de la spec §6** : `elapsed_minutes` a été retiré du schéma
  narratif et le Timekeeper est devenu **primaire** (second appel LLM systématique) au lieu de fallback.
- Anomalies relevées et consignées dans `maintenance/PENDING.md` (lot **TICKET-015 → 022**) :
  Timekeeper primaire = ×2 appels LLM/tour (015) ; réglage « Time Model » mort, `_time_llm` jamais
  câblé (016) ; `major_event_description` ignoré + time-skip §6.4 absent (017) ; Chronicler repassé en
  tours, bénéfice voyage perdu (018) ; doublons `Timeline` au voyage (019) ; scaffolding mort en prod
  (020) ; aucune couverture de tests (021) ; collision de numérotation dans `DONE.md` (022).
- `DOC.md` réécrit pour décrire l'architecture **réellement livrée** + la divergence (l'ancien DOC
  décrivait la cible théorique « le LLM décide du temps », faux depuis l'optimisation finale).

## Correctifs 2026-06-07 (suite review)
- **TICKET-016** : `Session._resolve_time_llm` câble enfin le réglage « Time Model » (le Timekeeper
  utilise le modèle configuré, plus le modèle de narration).
- **TICKET-015** : Timekeeper rendu **désactivable** via `timekeeper_enabled` (case « Horloger IA » dans
  Réglages → Général). Décoché → pas de 2ᵉ appel LLM, temps estimé via `scene_pace`.
- **TICKET-018** : Chronicler repassé en **minutes in-game** (franchissement de palier
  `chronicler_minutes_interval`, défaut 720). `should_trigger` redevient à 2 args. Un long voyage
  redéclenche une simulation off-screen.
- **TICKET-019** : une **seule** ligne `Timeline` par tour (fin du doublon au voyage).
- **TICKET-020** : scaffolding mort retiré (`session.py`, `tabletop_view.py`).
- **TICKET-021** : `pytest` installé ; 6 tests `should_trigger` réparés + 2 tests arbitrator réparés +
  6 nouveaux tests (`TestCausalTime`, franchissement de palier). 215 tests ciblés verts, zéro régression.
- **TICKET-022** : tickets temps causal de `DONE.md` renumérotés TICKET-TC1→TC5 (fin de la collision).
- Reste ouvert : **TICKET-017** (`major_event_description` non consommé).
