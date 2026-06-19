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
| TICKET-072| **Lore Book : recherche sémantique + link expansion** | ✅ implémenté (⚠ non commité, 2026-06-19) — `maintenance/ticket-072-lore-semantic/` |
| TICKET-073| **Focus boost RAG : noms des persos en scène** ajoutés au `focus_terms` de `memory.query` | ✅ implémenté (⚠ non commité, 2026-06-19) — `maintenance/hindsight-followups-073-076/` |
| TICKET-074| **Rewind restaure les `Active_Modifiers`** (buffs/débuffs) | ✅ implémenté (⚠ non commité, 2026-06-19, Option A snapshot par tour) — `maintenance/hindsight-followups-073-076/` |
| TICKET-075| **Rewind « dé-tire » les `Fired_Scheduled_Events`** | ✅ implémenté (⚠ non commité, 2026-06-19) — `maintenance/hindsight-followups-073-076/` |
| TICKET-076| **Résidu legacy `config.chronicler_interval` retiré** | ✅ implémenté (⚠ non commité, 2026-06-19) — `maintenance/hindsight-followups-073-076/` |

Tickets résolus/clos : voir `DONE.md` (001→056 sauf 017, 058→060, **071**, **+ lot validations GUI du 2026-06-13 : 050, 062 items 1/2/4, 066, 068**).
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

## TICKET-072 — Lore Book : recherche sémantique (vectorielle) plutôt que mots-clés SQL

**Contexte.** L'audit moteur du 2026-06-14 (étape `maintenance/audit-moteur-2026-06-14/`) a
réparé une feature morte (**B1**) : `_fetch_relevant_lore` ne renvoyait jamais rien (filtre sur une
clé `metadata.type` que `VectorMemory.query()` ne produit pas, et le lore n'était de toute façon
jamais vectorisé). Le fix retenu, **pragmatique et correct**, lit directement la table `Lore_Book`
et classe les entrées par **recouvrement de mots-clés / nom** avec l'input du tour (`axiom/
arbitrator.py::_fetch_relevant_lore`, `keywords` + filtre stopwords).

**Limite actée (retour utilisateur).** Ce match par mots-clés **ne gère ni les synonymes ni la
proximité de sens** — il faut que le mot exact (ou un mot du nom) apparaisse. Pour la **narration**,
une recherche **sémantique** (« le héros parle de trahison » doit ramener la lore sur les complots
même sans le mot « trahison ») est nettement supérieure. « Pour le moment ça passe », mais c'est la
bonne cible.

**Ce qui serait à faire.**
- **Vectoriser les entrées `Lore_Book`** dans le store du save avec `chunk_type="lore"` et des
  métadonnées exploitables (`category`, `name`), p. ex. à la création de la save / au 1ᵉʳ tour, de
  façon idempotente (et resync au refresh de définition / hot reload).
- **Récupérer par similarité** : soit une requête vectorielle dédiée filtrée `chunk_type="lore"`,
  soit fusionner avec la requête narrative existante en **exposant `chunk_type` dans le retour de
  `VectorMemory.query()`** (aujourd'hui il renvoie `text/turn_id/chunk_type/distance/score` mais les
  consommateurs filtrent un `metadata.type` inexistant — corriger cette incohérence au passage).
- **Garder un repli mots-clés** (l'implémentation SQL actuelle) quand l'embedding est indisponible
  (cf. dégradation gracieuse `VectorMemory._disabled` sous Windows sans VC++, TICKET-070) — le lore
  ne doit jamais disparaître faute de torch.

**Points d'attention.**
- **Duplication par save** : la lore est universe-level mais le store vectoriel est par save_id →
  ré-embarquer la lore pour chaque save. Acceptable (petits volumes) mais à acter.
- **Coût** : une requête vectorielle de plus par tour (ou fusionnée avec l'existante). L'audit avait
  justement *supprimé* la requête lore gaspillée ; n'en ré-introduire une que si elle sert vraiment.
- Tests existants de garde : `tests/test_arbitrator.py::TestLoreBookRetrieval` (à faire évoluer vers
  l'assertion sémantique le jour J).

**Priorité :** moyenne — amélioration de qualité narrative, pas un bug (la feature marche). Lié à
[[B1]] de l'audit moteur et à la couche `axiom/memory.py`.

---

## TICKET-074 — Rewind n'annule pas les `Active_Modifiers`

**Découvert le 2026-06-18** en investiguant le rapport temps causal ↔ tours (avant Phase 3 Hindsight).

`checkpoint.rewind` supprime tout ce qui a `turn_id > N` : `Event_Log`, `Snapshots`, `Timeline`,
`Facts`, puis reconstruit le `State_Cache`. Mais la table **`Active_Modifiers`** (buffs/débuffs
temporaires) **n'a pas de colonne `turn_id`** — elle est clé par `modifier_id` et décomptée en
`minutes_remaining` (`axiom/modifiers.py::tick_modifiers`). Le rewind **ne la touche pas** : après un
rembobinage, un modificateur posé *après* le tour N reste présent (ou un modificateur qui aurait dû
être encore actif au tour N a déjà été décompté/supprimé). L'overlay de stats est recalculé via
`rebuild_state_cache`, mais l'**état du buffer de modifiers lui-même** n'est pas rétabli au tour N.

**Pistes.** Soit ajouter une colonne `turn_id` (ou `applied_turn_id`) aux `Active_Modifiers` et les
purger/rejouer au rewind comme le reste ; soit reconstruire la table à partir des events modifiers du
`Event_Log` survivants (si les poses de modifiers sont event-sourcées). À croiser avec
`rebuild_state_cache`.

**Priorité :** moyenne — incohérence de rewind dans un cas de bord (buffs temporaires + rembobinage).
Indépendant des Phases Hindsight (qui restent strictement turn-keyed).

---

## TICKET-075 — Rewind ne « dé-tire » pas les `Fired_Scheduled_Events`

**Découvert le 2026-06-18** (même investigation que TICKET-074).

Les événements programmés se déclenchent à une minute-cible absolue ; une fois tirés, ils sont
marqués dans **`Fired_Scheduled_Events`**, clé `(save_id, event_id)` — **sans `turn_id`**.
`checkpoint.rewind` ne purge pas cette table. Conséquence : un événement programmé tiré à la minute
500, si on rembobine à un tour antérieur (horloge ramenée sous 500), **reste marqué tiré** et ne se
redéclenchera pas, alors que côté monde le temps n'a « pas encore » atteint sa minute.

**Pistes.** Enregistrer le `turn_id` (ou la `in_game_time`) de déclenchement dans
`Fired_Scheduled_Events` et purger au rewind les lignes dont le déclenchement est postérieur au tour
cible. Vérifier le sens voulu : un saut temporel re-traversé doit-il refaire l'événement ?

**Priorité :** moyenne — incohérence de rewind sur les événements programmés.

---

## TICKET-076 — Résidu legacy `config.chronicler_interval` (tours) vs `chronicler_minutes_interval` (minutes)

**Découvert le 2026-06-18** (même investigation). `AppConfig` porte **deux** champs Chronicler :
- `chronicler_interval` (en **tours**) — **LEGACY**, plus utilisé pour le déclenchement depuis
  TICKET-018 ; conservé pour rétro-compat des vieux settings, et `collect_config` le préserve tel quel.
- `chronicler_minutes_interval` (en **minutes**) — le vrai déclencheur (`ChroniclerEngine.should_trigger`
  franchit un palier de minutes de jeu).

Le champ mort entretient l'impression qu'il existe « deux systèmes de temps » (tours vs minutes) alors
qu'il n'y en a qu'un (Timeline = un pont `turn_id ↔ in_game_time`). À **retirer** (ou commenter
clairement comme purement historique) après un grep confirmant qu'aucun chemin de déclenchement ne le
lit plus. Attention à la migration des settings existants (ne pas casser le chargement).

**Priorité :** basse — nettoyage/clarté, pas un bug fonctionnel.
