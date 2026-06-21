# QA — Ambiance trompeuse + bruit console + lenteur images (2026-06-13)

Contrôle qualité demandé par l'utilisateur (3 symptômes observés en usage réel).

- [x] **Point 1 — images lentes au 1ᵉʳ passage** : vérité terrain (save inspectée).
      11 liens externes `![](https://cdn.imgchest.com/...)` ~1,4 Mo chacun = ~15 Mo,
      derrière Cloudflare. Pas dans la carte. Lenteur = les 15 Mo téléchargés.
      Tentative cache disque + placeholder gris (session 2) → **ANNULÉE** sur choix
      utilisateur (placeholder gris empirait le ressenti ; cache n'aide qu'au 2ᵉ
      passage). État images = identique à l'avant-session. Piste « télécharger dans
      la save » proposée, **refusée pour l'instant**.
- [x] **Vignette « génération en cours… »** (demande explicite, images GÉNÉRÉES) :
      vignette inline affichée pendant la génération cloud d'illustration, remplacée
      par l'image (ou retirée si échec). Constante `axiom.session.IMAGE_GEN_STATUS`,
      slot `tabletop._on_turn_status`, `chat_display.show/clear_image_placeholder`,
      clé i18n `generating_image` ×10. Suppression par plage explicite (le flush
      final peut ajouter du texte après la vignette).
- [x] **Point 2 — « Ambiance: exploration (fading...) » affiché en bas** : bug UX.
      Le statut était affiché à chaque transition même sans asset audio (rien ne
      fade réellement). → `update_ambiance()` renvoie désormais un `bool` ; le
      statut n'est affiché que si une piste a réellement démarré.
- [x] **Point 3 — `[AMBIANCE] No audio assets found...` dans le shell** : bruit.
      Les `print()` directs vers stdout passent désormais par `logger.debug`
      (console en INFO → silencieux dans le shell, conservé dans le fichier log).
- [x] Tests : 2 ajoutés (contrat du retour `bool`), suite ambiance verte (7/7).
