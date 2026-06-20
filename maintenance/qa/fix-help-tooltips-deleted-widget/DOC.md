# DOC — fix retranslate_tooltips sur widget C++ détruit

## Objectif
Fiabiliser `ui/help_system.py::retranslate_tooltips` face aux widgets dont l'objet C++ a été détruit
(dialogue fermé, vue démontée) alors que le wrapper Python survit encore dans le registre.

## Décision technique
Un `WeakKeyDictionary` ne suffit pas : Qt peut détruire le QObject C++ indépendamment du wrapper
Python. La parade canonique PySide est `shiboken6.isValid(obj)` : on saute et on purge ces entrées.
Appliqué aux deux registres (`_live_widgets` et `_live_tabs`).

Lié à la fiabilité de suite (TICKET-059/067) mais c'est ici un vrai durcissement **produit**, pas un
contournement de test.
