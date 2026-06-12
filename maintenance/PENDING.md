# PENDING — tickets à étudier

> Règle de vie du fichier : un ticket **terminé** part dans `DONE.md` (trace condensée) et
> **disparaît d'ici**, index compris. Ne restent dans PENDING que les tickets ouverts,
> différés ou en attente d'une validation utilisateur.

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-017| Temps causal : `major_event_description` ignoré + **time-skip Chronicler** (spec §6.4) | ouvert (partiellement couvert par TICKET-018, domaine Pilier 5/Gemini) |
| TICKET-050| Gemini 429 `limit: 0` (modèle hors free tier) : fail-fast au lieu de 3 retries inutiles | ouvert — quick win |
| TICKET-053| i18n : couverture incomplète + maintenabilité (monolithe) — rework | ✅ terminé (2026-06-12) — relocalisé côté app par TICKET-054 |
| TICKET-054| i18n : sortir la traduction du moteur (moteur = données/anglais, app = i18n) | ✅ code terminé (2026-06-12) — ⚠ validation GUI en attente (cf. `maintenance/TICKET-054-i18n-engine-gui-split/`) |
| TICKET-056| Messages user-facing du moteur encore en français (event `axiom dev`, exceptions) → anglais | ✅ terminé (2026-06-12, cf. `maintenance/TICKET-056-engine-english/`) |
| TICKET-057| 📋 **Chantier planifié** — Doc intégrée à l'app GUI (tooltips, bouton « explique cette page », quick tour, annuaire cherchable), 10 langues, « tout d'un bloc » | à faire (feature, pas un bug ; cf. [[project-doc-chantier]]) |
| TICKET-058| 📋 **Chantier planifié** — Site de doc de la lib `axiomai-engine` en **Sphinx** (style devguide.python.org : quickstart, tutos, référence API autodoc), GitHub Pages | ✅ terminé (2026-06-12, cf. `maintenance/TICKET-058-doc-sphinx/`) — ⚠ activer Pages + push pour publier |
| TICKET-059| Test threadé flaky : `test_generation_cancel.py::test_registre_cancel_active_generations` (passe en isolation, flanche sous charge) | ouvert — fiabilité de la suite |
| TICKET-060| `axiom.help` (guide REPL publié dans le wheel) encore 100 % en français — angle mort des TICKET-055/056 | ✅ terminé (2026-06-12, cf. `maintenance/TICKET-060-help-english/`) |
| TICKET-061| Backend `openai` : modèles reasoning (gpt-5/o-series) incompatibles avec le payload actuel (`max_tokens`→`max_completion_tokens`, `temperature` figée à 1) | ouvert — suite de `feature-cloud-text-providers` |
| TICKET-062| Backend d'**images** Venice AI (`POST /image/generate`, clé `venice_api_key` déjà en config) | ouvert — idée feature |

Tickets résolus/clos : voir `DONE.md` (001→012, TC1→TC5, 015→049 sauf 017, 051→052).


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

## TICKET-053 — i18n : couverture incomplète + maintenabilité (rework avant la doc intégrée)

**✅ TERMINÉ (2026-06-12) — relocalisé par TICKET-054.** Rework complet livré : traductions
externalisées en TOML par langue (API `tr()` inchangée), 10 langues complétées à 295/295, outil de
couverture + test. ⚠ **Les emplacements créés ici (`axiom/locales/`, commande `axiom i18n-check`) ont
été déplacés côté app par TICKET-054** : le moteur ne traduit plus, l'i18n vit dans
`core/localization.py` + `core/locales/` (outil `tools/i18n_check.py`). Voir
`maintenance/TICKET-054-i18n-engine-gui-split/`. Constat d'origine conservé ci-dessous.

**Constat (2026-06-12, audit de `axiom/localization.py`).** Le système de traduction maison
fonctionne (dict `_TRANSLATIONS` → `tr(key, **kwargs)`, fallback EN puis clé brute, `load_config`
déjà mis en cache par mtime — pas de souci de perf), mais il a trois faiblesses :

1. **Couverture incomplète.** EN et FR = 295 clés (complets). Les **8 autres langues**
   (es, de, it, pt, ru, zh, ja, ko) n'ont que **210 clés → ~85 manquantes chacune (≈29 %)**.
   En jeu, ces clés retombent sur l'anglais : un utilisateur non-EN/FR voit une **UI mi-traduite,
   mi-anglaise**. (Mesuré : `en/fr=0 manquante`, les 8 autres `=84-85`.)
2. **Maintenabilité.** Tout vit dans **un seul fichier de 2419 lignes** (gros dict imbriqué) :
   pénible à éditer, **gros générateur de conflits de merge** en dev parallèle.
3. **Aucun outil de contrôle de couverture.** La seule détection est un `logger.warning` au
   *runtime*, quand la clé manque déjà en pleine session. Pas de moyen d'auditer les trous à froid
   (il a fallu écrire un script ad hoc).

**Pourquoi c'est un prérequis du chantier « doc intégrée à l'app ».** La doc in-app (tooltips sur
chaque élément, explications de page, quick tour, annuaire cherchable) va ajouter **des centaines de
clés × 10 langues**. Les empiler dans ce fichier déjà monolithique le rend ingérable et démultiplie
les conflits. Mieux vaut assainir la fondation i18n **avant** d'y déverser la doc.

**Pistes de rework (à arbitrer avec l'utilisateur, non-codeur — expliquer les options) :**
- **Externaliser** les traductions hors du `.py` : un fichier de données par langue
  (`axiom/locales/<lang>.json` ou `.toml`), chargés à la volée. Le code rétrécit, chaque langue
  devient un fichier autonome (moins de conflits, plus facile à remplir/relire — y compris par IA).
- **Outil de couverture** : un petit script/commande CLI (`axiom i18n-check`) + un test qui liste les
  clés manquantes/en trop par langue, pour ne plus jamais publier une langue à 71 %.
- **Compléter les ~85 clés manquantes** des 8 langues (volume modéré, faisable à l'IA — l'utilisateur
  ne pourra pas vérifier la qualité zh/ja/ko/ru, en tenir compte).
- Garder l'API publique `tr(key, **kwargs)` **inchangée** (zéro impact sur les ~tous les appels UI).

**Priorité :** haute **si** on lance la doc intégrée (prérequis structurel) ; moyenne sinon
(dette technique + UI partiellement traduite pour 8 langues).

---

## TICKET-056 — Messages user-facing du moteur en français (events `dev` + exceptions)

**✅ TERMINÉ (2026-06-12).** ~30 messages d'exception + events `dev` + statuts `populate` traduits
en anglais (méthode : liste exhaustive des `raise`, car le FR sans accent échappe au grep ; traduction
par fragments préservant les `{placeholders}`). Tests impactés mis à jour, 166 passed. Restent FR hors
périmètre : logs `logger.*` (diagnostic) et l'app `workers/` (couche localisée). Détails :
`maintenance/TICKET-056-engine-english/`. Constat d'origine ci-dessous.

**Constat (2026-06-12, en finissant TICKET-055).** Le CLI `axiom` est désormais 100 % anglais
(TICKET-055), mais il **surface encore du français émis par le moteur hors `axiom/cli/`** :
- **`axiom/dev.py`** : l'événement de `axiom dev` (« Définition compilée » / « Modification détectée
  — définition rechargée ») affiché via `on_event`.
- **Messages d'exception** dans plusieurs modules moteur (`package.py`, `library.py`, `compile.py`,
  `saves.py`, `savestore.py`…) en français, affichés à l'utilisateur quand le CLI imprime
  `print(f"...: {exc}")` (ex. « Décompilation impossible : … », « Cet univers est déjà un
  univers-dossier. », « Préciser soit at_turn, soit at_minute… »).

**Pourquoi c'est cohérent de le faire :** même principe que TICKET-054/055 — le moteur publié parle
anglais pour tout ce qu'il expose à l'utilisateur (données, clés, **et messages d'erreur**).

**Pourquoi c'est un ticket distinct (pas fait dans 055) :** périmètre **moteur** (pas `cli/`), plus
large et plus diffus (exceptions réparties dans de nombreux modules), et il **impacte des tests qui
assertent le texte français** (`test_populate_resume`, `test_savestore`, `test_dev_hotreload`,
`test_saves_editing`…). Mérite un passage dédié + relecture, comme le CLI a eu le sien.

**À faire :** recenser toutes les chaînes user-facing FR émises par `axiom/*.py` (events, exceptions
levées avec message destiné à l'utilisateur), traduire en anglais, mettre à jour les assertions de
tests correspondantes. Ne PAS toucher commentaires/docstrings internes.

**Priorité :** moyenne (cohérence du moteur publié ; le happy-path CLI est déjà EN).

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

**Pourquoi pas démarré :** on enchaînait l'assainissement i18n + l'anglais moteur d'abord.

---

## TICKET-058 — 📋 Chantier planifié : site de doc de la librairie (Sphinx)

**✅ TERMINÉ (2026-06-12).** Site Sphinx complet livré dans `docs/` : **anglais + français**
(sélecteur de langue, gettext `.po`, fallback EN pour le non-traduit), thème Furo, pages en
Markdown (MyST), quickstart + 6 guides + référence d'API autodoc, workflow GitHub Pages
(`.github/workflows/docs.yml`, build strict `-W`, deps lourdes mockées). Au passage : ~100
docstrings publiques du moteur traduites FR→EN (la réf API est en anglais), warnings reST corrigés.
**Reste côté utilisateur :** activer Pages (Settings → Pages → Source « GitHub Actions ») et merger
dans `main`. Détails : `maintenance/TICKET-058-doc-sphinx/`. Constat d'origine ci-dessous.

**Constat d'origine.** Feature planifiée (décidée le 2026-06-12, cf. [[project-doc-chantier]]).
Vraie documentation publique de la lib `axiomai-engine`, façon `devguide.python.org` / PySide6 :
**quickstart, tutoriels, guides, + référence d'API auto-générée depuis les docstrings**. Destinée à
**GitHub Pages**. **Outil tranché : Sphinx** (et non MkDocs) — pour matcher les sites de référence
cités et générer l'API depuis les docstrings existantes. Chantier **autonome** (nouveau dossier
`docs/`, ne touche aucun code → zéro conflit, zéro risque). Bon candidat pour démarrer le volet doc.

---

## TICKET-061 — Backend `openai` : modèles reasoning (gpt-5 / o-series) incompatibles

**Constat (2026-06-12, en livrant `feature-cloud-text-providers`).** Le backend `openai` passe par
`UniversalClient`, dont le payload utilise `max_tokens` et `temperature=0.7`. Les modèles
« reasoning » d'OpenAI (famille gpt-5, o-series) **refusent ce payload en 400** : ils exigent
`max_completion_tokens` à la place de `max_tokens` et n'acceptent que `temperature=1` (défaut).
Le défaut livré (`gpt-4.1-mini`, paramètres classiques) fonctionne ; c'est le choix manuel d'un
modèle reasoning qui casse.

**Piste.** Détection du préfixe de modèle (`gpt-5`, `o1`/`o3`/`o4`) dans `UniversalClient` ou un
paramètre de construction supplémentaire dans `build_llm_from_config` (comme `max_stop_sequences`) :
basculer `max_tokens`→`max_completion_tokens` et omettre `temperature`/`top_p`.

**Priorité :** basse tant que le défaut documenté reste un modèle classique.

---

## TICKET-062 — Backend d'images Venice AI

**Idée (2026-06-12, sortie du malentendu initial de la session cloud-providers).** Venice AI expose
une API d'images native `POST https://api.venice.ai/api/v1/image/generate` (Bearer, JSON
`{model, prompt, negative_prompt, width≤1280, height≤1280, steps, cfg_scale, format, return_binary}`
→ `{"images": ["<base64>"]}`), qui mappe **exactement** les paramètres existants de la config image
(`image_width/height/steps/cfg_scale`). La clé `venice_api_key` existe déjà depuis
`feature-cloud-text-providers`. Ajouter un backend `venice` dans `axiom/image_generator.py` (même
patron que `_generate_gemini` : échec → None, TICKET-045) + entrée combo dans l'onglet Illustration
+ champ modèle (`image_venice_model`, ex. `venice-sd35`, steps max 30).

**Priorité :** moyenne (feature, rend l'illustration utilisable sans GPU local ni clé Google).

---

## TICKET-060 — `axiom.help` encore en français (angle mort de 055/056)

**✅ TERMINÉ (2026-06-12).** `_HELP_TEXT` + docstrings de module/`_Help` de `axiom/__init__.py`
traduits FR→EN, lien vers le site de doc (TICKET-058) ajouté en pied de guide ; aucun test
n'assertait le texte FR (`test_packaging.py` 15 verts). Détail :
`maintenance/TICKET-060-help-english/`.

**Constat d'origine (2026-06-12, en démarrant TICKET-058).** Le guide REPL `axiom.help`
(`axiom/__init__.py::_HELP_TEXT`, affiché par `axiom.help()` / `print(axiom.help)`) était **publié
dans le wheel** et toujours **100 % en français**. Les TICKET-055 (CLI) et 056 (exceptions/events)
ne couvraient pas ce texte. Même principe : le moteur publié parle anglais.

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

---
