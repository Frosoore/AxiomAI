# TODO — Étape : Feature SillyTavern en Mod

> Référence : `maintenance/Mods/DOC.md` & Demande utilisateur du 2026-09-30.
> Objectif : Transformer le bouton et la fonctionnalité d'importation de cartes SillyTavern en mod activable/désactivable (`axiom.sillytavern`), avec traductions complètes dans les 10 langues d'Axiom AI pour tous les mods.

## Tâches

- [x] 1. Créer le mod officiel `axiom.sillytavern` dans `mods/axiom.sillytavern/` (`mod.toml`, `main.py`).
- [x] 2. Fournir les fichiers de localisation pour `axiom.sillytavern` dans les 10 langues (`en`, `fr`, `de`, `es`, `it`, `ja`, `ko`, `pt`, `ru`, `zh`).
- [x] 3. Compléter les traductions des autres mods (`community.survival`) pour garantir que 100 % des mods disposent des 10 langues.
- [x] 4. Câbler la visibilité dynamique du bouton « Import SillyTavern » dans l'UI Qt (`ui/hub_view.py` et `mods/axiom.ui.qt/ui/hub_view.py`) selon l'état du mod (`is_mod_enabled`).
- [x] 5. Câbler la gestion dans l'UI Web (`main_web.py` et `web/app.js`) : masquage du bouton si désactivé et blocage de l'API `/api/universes/import-st` si le mod est inactif.
- [x] 6. Mettre à jour l'index du store local (`dist/mods/store_index.json`).
- [x] 7. Créer une suite de tests automatisés dédiée (`tests/test_sillytavern_mod.py`).
- [x] 8. Exécuter la suite de tests et vérifier le passage à 100 % vert.
