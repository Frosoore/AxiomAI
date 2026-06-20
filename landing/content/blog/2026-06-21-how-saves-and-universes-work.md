+++
title = "Under the hood: how saves and universes work"
slug = "how-saves-and-universes-work"
date = "2026-06-21"
author = "Pinpanicaille"
summary = [
  "We ran a full quality pass on the save and universe system, so here's a tour of how the thing actually works.",
  "Your universe is plain text you can read and version, the database is just a throwaway cache, and each save is one self-contained, shareable file.",
  "The QC caught a sneaky rewind bug, we fixed it, and we added a test so it can never sneak back.",
]
+++

We just spent a session doing quality control on the part of Axiom that holds your worlds and your games: the save and universe system. Good news first, it works, end to end, the way it's supposed to. But while we had the hood open, we figured we'd show you what's actually under there. It's one of the bits we're most proud of, and almost nobody ever sees it.

So grab a coffee. Here's how Axiom stores a universe and a game.

## Your universe is just text

Most apps store your world in some opaque binary blob. Open it in a text editor and you get garbage. We hated that.

In Axiom, a universe is a folder of plain text files. Characters, locations, lore, rules, the starting setup, each lives in its own little TOML or Markdown file. You can open them, read them, edit them by hand, drop them in a Git repo, diff two versions, whatever you want. The text is the truth. We call it Universe as Code.

```
Myria/
  universe.toml
  entities/        (the characters)
  locations/       (the map)
  lore/            (the lore book)
  rules/           (deterministic rules)
  setup/           (starting questions)
```

When the engine actually plays, it doesn't read all those files turn by turn. That would be slow. Instead it **compiles** the folder once into a single database file (a `.db` tucked away in a hidden cache folder), and reads from that.

Here's the important part: that database is disposable. Delete it and nothing is lost, the next launch just recompiles it from your text. The cache is a convenience, never the source of truth. If your files haven't changed, Axiom skips the recompile and reuses the cache. If they have, it rebuilds. You never think about it.

## One save, one file

Now the part people get wrong in other apps: your playthroughs are not glued to the world.

Every game you start lives in its own file, `save_<something>.db`, sitting in a `saves/` folder next to your universes. And it's fully self-contained. At creation, Axiom copies the universe definition right into the save. Your game carries its own little snapshot of the world.

Why bother? Two big wins.

First, you can patch a universe without bricking your saves. Fix a typo in a character, rebalance a rule, add a location, your existing games keep working. Next time you open one, Axiom notices the source changed and quietly resyncs the new definition into the save, without touching your story, your progress, or any character that only exists in your run. The world updates, your game survives.

Second, one save equals one file. That makes it trivial to back up, copy, or hand to a friend.

## Sharing: .axiom and .axiomsave

Two clean formats fall out of all this.

A whole universe exports to a `.axiom` file. It's really just a zip of your text folder plus the compiled cache, so whoever opens it can play instantly without a recompile. And it ships the **definition only**, your private playthroughs never travel inside a universe you share.

A single game exports to a `.axiomsave` file. That's your self-contained save, zipped up with its generated illustrations. Import it on another machine and if a game with the same id already exists, Axiom gives the newcomer a fresh id instead of stomping your existing one. No accidental overwrites, ever.

Old formats still load too. We convert legacy archives on the fly, because nothing is more annoying than an update that eats your old files.

## What the QC actually caught

Quality control isn't just clicking around and going "yep, looks fine". We replayed the whole lifecycle on our demo universe: compile, pack, unpack, create a save, duplicate it, export it, re-import it. All green.

Then we went hunting for the boring kind of bug, the silent one. And we found a good one.

A while back we taught the rewind feature to "un-fire" scheduled world events: rewind past the moment an event triggered, and it should be allowed to trigger again later. To do that, each fired event remembers the turn it fired on. Simple.

Except two code paths that copy a save (exporting an old-style embedded save, and duplicating one) were copying everything about those events **except** that one little turn number. So a rewound-then-exported game could end up with events that refused to re-fire. Nothing crashes, nothing shouts, it just quietly misbehaves much later. The worst kind.

We fixed both paths. And because this class of bug comes from a copy list drifting out of sync with the database shape, we added a test that fails loudly the moment they disagree again. Future us is covered.

## TL;DR for real

Your world is text you own. The database is a cache you can throw away. Each game is one portable file that survives world updates. And we just gave the whole machine a thorough once-over.

If you want the deep technical version, it's in the engine docs under the Universe as Code and saves guides. Otherwise, go make a universe, it's just files. You've got this.
