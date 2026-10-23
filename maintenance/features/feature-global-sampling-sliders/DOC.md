# DOC — feature-global-sampling-sliders

## Objectif
1. Ajouter dans les paramètres de l'application (Settings -> Universe Parameters) des contrôles visuels sliders/spinboxes pour configurer :
   - `Temperature` (0.00 à 2.00, pas 0.05, défaut 1.12)
   - `Top-P` (0.00 à 1.00, pas 0.01, défaut 1.00)
   - `Min-P` (0.00 à 1.00, pas 0.01, défaut 0.10)
   - `DRY Multiplier` (0.00 à 2.00, pas 0.05, défaut 0.80)
2. Passer ces paramètres d'une portée locale par base d'univers (`Universe_Meta`) à une portée **globale** (`AppConfig` / `config.json`), constante et persistante à travers tous les univers et lancements.
3. Unifier la source de vérité dans toute la codebase afin que les appels narratifs lisent ces valeurs globales sans valeurs contradictoires masquées (ex. 0.7 en dur), tout en préservant impérativement les températures basses et fixes des appels techniques déterministes (ex. Timekeeper à 0.1).
