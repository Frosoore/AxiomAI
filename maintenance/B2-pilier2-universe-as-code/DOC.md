# DOC — B2 · Pilier 2 : Universe-as-Code

**Objectif.** Un univers = arborescence de fichiers texte (TOML/MD) versionnable. Le `.db` SQLite
devient un cache compilé dérivé du texte (la vérité = le texte). Voir doc `§7` + annexe `C.1`.

**Modules visés (moteur, zéro Qt) :**
- `axiom/compile.py` — `compile_universe(src_dir, output_db, force=False)` : arbo → `.db`.
- `axiom/decompile.py` — `decompile_universe(db_path, output_dir)` : `.db` → arbo (migration de l'existant).
- CLI : `axiom compile` / `axiom decompile` (dans `axiom/cli/`).

**Décisions techniques :**
- Lecture TOML : `tomllib` (stdlib). Écriture TOML : `tomlkit` (préserve commentaires/format — utile au futur Creator Studio).
- Frontière : seules les **tables de définition** vont dans l'arbo ; les tables **runtime/save** restent binaires (cf. TODO.md pour la liste).
- Cache : `.axiom-cache/{universe.db, cache_hash.txt}`, gitignoré ; recompile seulement si le hash source change.
- `.axiom` v2 = zip {arbo + cache `.db`}. Compat v1 (zip JSON) via import → decompile → compile.

**Usage (cible) :**
```
axiom compile   universes/drakthar/            # arbo → .axiom-cache/universe.db
axiom decompile mon_monde.db  out_dir/         # .db → arbo texte (migration)
```

**Hors-scope de ce lot :** Creator Studio (Qt), hot reload `axiom dev`, séparation des saves (§7.6),
migration des `Populate*` (authoring LLM). Voir TODO.md « différé ».
