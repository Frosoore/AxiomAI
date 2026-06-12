# PENDING — tickets à étudier

> Règle de vie du fichier : un ticket **terminé** part dans `DONE.md` (trace condensée) et
> **disparaît d'ici**, index compris. Ne restent dans PENDING que les tickets ouverts,
> différés ou en attente d'une validation utilisateur.

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-017| Temps causal : `major_event_description` ignoré + **time-skip Chronicler** (spec §6.4) | ouvert (partiellement couvert par TICKET-018, domaine Pilier 5/Gemini) |
| TICKET-050| Gemini 429 `limit: 0` (modèle hors free tier) : fail-fast au lieu de 3 retries inutiles | ouvert — quick win |
| TICKET-057| 📋 **Chantier planifié** — Doc intégrée à l'app GUI (tooltips, bouton « explique cette page », quick tour, annuaire cherchable), 10 langues, « tout d'un bloc » | 🚧 en cours (2026-06-12, cf. [[project-doc-chantier]]) |
| TICKET-059| Test threadé flaky : `test_generation_cancel.py::test_registre_cancel_active_generations` (passe en isolation, flanche sous charge) | ouvert — fiabilité de la suite |
| TICKET-061| i18n : placeholders/titres encore en dur dans les éditeurs du Studio | ouvert — quick win |
| TICKET-063| Backend `openai` : modèles reasoning (gpt-5/o-series) incompatibles avec le payload actuel (`max_tokens`→`max_completion_tokens`, `temperature` figée à 1) | ouvert — suite de `feature-cloud-text-providers` |
| TICKET-064| Backend d'**images** Venice AI (`POST /image/generate`, clé `venice_api_key` déjà en config) | ouvert — idée feature |

Tickets résolus/clos : voir `DONE.md` (001→012, TC1→TC5, 015→049 sauf 017, 051→056, 058→060).
Réserves portées dans `DONE.md` : TICKET-054 (validation GUI i18n en attente), TICKET-058
(activer GitHub Pages — droits admin — puis relancer le job `deploy`).


---

## TICKET-017 — Temps causal : `major_event_description` ignoré + time-skip Chronicler non implémenté

**⏳ OUVERT — partiellement couvert (2026-06-07).** Depuis TICKET-018, un grand saut temporel franchit
un palier de minutes et **déclenche bien le Chronicler** (le monde évolue pendant un long voyage), ce qui
couvre l'essentiel de l'intention §6.4. **Reste à faire** : le champ `major_event_description` renvoyé par
le Timekeeper n'est toujours **pas consommé** — soit l'exploiter (ex. forcer un World Turn sur événement
majeur explicite, indépendamment du palier), soit le retirer du prompt pour cesser de payer ces tokens.
Constat d'origine ci-dessous.

**Constat (`axiom/prompts.py:898,902-903` ; `axiom/arbitrator.py:300-311`).** Le prompt Timekeeper
demande au LLM un champ `major_event_description` (« Arrived at Hemlock », « Defeated the Goblin King »…),
mais `process_turn` ne lit que `elapsed_minutes` (l.310-311) : le champ est **parsé puis jeté**. On paie
des tokens pour une sortie inutilisée.

En parallèle, l'**edge case spec §6.4 « Time skip narratif »** (« si `elapsed_minutes > 480` (8h),
déclencher le Chronicler **avant** de retourner le résultat, pour que le monde évolue pendant le
voyage ») **n'est pas implémenté**. Les deux pointent vers la même fonctionnalité manquante : un grand
saut temporel devrait faire évoluer le monde.

**Ce qui serait à faire :**
- Soit **implémenter** le time-skip : si `elapsed_minutes` dépasse un seuil (ou si
  `major_event_description` est non-null), forcer un World Turn (`chronicler.force_trigger`) — ce qui
  redonne du sens au champ.
- Soit **retirer** `major_event_description` du prompt Timekeeper pour cesser de payer des tokens inutiles.

**Priorité :** moyenne (fonctionnalité spec manquante + léger gaspillage tokens). Lié à TICKET-018.

---

## TICKET-050 — Gemini 429 `limit: 0` : fail-fast au lieu de retries inutiles

**Constat (2026-06-10, test réel du backend image Gemini).** Quand un modèle n'est **pas inclus
dans le free tier** de la clé (tous les modèles d'image : `limit: 0`, déjà vu sur
`gemini-2.0-flash` texte), l'API renvoie quand même un 429 avec un `retryDelay` (« retry in
14s ») **trompeur** : le quota journalier est à zéro, attendre ne servira jamais. Or
`_call_with_quota_retry` (`axiom/backends/gemini.py`) enchaîne 3 retries avec compte à rebours →
jusqu'à ~1-2 min de blocage par tour pour rien (et par appel Populate, etc.).

**Fix proposé :** dans `_is_quota_error`/le handler 429, détecter `"limit: 0"` dans le message
(ou `QuotaFailure` avec quota par jour à 0) → **échec immédiat** sans retry ni fallback inutile,
avec un message clair (« modèle hors free tier — facturation requise »). Couvre texte ET image
(le backend est partagé).

**Priorité :** moyenne (UX/perf, aucun comportement correct perdu), quick win.

---

## TICKET-057 — 📋 Chantier planifié : doc intégrée à l'app GUI

**Ce n'est pas un bug — c'est une feature planifiée** (décidée le 2026-06-12, cf. mémoire
[[project-doc-chantier]]). Rendre l'app auto-explicative, en **4 briques** :
1. **Tooltips au survol** de chaque élément.
2. **Bouton « explique cette page »** par page (présente chaque élément de la page).
3. **Quick tour** de départ.
4. **Annuaire global cherchable** (référence + explication des éléments de l'app).

**Contraintes :** traduit dans les **10 langues** via `core/localization.py` (l'i18n est prêt :
TICKET-053/054). Décision : conçu et livré **« tout d'un bloc »** (les 4 briques ensemble).
Prérequis (i18n propre) **fait**. Périmètre = `ui/` (+ `core/locales/`).

**Démarré le 2026-06-12** (les prérequis i18n + anglais moteur sont clos).

---

## TICKET-059 — Test threadé flaky : `test_registre_cancel_active_generations`

**Constat (2026-06-12, repéré en finissant TICKET-056).** `tests/test_generation_cancel.py::`
`test_registre_cancel_active_generations` est **non déterministe** : il passe **3/3 en isolation**
mais **flanche par intermittence** quand il tourne dans un lot chargé (ex. 9 suites en série). Le test
n'a **aucun rapport avec TICKET-055/056** (il utilise un fake `BlockingGen(BaseDbTask)` qui lève sa
propre chaîne « annulé » ; il n'exécute pas `populate_entities` ni de code traduit) — la flakiness
**préexiste**.

**Cause probable.** Le test lance un vrai `threading.Thread(target=task.run)`, attend des événements
via `started.wait(timeout=5)` / `worker.join`, et vérifie le **registre global** des générations
actives (`active_generation_count()`, `cancel_active_generations()`) + un signal Qt
`cancelled.connect(got.append, Qt.DirectConnection)`. Sous charge/ordonnancement de threads, une
fenêtre de course fait que l'assertion (`active_generation_count() == 1`, ou `got == ["annulé"]`)
tombe au mauvais instant. Sensible au timing, pas à la logique.

**Pistes :** remplacer les attentes par des `Event`/condition synchronisés plutôt que des `sleep`/
fenêtres implicites ; s'assurer que le registre est bien nettoyé/isolé entre tests (fixture de reset) ;
éventuellement marquer le test pour qu'il tourne sérialisé/isolé. **Ne pas** masquer en augmentant
aveuglément les timeouts.

**Priorité :** basse (n'affecte pas le produit ; gêne seulement la fiabilité de la suite en lot).

---

## TICKET-061 — i18n : placeholders/titres encore en dur dans les éditeurs du Studio

**⏳ OUVERT (2026-06-12, découvert pendant la suite du TICKET-057).** Le balayage des chaînes en dur
de `ui/` a corrigé la vue setup, le Studio (labels temp/top-p), la loading view et le dialogue
persona ; restent des chaînes anglaises en dur **dans les éditeurs internes du Studio** (zone déjà
en « dette assumée » côté doc) :

- `ui/widgets/story_setup_editor.py:53,57` — placeholders "Tag ID (e.g., race)" / "Question Text"
- `ui/widgets/scheduled_events_editor.py:63` — placeholder "Month 1, Month 2, ..."
- `ui/widgets/populate_tab.py:80` — placeholder d'exemple "e.g. 'Add a group of 3 rival merchants...'"
- `ui/widgets/map_editor.py:130` — titre de dialogue "Distance (km)"

À faire : clés i18n ×10 langues + branchement `tr()` (+ retranslate si l'éditeur reste vivant au
changement de langue). Les placeholders purement techniques (URLs, noms de modèles dans les
settings) sont volontairement exclus.

---

## TICKET-063 — Backend `openai` : modèles reasoning (gpt-5 / o-series) incompatibles

**Constat (2026-06-12, en livrant `feature-cloud-text-providers` ; ex-061 renuméroté au merge).**
Le backend `openai` passe par `UniversalClient`, dont le payload utilise `max_tokens` et
`temperature=0.7`. Les modèles « reasoning » d'OpenAI (famille gpt-5, o-series) **refusent ce
payload en 400** : ils exigent `max_completion_tokens` à la place de `max_tokens` et n'acceptent
que `temperature=1` (défaut). Le défaut livré (`gpt-4.1-mini`, paramètres classiques) fonctionne ;
c'est le choix manuel d'un modèle reasoning qui casse.

**Piste.** Détection du préfixe de modèle (`gpt-5`, `o1`/`o3`/`o4`) dans `UniversalClient` ou un
paramètre de construction supplémentaire dans `build_llm_from_config` (comme `max_stop_sequences`) :
basculer `max_tokens`→`max_completion_tokens` et omettre `temperature`/`top_p`.

**Priorité :** basse tant que le défaut documenté reste un modèle classique.

---

## TICKET-064 — Backend d'images Venice AI

**Idée (2026-06-12, sortie du malentendu initial de la session cloud-providers ; ex-062 renuméroté
au merge).** Venice AI expose une API d'images native `POST https://api.venice.ai/api/v1/image/generate`
(Bearer, JSON `{model, prompt, negative_prompt, width≤1280, height≤1280, steps, cfg_scale, format,
return_binary}` → `{"images": ["<base64>"]}`), qui mappe **exactement** les paramètres existants de
la config image (`image_width/height/steps/cfg_scale`). La clé `venice_api_key` existe déjà depuis
`feature-cloud-text-providers`. Ajouter un backend `venice` dans `axiom/image_generator.py` (même
patron que `_generate_gemini` : échec → None, TICKET-045) + entrée combo dans l'onglet Illustration
+ champ modèle (`image_venice_model`, ex. `venice-sd35`, steps max 30).

**Priorité :** moyenne (feature, rend l'illustration utilisable sans GPU local ni clé Google).
