# CHANGELOG — TICKET-057 enrichissement (passe 1)

## 2026-06-15
- **Découpage du Creator Studio par onglet** (bug structurel signalé) : F1/« Information » suit
  désormais l'onglet actif (Metadata, Stats, Règles… ont chacun leur page). `make_help_button`
  accepte un callable ; `CreatorStudioView.current_doc_page()` + `CREATOR_TAB_PAGES` ;
  `MainWindow._current_doc_page()` délègue à la vue dans le Studio. Registre `PAGES` restructuré :
  base `creator` (chrome + survols d'onglets) + 10 pages `creator_<onglet>`. Refs metadata
  renommées `creator.*` → `creator_meta.*` (9 refs vue, 16 clés i18n × 10 langues).
- **Couche de détails riches `_d`** : `help_system.DETAILS` + `details_key()`/`has_details()` ;
  `_entry_html` rend le `_d` en F1/annuaire ; le **tooltip de survol reste court** (vérifié : les
  détails ne fuient pas dans le hover). `all_doc_keys()` n'exige `_d` que pour les refs déclarées.
- **Contenu enrichi (10 langues)** : 6 intros de page réécrites (Hub, Setup, Tabletop, Settings,
  App, Studio base) + 10 sous-pages Studio (titre + intro riche : exemples, comment faire, effet,
  pourquoi) + 8 détails `_d` des éléments Metadata. 34 clés × 10 langues (340 chaînes), via 2
  scripts d'application idempotents (supprimés après usage).
- **Correctif** `help_dialogs._apply_filter` : les pages sans élément (nouvelles sous-pages vides)
  étaient masquées quand la recherche était vide → corrigé.
- **Vérifs** : `tools/doc_check.py` OK (242 clés alignées) ; couverture i18n verte ; rendu HTML
  confirmé (F1 riche, survol court, sous-page vide = intro seule) ; **783 tests verts** (lot
  principal) + help_system/i18n.

⚠ Rien commité — l'utilisateur gère git. Passe 1 d'un chantier en plusieurs passes (cf. TODO.md
pour les détails élément par élément Tabletop/Settings/Hub/Setup à venir).
