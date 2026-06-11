# PENDING — tickets à étudier

> Règle de vie du fichier : un ticket **terminé** part dans `DONE.md` (trace condensée) et
> **disparaît d'ici**, index compris. Ne restent dans PENDING que les tickets ouverts,
> différés ou en attente d'une validation utilisateur.

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-017| Temps causal : `major_event_description` ignoré + **time-skip Chronicler** (spec §6.4) | ouvert (partiellement couvert par TICKET-018, domaine Pilier 5/Gemini) |
| TICKET-049| `compile.py` cassé sous Python ≤ 3.12 (`Path.read_text(newline=)` = 3.13+) | ouvert — quick win |
| TICKET-050| Gemini 429 `limit: 0` (modèle hors free tier) : fail-fast au lieu de 3 retries inutiles | ouvert — quick win |

Tickets résolus/clos : voir `DONE.md` (001→012, TC1→TC5, 015→048 sauf 017).


---

## TICKET-017 — Temps causal : `major_event_description` ignoré + time-skip Chronicler non implémenté

**⏳ OUVERT — partiellement couvert (2026-06-07).** Depuis TICKET-018, un grand saut temporel franchit
un palier de minutes et **déclenche bien le Chronicler** (le monde évolue pendant un long voyage), ce qui
couvre l'essentiel de l'intention §6.4. **Reste à faire** : le champ `major_event_description` renvoyé par
le Timekeeper n'est toujours **pas consommé** — soit l'exploiter (ex. forcer un World Turn sur événement
majeur explicite, indépendamment du palier), soit le retirer du prompt pour cesser de payer ces tokens.
Constat d'origine ci-dessous.

**Constat (`axiom/prompts.py:898,902-903` ; `axiom/arbitrator.py:300-311`).** Le prompt Timekeeper
demande au LLM un champ `major_event_description` (« Arrived at Hemlock », « Defeated the Goblin King »…),
mais `process_turn` ne lit que `elapsed_minutes` (l.310-311) : le champ est **parsé puis jeté**. On paie
des tokens pour une sortie inutilisée.

En parallèle, l'**edge case spec §6.4 « Time skip narratif »** (« si `elapsed_minutes > 480` (8h),
déclencher le Chronicler **avant** de retourner le résultat, pour que le monde évolue pendant le
voyage ») **n'est pas implémenté**. Les deux pointent vers la même fonctionnalité manquante : un grand
saut temporel devrait faire évoluer le monde.

**Ce qui serait à faire :**
- Soit **implémenter** le time-skip : si `elapsed_minutes` dépasse un seuil (ou si
  `major_event_description` est non-null), forcer un World Turn (`chronicler.force_trigger`) — ce qui
  redonne du sens au champ.
- Soit **retirer** `major_event_description` du prompt Timekeeper pour cesser de payer des tokens inutiles.

**Priorité :** moyenne (fonctionnalité spec manquante + léger gaspillage tokens). Lié à TICKET-018.

---

## TICKET-049 — `compile.py` cassé sous Python ≤ 3.12 (`Path.read_text(newline=)`)

**Constat (2026-06-10, session backend image Gemini).** `axiom/compile.py:119` et `:297` appellent
`Path.read_text(encoding="utf-8", newline="")` — le paramètre `newline` de `read_text` n'existe
qu'à partir de **Python 3.13**. Sous 3.12 : `TypeError: Path.read_text() got an unexpected keyword
argument 'newline'`. Or `run.sh`/`test.sh` créent le venv avec le **python3 système** (3.12.3 sur la
machine actuelle — l'ancien venv, disparu, devait être en 3.13) et le README annonce « Python 3.10+ ».

**Impact réel :** toute compilation d'arbo source → .db échoue (donc `ensure_compiled` au lancement
d'une partie sur un univers-dossier, hot reload, pack v2, preview Populate…). **21 tests** échouent
sous 3.12 (`test_universe_as_code.py` ×20, `test_source_preview.py::test_stage_puis_apply`) —
vérifiés préexistants, sans rapport avec le chantier image.

**Fix trivial (2 lignes) :** remplacer par `with path.open("r", encoding="utf-8", newline="") as f:
f.read()` — `open(newline=)` existe depuis toujours. (`write_text(newline=)` est OK : dispo
depuis 3.10, `decompile.py`/`saves.py` ne sont pas concernés.)

**Priorité :** haute sur cette machine (bloque le jeu sur univers-dossiers + 21 tests rouges),
quick win sans risque.

---

## TICKET-050 — Gemini 429 `limit: 0` : fail-fast au lieu de retries inutiles

**Constat (2026-06-10, test réel du backend image Gemini).** Quand un modèle n'est **pas inclus
dans le free tier** de la clé (tous les modèles d'image : `limit: 0`, déjà vu sur
`gemini-2.0-flash` texte), l'API renvoie quand même un 429 avec un `retryDelay` (« retry in
14s ») **trompeur** : le quota journalier est à zéro, attendre ne servira jamais. Or
`_call_with_quota_retry` (`axiom/backends/gemini.py`) enchaîne 3 retries avec compte à rebours →
jusqu'à ~1-2 min de blocage par tour pour rien (et par appel Populate, etc.).

**Fix proposé :** dans `_is_quota_error`/le handler 429, détecter `"limit: 0"` dans le message
(ou `QuotaFailure` avec quota par jour à 0) → **échec immédiat** sans retry ni fallback inutile,
avec un message clair (« modèle hors free tier — facturation requise »). Couvre texte ET image
(le backend est partagé).

**Priorité :** moyenne (UX/perf, aucun comportement correct perdu), quick win.

---
