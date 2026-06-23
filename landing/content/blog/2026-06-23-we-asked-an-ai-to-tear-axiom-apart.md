+++
title = "We asked an AI to tear Axiom apart"
slug = "we-asked-an-ai-to-tear-axiom-apart"
date = "2026-06-23"
author = "Pinpanicaille"
summary = [
  "A stranger gave me a tip: feed your project to a capable AI and tell it to attack your assumptions, not flatter them. So we did.",
  "The uncomfortable finding: our 'deterministic firewall' guards the game-state numbers, not the story text, so the prose can still fib for a turn.",
  "Nothing here is fatal. Two fixes plus our existing test-harness and actor-model plans just moved to the top of the roadmap.",
]
+++

A while back, someone outside the project gave me a piece of advice that stuck. Roughly: take your whole project, hand it to a capable AI, and tell it to question your assumptions, and its own, without being dismissive. Don't ask it to agree with you. Ask whether your thing is actually unique, because maybe there's an Axiom out there already, under some other name, in a research paper somewhere. Not to kill your motivation, but to learn from what those others got wrong.

That's good advice, so we ran the experiment on Axiom itself. This post is what came out of it.

## The procedure

No hand-waving, no "summarize the README and tell me it's cool". We did two things for real.

First, a line-by-line read of the engine's most important file, the Arbitrator. That's the part we keep bragging about, the deterministic layer that's supposed to keep the AI honest. All 1466 lines of it, no skimming.

Second, a sweep of the field. Academic work (neuro-symbolic interactive fiction, benchmarks that grade LLMs as game engines, the "generative agents" line of research, the recent wave of agent-memory papers) and the consumer products (AI Dungeon, NovelAI, Friends and Fables, Hidden Door, and the rest). The goal was blunt: is any single thing Axiom does actually new, and where are we weaker than we tell ourselves.

## Is Axiom even unique?

Honest answer: no single piece is brand new. A deterministic layer validating an LLM's moves? People do that. Off-screen world simulation with autonomous characters? There's a whole research lineage. Event sourcing with rewind, evolving memory, an in-game clock that moves while you're away? All of it exists somewhere, sometimes in a paper written independently that describes almost exactly our time system.

What's rare is the combination, finished and integrated, running fully local, shipped as both an app and a Python library. Most of the prior art is a demo or a paper that was never maintained, missing saves, missing local support, missing the boring glue that makes a thing usable. So the moat isn't a clever idea. It's that the whole thing actually works together, on your machine. That's a more honest pitch, and frankly a better one.

## The uncomfortable bit

Here's the part that stung.

We say "every narrative turn is validated against a deterministic state machine before being committed." Reading the actual code, that's only half true.

The AI produces two things at once: the story text, and a structured list of state changes (you lost 10 HP, you gained 3 gold, you moved here). The Arbitrator checks the structured list. It rejects illegal moves, like spending gold you don't have. That part is real and it works.

But the story text itself is never checked against the numbers. It gets shown to you immediately, and saved, before any validation. So the AI can write "you cleave the dragon clean in half" while the change that actually kills the dragon gets rejected or never declared at all. You read the win. The database disagrees. And the only correction is a quiet hint slipped into the next turn, asking the AI to walk it back. The lie already happened.

A couple of smaller things fell out of the same read. The firewall blocks negative resources, but it happily accepts absurd values (set your HP to 9999, sure) and illegal teleports. And we found a likely bug where Companion mode's "plot armor" doesn't actually protect the hero the way the comment claims.

None of this is a disaster. The deterministic rules engine, the event sourcing, the rewind, all of that is solid. But the headline claim was oversold, and the fix matters.

## So what now

The audit turned straight into roadmap items, and you can see them on the Dev page.

The cheap fixes are going in by default, because they cost nothing extra: make the AI return structured output instead of us parsing text with a regex, add real value bounds and legal-move checks, fix that plot-armor bug. That's just the firewall finally doing what we said it did.

The expensive fix (a second AI pass that resolves your action first, then writes the prose around the real outcome, so the story can't lie) is optional. Which leads to the other new item: cost controls. As we add more of these AI passes, we don't want to quietly grow your bill. So everything optional becomes a toggle, grouped under three simple budget presets (Thrifty, Balanced, Faithful), with the free deterministic safety net always on. You pick how much you want to spend per turn. We don't pick for you.

One nice surprise: two things we'd already planned, a test harness for community universes and a proper NPC actor model, turn out to be exactly where the serious research is heading. So those got validated, not invalidated. We just bumped them up.

## The honesty corner

We also rewrote our internal upgrade plan: cut the parts that are already done down to a one-line "shipped" note, and added everything the audit surfaced. It's early alpha, and this is the kind of thing we'll keep doing in the open: point a cold, slightly mean AI at our own work, write down what it finds, and fix it.

If your "unbreakable" feature has never been read by something that wanted to break it, you don't actually know it holds. Now we know a bit more about where ours doesn't. That's a good day.

Signed, Pinpanicaille.
