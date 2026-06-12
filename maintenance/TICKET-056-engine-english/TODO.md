# TODO — TICKET-056 : messages user-facing du moteur en anglais

Suite de TICKET-055. Le moteur publié (`axiomai-engine`) doit dire **en anglais** tout ce qu'il
expose à l'utilisateur. Périmètre : **messages d'exception** + **events** (`axiom dev`) + statuts
surfacés. **Pas** les commentaires/docstrings internes, **pas** les logs `logger.*` (chantier à part).
Attention : le français **sans accent** (« invalide », « introuvable », « impossible ») échappe au
grep d'accents → se baser sur la liste exhaustive des `raise`.

## Exceptions à traduire (FR → EN)
- [x] `compile.py` (6), `decompile.py` (1), `dev.py` (1 raise)
- [x] `library.py` (4), `package.py` (6)
- [x] `saves.py` (« Sauvegarde introuvable » ×3 + 4 autres), `savestore.py` (6 + 2e ligne « force »)
- [x] `backends/gemini.py` (message d'exception quota mixte FR/EN)
- [x] Déjà EN (laissés) : backends/base, backends/universal, memory, modifiers, rules, schema.

## Events / statuts
- [x] `dev.py` event (compilée/rechargée) + event d'erreur « Source invalide → Invalid source ».
- [x] `populate.py` messages d'annulation/reprise surfacés.
- [x] `saves.py` libellé de journal « Save importée » → « Save imported ».

## Tests
- [x] Assertions FR mises à jour : `test_dev_hotreload`, `test_populate_resume` (×2),
      `test_generation_cancel` (match="kept"), `test_savestore` (fait en 055). Pas de suppression.

## Validation
- [x] `grep` : plus de message user-facing FR dans les `raise`/events du moteur.
- [x] Tests (offscreen) : 166 passed sur 9 suites ; 1 flaky préexistant non lié
      (`test_registre_cancel_active_generations`, threadé, OK en isolation 3/3).

## Hors périmètre (signalé, non fait)
- Logs `logger.*` du moteur (diagnostic), et français côté app `workers/` (couche localisée via i18n).
