+++
title = "Axiom is getting mods"
slug = "axiom-is-getting-mods"
date = "2026-10-03"
author = "Pinpanicaille"
summary = [
  "Axiom is turning into a small kernel plus mods you can tick on and off, Minecraft style.",
  "Even the core features (memory, time, inventory, the interfaces) are becoming mods you can swap out.",
  "A first version exists on a separate branch, it is not ready yet, and we are fixing it before merging.",
]
+++

Remember the "quiet, but stable" post from last month? Well, it stayed stable. It did not stay quiet.

We started working on the biggest change Axiom has had so far: **mods**.

## The idea

Today, every feature of Axiom is baked into the engine. Memory, time, inventory, image generation, the desktop app, the web app, all of it. If you want something different, you have to dig into the code.

The plan is to flip that around. Axiom becomes a tiny kernel that does almost nothing on its own, and everything else becomes a mod. Think Minecraft with Fabric, or Skyrim with its load order:

- a mod is a single `.axmod` file you import;
- you tick it on or off in a list;
- mods can depend on other mods, and the order of the list decides who wins when two of them touch the same thing;
- and the features we ship (memory, time, inventory, the interfaces...) are mods too, so you can disable them or replace them with someone else's version.

Want a completely different memory system? Write a mod that takes over the memory slot. Want a hunger gauge that drops over time? That's a small mod. Want to use Axiom for something that isn't role-play at all? In theory, even the turn itself is a mod.

## Mods written by an AI

The part I'm most excited about: making a mod should be simple enough that an AI can write one for you. You ask "add a hunger gauge that goes down every hour", Axiom drafts the mod, shows you exactly what it's going to install, and you say yes or no.

That only works if the mod API is small, documented, and honest about what it does. So a lot of the work so far went into the boring part: rules about what the kernel is allowed to know, how mods store their data so rewinding a game still works, what happens when a mod crashes (spoiler: the mod gets turned off, not your game).

## Where we are, honestly

Frosoore built a first version on a separate `mods` branch, and it's a big one. Some of it is really solid: you can already disable most features one by one and the game keeps running.

But we reviewed it closely, and it is **not ready**. The turn engine is still wrapped inside the kernel instead of living in its own mod, a few promises are only half kept, and the review found some regressions (like the narrator no longer being told when one of its moves got rejected). We've already fixed a good chunk of that, and the rest is written down in a public status file so nothing gets lost.

So: no merge yet, no release yet, and definitely no mod store yet. When it lands on the main branch, you'll hear about it here.

## One more thing

We haven't decided anything about licensing for third-party mods. Until we do (after some proper legal advice), everything stays under the project's AGPL-3.0-or-later, same as today.

If you have ideas of mods you'd want, or features you'd love to rip out of Axiom, come tell us on Discord or open an issue. That's exactly the kind of feedback that shapes the API.

See you around.
