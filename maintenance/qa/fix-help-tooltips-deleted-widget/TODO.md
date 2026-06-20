# TODO — fix retranslate_tooltips sur widget C++ détruit

- [x] Reproduire le crash (`shiboken6.delete` + `retranslate_tooltips`).
- [x] Garder `retranslate_tooltips` avec `shiboken6.isValid` + purge des entrées mortes.
- [x] Vérifier `test_help_system` (21) + suite large (882).
- [x] Ligne `AXIOM_STATUS.md`.
