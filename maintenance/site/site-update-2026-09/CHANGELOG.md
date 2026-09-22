# CHANGELOG — Mise à jour du site (2026-09-22)

- `landing/content/updates.toml` : bloc `2026-07` (Added : web UI alpha ; Fixed : `libxcb-cursor0`,
  ménage Myria), résumé d'août réécrit, section `known` ajoutée à août.
- Bannière testeurs retirée : `landing/index.html`, `landing/dev-updates.html`, gabarit des pages de
  blog dans `landing/build_site.py::_page`, et CSS `.alpha-banner`/`.alpha-inner`/`.alpha-tag`
  supprimé de `landing/styles.css` (plus aucun usage).
- Blog : `landing/content/blog/2026-09-22-quiet-but-stable.md` (anglais, ton Korben, TL;DR 3 points,
  zéro tiret cadratin/demi-cadratin vérifié par grep, signé Pinpanicaille).
- `python landing/build_site.py` → `dev-updates.html`, `blog/index.html`, `blog/quiet-but-stable.html`,
  `feed.xml` et les autres pages de blog régénérés (bannière retirée partout) ; `--check` : à jour.
- Constaté en passant : `core/builtin_keys.py::BUILTIN_KEYS_ENABLED` encore à `True` alors que les clés
  ont expiré le 2026-06-30 → **TICKET-099** (décision utilisateur).
