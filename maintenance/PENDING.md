# PENDING — tickets à étudier

> Règle de vie du fichier : un ticket **terminé** part dans `DONE.md` (trace condensée) et
> **disparaît d'ici**, index compris. Ne restent dans PENDING que les tickets ouverts,
> différés ou en attente d'une validation utilisateur.

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-017| Temps causal : `major_event_description` ignoré + **time-skip Chronicler** (spec §6.4) | ouvert (partiellement couvert par TICKET-018, domaine Pilier 5/Gemini) |
| TICKET-057| 📋 Doc intégrée à l'app GUI (tooltips, bouton « explique cette page », quick tour, annuaire) | 🔄 ouvert — **contenu jugé trop succinct (2026-06-13), à enrichir** (cf. [[project-doc-chantier]]) |
| TICKET-059| Test threadé flaky : `test_generation_cancel.py::test_registre_cancel_active_generations` (passe en isolation, flanche sous charge) | ouvert — fiabilité de la suite |
| TICKET-061| i18n : placeholders/titres encore en dur dans les éditeurs du Studio | ouvert — quick win |
| TICKET-062| 🚀 **Préparation bêta publique** : items 1/2/4 ✅ **validés GUI (2026-06-13)** ; reste **check Windows** + **screens/GIF** | ouvert — chantier, priorité haute |
| TICKET-063| Backend `openai` : modèles reasoning (gpt-5/o-series) incompatibles avec le payload actuel (`max_tokens`→`max_completion_tokens`, `temperature` figée à 1) | ouvert — suite de `feature-cloud-text-providers` |
| TICKET-064| Backend d'**images** Venice AI (`POST /image/generate`, clé `venice_api_key` déjà en config) | ouvert — idée feature |
| TICKET-065| `world_tension_level` : **deux casses de clé** (`World_Tension_Level` seedée/lue par le Chronicler vs `world_tension_level` écrite par Studio/compilateur) → le curseur de tension du Studio est sans effet réel | ouvert — bug latent |
| TICKET-067| Suite de tests : **segfault** quand `test_ambiance_manager.py` (Qt multimédia) précède `test_arbitrator.py` (import torch→triton) — `pytest tests/` plante, chaque moitié passe seule | ouvert — fiabilité de la suite, environnement (Python 3.14/Fedora) |
| TICKET-069| **Validation Windows sur machine réelle** : 🔄 **gros lot fait les 2026-06-14** (crash WinError 32 résolu, classe connexion-non-fermée corrigée moteur+app, suite 753✅, **`run.bat`/startup_check OK + `main.py` atteint la boucle d'événements sans crash**, **audio requalifié quasi nul** : Ogg/FLAC/AAC supportés sur Win11 + aucun asset audio embarqué — cf. `TICKET-062-windows-support/CHANGELOG.md`). Reste : **un vrai tour de jeu GUI** + génération d'images locale | ouvert — bien allégé |
| TICKET-070| **torch ne charge pas sous Windows** (`OSError WinError 126`) : **VC++ Redistributable x64 manquant**. App dégradée gracieusement (no-op + warning) ; **diagnostic FAIL actionnable** (`_check_embedding_runtime`) **+ alerte GUI au lancement** avec lien de téléchargement (`ui/runtime_check.py`, i18n ×10, marqueur « ne plus afficher »). `requirements.txt` impossible (composant système, pas un paquet pip). Reste action utilisateur → **installer vc_redist.x64.exe** | ouvert — environnement (code côté app = FAIT) |
| TICKET-083| **Croyances : fuite temporelle au rewind** (`created_turn_id = min(tours des sources)` → une croyance survit à un rembobinage avant qu'elle ait été consolidée) | ouvert — QA Hindsight 2 (2026-06-19), sévérité basse-moyenne |
| TICKET-084| **Budget de prompt `living` = jusqu'à 3× `rag_chunk_count`** (croyances + faits + chunks narratifs cumulés) | ouvert — QA Hindsight 2 (2026-06-19), coût tokens |
| TICKET-085| **Cache BM25 : `collection.get()` plein corpus tourne encore au cache-hit** (seul le build d'index est caché) | ouvert — QA Hindsight 2 (2026-06-19), micro-opt mineure |
| TICKET-086| **`fired_turn_id` perdu** à l'extraction/export (`savestore._RUNTIME_COPY`) et au fork (`saves.fork_save`) → rewind ne « dé-tire » plus les events | ✅ corrigé + test de garde (⚠ non commité, 2026-06-21) — `maintenance/qa/qa-fs-univers-saves-2026-06-21/` |
| TICKET-087| **Cache compilé `universes/Myria/.axiom-cache/` commité bien que gitignoré** + schéma périmé (pré-`fired_turn_id`), jamais reconstruit (hash source inchangé) | ouvert — QA fs 2026-06-21, hygiène repo (sans impact utilisateur : installateur exclut le cache) |
| TICKET-088| **`fork_save` ne copie pas** Facts/Observations/Mental_Models/Snapshots/Modifier_Snapshots (mémoire living + snapshots de rewind perdus au fork d'une save embarquée) | ouvert — QA fs 2026-06-21, même classe que 086 |
| TICKET-089| **`package._RUNTIME_TABLES` omet** Facts/Observations/Mental_Models (mémoire living d'une save embarquée peut fuir dans un `.axiom` « définition seule ») | ouvert — QA fs 2026-06-21, basse sévérité |
| TICKET-090| **`paths` : pas de `get_universes_dir()`**, `UNIVERSES_DIR` figé à l'import (insensible à `AXIOM_DATA_DIR`/`configure`) alors que saves/vector le sont → isolation asymétrique | ouvert — QA fs 2026-06-21, archi/cohérence |

Tickets résolus/clos : voir `DONE.md` (001→056 sauf 017, 058→060, **071**, **072→082** (lot Hindsight, commités), **+ lot validations GUI du 2026-06-13 : 050, 062 items 1/2/4, 066, 068**).
Réserves portées dans `DONE.md` : TICKET-058 (activer GitHub Pages — droits admin — puis
relancer le job `deploy`). TICKET-054 (i18n) **validé GUI le 2026-06-13**.


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

## TICKET-057 — 📋 Doc intégrée à l'app GUI — **contenu à enrichir**

**Feature planifiée** (décidée le 2026-06-12, cf. mémoire [[project-doc-chantier]]). Rendre l'app
auto-explicative, en **4 briques** :
1. **Tooltips au survol** de chaque élément.
2. **Bouton « explique cette page »** par page (présente chaque élément de la page).
3. **Quick tour** de départ.
4. **Annuaire global cherchable** (référence + explication des éléments de l'app).

**Structure livrée et VALIDÉE en GUI (2026-06-13)** : les 4 briques sont en place et marchent
(registre `ui/help_system.py::PAGES`, dialogues `ui/help_dialogs.py`, 10 langues, toggle tooltips).

**⚠ Reste à faire — le seul point qui rouvre le ticket (retour utilisateur 2026-06-13) :** le
**contenu textuel est jugé trop succinct**. Les explications (tooltips + « expliquer cette page »
+ annuaire) doivent être **étoffées** : phrases plus complètes, contexte/exemples, pourquoi de
chaque réglage, pas juste un libellé reformulé. Travail = ré-écriture des ~242 clés `doc_*` dans
`core/locales/*.toml` (EN d'abord, puis propagation 10 langues), périmètre `core/locales/` (pas de
code). Outil de repérage des trous : `python tools/doc_check.py`.

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

---

## TICKET-062 — 🚀 Préparation bêta publique (testeurs app + librairie)

**Décision utilisateur (2026-06-12).** Le projet est jugé assez mûr pour recruter des
bêta-testeurs (app GUI + lib `axiomai-engine`). Chantier de préparation, par sous-items :

1. **Univers par défaut embarqué** — fondé sur **Myria**, la fiction de l'utilisateur.
   **✅ Univers créé (2026-06-12)** : `universes/Myria/` (Universe-as-Code, 40 fichiers, EN),
   adapté du wiki fourni (`myrial_wiki.zip`) — lore book = savoir public seulement, secrets
   (dieux morts, Aléa, Arodan, traque Coalition) dans le global lore côté narrateur ; départ
   jouable à Highport (5 PNJ, carte 18 lieux, 3 questions de setup, 2 événements programmés).
   Compile + pack vérifiés ; `.gitignore` restructuré (`universes/*` + `!universes/Myria/`,
   cache exclu). Noms inventés pour les placeholders du wiki listés dans son README.
   **✅ Câblage premier lancement fait (2026-06-12)** : `core/bundled_universes.py` branché
   dans `main.py` — une offre par univers à vie (`installed_bundles.txt`), jamais
   d'écrasement, cache recompilé par la découverte Hub ; détail dans
   `maintenance/TICKET-062-univers-par-defaut/`.
   **✅ VALIDÉ GUI (2026-06-13).** Reste optionnel : relecture canon fine ; version FR.
2. **Clés Fireworks.ai embarquées dans le repo** — **✅ FAIT (2026-06-12)** : 4 clés fournies
   par l'utilisateur (AXIOMAI-0/1 à 6 $, AXIOMAI-2/3 à 1 $, **expirent le 2026-06-30**),
   embarquées obfusquées (inversion + base64) dans `core/builtin_keys.py`, utilisées seulement
   sans clé utilisateur, **rotation automatique** sur 401/402/403/429
   (`UniversalClient.fallback_api_keys` + registre `axiom.config.register_builtin_keys` — le
   moteur PyPI ne contient aucune clé). 1ᵉʳ lancement sans config → backend `fireworks`,
   modèles plafonnés « pas chers » (≤ 0,30 $ in / ≤ 1,00 $ out par M tokens), bouton
   « Parcourir… » les modèles avec prix dans Réglages → Cloud. Défaut `deepseek-v3p1` mort →
   `gpt-oss-120b`. **Rotation re-vérifiée en réel (2026-06-12, complétion + streaming)** :
   clé morte en tête → bascule sur clé valide → réponse OK. **Kill-switch ajouté** :
   `core/builtin_keys.py::BUILTIN_KEYS_ENABLED = True` → à `False`, l'offre « clés gratuites »
   est retirée d'un geste (register/défaut bêta = no-ops, pool vide, message « add your key »)
   **sans rien supprimer** (clés/prix/rotation conservés). Détail :
   `maintenance/TICKET-062-clefs-fireworks/`.
   **✅ VALIDÉ GUI (2026-06-13).** ⏰ Reste : après le 2026-06-30, flipper
   `BUILTIN_KEYS_ENABLED=False` (ou renouveler le pool).
3. **Vérifier le support Windows** — **✅ AUDIT CODE FAIT (2026-06-13)**, détail dans
   `maintenance/TICKET-062-windows-support/`. Verdict : moteur/workers déjà Windows-safe
   (pathlib, fermeture sqlite avant replace/unlink, sanitisation des noms de fichiers, hardcore
   conçu pour Windows). **Bugs corrigés** : `run.bat` (plancher Python 3.10→3.11), `#`→`REM` +
   emoji dans `run.bat`/`test.bat`, garde-fou UTF-8 stdout dans `tools/diagnostic.py`.
   **Reste (test machine Windows requis, pas corrigeable à l'aveugle)** : audio `.ogg` (Media
   Foundation ne décode pas Vorbis), install torch/chromadb/PySide6, images locales, run.bat
   de bout en bout.
4. **Outil de diagnostic accessible aux utilisateurs** — **✅ CLI + GUI FAITS (2026-06-12/13)** :
   `tools/diagnostic.py` autonome (`python -m tools.diagnostic`) → rapport copiable ✅/⚠️/❌
   (env, versions libs, embedding caché, config, dossiers, **connectivité backend**), drapeaux
   `--tests` (pytest en 2 lots, contourne segfault TICKET-067), `--offline`, `--json`,
   `--output`, code de sortie = sévérité ; reflète le runtime réel (clés bêta enregistrées).
   Brique GUI : Aide → Diagnostic (`ui/diagnostic_dialog.py` + `workers/diagnostic_worker.py`,
   boutons Actualiser/Tests/Copier/Enregistrer, i18n ×10). Détail :
   `maintenance/TICKET-062-outil-diagnostic/`. **✅ VALIDÉ GUI (2026-06-13).**
5. **Assets de com'** : nouvelles captures d'écran (celles du README datent d'avant la doc
   intégrée/les nouveaux onglets) + **un GIF** de ~30 s d'un tour de jeu pour le README et
   les annonces.

**Canaux de recrutement identifiés** (discussion 2026-06-12) : communauté SillyTavern (l'app
importe leurs cartes — feature à mettre en avant dans le README), r/LocalLLaMA, LinuxFr.org,
itch.io (app), Show HN + r/Python (lib). Prérequis conseillés avant annonce : TICKET-050
(fail-fast 429) **✅ fait** et une CI GitHub Actions **✅ faite** (`.github/workflows/tests.yml`,
2 lots, matrice 3.11/3.12 — reste à confirmer verte au 1ᵉʳ push).

**Priorité :** haute (bloque le recrutement de testeurs). Items 1-2 = cœur de l'onboarding.
**État au 2026-06-13 :** items 1, 2, 4 **validés GUI** ; item 3 (Windows) **audit code fait +
bugs scripts corrigés** (reste un test sur vraie machine Windows) ; **reste à produire : item 5
(screens/GIF)** — et le test Windows réel quand une machine sera dispo.

## TICKET-065 — `world_tension_level` : clé en deux casses, curseur Studio sans effet

**Découvert le 2026-06-12** en corrigeant le crash du Studio sur l'univers Myria
(`maintenance/TICKET-062-univers-par-defaut/`).

La même méta existe sous deux clés selon le chemin d'écriture :
- `axiom/db_helpers.py:115` (création wizard) seed **`World_Tension_Level`** = "0.3" ;
- `axiom/chronicler.py:290` (`_fetch_world_tension`) lit **`World_Tension_Level`** ;
- `ui/creator_studio_view.py` (charge/sauve) et `axiom/compile.py` (univers-dossier)
  utilisent **`world_tension_level`** (minuscules).

Conséquences : pour un univers wizard, le Chronicler lit à vie le 0.3 seedé (le Studio
écrit l'autre clé) ; pour un univers-dossier, la clé majuscule n'existe pas → défaut 0.3.
**Le curseur « World Tension » du Studio n'influence donc jamais le Chronicler.**

Piste : normaliser sur une seule clé (minuscules, cohérente avec compile/decompile) +
migration de lecture tolérante (lire les deux, écrire la canonique) dans le Chronicler
et `db_helpers`. Vérifier au passage s'il existe d'autres méta à double casse.

## TICKET-067 — Suite de tests : segfault Qt multimédia + torch/triton

**Découvert le 2026-06-12** en validant TICKET-066 (la grande suite plantait).

`pytest tests/` segfault systématiquement au début de `test_arbitrator.py` :
`Fatal Python error: Segmentation fault` pendant l'import de `triton` (chargé par
`torch._dynamo`, lui-même tiré par un import du chemin arbitrator/TTS). Reproduction
minimale : `pytest tests/test_ambiance_manager.py tests/test_arbitrator.py` —
l'ordre compte, c'est le chargement préalable de PySide6 QtMultimedia qui rend
l'import natif de triton fatal. Chaque fichier passe **seul** ; la suite passe en
deux moitiés (`--ignore=tests/test_ambiance_manager.py` → 710 verts, puis
`test_ambiance_manager.py` seul → 5 verts).

Indépendant du code applicatif (crash dans le module natif triton, venv Python
3.14.5/Fedora). Pistes : épingler/mettre à jour triton, le désinstaller s'il ne sert
pas (dépendance transitive de torch), ou forcer l'ordre/l'isolation des tests
(pytest-forked, marqueur). À recouper avec TICKET-059 (fiabilité de la suite).

**Priorité :** moyenne — bloque la validation « grande suite » en un seul passage.

## TICKET-069 — Validation Windows sur machine réelle (reste de l'audit item 3)

**Ouvert le 2026-06-13.** Suite de l'audit statique TICKET-062 item 3
(`maintenance/TICKET-062-windows-support/`) : le code est jugé Windows-safe et les bugs de
scripts sont corrigés, mais **rien n'a été lancé sur Windows**. Ce ticket regroupe ce qui ne
peut être levé que sur une vraie machine/VM Windows. À dérouler dans l'ordre :

1. **Install des dépendances** (risque n°1). `pip install -r requirements.txt` via `run.bat`.
   ⚠ **Tester avec Python 3.11, 3.12 ou 3.13** — PAS 3.14 : `onnxruntime`/`torch`/`PySide6`
   n'ont pas toujours de wheel `cp314` Windows → l'install tenterait une compilation source et
   échouerait. **Décision à prendre** : recommander 3.11–3.13 dans le README + message `run.bat`
   (voire borne haute), et/ou borner légèrement les versions de deps (non borné = `>=` partout).
2. **Lancement de bout en bout** : `run.bat` (venv, deps, `startup_check.py`, GUI s'ouvre).
3. **1ᵉʳ téléchargement du modèle d'embedding** sur cache vierge (`all-MiniLM-L6-v2`) — le fix
   TICKET-068 (`local_files_only=True`) suppose le modèle déjà caché ; le tout 1ᵉʳ download
   (réseau + cache HF sous `%USERPROFILE%`) n'a jamais été exercé sous Windows.
4. **Audio** : `QtMultimedia` s'importe ? (éditions Windows « N » sans Media Feature Pack =
   échec possible) ; ambiances `.mp3`/`.wav` jouent ; **`.ogg` attendu muet** (Media Foundation
   ne décode pas Vorbis) → si confirmé, privilégier mp3/wav pour les assets ou documenter.
5. **Génération d'images** locale (SD WebUI/ComfyUI sur `localhost`) + backend Gemini.
6. **Un tour de jeu complet** + le Creator Studio + Aide → Diagnostic (le rapport doit être
   parlant ; vérifier qu'il signale correctement l'environnement Windows).

**Priorité :** haute (bloque l'annonce bêta côté Windows). **Prérequis : accès à un Windows**
(VM, ou testeur de confiance). Le diagnostic GUI/CLI (`tools/diagnostic.py`) est l'outil à faire
tourner en premier par un testeur pour remonter un rapport.

---

## TICKET-083 — Croyances : fuite temporelle au rewind (`created_turn_id`)

**Découvert le 2026-06-19** (2ᵉ passe QA du chantier Hindsight).

`axiom/observations.py::apply_consolidation` (branche CREATE) stampe
`created_turn_id = min(tours des sources)`, **pas le tour T où la consolidation a tourné**. Or le
rollback (`rollback_observations`) supprime sur `created_turn_id > target`. Donc une croyance
consolidée au tour T à partir de faits plus anciens **survit à un rembobinage à un tour situé entre
sa plus vieille source et T**, alors que la passe de consolidation n'avait pas encore eu lieu à ce
moment-là → fuite de « connaissance future » vers le passé, bornée à ~l'intervalle de consolidation
(`memory_fact_interval`).

**Piste.** Soit stamper `created_turn_id = turn_id` (le tour de consolidation) — la croyance
disparaît alors proprement si on rembobine avant sa formation ; soit assumer le comportement actuel et
le documenter. Vérifier l'effet sur les sources : les `sources` restent turn-keyed et sont déjà
filtrées correctement au rewind, donc seul le critère de suppression de la croyance entière est en jeu.

**Priorité :** basse-moyenne — incohérence de rewind dans un cas de bord (croyance bâtie sur faits
anciens + rembobinage). Aucun impact hors mode « living » + croyances.

---

## TICKET-084 — Budget de prompt `living` = jusqu'à 3× `rag_chunk_count`

**Découvert le 2026-06-19** (2ᵉ passe QA Hindsight).

`axiom/arbitrator.py` (~l.367-386, mode living) injecte **trois** blocs dimensionnés chacun par
`cfg.rag_chunk_count` : croyances (si activées) + faits + chunks narratifs. L'utilisateur qui règle
`rag_chunk_count` s'attend probablement à un **total**, pas à un triplement du contexte (coût tokens
×3 dans le pire cas, mode « living » + croyances).

**Piste.** Soit un budget partagé (répartir `rag_chunk_count` entre les trois sources), soit des
sous-quotas explicites/configurables (ex. `memory_belief_count`, `memory_fact_count`), soit documenter
clairement que le total grimpe en living. À arbitrer avec la qualité de rappel (les trois niveaux sont
complémentaires : croyances synthétiques → faits atomiques → prose brute).

**Priorité :** basse — coût/clarté, pas un bug. Pertinent seulement en mode « living ».

---

## TICKET-085 — Cache BM25 : `collection.get()` plein corpus encore exécuté au cache-hit

**Découvert le 2026-06-19** (2ᵉ passe QA Hindsight).

`axiom/memory.py::query` : même quand l'index BM25 est réutilisé (cache-hit TICKET-078), le
`self._collection.get(where=where_cond, include=["documents","metadatas"])` recharge **tout** le corpus
filtré à chaque requête (nécessaire aujourd'hui pour calculer l'empreinte d'ids ET pour le backfill des
hits lexicaux-seuls). Seul le coût dominant (tokenisation + IDF dans `build_bm25`) est caché ; la
lecture Chroma plein-corpus, elle, reste par requête.

**Piste (si jamais ça devient chaud).** Mettre aussi `corpus_docs`/`corpus_metas` en cache à côté de
l'index (clé identique), invalidés par la même empreinte — au prix d'un peu de RAM. Gain réel surtout
sur le corpus lore figé ; négligeable sur petits volumes. À ne faire que si un profilage le justifie.

**Priorité :** très basse — micro-optimisation. Le fix TICKET-078 (le vrai poste de coût) tient.

---

## TICKET-086 — `fired_turn_id` perdu à l'extraction/export et au fork ✅

**Découvert le 2026-06-21** (QA système fichiers/univers/saves), **corrigé le même jour**
(⚠ non commité, `maintenance/qa/qa-fs-univers-saves-2026-06-21/`).

TICKET-075 a ajouté la colonne `fired_turn_id` à `Fired_Scheduled_Events` (pour que le rewind
« dé-tire » les events tirés après le tour cible : `DELETE … WHERE fired_turn_id > target`). Mais deux
chemins de copie codaient la liste de colonnes **en dur** sans la suivre → `fired_turn_id` retombait à
`0` (défaut), donc le rewind ne dé-tirait plus rien (`0 > target` toujours faux) :
- `axiom/savestore.py::_RUNTIME_COPY` — utilisé par `extract_save` (donc `pack_save`/`.axiomsave`
  d'une save **embarquée legacy**). Repro confirmée : seed `fired_turn_id=7` → extrait à `0`.
- `axiom/saves.py::fork_save` — `SELECT event_id` / `INSERT (save_id, event_id)` sans la colonne ;
  utilisé par `duplicate_save` d'une save embarquée.

**Correctif.** Les deux chemins propagent `fired_turn_id` ; `fork_save` appelle d'abord
`ensure_fired_event_turn_column` (robuste sur vieille base). **Test de garde anti-dérive** ajouté
(`tests/test_savestore.py::TestCopyListSchemaCoherence`) : `_DEFINITION_COPY`/`_RUNTIME_COPY` doivent
matcher exactement le schéma vivant + régression `fired_turn_id` sur `extract_save`. 160 tests verts.

**Priorité :** moyenne — perte de donnée silencieuse cassant TICKET-075 sur les chemins export/fork.

---

## TICKET-087 — Cache compilé Myria commité (gitignoré mais tracké) + schéma périmé

**Découvert le 2026-06-21** (QA fs). `universes/Myria/.axiom-cache/universe.db` (+ `cache_hash.txt`)
sont **suivis par git** alors qu'ils matchent une règle `.gitignore` (un fichier déjà tracké ignore
le gitignore). Le cache commité date du 2026-06-15, **avant** l'ajout de `fired_turn_id` → schéma
périmé. Comme `cache_hash.txt` matche la source, `compile_universe` (sans `force`) **ne le reconstruit
jamais**.

**Impact.** Nul pour l'utilisateur final : `core/bundled_universes.py` exclut `.axiom-cache` à la
copie (`ignore_patterns`) → recompile propre dans la bibliothèque. N'affecte que le dev qui lance
depuis le repo (cache stale) et l'hygiène du dépôt (binaire 221 Ko commité contre l'intention).

**Piste.** `git rm --cached universes/Myria/.axiom-cache/universe.db universes/Myria/.axiom-cache/cache_hash.txt`
(désuivre, l'utilisateur gère git) — le cache se régénère à la première compilation. Vérifier qu'aucun
autre univers bundlé n'a un cache tracké.

**Priorité :** basse — hygiène repo.

---

## TICKET-088 — `fork_save` ne copie pas la mémoire living ni les snapshots

**Découvert le 2026-06-21** (QA fs, même classe que TICKET-086). `axiom/saves.py::fork_save` copie
Saves/Event_Log/Active_Modifiers/Fired_Scheduled_Events/Items_Inventory/Timeline, et reconstruit le
State_Cache. Il **ne copie pas** : `Facts`, `Observations`, `Mental_Models` (mémoire mode living),
ni `Snapshots`/`Modifier_Snapshots` (snapshots de rewind). Forker une save **embarquée** (via
`duplicate_save` legacy) perd donc les faits/croyances/modèles mentaux accumulés et empêche un rewind
correct dans la copie.

**Portée.** `fork_save` ne sert qu'aux saves embarquées legacy (les saves séparées sont copiées
fichier→fichier et gardent tout). Impact réel : legacy + living + duplication.

**Piste.** Étendre `fork_save` aux tables manquantes (en gérant leur création paresseuse : `Facts`/
`Observations`/`Mental_Models` peuvent être absentes d'une vieille base), ou documenter la limite.

**Priorité :** basse-moyenne.

---

## TICKET-089 — `package._RUNTIME_TABLES` omet les tables living

**Découvert le 2026-06-21** (QA fs). `axiom/package.py::_runtime_free_cache_copy` purge les tables
runtime du cache embarqué dans un `.axiom` (« définition seule ») via `_RUNTIME_TABLES`. Cette liste
n'inclut **pas** `Facts`/`Observations`/`Mental_Models`. Si une save embarquée legacy a joué en mode
living, sa mémoire (potentiellement du contenu de partie) pourrait voyager dans une archive censée ne
porter que la définition.

**Piste.** Ajouter les trois tables à `_RUNTIME_TABLES` (purge conditionnelle : déjà gardée par
`SELECT 1 FROM sqlite_master`).

**Priorité :** basse — fuite de données de partie dans un export de définition (cas legacy + living).

---

## TICKET-090 — `paths` : `UNIVERSES_DIR` figé, pas de `get_universes_dir()`

**Découvert le 2026-06-21** (QA fs). `axiom/paths.py` expose des getters override-aware pour les
saves/vector/assets (`get_saves_dir`/`get_vector_dir`/`get_assets_dir`, sensibles à `AXIOM_DATA_DIR`
et `configure(data_dir=)`), mais **pas pour les univers** : seul le constant `UNIVERSES_DIR` existe,
gelé à l'import sur `~/AxiomAI/universes`. Conséquence : un embarqueur/test qui isole via
`AXIOM_DATA_DIR` déplace saves+vector mais **pas** la bibliothèque d'univers (asymétrie). La fixture
de test `isolated_axiom_data_dir` n'isole d'ailleurs pas les univers — les tests qui écrivent dans la
bibliothèque doivent passer un `library_dir` explicite (ce qu'ils font aujourd'hui).

**Piste.** Ajouter `get_universes_dir()` (= `_data_root()/universes`) et l'utiliser dans
`compile_cmd`/`play`/`bundled_universes`/`hub_view` ; garder `UNIVERSES_DIR` en alias de compat.
Décider si les univers DOIVENT suivre `data_dir` (cohérence) ou rester volontairement machine-globaux.

**Priorité :** basse — cohérence/archi, pas de bug pour l'app (qui n'override jamais `data_dir`).
