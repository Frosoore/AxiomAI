# Changelog — Fix : JSON visible dans le chat pendant le streaming

## 2026-06-10

- `ui/widgets/chat_display.py` : `_JSON_OPEN`/`_JSON_CLOSE` (uniquement `~~~json`) remplacés
  par `_JSON_FENCES = (("~~~json", "~~~"), ("```json", "```"))` ; `_flush_token_buffer`
  détecte l'ouverture la plus précoce des deux styles et attend la fermeture du même style
  (`self._json_fence_close`). La garde qui retient un suffixe pouvant être un début de fence
  couvre maintenant les deux préfixes. Comportement inchangé pour le reste (italique/gras,
  images, variantes).
- `tests/test_phase6.py` : fake `_FakeFlusher` aligné sur les nouveaux attributs.
- `tests/test_chat_buffer.py` : +3 tests (backticks).

### Pourquoi le JSON apparaissait

Le moteur demande au LLM un bloc `~~~json … ~~~` en fin de réponse et le retire du texte
sauvegardé (parse résilient, 4 patterns). Mais le **stream** affiché en direct n'était filtré
que pour `~~~json` : quand le modèle ouvrait son bloc avec ``` ```json ``` (réflexe markdown
fréquent), tout le JSON défilait dans le chat. Au rechargement de la partie le texte propre
réapparaissait (l'historique stocke la version parsée) — d'où un bug « visible seulement en
live ».
