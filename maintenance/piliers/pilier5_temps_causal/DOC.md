# Documentation — Pilier 5 : Le Temps comme substrat causal

Objectif du pilier (spec `AXIOM_AI_UPGRADE_DETAILS.md §6`) : que le temps in-game
écoulé à chaque tour soit **décidé dynamiquement** (plus de `+15 min` codé en dur),
et que tous les systèmes temporels (modifiers, Chronicler, scheduled events,
affichage topbar) se basent sur ce temps.

## Architecture réellement livrée (≠ cible spec — voir « Divergence »)

Tout le calcul du temps vit dans le **moteur headless** (`axiom/`), plus dans la GUI :

1. **Décision du temps — `axiom/arbitrator.py`.** Après la génération narrative,
   `process_turn` fait (par défaut) un **second appel LLM dédié** (« Timekeeper »,
   `build_timekeeper_prompt`, `axiom/prompts.py:883`) qui relit `player_action`
   + `narrative_text` et renvoie `{"elapsed_minutes": <int>, "major_event_description": …}`.
   - Ce 2ᵉ appel est **désactivable** via le réglage `timekeeper_enabled` (défaut
     `True`). Décoché → l'appel est sauté et le temps vient directement de
     `pace_defaults` (TICKET-015).
   - Si l'appel échoue / ne parse pas → **fallback** sur une table `pace_defaults`
     indexée par `scene_pace` (combat=2, conversation=5, exploration=15, travel=60…).
   - `scene_pace`, lui, vient toujours du tool_call du LLM **principal**
     (`NARRATIVE_TOOL_CALL_SCHEMA`, `axiom/prompts.py:48`).
2. **Persistance de l'horloge — `axiom/arbitrator.py`.** Le temps avancé est écrit
   dans la table `Timeline` (`in_game_time = MAX(Timeline) + elapsed_minutes`),
   **une seule ligne par tour** (description enrichie « Traveled to … (km) » en cas
   de voyage — TICKET-019). `axiom/db_helpers.py:get_current_time` relit le `MAX`.
   La GUI ne maintient plus de compteur local : `tabletop_view._on_turn_complete`
   relit l'heure depuis la DB.
3. **Modifiers — `axiom/arbitrator.py`.** `tick_modifiers(save_id, elapsed_minutes=…)`
   décrémente les durées en minutes réelles (`axiom/modifiers.py:88`).
4. **Chronicler — `axiom/session.py`.** Instancié et déclenché **dans le moteur**
   (fin de `Session.take_turn`), plus dans la GUI. Déclenchement par **franchissement
   d'un palier de `chronicler_minutes_interval` minutes in-game** (défaut 720),
   calculé via `should_trigger(current_time, previous_time)` où
   `previous_time = current_time - result.elapsed_minutes` (TICKET-018). Un long
   time-skip déclenche donc une simulation off-screen.
5. **Scheduled events — `axiom/arbitrator.py:239,697`.** `_fetch_triggered_events`
   sélectionne les `Scheduled_Events` dont `trigger_minute <= current_time` et non encore
   « fired » (`Fired_Scheduled_Events`), les injecte au prompt, puis les marque tirés.
6. **Affichage — `ui/tabletop_view.py:782`.** `_format_time` passe par
   `TimeSystem.get_time_string` (calendrier custom de l'univers, `axiom/time_system.py`).
7. **Time Model — `axiom/config.py` + `axiom/session.py::_resolve_time_llm`.** Le
   Timekeeper tourne sur le modèle configuré (`resolve_time_model`), construit en
   lazy par `Session` quand aucun `time_llm` explicite n'est fourni, repli sur le
   backend principal sinon (TICKET-016).

## Divergence vs la spec §6 (état après review du 2026-06-07)

La spec voulait que le **LLM de narration déclare `elapsed_minutes` inline** (1 appel/tour),
le Timekeeper n'étant qu'un **fallback**. L'implémentation a fait **l'inverse** : Timekeeper
**primaire** (2ᵉ appel LLM). Décision prise à la review : **on garde** ce choix (fiabilité +
prompt principal allégé) mais on le **rend désactivable**.

Suite à la review (lot **TICKET-015 → 022**, voir `maintenance/PENDING.md` et `DONE.md`) :
- ✅ **Timekeeper désactivable** (`timekeeper_enabled`) — le ×2 appels LLM n'est plus subi
  par défaut imposé : on peut retomber sur `scene_pace` pour économiser le quota (TICKET-015) ;
- ✅ **« Time Model » câblé** (`_resolve_time_llm`) — le Timekeeper utilise enfin le modèle
  configuré (TICKET-016) ;
- ✅ **Chronicler en minutes** — franchissement de palier ; un long voyage déclenche une
  simulation off-screen, bénéfice clé restauré (TICKET-018) ;
- ✅ **une seule ligne `Timeline`** par tour (TICKET-019) ; scaffolding mort retiré (TICKET-020) ;
- ✅ **tests** : chemin temps causal couvert, tests cassés réparés (TICKET-021) ;
- ✅ **numérotation** des tickets corrigée (TICKET-022) ;
- ⏳ **reste** : `major_event_description` toujours non consommé (TICKET-017, partiellement
  couvert par le déclenchement minutes du Chronicler).

Statut : pilier **fonctionnel et aligné** sur l'esprit de la spec ; la seule divergence assumée
(Timekeeper primaire) est désormais documentée et désactivable.
