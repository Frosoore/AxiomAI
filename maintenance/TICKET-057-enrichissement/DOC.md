# DOC — TICKET-057 enrichissement (passe 1)

## Problème
Doc intégrée trop succincte (note F1 + annuaire) ; survol des boutons déjà bon (à préserver).
Bug structurel : le Creator Studio n'avait qu'une page d'aide → F1 dumpait tout le Studio,
metadata et stats mélangés.

## Architecture mise en place

### 1. Découpage du Studio par onglet
- `ui/help_system.py::PAGES` : la page `creator` ne garde que le chrome (save/back) + les
  **survols** d'onglets (`tab_meta`, `tab_stats`, …, courts). Les éléments de l'onglet Metadata
  passent dans une page dédiée `creator_meta`. Chaque onglet a sa page : `creator_meta`,
  `creator_stats`, `creator_entities`, `creator_map`, `creator_rules`, `creator_events`,
  `creator_setup`, `creator_lore`, `creator_populate`, `creator_files`.
- `CREATOR_TAB_PAGES` = ordre des onglets → page. `CreatorStudioView.current_doc_page()` mappe
  l'onglet actif. Le bouton « Information » reçoit un **callable** (`make_help_button` accepte
  désormais str **ou** callable, résolu au clic) ; `MainWindow._current_doc_page()` délègue à la
  vue quand on est dans le Studio (donc menu Aide → Expliquer / Documentation suivent l'onglet).

### 2. Couche de détails riches (`_d`)
- Le **corps** d'un élément (`doc_<page>_<el>`) sert AUSSI au tooltip de survol → il reste court.
- Le contenu riche (exemples, comment faire, effet, pourquoi) vit dans une clé séparée
  `doc_<page>_<el>_d`, déclarée dans `help_system.DETAILS`, rendue **seulement** en F1 et dans
  l'annuaire (`_entry_html`). Le survol n'est jamais gonflé.
- `all_doc_keys()` n'exige le `_d` que pour les refs listées dans `DETAILS` (le test « clés
  orphelines » et `tools/doc_check.py` restent cohérents).

### 3. Contenu (10 langues)
- Intros de page réécrites (riches) : hub, setup, tabletop, settings, app, creator + 10 sous-pages.
- Détails `_d` des 8 éléments de l'onglet Metadata.
- Le rendu étant HTML (`QTextBrowser`), le contenu utilise `<b>`, `<br/>` (pas de guillemets
  doubles → pas d'échappement TOML).

### Correctif au passage
`help_dialogs._apply_filter` masquait les pages **sans éléments** quand la recherche était vide
(révélé par les nouvelles sous-pages vides). Corrigé : une page reste visible si la recherche est
vide ou si son titre/intro correspond.

## Fichiers
- Code : `ui/help_system.py`, `ui/help_dialogs.py`, `ui/creator_studio_view.py`, `ui/main_window.py`.
- Contenu : `core/locales/*.toml` (10).

## Reste (passes suivantes)
Détails `_d` élément par élément pour Tabletop, Settings, Hub, Setup ; option : documenter les
widgets internes des éditeurs Studio. Voir TODO.md.
