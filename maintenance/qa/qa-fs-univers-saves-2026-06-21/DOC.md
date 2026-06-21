# DOC — QA système fichiers / univers / saves (2026-06-21)

## Objectif
Vérifier que le système Universe-as-Code (sources TOML/MD + cache `.db`), les saves séparées
(`.axiomsave`) et le packaging (`.axiom`) sont **cohérents avec le schéma** et **fonctionnels de
bout en bout**.

## Verdict
Le système est sain et fonctionne de bout en bout (compile/pack/unpack/saves CRUD/export/import).
Une classe de bug bien réelle a été trouvée et corrigée : **dérive entre les listes de colonnes
codées en dur dans `savestore`/`saves` et le schéma vivant** (`fired_turn_id`, TICKET-075).

## Décision technique
- Les listes `_DEFINITION_COPY`/`_RUNTIME_COPY` de `savestore.py` sont une **copie manuelle** du
  schéma : tout ajout de colonne au schéma DOIT y être répercuté. On verrouille désormais cet
  invariant par un test (`TestCopyListSchemaCoherence`) pour transformer une perte de donnée
  silencieuse en échec de CI bruyant.
- Fix de `fork_save` aligné sur le pattern de `checkpoint.py` (`ensure_fired_event_turn_column`
  avant lecture) pour rester robuste sur les vieilles bases embarquées.

## Suite
Voir PENDING TICKET-087→090 (cache commité, fork incomplet living/snapshots, purge archive, paths).
