#!/usr/bin/env python3
"""tools/i18n_check.py — audit de couverture des traductions (côté app).

Remplace l'ancienne commande `axiom i18n-check` : depuis TICKET-054 l'i18n vit
côté frontend (`core/localization.py` + `core/locales/`), plus dans le moteur.

Usage :
    python tools/i18n_check.py              # audite vs EN, exit≠0 si une langue est incomplète
    python tools/i18n_check.py --show-keys  # liste chaque clé manquante / en trop
    python tools/i18n_check.py -r fr         # référence = fr
    python tools/i18n_check.py --strict      # échoue aussi sur les clés en trop
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permet de lancer le script depuis n'importe où (le repo racine doit être importable).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.localization import SUPPORTED_LANGUAGES, compute_coverage, get_translations_dict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit de couverture i18n d'Axiom AI.")
    parser.add_argument("--reference", "-r", default="en", help="Langue de référence (défaut : en).")
    parser.add_argument("--strict", action="store_true", help="Échouer aussi sur les clés en trop.")
    parser.add_argument("--show-keys", action="store_true", help="Lister chaque clé manquante / en trop.")
    args = parser.parse_args(argv)

    if args.reference not in SUPPORTED_LANGUAGES:
        print(f"Langue de référence inconnue : {args.reference}")
        return 2

    ref_count = len(get_translations_dict().get(args.reference, {}))
    report = compute_coverage(args.reference)

    print(f"Couverture i18n (référence : {args.reference} = {ref_count} clés)\n")
    has_missing = has_extra = False
    for lang, data in report.items():
        missing, extra = data["missing"], data["extra"]
        count = ref_count - len(missing)
        status = "OK" if not missing else "INCOMPLET"
        print(f"  {lang:<3} {count:>4}/{ref_count} clés | manquantes={len(missing):>3} | en trop={len(extra):>3} | {status}")
        if missing:
            has_missing = True
            if args.show_keys:
                for k in missing:
                    print(f"        - manquante : {k}")
        if extra:
            has_extra = True
            if args.show_keys:
                for k in extra:
                    print(f"        + en trop   : {k}")

    print()
    if has_missing:
        print("Résultat : INCOMPLET — des clés manquent (voir ci-dessus).")
        return 1
    if has_extra and args.strict:
        print("Résultat : des clés en trop (--strict).")
        return 1
    print("Résultat : OK — toutes les langues sont complètes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
