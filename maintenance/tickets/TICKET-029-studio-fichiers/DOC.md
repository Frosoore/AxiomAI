# TICKET-029 — Creator Studio : onglet « Fichiers » — DOC

Onglet « Fichiers » dans le Creator Studio : voir/éditer l'arborescence texte de l'univers
(universe.toml, entities/*.toml, lore/**/*.md…). À l'enregistrement d'un fichier, la
définition est recompilée **in-place** dans le `.db` (`axiom.dev.refresh_definition`) et la
vue Studio classique se recharge. Une source momentanément invalide affiche l'erreur de
compilation sans rien casser (même sémantique que `axiom dev`).

Pour un `.db` plat (legacy), l'onglet propose la conversion en univers-dossier :
`axiom.library.convert_flat_db_to_folder` (saves embarquées extraites vers `saves/<clé>/`
et reliées à la nouvelle source ; l'original est conservé en `.db.bak`).

Limite connue : éditer en même temps les widgets Studio ET les fichiers peut se marcher
dessus (Ctrl+S Studio réécrit la source depuis ses widgets) ; l'onglet recharge la vue
classique après chaque save de fichier, et se recharge lui-même à chaque activation.
