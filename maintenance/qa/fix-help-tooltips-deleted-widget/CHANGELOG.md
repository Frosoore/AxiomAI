# CHANGELOG — fix retranslate_tooltips sur widget C++ détruit (2026-06-21)

## Contexte
CI Python 3.12 rouge : `tests/test_help_system.py::TestTooltips::test_retranslate_follows_language`
→ `RuntimeError: libshiboken: Internal C++ object (PySide6.QtWidgets.QLabel) already deleted.`
Vert en local, rouge en CI = **dépendant de l'ordre des tests** : un test précédent enregistre un
widget (QLabel) via `help_system.doc()`, son objet C++ est détruit mais le wrapper Python survit dans
`_live_widgets` (un `WeakKeyDictionary` ne capte pas ce cas). `retranslate_tooltips()` itère alors sur
un widget mort → `setToolTip` lève.

## Bug (produit, pas que test)
`ui/help_system.py::retranslate_tooltips` n'avait aucune garde contre un objet C++ détruit côté widgets
(et la boucle des onglets ne gardait que le cas weakref mort). Le bug frapperait aussi l'app réelle :
fermer un dialogue documenté puis changer de langue.

## Correctif
`retranslate_tooltips()` saute et purge les widgets/onglets dont `shiboken6.isValid()` est faux
(pruning de `_live_widgets`, skip des onglets invalides). Reproduit puis vérifié :
`shiboken6.delete(widget)` + `retranslate_tooltips()` → plus de crash, entrée stale retirée.

## Vérif
- `tests/test_help_system.py` → 21 verts.
- Suite large (hors 4 fichiers segfault torch/Qt local) → **882 verts**.
