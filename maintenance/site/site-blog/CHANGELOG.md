# CHANGELOG — Site : blog Markdown + RSS

## 2026-06-20 — Ajout d'un blog au site GitHub Pages

Blog en plus de la page Dev : news détaillées, deep-dives, vie du projet. Articles
en **Markdown**, rendus en HTML stylé au thème du site, générés par
`landing/build_site.py` (réutilise le système TOML/build existant).

### Système
- **Contenu** : `landing/content/blog/*.md` — front-matter TOML (`+++`) + corps
  Markdown. Champs : `title, slug, date, author, summary = [3 points]`.
- **Rendu** : `markdown-it-py` (déjà tiré par `myst-parser` ; ajouté explicitement
  au workflow). Sous-ensemble CommonMark + tables + strikethrough.
- **Sorties générées** : `landing/blog/index.html` (liste), `landing/blog/<slug>.html`
  (un par article), `landing/feed.xml` (**RSS 2.0**, résumé + lien, déterministe :
  `lastBuildDate` = date du dernier article, pas l'horloge → `--check` reste vert).
- **Styles** : bloc CSS `.post-body` (titres/gras/listes/code/blockquote/tables…)
  + `.tldr`, `.post-card`, `.blog-hero` au palette Catppuccin du site. Définis une
  fois, réutilisés par tous les articles (l'auteur n'écrit que du Markdown).
- **Nav** : entrée « Blog » ajoutée sur `index.html` et `dev-updates.html` ; footer
  des pages blog avec liens RSS / Blog / Dev updates.
- CI : `docs.yml` lance déjà `build_site.py` avant la copie ; `markdown-it-py` ajouté
  au `pip install`.

### Conventions d'écriture (cf. [[project-blog]] en mémoire)
Anglais only · ton humain/détendu façon Korben · **pas de tiret cadratin `—`**
(virgules) · **TL;DR 3 points** en tête (`summary`) · signature **Pinpanicaille**
(Frosoore signera en son nom s'il écrit).

### Premiers articles
- `the-blog-is-live` — annonce du blog (but, RSS, Discord).
- `what-we-took-from-hindsight` — le rework mémoire (recherche hybride, faits,
  croyances, modèles mentaux), vulgarisé.

### Validation
- `build_site.py` EXIT 0, `--check` idempotent EXIT 0.
- `feed.xml` = XML valide ; les 3 pages blog parsent (html.parser) ; **0 tiret
  cadratin** dans les articles ; chemins relatifs `../` corrects (sous-dossier blog/).
- ⚠ Rendu visuel non vérifié en navigateur (extension Chrome non connectée).

⚠ **Non commité** au moment de l'écriture — voir push.
