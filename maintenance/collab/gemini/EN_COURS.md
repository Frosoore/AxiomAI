# EN_COURS — côté Gemini (le pote)

> Écrit **uniquement par Gemini CLI**. Claude (l'utilisateur) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main`
**Chantier :** feature-edit-messages (modification dynamique de messages de l'historique) — terminé

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour Claude |
|-------------------------|----------------------|---------------|------------------|
| _(rien)_                |                      |               |                  |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(aucun)_

## Fini / mergé récemment (info pour Claude)

- `core/locales/*.toml` (Traductions locales)
- `axiom/events.py` (Mise à jour SQLite)
- `axiom/memory.py` (Mise à jour vectorielle)
- `workers/db_tasks.py` & `workers/db_worker.py` (Tâches de fond)
- `workers/vector_worker.py` (Tâche de fond vectorielle)
- `ui/widgets/chat_display.py` & `ui/tabletop_view.py` (Intégration UI chat)
