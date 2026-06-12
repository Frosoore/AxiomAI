#!/usr/bin/env python3
"""tools/doc_check.py — audit de couverture de la doc intégrée (TICKET-057).

Deux contrôles, pensés pour étendre la doc au fil de l'évolution de l'app :

1. Registre ↔ clés i18n (statique, rapide) :
   chaque entrée de `ui/help_system.PAGES` (+ pages + étapes du tour) doit avoir
   ses deux clés (`doc_..._t` et `doc_...`) dans `core/locales/en.toml`, et
   aucune clé `doc_*` orpheline ne doit traîner dans en.toml.
   (La complétude des 9 autres langues est l'affaire de tools/i18n_check.py.)

2. Widgets sans doc (--qt, nécessite PySide6, lance Qt en offscreen) :
   construit chaque vue principale et liste les widgets interactifs qui n'ont
   pas de tooltip — c'est la liste de ce qui reste à documenter.

Usage :
    python tools/doc_check.py            # contrôle statique seul
    python tools/doc_check.py --qt       # + audit des widgets sans doc
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_registry_keys() -> int:
    """Contrôle 1 : registre ↔ clés EN. Retourne le nombre de problèmes."""
    from core.localization import get_translations_dict
    from ui import help_system

    en = get_translations_dict()["en"]
    required = help_system.all_doc_keys()

    missing = [k for k in required if k not in en]
    known = set(required)
    orphans = [k for k in en if k.startswith(("doc_", "tour_")) and k not in known
               and not k.startswith(("doc_directory", "doc_search"))
               and k not in ("tour_title", "tour_step_fmt", "tour_back",
                             "tour_next", "tour_finish", "tour_skip")]

    print(f"Registre : {len(required)} clés requises par ui/help_system.PAGES")
    if missing:
        print(f"  MANQUANTES dans en.toml ({len(missing)}) :")
        for k in missing:
            print(f"    - {k}")
    if orphans:
        print(f"  ORPHELINES dans en.toml ({len(orphans)}, absentes du registre) :")
        for k in orphans:
            print(f"    + {k}")
    if not missing and not orphans:
        print("  OK — registre et en.toml alignés.")
    return len(missing) + len(orphans)


def check_widgets() -> int:
    """Contrôle 2 : widgets interactifs sans tooltip, vue par vue."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from axiom.config import AppConfig
    from ui import help_system
    from ui.hub_view import HubView
    from ui.setup_view import SetupView
    from ui.tabletop_view import TabletopView
    from ui.creator_studio_view import CreatorStudioView
    from ui.settings_dialog import SettingsDialog

    views = {
        "hub": HubView(main_window=None),
        "setup": SetupView(main_window=None),
        "tabletop": TabletopView(main_window=None),
        "creator": CreatorStudioView(main_window=None),
        "settings": SettingsDialog(AppConfig()),
    }

    total = 0
    for name, view in views.items():
        # Dette assumée : l'intérieur des éditeurs du Creator Studio n'est pas
        # encore documenté widget par widget (chaque onglet a sa doc globale).
        skip = ()
        if name == "creator":
            skip = (
                view._entity_editor, view._rule_editor, view._stat_editor,
                view._lore_book_editor, view._scheduled_events_editor,
                view._story_setup_editor, view._map_editor,
                view._populate_tab, view._files_tab,
            )
        elif name == "settings":
            skip = (view._persona_editor,)
        missing = help_system.audit_undocumented(view, skip=skip)
        status = "OK" if not missing else f"{len(missing)} widget(s) sans doc"
        print(f"  {name:<9} {status}")
        for entry in missing:
            print(f"      - {entry}")
        total += len(missing)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit de la doc intégrée (TICKET-057).")
    parser.add_argument("--qt", action="store_true",
                        help="Aussi auditer les widgets sans tooltip (lance Qt offscreen).")
    args = parser.parse_args(argv)

    problems = check_registry_keys()
    if args.qt:
        print("\nWidgets interactifs sans doc :")
        problems += check_widgets()

    print()
    if problems:
        print(f"Résultat : {problems} point(s) à documenter.")
        return 1
    print("Résultat : OK — doc intégrée complète.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
