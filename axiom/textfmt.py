"""axiom.textfmt — language-neutral text formatting, engine-side.

`fmt_num` is NOT translation: it is display cleanup for numbers (avoids
"3.0" or "0.1000000001"). The engine needs it regardless of any language;
localisation itself lives on the frontend side (see `core.localization`).
"""

from __future__ import annotations


def fmt_num(val: object) -> str:
    """Format a number to avoid 'weird' float displays.

    Returns a string representation of the number, rounded to 2 decimal places
    if it's a float, or as an integer if it has no fractional part.
    """
    try:
        f = float(val)
        if f == int(f):
            return str(int(f))
        return f"{f:.2f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return str(val)
