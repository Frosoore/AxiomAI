# CHANGELOG — TICKET-060

## 2026-06-12

- `axiom/__init__.py` : `_HELP_TEXT` (le guide `axiom.help` embarqué dans le wheel) traduit
  FR→EN, exemples inclus (« MyWorld.db », « I open the tavern door. ») ; docstrings du module
  et de `_Help` traduits aussi. Commentaires internes laissés en FR (règle TICKET-055/056).
- Ajout d'une ligne « Documentation: https://frosoore.github.io/AxiomAI/ » en pied de guide
  (le site du TICKET-058).
- Tests : `tests/test_packaging.py` 15 passed (aucune assertion sur le texte français).
