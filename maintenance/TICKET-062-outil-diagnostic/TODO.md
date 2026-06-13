# TICKET-062 item 4 — Outil de diagnostic pour les bêta-testeurs

**Statut : ✅ CLI + GUI FAITS (2026-06-12/13). ⚠ validation GUI réelle utilisateur en attente.**

Décision session : **santé rapide + tests en option**, **CLI d'abord**, dialogue
GUI (Aide → Diagnostic) ensuite — les deux livrés.

## Fait — `tools/diagnostic.py` (autonome, sans GUI)
- `python -m tools.diagnostic` → rapport texte copiable, ✅/⚠️/❌ par point :
  environnement (Python/OS/venv), versions des libs lourdes, **modèle
  d'embedding caché ?** (le bug TICKET-068), config (backend/modèle/clé
  présente sans sa valeur/Timekeeper), dossiers de données inscriptibles,
  **connectivité backend** (`is_available`).
- Drapeaux : `--tests` (lance pytest en **2 lots** pour contourner le segfault
  TICKET-067), `--offline` (saute le check réseau), `--json`, `--output FICHIER`.
- Code de sortie = sévérité (0 OK / 1 WARN / 2 FAIL) — exploitable en script/CI.
- **Reflète le vrai runtime** : `run_diagnostics()` appelle
  `register_builtin_providers()` (comme l'app) pour que le cas zéro-config
  (clés bêta partagées) ne tombe pas en faux « no API key ». N'applique JAMAIS
  les défauts bêta (ne mute pas settings).
- Importable : `run_diagnostics()` / `format_report()` resserviront au dialogue GUI.

## Fait — brique GUI (2026-06-13)
- `ui/diagnostic_dialog.py` (Aide → Diagnostic) : rapport monospace copiable,
  boutons **Actualiser**, **Lancer tous les tests (lent)**, **Copier**,
  **Enregistrer…**, fermeture. Auto-lance les checks rapides à l'ouverture.
- `workers/diagnostic_worker.py` (QThread) : `run_diagnostics()` off-thread
  (le check backend fait du réseau / les tests forkent pytest), émet
  `report_ready(report, overall)`. Ne lève jamais.
- Branché dans `ui/main_window.py` (`_show_diagnostic`, action menu + tooltip).
- i18n : 12 clés ×10 langues (`menu_diagnostic`, `diagnostic_*`),
  `tools/i18n_check.py` → 547/547 partout.

## Reste
- [ ] Validation réelle utilisateur : Aide → Diagnostic dans l'app, vérifier que
  le rapport est parlant + le bouton « Lancer tous les tests ».

## Vérifications
- CLI : rapport complet, Overall ✅ OK sur le setup zéro-config
  (fireworks/clés bêta, backend répond). `--offline`/`--json` OK.
- `_run_test_batch` réel sur cible légère : « 18 passed … » parsé, status OK.
- GUI smoke (Qt offscreen) : dialogue construit, worker tourne, rapport peuplé
  (1025 chars, « Overall »), boutons réactivés, copie presse-papiers OK.
- Tests : `tests/test_diagnostic.py` (18) + `tests/test_diagnostic_dialog.py`
  (7, worker + dialogue avec worker factice) verts.
