# DOC — QA-test-connexion-gemini

## Symptôme

Réglages → Cloud → fournisseur « Google Gemini » → « Test Connection » : rien
ne se passe (statut « Testing… » qui ne se termine jamais à l'échelle d'une
patience humaine).

## Cause racine (diagnostic du 2026-06-12)

1. **La connectivité IPv6 vers Google est cassée sur la machine** : les SYN TCP
   vers les adresses IPv6 de `generativelanguage.googleapis.com` ne reçoivent
   jamais de réponse (`curl -6` → timeout, `curl -4` → 403 en 0,14 s, normal
   sans clé). Ce n'est pas un bug de l'app, mais l'app doit y être résiliente :
   `curl` s'en sort car il tente IPv4 et IPv6 en parallèle (happy eyeballs),
   Python essaie les adresses une par une.
2. **Le SDK `google-genai` n'a aucun timeout par défaut**, et pire : il passe
   `timeout=None` explicitement à chaque requête httpx, ce qui désactive même
   un timeout configuré au niveau du client httpx (`client_args`). Résultat :
   chaque adresse IPv6 est tentée jusqu'au timeout SYN du noyau (~130 s), et
   Google publie plusieurs adresses IPv6 → plusieurs minutes avant d'atteindre
   une adresse IPv4 qui marche.

Le code du dialogue Réglages et du `ConnectionTestWorker` est correct
(36 tests verts) — le blocage était entièrement dans la couche réseau.

## Correctif (design final, itération 2)

Module partagé **`axiom/backends/transport.py`** : `IPv4FirstTransport`,
utilisé par les deux clients (`gemini.py` via
`HttpOptions(client_args={"transport": …})`, `universal.py` via
`httpx.Client(transport=…)`). Trois étages :

1. **IPv4 d'abord** : la connexion part sur une socket épinglée en famille
   IPv4 (`local_address="0.0.0.0"`) — les adresses IPv6 sont écartées
   instantanément (erreur de bind locale, aucune attente réseau). Quasi tous
   les fournisseurs ont de l'IPv4 : c'est le chemin rapide partout, aucun
   coût sur les machines saines.
2. **Fallback dual-stack** : si l'IPv4 elle-même ne se connecte pas (réseau
   IPv6-only), la requête est rejouée une fois sur un transport classique et
   le choix est mémorisé (les requêtes suivantes ne repayent pas la sonde).
   Rejouer est sûr : un échec de connexion survient avant tout envoi, et nos
   corps de requêtes sont des bytes, pas des streams.
3. **Connect timeout 5 s/adresse** injecté quand la requête n'en a pas (le
   SDK genai passe `timeout=None` par requête, ce qui annule même un timeout
   client httpx). Lecture/écriture intactes : générations longues illimitées.

`universal.py` garde en plus `httpx.Timeout(600.0, connect=5.0)` au niveau
client (garde-fou ; l'ancien scalaire 600 s s'appliquait aussi au connect).

## Vérification

Sur la machine réelle (IPv6 cassée) : `is_available()` → **True en 0,27 s**
connexion incluse (itération 1, timeout seul : 20,3 s ; avant : bloqué
> 5 min). Suites : 612 + 56 Qt/vector, vertes.

## Note environnement

L'IPv6 de la machine reste cassée au niveau OS/box (probablement depuis la
MAJ Fedora du 2026-06-11) — l'app n'en dépend plus, mais d'autres logiciels
peuvent ramer pour la même raison. La vraie guérison reste de
réparer/désactiver l'IPv6 côté système.
