# DOC — Encapsulation et détachement total des mods

## 1. Objectif Architectural

Garantir le principe fondamental formulé par l'utilisateur :
> *« Le mod ne doit pas seulement masquer le code, le mod doit CONTENIR le code et sa désactivation veut dire le détachement total du code du noyau. »*

## 2. Principes Appliqués

1. **Localisation canonique du code :**
   - Chaque fonctionnalité modulaire a son implémentation de référence dans `mods/<mod_id>/`.
   - Aucun fallback silencieux ni copie dégradée n'est conservée dans le cœur pour « faire comme si » le mod était là.

2. **Détachement total quand désactivé :**
   - Si un mod est désactivé dans `AppConfig` (`mods_enabled`), ses hooks, slots, services et filtres d'événements ne sont jamais enregistrés.
   - Les appels directs vers une fonctionnalité de mod désactivée lèvent une erreur explicite ou retournent des sentinelles inertes sans effet de bord.

3. **Étancheité Headless & PyPI (`axiomai-engine`) :**
   - Le sous-répertoire `axiom/` constitue le moteur headless pur exportable sur PyPI.
   - Aucun import statique vers `mods`, `ui`, `web`, `workers`, `database` ou `PySide6` n'est autorisé dans `axiom/` (testé par `check_headless`).
   - Les modules de rétrocompatibilité résidant dans `axiom/` utilisent `importlib.import_module` dynamiquement, préservant la compatibilité pour les scripts externes sans violer l'indépendance structurelle du moteur.
