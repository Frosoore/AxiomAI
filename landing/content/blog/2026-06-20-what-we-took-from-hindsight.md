+++
title = "What we took from Hindsight"
slug = "what-we-took-from-hindsight"
date = "2026-06-20"
author = "Pinpanicaille"
summary = [
  "Axiom's memory got a serious rework, inspired by an open-source project called Hindsight.",
  "NPCs can now keep facts, form opinions that shift over time, and hold a living profile of who they are.",
  "It's all optional, and the offline mode that never touches an AI still works exactly like before.",
]
+++

For a long time, Axiom's memory was honest but kind of dumb. When the game needed to remember something, it grabbed a few past snippets of text that looked similar to the current moment and dropped them into the prompt. That's classic retrieval, it works, and for short sessions you barely notice the limits.

The problem shows up on long campaigns. You insult a merchant in hour one, do a hundred other things, come back in hour six, and the merchant greets you like a stranger. The raw text was technically "in there" somewhere, but nothing turned it into something the NPC actually carries around. Memory was a pile of quotes, not an understanding.

So we went looking, and we found Hindsight.

## What Hindsight is

Hindsight is an open-source memory system (MIT licensed). It's built for a totally different world than ours, a server backend with Postgres and an API, so we did not copy their code. What we took was the way they think about memory, and we rebuilt it on our own stack, which is local, file-based and offline-friendly.

Three ideas stuck with us.

## 1. Search that actually understands

The old retrieval matched on meaning only, which sounds great until someone types an exact name or a made-up word that carries no "meaning" for the model. So now we run two searches at once: one by meaning, one by exact words, then we merge the results. You get the best of both, the vibe match and the literal match.

This part is fully deterministic and runs offline. No AI call involved.

## 2. Facts, then beliefs

In the richer mode, the game quietly distills each turn into small **facts**, the who, what, when, where and why of what just happened. Atomic, boring, verifiable. Good memory is built on boring facts.

On top of those, it forms **beliefs**. A belief is an opinion that evolves: "the merchant resents me" can get stronger as more facts pile up, or fade, or flip when something contradicts it. That's the grudge that finally sticks. The merchant remembers.

## 3. A living profile per character

One layer up sits the **mental model**, a short profile of who a character is right now, rewritten as their beliefs change. Instead of feeding the AI a heap of scattered statements, it leads with a clean little character sheet. The narration gets a lot more consistent because the model starts from "here's who this person is" instead of reconstructing it every single turn.

## Two modes, your call

None of this is forced on you. There are two modes.

Lite mode is the default. It's deterministic, offline, and never sends your memory to an AI. It just got the smarter hybrid search, that's it.

Living mode is the opt-in. That's where facts, beliefs and profiles come to life, using the model you already configured, as a background job that never blocks your turn. You can turn each layer on or off. And because it all rolls back cleanly, rewinding the story rewinds the memory with it.

## What we left on the table

Hindsight also ships a full agent that reasons about memory with its own tool-calling loop. It's clever, but it's overkill for a single-player game, and it would have cost a fortune in tokens. We kept the idea (a curated top layer) and dropped the machinery.

If you want the technical version, it's all in the engine docs under the memory guide. Otherwise, just flip on Living mode and go annoy a merchant. They'll remember.
