# skills

Skills are everywhere, but these ones are mine.

A collection of AI agent skills I've written for my own workflows.

## Skills

- [`discord/`](./discord) — Read-only Discord access for agents: sync channels into a local SQLite cache, search and read recent messages, or use Discord's native search via a bundled stdlib CLI (user token via `DISCORD_TOKEN`).
- [`google-map/`](./google-map) — Google Maps place search, place details, opening hours, route/travel-time calculation, and KML export for Google My Maps via a bundled CLI (Places API + Routes API).
- [`human-review/`](./human-review) — Explain a code change to a human reviewer: groups diff hunks by concern and writes a WHAT / WHY / REVIEWER FLAG walkthrough, ending with deliberate scope cuts.
- [`write-agents-md/`](./write-agents-md) — Guidance for writing, scaffolding, auditing, or trimming an `AGENTS.md` (or `CLAUDE.md`) into a lean, ownership-driven contract focused on project invariants and runnable quality gates.

## Install

Each skill lives in its own subdirectory and can be installed individually:

```bash
bunx skills add https://github.com/yuhua99/skills
```

See each skill's `README.md` or `SKILL.md` for setup and usage details.
