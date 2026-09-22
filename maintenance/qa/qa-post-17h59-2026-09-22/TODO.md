# TODO — QA des commits post-`cb9e56d` (2026-09-22)

Périmètre : les 7 commits postérieurs au dernier commit propre de 17h59 (`cb9e56d`, 2026-06-25) :
`4d11fca`, `c326aa1`, `ffc09e8`, `d491365`, `a11a554`, `cdad0ff`, `4967506`.

## Bugs signalés
- [x] GUI ne s'ouvre pas (bloqué après la ligne `qt.multimedia.ffmpeg`)
- [x] Windows : pop-up « FOREIGN KEY constraint failed » à chaque retour sur l'accueil (compile Myria)
- [x] CI rouge : `test_no_language_has_missing_keys` (6 clés ×9 langues)

## Audit
- [x] Audit moteur `axiom/` de `4967506`
- [x] Audit app/web (`ui/`, `workers/`, `main*.py`, `web/`, tests) de `4967506`
- [x] Audit `4d11fca`, `c326aa1`, `ffc09e8`, `d491365`, `a11a554` + conformité méthodo
- [x] Trier les findings : corriger ici ce qui est bloquant/évident, le reste → `PENDING.md` (TICKET-092→098)
- [x] Suite de tests complète verte
- [ ] Validation GUI par l'utilisateur (lancement, Hub, export d'univers)
