# CHANGELOG — Licence : AGPL conservée + obligation de citation + liens PyPI

## 2026-06-11 — Passage GPL v3 (annulé le jour même)

- `LICENSE` remplacé par le texte officiel GPL v3 (copie système Fedora, md5 canonique
  gnu.org), `NOTICE` créé (attribution §7(b)), propagé dans pyproject/README/export_engine/
  test packaging, wheel validée `License-Expression: GPL-3.0-or-later`.
- **Annulé sur décision utilisateur** : son doute sur l'AGPL venait d'un malentendu sur
  l'en-tête FSF du fichier LICENSE (qui protège le texte de la licence, pas le logiciel).
  Retour à l'AGPL demandé, qui conserve en plus la protection SaaS.

## 2026-06-11 — État final : AGPL + NOTICE + liens PyPI

- `LICENSE` : texte **AGPL v3 d'origine restauré** (`git restore`, 661 lignes, inchangé vs HEAD).
- `NOTICE` : reformulé pour l'AGPL — copyright « The Axiom AI authors: 17h59 and Frosoore »,
  URL du projet, terme additionnel **AGPLv3 §7(b)** (clause vérifiée présente à la ligne 357
  du LICENSE) : toute redistribution doit préserver le NOTICE et l'attribution
  « Based on Axiom AI (https://github.com/Frosoore/AxiomAI) by 17h59 and Frosoore ».
- `pyproject.toml` : `license = "AGPL-3.0-or-later"` (revenu), `license-files =
  ["LICENSE", "NOTICE"]` (nouveau), **`[project.urls]`** Homepage/Repository/Issues →
  `github.com/Frosoore/AxiomAI` (encadré « Project links » de la page PyPI — demande
  utilisateur : la lib était introuvable depuis PyPI).
- `README.md` : section License = AGPL v3 + exigence d'attribution (NOTICE).
- `export_engine.py` : README généré de la lib — nouvelle section « Projet » avec lien repo,
  licence AGPL + renvoi NOTICE ; le `NOTICE` est copié dans chaque export ; docstring à jour.
- `tests/test_packaging.py` : + assertion `NOTICE` présent dans l'export.
- Vérifications : 15 tests packaging verts ; wheel construite → `License-Expression:
  AGPL-3.0-or-later`, 3 `Project-URL`, `LICENSE` + `NOTICE` dans le dist-info.

**Accord de Frosoore obtenu le 2026-06-11** (confirmé par l'utilisateur). Reste : la
republication PyPI par l'utilisateur (token en main, commandes `export_engine.py --bump patch
--build` + `twine upload` fournies — la 0.1.0 en ligne n'a ni NOTICE ni liens).
