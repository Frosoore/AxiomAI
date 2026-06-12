"""axiom.textfmt — formatage de texte langue-neutre côté moteur.

`fmt_num` n'est PAS de la traduction : c'est un nettoyage d'affichage des nombres
(évite « 3.0 » ou « 0.1000000001 »). Le moteur en a besoin indépendamment de toute
langue ; la localisation, elle, vit côté frontend (cf. `core.localization`, TICKET-054).
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
