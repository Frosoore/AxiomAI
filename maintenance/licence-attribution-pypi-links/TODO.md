# TODO — AGPL conservée + obligation de citation + liens PyPI

- [x] (annulé) Passage GPL v3 — fait puis reverté sur décision utilisateur (malentendu AGPL clarifié)
- [x] `LICENSE` : texte AGPL v3 d'origine restauré (`git restore`)
- [x] `NOTICE` : copyright (17h59 & Frosoore) + terme additionnel **AGPLv3 §7(b)** imposant la citation de l'origine
- [x] `pyproject.toml` : `license = "AGPL-3.0-or-later"`, `license-files = ["LICENSE", "NOTICE"]`
- [x] `pyproject.toml` : `[project.urls]` Homepage/Repository/Issues → github.com/Frosoore/AxiomAI
- [x] `README.md` : section License (AGPL + mention attribution)
- [x] `export_engine.py` : README généré (section « Projet » avec lien repo, licence AGPL + NOTICE) ; NOTICE copié dans l'export
- [x] `tests/test_packaging.py` : assertion NOTICE présent dans l'export
- [x] Wheel de validation : `License-Expression: AGPL-3.0-or-later` + 3 `Project-URL` + LICENSE/NOTICE embarqués ; 15 tests verts
- [x] **Utilisateur** : accord explicite de Frosoore (co-auteur) sur le terme d'attribution — **obtenu le 2026-06-11**
- [ ] **Utilisateur** : republier sur PyPI (la 0.1.0 en ligne n'a ni NOTICE ni liens projet) — commandes fournies
