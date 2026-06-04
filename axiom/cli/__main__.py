"""Permet `python -m axiom.cli ...` (équivalent du futur console_script `axiom`)."""

import sys

from axiom.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
