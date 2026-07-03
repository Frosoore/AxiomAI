# EN_COURS — côté Gemini (le pote)

> Écrit **uniquement par Gemini CLI**. Claude (l'utilisateur) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main`
**Chantier :** `TICKET-092-fix-xcb-cursor-crash` — terminé, en attente de commit utilisateur

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour Claude |
|-------------------------|----------------------|---------------|------------------|
| _(rien)_                |                      |               |                  |



## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(aucun)_

## Fini / mergé récemment (info pour Claude)

- `TICKET-092-fix-xcb-cursor-crash` : Validation de `libxcb-cursor.so.0` sur Linux (`debug/startup_check.py`, `run.sh`, `tools/diagnostic.py`)
- `axiom/compile.py` / `axiom/decompile.py` / `axiom/db_helpers.py` / `axiom/library.py` (Universe description compilation, decompilation, and metadata retrieval roundtrip)
- `ui/hub_view.py` / `ui/widgets/universe_card.py` (Display of word-wrapped universe descriptions in library cards)
- `ui/creator_studio_view.py` (Metadata editing of descriptions in Creator Studio)
- `ui/help_system.py` / `core/locales/*.toml` (Registered and localized help documentation for the description field across 10 languages)
- `feature-edit-start-date` (Adventure start date/time customization in Creator Studio, 10 languages localized, tests OK, pending commit)
- `feature-sort-saves` (Saves sorting by last updated / creation date in launch lobby view, 10 languages localized, tests OK, pending commit)




