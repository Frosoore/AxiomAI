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
| TICKET-088| **`fork_save` ne copie pas** Facts/Observations/Mental_Models/Snapshots/Modifier_Snapshots (mémoire living + snapshots de rewind perdus au fork d'une save embarquée) | ouvert — QA fs 2026-06-21, même classe que 086 (inventaire + ses snapshots désormais copiés au fork, TICKET-095) |
| TICKET-089| **`package._RUNTIME_TABLES` omet** Facts/Observations/Mental_Models **+ `Item_Instances`/`Session_Lore`** (données de partie d'une save embarquée peuvent fuir dans un `.axiom` « définition seule ») | ouvert — QA fs 2026-06-21, basse sévérité |
| TICKET-090| **`paths` : pas de `get_universes_dir()`**, `UNIVERSES_DIR` figé à l'import (insensible à `AXIOM_DATA_DIR`/`configure`) alors que saves/vector le sont → isolation asymétrique | ouvert — QA fs 2026-06-21, archi/cohérence |
| TICKET-099| **Clés Fireworks intégrées expirées (2026-06-30) mais `BUILTIN_KEYS_ENABLED = True`** → un nouvel utilisateur est configuré par défaut sur des clés mortes | ouvert — **décision utilisateur** (couper l'interrupteur ou renouveler le pool) |
| TICKET-100| **Rewind web/CLI ne rembobine pas ChromaDB** + ids `uuid4` → rejouer un tour **ajoute un doublon** (le RAG voit le « futur annulé ») | ouvert — arbitrage mods 2026-09-26, **important** |
| TICKET-101| **Tour échoué ou annulé → `user_input` orphelin + `turn_id` décalé** (2 messages joueur d'affilée au tour suivant) | ouvert — arbitrage mods 2026-09-26, **important**, reproduit |
| TICKET-102| **Job mémoire living web sans verrou** : un rewind pendant l'appel LLM laisse des faits de tours annulés | ouvert — arbitrage mods 2026-09-26, probable (course) |
| TICKET-103| **`fork_save --turn` copie `Fired_Scheduled_Events` et `Session_Lore` postérieurs au point de fork** | ouvert — arbitrage mods 2026-09-26, mineur |
| TICKET-104| **`regenerate.py` : `.replace` d'une consigne absente** → bloc JSON stocké dans les variantes et renvoyé au LLM | ouvert — arbitrage mods 2026-09-26, mineur, reproduit |
| TICKET-105| **`_pending_correction` non remise à zéro au rewind** (indice d'un tour annulé réinjecté une fois) | ouvert — arbitrage mods 2026-09-26, mineur |
| TICKET-106| **Audit et alignement de l'encapsulation / détachement total du noyau sur l'ensemble des autres mods officiels** | ✅ résolu (2026-09-30) — tous les mods officiels contiennent leur code et se détachent totalement du noyau |

Tickets 100→106 : issus du cadrage du système de mods (`Mods/`). Tickets résolus/clos : voir `DONE.md` (**086, 087, 091, 092→098 clos le 2026-09-22** ; 001→056 sauf 017, 058→060, **071**, **072→082** (lot Hindsight, commités), **+ lot validations GUI du 2026-06-13 : 050, 062 items 1/2/4, 066, 068**).
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

**MAJ 2026-09-22 (TICKET-095).** Le fork prend désormais l'inventaire **au tour du fork** (via
`Inventory_Snapshots`) et copie ces snapshots, avec remappage cohérent des `instance_id` (le contenu
des sacs pointait avant vers des ids de la save source). Restent non copiés : Facts/Observations/
Mental_Models, `Snapshots`, `Modifier_Snapshots`.

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

**Extension (2026-09-26, arbitrage mods, rang 23).** La liste oublie aussi **`Item_Instances`** et
**`Session_Lore`** (`axiom/package.py:94-105`). La purge tourne sous `PRAGMA foreign_keys=OFF`
(`package.py:123`) : pas de cascade depuis `Saves`, ces lignes restent dans l'archive. À traiter avec
088 ; la vraie correction est le registre unique des données de save (`Mods/DOC.md` §13 phase 0c).

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

---

## TICKET-099 — Clés intégrées expirées toujours proposées

**Découvert le 2026-09-22** (mise à jour du site). `core/builtin_keys.py::BUILTIN_KEYS_ENABLED` vaut
encore `True`, alors que le pool Fireworks prépayé a expiré le 2026-06-30 (TICKET-062 item 2). Au premier
lancement, `apply_beta_defaults()` configure donc le backend `fireworks` sur des clés mortes : le premier
tour d'un nouvel utilisateur échoue au lieu d'afficher « ajoute ta clé dans les Réglages ».
La bannière du site qui annonçait ces clés a été retirée le 2026-09-22.

**Options.** (a) passer `BUILTIN_KEYS_ENABLED = False` (le commentaire du module prévoit exactement ce
cas : rien n'est supprimé, réactivable) ; (b) renouveler/recharger le pool.
**Priorité :** haute pour l'expérience d'un nouvel utilisateur — une ligne à changer une fois décidé.

---

> Tickets 100→105 : bugs trouvés par la critique du système de mods (`maintenance/Mods/CRITIQUE.md`)
> et **confirmés** par l'arbitrage (`maintenance/Mods/ARBITRAGE.md`, rangs 3/6/16/21/22/24).
> Décision utilisateur D-1 (2026-09-26) : corriger **tout de suite**, en tickets normaux, hors chantier mods.

## TICKET-100 — Rewind web/CLI : ChromaDB jamais rembobinée, doublons au rejeu

**Découvert le 2026-09-23** (critique mods §3.4, confirmé arbitrage rang 3). `Session.rewind`
(`axiom/session.py:408-437`) n'appelle jamais `VectorMemory.rollback` (`axiom/memory.py:482-501`) ;
le docstring de `CheckpointManager.rewind` laisse ça « au caller » (`checkpoint.py:62-63`) et aucun
caller web/CLI ne le fait (`main_web.py:1815`, `main_web.py:1930` — édition de message —,
`axiom/cli/play.py:185`). Seul le chemin Qt le fait (`ui/tabletop_view.py:1012-1023`, avec backup
auto via `workers/db_tasks.py:151-178`).
**Aggravant :** `embed_chunk` identifie chaque chunk par un `uuid4` (`axiom/memory.py:238`) → rejouer
un tour **ajoute** un second chunk au lieu de remplacer ; le RAG voit le futur annulé **et** le nouveau.

**Piste.** `Session.rewind` appelle `VectorMemory.rollback` (et idéalement le backup auto) → le chemin
Qt n'a plus à le faire lui-même (un seul rewind). Ids de chunks déterministes (ex. `save:turn:idx`)
pour que le rejeu écrase. Préfigure le point d'entrée unique de `Mods/DOC.md` §13 phase 0c.
**Priorité :** haute — touche tous les joueurs web/CLI aujourd'hui.

---

## TICKET-101 — Tour échoué ou annulé : `user_input` orphelin + `turn_id` décalé

**Découvert le 2026-09-23** (critique §3.2), **reproduit en exécution** par l'arbitrage (rang 6) avec un
faux LLM levant `LLMConnectionError` : après l'échec, `turn_id == 1`, l'`Event_Log` contient
`(1, 'user_input')` sans narration, `_load_history()` renvoie le message joueur seul.
**Cause :** `self._turn_id += 1` **avant** `process_turn` (`axiom/session.py:209`) ; l'intent est
commité avant l'appel LLM (`axiom/arbitrator.py:230-236`) ; l'intent pool est vidé (`session.py:212-213`).
Même chemin pour `GenerationCancelled` (bouton stop). Au tour suivant, deux messages joueur d'affilée
partent au LLM. Touche Qt, web et CLI (tous passent par `Session`).

**Piste.** En cas d'échec/annulation : restaurer `_turn_id`, supprimer les events du tour avorté (ou
ne les commiter qu'après le LLM, via le tampon `_pending_events` déjà présent), remettre l'intent dans
le pool. Préfigure le tour transactionnel (`Mods/DOC.md` phase 0d).
**Priorité :** haute.

---

## TICKET-102 — Job mémoire living web sans verrou (course avec le rewind)

**Découvert le 2026-09-23** (critique §3.9, arbitrage rang 16 : **probable**, non reproduit — course).
Le job living web est un `threading.Thread` daemon (`main_web.py:2751`) qui lit `turn`, appelle le LLM
(plusieurs secondes) puis écrit Facts/Observations **sans `ACTIVE_SESSION_LOCK`**
(`main_web.py:2685-2745`). Un rewind pendant ce délai laisse des faits pour des tours annulés, puis des
doublons au rejeu. (Sans rapport avec TICKET-083, contrairement à ce que disait la critique.)

**Piste.** « Époque » de session : le job capture un compteur incrémenté à chaque rewind/fork/
chargement et **refuse d'écrire** s'il a changé (`Mods/DOC.md` §10.4). Vérifier aussi le chemin Qt
(`workers/fact_worker.py`).
**Priorité :** moyenne.

---

## TICKET-103 — `fork_save --turn` copie des données postérieures au point de fork

**Découvert le 2026-09-23** (critique §3.6, confirmé arbitrage rang 21). `axiom/saves.py:947-957`
copie tous les `Fired_Scheduled_Events` sans filtrer `fired_turn_id <= turn_id` (la colonne existe
pour ça, TICKET-075 ; le rewind filtre bien, `checkpoint.py:148-151`). Même défaut pour
`Session_Lore` (copie sans filtre sur `origin_turn`, `saves.py:920-930`). Accessible via
`axiom saves fork --turn N` (`axiom/cli/saves_cmd.py:234`) ; `duplicate_save` forke sans point, pas
d'effet. (Les modifiers copiés « as-is » sont un choix documenté, `saves.py:856`, rattaché à 088.)

**Piste.** Ajouter les deux filtres. **Priorité :** basse.

---

## TICKET-104 — `regenerate.py` : remplacement de consigne sans effet

**Découvert le 2026-09-23** (critique §3.11), **reproduit** par l'arbitrage (rang 22) :
`build_narrative_prompt` ne contient pas la chaîne `"You MUST end your response with a JSON block"`
(la consigne réelle est le bloc `~~~json`, `axiom/prompts.py:57`) → le `.replace` de
`axiom/regenerate.py:73-79` ne fait rien. Le texte régénéré, **JSON compris**, est stocké tel quel
(`regenerate.py:103`) ; masqué à l'affichage (Qt `ui/widgets/chat_display.py:84`, web
`web/app.js:1516`) mais **renvoyé au LLM** dans l'historique (`regenerate.py:36`, `Session._load_history`).
Note : la régénération se fait aussi sans stats, RAG ni lore (`regenerate.py:60-70`).

**Piste.** Cibler la vraie consigne (ou construire le prompt sans le bloc JSON) et retirer tout bloc
JSON du texte avant `append_variant`. **Priorité :** basse-moyenne.

---

## TICKET-105 — `_pending_correction` non remise à zéro au rewind

**Découvert le 2026-09-23** (critique §3.3, confirmé arbitrage rang 24). L'indice « l'action a échoué »
vit sur `self._pending_correction` (`axiom/arbitrator.py:152,450,465,1731-1734`). Au rewind,
`Session.rewind` appelle `invalidate_stats_cache` (`session.py:415`), qui ne le touche pas
(`arbitrator.py:166-176`) → un indice issu d'un tour annulé peut être injecté une fois.

**Piste.** Remettre à `None` au rewind (et au chargement de save). **Priorité :** basse.

---

## TICKET-106 — Audit et alignement de l'encapsulation / détachement total du noyau sur l'ensemble des autres mods officiels

**Besoin identifié le 2026-09-30** (clarification utilisateur lors du chantier `feature-help-system-mod`) :
Un mod officiel ne doit pas seulement masquer des éléments d'interface via un toggle ou des conditions `if is_mod_enabled(...)` dans le code du noyau.
Le mod doit **contenir** l'intégralité de son code fonctionnel, et sa désactivation doit signifier le **détachement total** du code du noyau (zero overhead, aucun listener ou hook résiduel sur l'application hôte).

**État :** ✅ **RÉSOLU (2026-09-30)**
- `axiom.sillytavern` : suppression du fallback doublon dans `core/st_parser.py`, délégation stricte au mod.
- `axiom.illustrations` : implémentation canonique `ImageGenerator` transférée dans `mods/axiom.illustrations/image_generator.py`.
- `axiom.inventory` : implémentation canonique déplacée dans `mods/axiom.inventory/inventory.py`.
- `axiom.time` : calendrier et dynamique diegétique déplacés dans `mods/axiom.time/time_system.py`.
- `core.stat_dynamics` : dynamique des statistiques déplacée dans `mods/core.stat_dynamics/stat_dynamics.py`.
- `axiom.living_memory` : accumulateur cognitif déplacé dans `mods/axiom.living_memory/living_memory.py`.
- Shims de rétrocompatibilité dans `axiom/` utilisant des imports dynamiques `importlib` (étanchéité headless `check_headless` validée à 0 violation).
- Archives `.axmod` et SHA-256 synchronisés dans `dist/mods/store_index.json`.
- Suivi et documentation : `maintenance/Mods/audit-and-fix-mods-decoupling/`.

