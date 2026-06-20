# TICKET-030 — Populate × Universe-as-Code — TODO

Périmètre validé par l'utilisateur le 2026-06-09 (cf. PENDING.md § TICKET-030) :
(1) Populate ciblé, (2) prévisualisation du diff texte, (3) canonisation depuis la partie
(toggle continu ou déclenchement ponctuel, inactif par défaut).

- [x] Moteur : `axiom.library.diff_source_trees` (diff unifié entre deux arbos source)
      + `apply_staged_source` (miroir arbre validé → source + `refresh_definition`)
- [x] Prompt : `axiom.prompts.build_canonize_prompt` (histoire récente → entités + lore canon)
- [x] Workers : sandbox `_stage_source_change` (copie db temporaire → mutation → sync arbre
      temporaire → diff vs baseline normalisée), `PreviewPopulateTask` (populate ciblé en
      sandbox), `ApplyStagedSourceTask` (+ resync save en cours), `CanonizeStoryTask`
      (preview ou direct), `discard_staged_source`
- [x] `DbWorker` : signaux/méthodes preview/apply/canonize
- [x] Widget `ui/widgets/diff_preview_dialog.py` : fichiers changés + diff unifié, Appliquer/Annuler
- [x] Populate tab : case « Prévisualiser le diff avant d'appliquer » (univers-dossier requis)
- [x] Creator Studio : flux save → preview → dialogue diff → apply → reload
- [x] Tabletop : bouton « Canoniser… » (preview) + toggle « Canon auto » (silencieux,
      par tour, OFF par défaut) ; erreur claire si la save n'est pas liée à un univers-dossier
- [x] Localisation EN + FR
- [x] Tests : diff_source_trees / apply_staged_source / sandbox / canon (hors LLM) ; smokes offscreen
- [ ] Validation GUI réelle par l'utilisateur (hors périmètre agent) — nécessite une clé LLM
