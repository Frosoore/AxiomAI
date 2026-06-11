# TODO — Fix : JSON visible dans le chat pendant le streaming

- [x] Diagnostiquer : le filtre de streaming (`ui/widgets/chat_display.py`) ne masquait que
      les fences `~~~json … ~~~`, alors que le parseur moteur (`axiom/backends/base.py`)
      accepte aussi ``` ```json … ``` ``` — format que les modèles (Gemini surtout) emploient
      souvent malgré la consigne. Le bloc d'état JSON s'affichait donc en clair dans le chat.
- [x] Étendre `_flush_token_buffer` aux deux styles de fence (ouverture la plus précoce,
      fermeture appariée au style ouvert, garde anti-affichage-prématuré pour les deux préfixes).
- [x] Aligner le fake de `tests/test_phase6.py::TestJsonFenceFiltering`.
- [x] Tests : +3 dans `tests/test_chat_buffer.py` (bloc backticks en un token, en streaming
      caractère par caractère, préfixe partiel retenu puis flush).
- [x] Suites : chat_buffer 5 ✅, phase6 ✅ (lot Qt/vector 56 ✅), suite large 523 ✅.
