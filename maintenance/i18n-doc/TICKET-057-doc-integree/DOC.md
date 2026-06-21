# DOC — TICKET-057 : doc intégrée à l'app GUI

Rendre l'app auto-explicative, en 4 briques livrées d'un bloc :
tooltips partout, bouton « expliquer cette page », quick tour de départ, annuaire cherchable.
Traduit dans les 10 langues (`core/localization.py` + `core/locales/*.toml`).
Périmètre : `ui/` (+ `core/locales/`). Le moteur (`axiom/`) n'est pas concerné.

Architecture retenue : un registre déclaratif unique (`ui/help_system.py::PAGES`) nourrit les
4 briques ; 1 élément = 2 clés TOML (`doc_<page>_<el>_t` / `doc_<page>_<el>`). Étendre la doc =
1 ligne de registre + 1 appel `doc()` + 2 clés ×10 langues ; `tools/doc_check.py` signale les trous.
Le quick tour remplace l'ancienne welcome box (déclencheur : `SETTINGS_FILE` absent).
