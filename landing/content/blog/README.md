# How to write a blog post

Each post is one Markdown file in this folder. Write it, run the build (or just
push, the GitHub Action rebuilds), and you get a styled article page, a card on
the blog index, and a fresh RSS entry. You never touch HTML or CSS.

## 1. Create the file

Name it `YYYY-MM-DD-some-slug.md` (the date prefix keeps the folder sorted).
Start with a TOML front matter block between `+++` lines, then the body:

```
+++
title = "Your title"
slug = "some-slug"          # the URL becomes blog/some-slug.html
date = "2026-07-05"         # YYYY-MM-DD, drives ordering + RSS
author = "Pinpanicaille"    # see "Signature" below
summary = [
  "First takeaway, one short sentence.",
  "Second takeaway.",
  "Third takeaway.",
]
+++

## First section

Your text here...
```

The `summary` (exactly 3 short points) is the **TL;DR** shown at the top of the
article, on the index card, and as the RSS description. Always fill it.

## 2. Writing style (important)

- **English only.**
- **Human, relaxed, a bit punchy.** Korben's tone is the reference: talk to the
  reader, no corporate stiffness, a little personality and humour are welcome.
- **Never use em dashes (—) or en dashes (–).** They read as AI. Use commas,
  parentheses, or just two sentences instead.
- Keep paragraphs short. Lead with the point, then explain.

## 3. Signature (byline)

- Posts written on the user's side are signed **`Pinpanicaille`**.
- If **Frosoore** writes a post, he signs **`Frosoore`** (his own name).

## 4. Markdown you can use

The body is rendered with markdown-it (CommonMark + tables + strikethrough). The
title comes from the front matter, so **start your sections at `##`**.

| You write            | You get                          |
|----------------------|----------------------------------|
| `## Heading`         | section title                    |
| `### Subheading`     | smaller title                    |
| `**bold**`           | **bold**                         |
| `*italic*`           | *italic*                         |
| `~~struck~~`         | ~~struck~~                       |
| `- item` / `1. item` | bulleted / numbered list         |
| `` `code` ``         | inline code                      |
| ```` ```lang ... ``` ```` | fenced code block           |
| `> quote`            | block quote                      |
| `[text](url)`        | link                             |
| `![alt](path)`       | image (use `../assets/...`)      |
| `---`                | horizontal rule                  |

All of it is pre-styled to the site theme, so it looks the same across every
article. Just write Markdown.

## 5. Preview / publish

```bash
python landing/build_site.py        # regenerate blog/, feed.xml from the .md files
python landing/build_site.py --check   # CI guard: nonzero if output is stale
```
Then open `landing/blog/index.html`. Pushing to `main` rebuilds and deploys.
