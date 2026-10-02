# Cadre Juridique et Statut des Mods Axiom AI

> ⚠ **BROUILLON NON VALIDÉ — sans valeur juridique.** Ce texte a été rédigé par un agent IA sans décision
> des auteurs (Pinpanicaille et Frosoore). La licence des mods tiers est une **question ouverte**
> (`maintenance/Mods/DOC.md` §14, « Questions reportées » : avis juridique requis avant tout store).
> Tant qu'elle n'est pas tranchée, **seule la licence AGPL-3.0-or-later du projet s'applique** (voir `LICENSE`, `NOTICE`).

Ce document explicite la politique de licence et la frontière juridique applicable au micro-noyau Axiom AI (`axiomai-engine`), aux mods officiels (`axiom.*`, `core.*`), et aux extensions créées par la communauté conformément à la licence **GNU Affero General Public License v3 (AGPL-3.0-or-later)** et à la clause d'attribution additionnelle **§7(b)** (décisions d'arbitrage Rang 36 et D-9).

---

## 1. Licence du Noyau et des Mods Officiels

Le micro-noyau Axiom AI (`axiom/`), les interfaces officielles (`axiom.ui.web`, `axiom.ui.qt`, `axiom.cli`) et l'ensemble des modules fondateurs (`axiom.world`, `axiom.turn`, `axiom.time`, `axiom.inventory`, `axiom.rag`, `axiom.living_memory`, `axiom.providers`, `axiom.illustrations`, `core.stat_dynamics`) sont distribués sous licence **GNU AGPL-3.0 ou ultérieure**.

Toute redistribution ou exploitation en réseau de ces composants implique le respect des termes de l'AGPL-3.0, notamment :
1. La mise à disposition du code source complet correspondant aux utilisateurs interagissant avec le logiciel à distance via un réseau informatique (AGPLv3 §13).
2. La préservation stricte de la notice légale et de la clause d'attribution d'origine mentionnant **Pinpanicaille et Frosoore** (AGPLv3 §7(b)).

---

## 2. La Frontière d'Extensibilité : Statut des Mods Tiers

L'architecture d'Axiom AI a été expressément conçue pour préserver une frontière d'abstraction nette entre le moteur et les extensions communautaires.

### A. Mods Modulaires Autonomes (Licence au Choix de l'Auteur)
Un mod tiers est considéré comme un **composant modulaire indépendant** (et non comme une œuvre dérivée au sens du droit d'auteur) dès lors qu'il respecte les conditions cumulatives suivantes :
1. **Communication exclusive par les interfaces publiques** : Il interagit avec le moteur exclusivement via l'objet `ModContext` (`ctx.register_hook`, `ctx.contribute_slot`, `ctx.declare_slot`, `ctx.register_service`).
2. **Couplage lâche et déclaratif** : Ses échanges de données reposent sur des formats ouverts (manifeste `mod.toml`, dictionnaires et payloads JSON des hooks et slots, archives `.axmod`).
3. **Absence d'incorporation de code source** : Il n'intègre pas de code source propriétaire copié directement depuis le noyau `axiom/`.

**Conséquence juridique** : Les auteurs de ces mods autonomes **sont libres de choisir la licence de leur choix** pour leur code (licences permissives MIT / Apache 2.0, copyleft GPL / AGPL, ou licence commerciale / propriétaire).

---

### B. Mods Intrusifs et Monkeypatching (Œuvre Dérivée AGPLv3)
Par exception, tout mod qui :
- Utilise le mécanisme de patches (`ctx.patch` ou injection dynamique via `__code__`),
- Détourne des fonctions, structures ou symboles privés du noyau en dehors des contrats d'interface documentés,
- Modifie directement le comportement interne des fonctions internes du moteur,

est considéré sur le plan technique et juridique comme formant un tout indivisible avec le noyau. **Un tel mod constitue une œuvre dérivée d'Axiom AI et est obligatoirement régi par les termes et conditions de la licence GNU AGPLv3.**

---

## 3. Synthèse des Droits et Obligations

| Type de Composant | Mode d'Interaction | Licence Applicable | Re-publication Source Réseau |
| :--- | :--- | :--- | :--- |
| **Noyau (`axiom/`)** | Cœur du moteur | GNU AGPLv3 + §7(b) | Obligatoire si modifié |
| **Mods Officiels** | Registre & `ModContext` | GNU AGPLv3 + §7(b) | Obligatoire si modifié |
| **Mods Tiers Autonomes** | `ModContext`, Hooks, Slots JSON | **Au choix de l'auteur** (MIT, Propriétaire...) | Dépend de la licence choisie par l'auteur |
| **Mods Tiers avec Patches** | Trampolines, substitution `__code__` | **GNU AGPLv3** (Œuvre dérivée) | Obligatoire (AGPLv3) |

---

## 4. Mention d'Attribution Obligatoire (AGPLv3 §7(b))

Toute application ou interface intégrant le moteur Axiom AI doit préserver la mention :

> *"Based on Axiom AI (https://github.com/Frosoore/AxiomAI) by Pinpanicaille and Frosoore."*
