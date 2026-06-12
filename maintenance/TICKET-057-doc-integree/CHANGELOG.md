# CHANGELOG — TICKET-057 : doc intégrée à l'app

## 2026-06-12 — démarrage

- Dossier d'étape créé ; tickets 053/054/055/056/058/060 archivés dans `DONE.md` au préalable.

## 2026-06-12 — implémentation des 4 briques (session interrompue faute de tokens)

- **Registre central** `ui/help_system.py` : dict déclaratif `PAGES` (6 pages, 208 éléments),
  1 élément = 2 clés i18n (`doc_<page>_<el>_t` titre + `doc_<page>_<el>` explication).
  Helpers `doc(widget, "page.el")` / `doc_tab(tabw, idx, "page.el")` : posent le tooltip
  (suivi par `weakref` → `retranslate_tooltips()` au changement de langue) et alimentent
  les dialogues.
- **Brique 1 — tooltips** : `doc()` câblé dans toutes les vues (`hub_view`, `setup_view`,
  `tabletop_view`, `creator_studio_view`, `settings_dialog`, `main_window`,
  `mini_dico_panel`, `constants_sidebar`, `widgets/chat_display`, `widgets/universe_card`).
- **Brique 2 — « expliquer cette page »** : `ui/help_dialogs.ExplainPageDialog` (liste
  titre+texte des éléments de la page courante), bouton « ? » par page
  (`make_help_button`) + raccourci F1 + entrée menu Aide.
- **Brique 3 — quick tour** : `QuickTourDialog` (étapes Précédent/Suivant/Passer), lancé au
  premier démarrage (`SETTINGS_FILE` absent — remplace l'ancienne welcome box), relançable
  via Aide → Visite rapide.
- **Brique 4 — annuaire** : `DocDirectoryDialog` (menu Aide → Documentation), recherche
  plein texte titre+explication, groupé par page, s'ouvre sur la page courante.
- **i18n** : ~242 clés ajoutées par langue (210 `doc_*` + chrome menus/tour) dans les
  **10 langues** (`core/locales/*.toml`), EN référence → FR → es de it pt ru zh ja ko.
- **Outillage** : `tools/doc_check.py` (éléments du registre sans clé EN / clés `doc_*`
  orphelines, page par page) ; `tests/test_help_system.py` (16 tests : registre cohérent,
  clés ×10 langues, helpers, contenu tour).

## 2026-06-12 — reprise et clôture (cette session)

- État des lieux : contrairement au souvenir de fin de session précédente (« arrêté au
  coréen »), les 10 langues étaient **complètes** — `tools/i18n_check.py` 515/515 partout,
  `tools/doc_check.py` OK, traduction ko vérifiée à la main (rien en anglais résiduel).
- **Fuites de traduction préexistantes** (restes du complètement de masse TICKET-053,
  détectées par balayage valeurs≡EN + valeurs latines en langues non latines +
  contamination inter-langues) corrigées :
  - `chronicler_interval_label` : « Intervallo del Cronista (turnos): » (mélange
    italien/espagnol) copié-collé dans **it/pt/ru/zh/ja/ko** → retraduit par langue
    (terminologie alignée sur `doc_settings_chronicler` : Cronista/Хронист/编年史官/
    年代記係/연대기 작성자) ; « (tours) » français en it → « (turni) ».
  - `univ_params` : resté « Universe Parameters » en **de/it/pt/ru/zh/ja/ko** → traduit
    (aligné sur `doc_settings_tab_params_t` existant).
  - `image_api_url` ko : « API URL: » → « API 주소: » (cohérent avec `doc_settings_base_url`).
  - Restes ≡EN jugés légitimes (non touchés) : noms propres/termes techniques
    (Creator Studio, Timekeeper, LLM Top P, UI en ja/ko, Backend: en de…).
- **Validation** : `i18n_check` 10/10 OK, `doc_check` OK, suite principale **581 verts**
  (hors lot Qt/vector) + lot Qt/vector (`test_vector_*`, `test_phase6`,
  `test_ambiance_manager`) **56 verts** = 637, 0 échec.

### Reste

- ⚠ Validation GUI réelle par l'utilisateur ; commit sur feu vert.

## 2026-06-12 — retours utilisateur : toggle des tooltips + trous i18n

- **Toggle « bulles d'aide au survol »** (demande utilisateur) :
  - `axiom/config.py` : champ `doc_tooltips_enabled` (défaut `True`).
  - `ui/help_system.py` : `tooltips_enabled()` + `install_tooltip_gate(app)` — filtre
    d'événements applicatif qui avale les `QEvent.ToolTip` des widgets/onglets enregistrés
    par `doc()`/`doc_tab()` quand l'option est décochée. Les tooltips restent posés sur les
    widgets (audit de couverture, dialogues et retranslation inchangés) : seul l'affichage
    au survol est coupé, donc effet immédiat dans les deux sens, et les tooltips hors doc
    (boutons « ? »…) ne sont pas affectés. Installé dans `MainWindow.__init__`.
  - `ui/settings_dialog.py` : case « Bulles d'aide au survol » (section Général), doc'ée
    (`settings.doc_tooltips`), load/collect/retranslate branchés.
- **Bug i18n signalé** (setup → Persona : « Nom de la sauvegarde »/« Difficulté » restaient
  en français en langue anglaise) : ces labels étaient posés à la construction et jamais
  retraduits. `ui/setup_view.py` : labels du formulaire (refs gardées), onglet Persona
  (tabText(1) manquait), libellé « Select your Persona », bouton « Add a Persona + » et items
  du combo Difficulté (retraduits par itemData, sélection/companion préservés) ajoutés à
  `retranslate_ui` ; dialogue de création de persona (titre + placeholders) passé sous `tr()`.
- **Autres chaînes en dur corrigées au passage** : labels « LLM Temperature/Top P » du Studio
  (clés existantes non utilisées), « Loading Universe... » de la loading view
  (clé `loading_universe` existante).
- **i18n** : 9 nouvelles clés ×10 langues (persona ×6, `show_doc_tooltips` —
  renommée pour échapper au test anti-orphelins `doc_*` —, `doc_settings_doc_tooltips_t/-`).
  Restes en dur dans les éditeurs internes du Studio → **TICKET-061** (PENDING).
- **Tests** : +6 (gate activé/désactivé/non-doc/tab bars, lecture config, round-trip du
  toggle dans le dialogue, rétranslation de l'onglet Persona en→fr). Vérifs : `i18n_check`
  10/10 (524/524), `doc_check` OK, suites **587 + 56 = 643 verts, 0 échec**.
