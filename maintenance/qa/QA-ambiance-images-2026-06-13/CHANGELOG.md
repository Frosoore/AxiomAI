# CHANGELOG — QA Ambiance / Images (2026-06-13)

## Session 1

### Point 1 — lenteur d'affichage des images (1ᵉʳ diagnostic, corrigé ci-dessous)
Premier diagnostic (génération à la demande) **invalidé** par l'utilisateur : les
images préexistaient dans le message de départ (save SillyTavern importée), rien
n'était généré. Vraie cause : ce sont des **URLs HTTP** dans le `first_mes` (le
parser `core/st_parser.py` ne télécharge pas les images), refetchées par le réseau
via `_RichTextBrowser._async_fetch`. Le « ça marche au retour » venait du cache
mémoire de session (`_image_cache`) ; il n'y avait **aucun cache disque
persistant** → re-téléchargement à chaque lancement.

### Point 1 — correctifs (Session 2)
`ui/widgets/chat_display.py::_RichTextBrowser` :
- **`QNetworkDiskCache` persistant** branché sur le `QNetworkAccessManager`
  (`paths.get_app_cache_dir()/image_cache`). Les images distantes sont
  téléchargées une fois puis servies du disque, y compris **entre les lancements**.
- Placeholder de chargement **visible** : remplacé le pixel transparent 1×1 par un
  cadre 16:9 sombre (`#23272E`, 640×360) → l'utilisateur voit un emplacement « en
  cours » au lieu d'un blanc qui pop soudain.

### Vignette « génération en cours… » (images générées par le cloud)
- `axiom/session.py` : la chaîne de statut extraite en constante
  `IMAGE_GEN_STATUS` (évite un match de chaîne fragile côté UI).
- `ui/widgets/chat_display.py` : `show_image_placeholder()` /
  `clear_image_placeholder()` (vignette inline « 🖼 {generating_image} »).
  Suppression par **plage explicite [start, end]** car le flush final du buffer de
  tokens peut insérer du texte narratif après la vignette. `append_image()` retire
  d'abord toute vignette en attente.
- `ui/tabletop_view.py` : 2ᵉ connexion de `status_update` → `_on_turn_status`
  (affiche la vignette quand le statut == `IMAGE_GEN_STATUS`) ; `_on_turn_complete`
  retire la vignette si aucune image n'a été produite (sinon `append_image` la
  remplace).
- i18n : clé `generating_image` ajoutée aux **10 langues** (i18n-check : 548/548 OK).

### Point 2 + 3 — ambiance trompeuse + bruit console (correctifs)
`ui/ambiance_manager.py` :
- `update_ambiance()` renvoie désormais `bool` (True seulement si une piste a
  réellement démarré). False si désactivé, tag inchangé, ou aucun asset audio.
- Les 3 `print("[AMBIANCE] ...")` → `logger.debug(...)` (`from axiom.logger import
  logger`). La console du logger est en INFO → plus rien dans le shell ;
  l'info reste dans le fichier de log pour le diagnostic.

`ui/main_window.py::update_audio_ambiance` :
- Le message de statut « Ambiance: <tag> (fading...) » n'est affiché que si
  `update_ambiance()` a renvoyé True (piste réellement lancée). Sans asset audio,
  plus aucun message trompeur.

### Tests
`tests/test_ambiance_manager.py` : +2 tests (retour False sans asset / désactivé /
tag inchangé). `tests/test_chat_buffer.py` : +3 tests (vignette affichée/retirée,
texte flushé après la vignette préservé, `append_image` retire la vignette en
attente). Lots CI : **748 passed** (sans ambiance) + **7 passed** (ambiance isolé).
i18n 548/548 ×10. Le segfault de la suite *complète* en un seul process est le
problème Qt-multimedia préexistant (TICKET-067) — d'où l'isolement CI.

## Session 3 — vérité terrain + REVERT du cache/placeholder

Inspection directe de la save (`~/AxiomAI/saves/ST_Aglae/save_*.db`,
`Event_Log`) : les images du message de départ sont **11 liens markdown
`![](https://cdn.imgchest.com/files/*.png)`** — externes, ~1,4 Mo chacun
(1024×1024), **~15 Mo au total**, derrière Cloudflare. Elles ne sont PAS dans la
carte ; l'auteur SillyTavern les a hébergées dehors. La lenteur = les 15 Mo à
télécharger ; le « OK au retour » = cache mémoire de session.

Tentative session 2 (cache disque + placeholder gris) : le cache fonctionnait
(11 Mo stockés) mais n'aide qu'aux ouvertures *suivantes* ; le placeholder gris a
**empiré le ressenti** (11 gros cadres + 1 relayout complet par image). **Choix
utilisateur : tout annuler côté images.**

REVERT (`ui/widgets/chat_display.py`) : suppression du `QNetworkDiskCache` et
retour au placeholder transparent 1×1 d'origine. Le chemin de chargement des
images web (`loadResource`/`_async_fetch`/`_on_fetch_finished`) est **identique à
l'avant-session**. Dossier `~/.cache/AxiomAI/image_cache` (créé par le code retiré)
supprimé.

**CONSERVÉ** : la vignette « génération en cours… » (images GÉNÉRÉES par le cloud,
demande explicite) — `IMAGE_GEN_STATUS`, `show/clear_image_placeholder`,
`_on_turn_status`, clé `generating_image` ×10 — et les correctifs ambiance
(points 2 & 3), non concernés par le revert.

**Piste non retenue (proposée, refusée pour l'instant)** : télécharger les images
externes une fois dans la save (→ locales, instantanées, hors-ligne). À ré-évaluer
si le sujet revient.

### Note
L'app est livrée sans dossier `assets/audio/` : le système d'ambiance reste
dormant tant qu'aucune piste n'est ajoutée. Ajouter des `.mp3/.ogg/.wav` sous
`assets/audio/<tag>/` (ex. `exploration`, `combat`) réactive automatiquement le
cross-fade et le message de statut.
