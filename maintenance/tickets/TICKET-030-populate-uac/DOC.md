# TICKET-030 — Populate × Universe-as-Code — DOC

Trois briques au-dessus du Populate existant, pour un **univers-dossier** (le texte = vérité) :

1. **Populate ciblé + prévisualisation** : le Populate tourne dans une **sandbox** (copie
   temporaire du `.db` → génération LLM dessus → sync vers un arbre texte temporaire), le
   **diff** entre la source réelle et l'arbre temporaire est montré à l'utilisateur ;
   « Appliquer » = miroir de l'arbre validé vers la source + `refresh_definition` in-place.
   Rien n'est écrit tant que l'utilisateur n'a pas validé.
2. **Canonisation depuis la partie** : dans la fenêtre narrateur, « Canoniser… » envoie
   l'histoire récente au LLM qui en extrait entités/lore canon → même dialogue de diff →
   appliqué à la **source de l'univers** (pas à la save), puis la save en cours est
   resynchronisée (`refresh_save_definition`). Le toggle « Canon auto » fait pareil en
   silencieux après chaque tour — **inactif par défaut**, jamais persisté.
3. Un `.db` plat n'a pas de source : ces options exigent un univers-dossier (conversion
   proposée par l'onglet Fichiers, TICKET-029).

Notes : le diff est calculé contre une **baseline normalisée** (la source telle que la sync
db→texte l'écrirait sans la génération) — il ne montre donc que l'effet sémantique de la
génération ; appliquer normalise au passage la source, comme toute sauvegarde Studio
(TICKET-027). Annuler supprime simplement la sandbox, rien n'a été écrit.
