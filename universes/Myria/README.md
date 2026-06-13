# Myria — default universe

The universe bundled with Axiom AI, in [Universe-as-Code](../../docs/guides/universe-format.md)
format. Based on the original fiction *Myria* by 17h59 (source wiki: post-divine steampunk
fantasy, year 5281).

```console
$ axiom compile universes/Myria/     # build the .db cache
$ axiom play universes/Myria/        # play it in the terminal
```

Play starts in **Highport**, capital of the Republic of the High-Ports.

## Adaptation notes

- The lore book (`lore/`) contains only what an educated inhabitant of Myria could know.
  The world's secrets (the dead gods, Alea, Arodan's identity, the Coalition manhunt, the
  Imperial Crypt) live in `lore/_global_lore.md`, which only the narrator sees — they are
  meant to be uncovered through play.
- Names invented for playability where the source wiki had placeholders: **Highport** (the
  Republic's unnamed capital), its districts and POIs, **Cinderhold** (the Empire's capital),
  the calendar month names, and the local NPCs Maela, Ysolde Brask and Sereth Voss.
  Arodan/Calder Veyran, Arven Deymar, the nations and the Coalition are canon.
- The divine war's concrete mechanics are deliberately vague in the source; the universe
  keeps them vague.
