# TODO — TICKET-057 : enrichissement de la doc intégrée (passe 1)

La doc GUI était jugée trop succincte (note page-à-page + annuaire) ; le survol des boutons
était jugé bon. Bug structurel : dans le Creator Studio, F1 dumpait tout le Studio au lieu de
l'onglet courant.

## Fait (passe 1)
- [x] **Découpage Studio par onglet** : page `creator` (chrome + survols d'onglets) + 10 pages
      `creator_<onglet>` ; bouton « Information »/F1 **sensible à l'onglet actif** (vue + menu Aide).
- [x] **Couche de détails riches `_d`** : affichée en F1/annuaire seulement, le **survol reste court**.
- [x] **Intros de page enrichies** (exemples, comment faire, effet, pourquoi) : Hub, Setup,
      Tabletop, Settings, App, Studio (base) + les 10 sous-pages Studio.
- [x] **Détails `_d` des éléments de l'onglet Metadata** (8 : world_lore, system_prompt,
      first_message, companion, tension, llm_temp, llm_top_p, verbosity).
- [x] Tout dans les **10 langues** (couverture i18n verte, doc_check OK : 242 clés).
- [x] Renommage des clés metadata `doc_creator_*` → `doc_creator_meta_*`.
- [x] Tests : 783 verts (lot principal) ; help_system + i18n verts.

## Passes suivantes (sur feu vert) — détails `_d` élément par élément
- [ ] Onglet **Tabletop** (turn_time, verbosity, canon_auto, rewind, sidebars, mini_dico…).
- [ ] **Settings** (backends LLM/Cloud, image, chronicler, rag_chunks…).
- [ ] **Hub** et **Setup** (éléments restants).
- [ ] (Option) documenter les widgets internes des éditeurs Studio (stats/entities/map/rules…)
      pour des éléments `_d` dédiés, au-delà de l'intro de page.

⚠ Rien commité — l'utilisateur gère git.
