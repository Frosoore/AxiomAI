# TODO — TICKET-057 : doc intégrée à l'app GUI

Décisions utilisateur (2026-06-12, cf. mémoire project-doc-chantier) : 4 briques conçues et
livrées « tout d'un bloc », traduites dans les 10 langues via `core/localization.py`.

- [x] Exploration UI : inventaire des pages/éléments à documenter
- [x] Architecture : registre central de doc (`ui/help_system.py`, pas `doc_registry.py` —
      nom final) — élément = clé i18n (titre + explication), helper `doc()`/`doc_tab()` qui
      pose le tooltip ET alimente les dialogues
- [x] Brique 1 — tooltips au survol de chaque élément (toutes les vues)
- [x] Brique 2 — bouton « expliquer cette page » par page (dialogue listant les éléments, F1)
- [x] Brique 3 — quick tour de départ (premier lancement = `SETTINGS_FILE` absent, étapes +
      skip ; remplace l'ancienne welcome box)
- [x] Brique 4 — annuaire global cherchable (menu Aide, recherche titre+texte, groupé par page)
- [x] Clés i18n : EN (référence) puis FR, puis les 8 autres langues (es de it pt ru zh ja ko)
      — 210 clés `doc_*` + chrome (menus, tour) ×10 langues
- [x] Outillage d'extension (demande utilisateur 2026-06-12) : ajouter de la doc = 1 ligne de
      registre + clés TOML ; outil `tools/doc_check.py` qui liste les éléments interactifs
      sans doc, page par page (pour étendre au fil de l'évolution de l'app)
- [x] `tools/i18n_check.py` vert (10 langues complètes, 515/515)
- [x] Tests (registre cohérent, clés présentes, logique tour/annuaire) — `tests/test_help_system.py`, 16 verts
- [x] Suites de tests existantes vertes (581 hors Qt/vector + 56 Qt/vector = 637, 0 échec)

## Hors brique, fait en chemin (2026-06-12, reprise de session)

- [x] Fuites de traduction préexistantes (restes TICKET-053) corrigées :
      `chronicler_interval_label` (italien/espagnol copié-collé dans it/pt/ru/zh/ja/ko),
      `univ_params` resté en anglais (de/it/pt/ru/zh/ja/ko), `image_api_url` ko.

## Retours utilisateur (2026-06-12, après livraison)

- [x] Toggle « bulles d'aide au survol » dans les paramètres (section Général) — config
      `doc_tooltips_enabled`, filtre d'événements `install_tooltip_gate` (ne coupe QUE les
      tooltips de doc ; ?, F1, annuaire, tour intacts ; effet immédiat sans redémarrage)
- [x] Textes non traduits signalés (setup → Persona : « Nom de la sauvegarde », « Difficulté »
      restaient dans la langue de démarrage) — labels du formulaire + onglet Persona + combo
      Difficulté ajoutés à `retranslate_ui` ; chaînes EN en dur traduites (Select your Persona,
      Add a Persona +, dialogue de création de persona, labels temp/top-p du Studio, loading
      view) ; 9 clés ×10 langues ; restes Studio → TICKET-061

## Reste

- [ ] ⚠ Validation GUI réelle par l'utilisateur (tooltips + leur toggle, F1, tour au 1ᵉʳ
      lancement, annuaire, changement de langue sur la page Persona)
