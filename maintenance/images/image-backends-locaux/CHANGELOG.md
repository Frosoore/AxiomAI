# Changelog — Fiabiliser les backends d'images locaux

## 2026-06-11 — workflow ComfyUI par défaut invalide

Erreurs réelles côté utilisateur au premier essai ComfyUI :
`Value not in list: ckpt_name: 'v1-5-pruned-emaonly.ckpt'` + `VAEDecode: Required
input is missing: samples`.

- `axiom/image_generator.py` :
  - Workflow par défaut : entrée du nœud VAEDecode renommée `latent_image` → **`samples`**
    (nom réellement attendu par ComfyUI ; l'ancien nom rendait le template invalide partout).
  - **Checkpoint auto-résolu** : `_comfyui_available_checkpoints()` interroge
    `GET /object_info/CheckpointLoaderSimple` ; tout nœud `CheckpointLoaderSimple` du
    workflow (défaut OU custom) pointant vers un checkpoint absent du serveur est basculé
    sur le 1ᵉʳ checkpoint installé (log INFO). `/object_info` injoignable → workflow envoyé
    tel quel.
  - **Rejet 400 de `/prompt`** (validation ComfyUI) : warning détaillé (message + erreurs
    nœud par nœud) au lieu d'un échec générique, retour None (TICKET-045).
- Tests (`test_image_generator.py`, +3 → 18) : checkpoint substitué + entrée `samples`
  vérifiés sur le test de succès ; `/object_info` en échec → workflow intact ; 400 → None
  sans exception. Mocks existants adaptés au GET supplémentaire.

### Validation

- Suites : image_generator 18 ✅, suite large 525 ✅ (21 échecs préexistants = TICKET-049),
  lot Qt/vector 56 ✅.
- ⚠ Test réel ComfyUI à refaire par l'utilisateur (le checkpoint `ilustmix_v111.safetensors`
  doit être sélectionné automatiquement).

## 2026-06-10

- **Cause racine du « SD ne marche pas »** : reForge tournait sans `--api` → 404 sur
  `/sdapi/v1/txt2img`. Fix permanent hors repo : `COMMANDLINE_ARGS="--api"` décommenté dans
  `~/stable-diffusion-webui-reForge/webui-user.sh` (redémarrage de reForge requis).
- `axiom/config.py` : + `image_timeout: int = 180` (secondes, partagé SD/ComfyUI).
- `axiom/image_generator.py` :
  - SD : `timeout=max(10, image_timeout)` au lieu de 30 s en dur ; **404 détecté avant
    `raise_for_status`** → warning explicite « lancé sans --api » + None ;
    `requests.exceptions.Timeout` → warning « augmentez le délai » distinct.
  - ComfyUI : polling `range(timeout_s)` (1 poll/s) au lieu de 60 itérations fixes ;
    message de timeout actionnable.
- `ui/settings_dialog.py` : + spinbox « Délai max par image » (10–900 s, pas de 10, suffixe
  « s ») dans l'onglet Illustration (load/collect/retranslate).
- `axiom/localization.py` : + clé `image_timeout` (en + fr).
- Tests : +4 (`test_image_generator.py` : timeout par défaut transmis, timeout custom,
  404 → None sans lever, polling ComfyUI borné via `time.sleep` mocké ;
  `test_settings_dialog.py` étendu au nouveau champ).

### Validation

- Test **réel** du chemin 404 contre le reForge en cours d'exécution : warning explicite,
  retour None. ✅
- Suites : image_generator 16 ✅, settings_dialog 2 ✅, chat_buffer 5 ✅, suite large 523 ✅,
  lot Qt/vector 56 ✅ (21 échecs préexistants = TICKET-049, Python 3.12).
- ⚠ Test end-to-end (vraie image dans le chat) en attente du redémarrage de reForge par
  l'utilisateur.
