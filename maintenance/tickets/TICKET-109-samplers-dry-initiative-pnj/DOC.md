# DOC — TICKET-109 : Samplers DRY, initiative physique PNJ & formatage roman

## Contexte & Constat (Session test 11 tours sur Stheno v3.4 / KoboldCPP)
Après la résolution de l'usurpation d'agence par le TICKET-108 (zéro godmoding sur 11 tours), quatre nouveaux symptômes ont émergé à partir du Tour 6 :
1. **Effondrement stylistique (boucles de phrases)** : des expressions spécifiques ("eyes widen", "flicker of something darker", "edges of her cloak", "air feels electric") se répètent mot pour mot à chaque tour. Cause : température trop basse (0.7) sans sampler anti-répétition DRY (*Don't Repeat Yourself*).
2. **Paralysie d'initiative PNJ & baiser bloqué** : l'interdiction trop absolue ("NEVER describe what 'You' do, say, or think") empêchait les PNJ d'interagir physiquement avec le joueur (ex. poser les lèvres sur les siennes pour un baiser).
3. **Perte des guillemets doubles `"..."`** : l'obligation des astérisques pour les actions (`*actions*`) créait une confusion typographique dès le premier tour.
4. **Coupure de fin de phrase au Tour 10** : plafond de tokens atteint ou coupure sans point final.

## Décisions techniques
1. **DRY Sampler & Température 1.12** : intégration dans `AppConfig` et `UniversalClient` des paramètres supportés nativement par KoboldCPP (`dry_multiplier=0.8`, `dry_base=1.75`, `dry_allowed_length=2`, `dry_sequence_breakers=["\n", ":", "\"", "*"]`, `trim_stop=True`).
2. **Consigne d'agence affinée** : les PNJ doivent accomplir les actions physiques demandées par le joueur, tandis que l'interdiction est circonscrite à la non-invention de dialogues et de décisions pour le joueur.
3. **Formatage roman** : narration en texte brut (sans astérisques), dialogues entre guillemets doubles.
