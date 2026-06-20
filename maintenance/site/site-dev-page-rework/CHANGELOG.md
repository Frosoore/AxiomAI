# CHANGELOG — Site : page Dev pilotée par fichiers

## 2026-06-20 — Roadmap + dev-updates générés depuis des TOML

Rework du site GitHub Pages (`landing/`) : le contenu qui bouge à chaque commit
sort du HTML et vit dans des fichiers de config TOML, régénérés au build.

### Données (source de vérité)
- `landing/content/roadmap.toml` — roadmap en **cycle de vie** : chaque `[[item]]`
  porte `status = "next" | "far" | "done"` (+ `date` optionnelle pour le done).
  « Déplacer » un item = changer un mot.
- `landing/content/updates.toml` — journal des dev-updates (`[[update]]` +
  `[[update.section]]`), repris de l'ancien tableau JS codé en dur.
- `landing/content/README.md` — guide d'édition (non-codeur).

### Générateur
- `landing/build_site.py` (stdlib seule : `tomllib`, idempotent) remplit les
  régions `<!-- BUILD:… -->` du HTML :
  - **roadmap** 3 colonnes (Next up / Far away / Recently done) sur `dev-updates.html` ;
  - **journal** : injecte `const DEV_UPDATES` (JSON) consommé par le sélecteur de mois ;
  - **meta** : version moteur (`axiom.__version__`) + « last updated » (date + hash git) ;
  - **teaser** roadmap sur `index.html` (aperçu Next up + lien vers la page Dev).
  - Modes : `--check` (garde CI), `--draft-update [ref]` (pré-remplit un bloc
    depuis les commits `feat:`/`fix:`).

### Pages
- `dev-updates.html` devient la **page « Dev » unique** : hero + barre méta +
  **badges GitHub/PyPI** (shields.io, live) + section **Roadmap** générée +
  section **Dev log** (sélecteur de mois conservé). UI inchangée (classes CSS
  existantes réutilisées).
- `index.html` : la roadmap complète est remplacée par un **teaser** généré qui
  pointe vers la page Dev (l'ancre `#roadmap` et la nav restent valides).
- `styles.css` : roadmap passée en **3 colonnes**, variante `.road-col.done`
  (accent vert), `.rl-date`, `.du-meta-bar/.du-stat`, `.du-badges`, `.road-teaser`.

### CI
- `.github/workflows/docs.yml` : étape **« Build landing content »**
  (`python landing/build_site.py`) avant la copie de `landing/` vers le site.
  Le filtre `paths` couvre déjà `landing/**` et `axiom/**` (un bump de version
  redéploie donc le badge).

### Automatisations livrées (demande user)
Badge version auto · date « dernière MAJ » (build) · stats GitHub (badges) ·
journal semi-auto depuis `git log` (`--draft-update`).

### Validation
- `build_site.py` EXIT 0 ; `--check` → « up to date » (idempotent).
- HTML des 2 pages parse OK (html.parser) ; JSON injecté valide ; 3 colonnes roadmap.
- ⚠ Preview navigateur non faite (extension Chrome non connectée) — à regarder en local.

⚠ **Non commité** — attente feu vert utilisateur.
