---
name: human-review
description: "Explain a code change to a human reviewer. Use only when the user explicitly says they will review the change themselves."
---

# Human Review

All comment text is **zh-tw**.

## Tool
- Wrapper: `{baseDir}/scripts/tuicr-review.sh`.
- Subcommands:
  - `start [--repo PATH] [SCOPE]` — open the review; print session slug.
  - `comments [--repo PATH]` — new human comments as a JSON array.
  - `add [--repo PATH] <flags> "text"` — post a comment. Flags: `--target-file`, `--line`, `--end-line`, `--side old|new`, `--type issue|suggestion|note|praise`.

## Scope
Pass SCOPE to `start`: `working` (uncommitted, default), a git revision/range (e.g. `start HEAD`, `start main..HEAD`), or `start pr <n>`. Ask once if scope is missing.

## Workflow
1. Gather: `git --no-pager show/diff` for the scope; read surrounding code when a hunk's intent depends on it.
2. Group hunks by **logical group** (concern, not file order). Draft every comment before `start`.
   Done when: every non-trivial group has how + why + one anticipated objection (or "no surprises"); trivial/repeated hunks are annotated once and summarized at review level; secrets redacted (`<password>`, `<ip>`).
3. `start` (capture slug), then `add` every drafted comment. Per logical group:
   - File-level (`--target-file`, no `--line`): one sentence on what the change does.
   - Line/range (`--line`/`--end-line`) at the most relevant code: **how** (mechanism, before/after — assume the reviewer has not read this code); **why** (rationale + rejected alternatives); sharpest reviewer objection, answered up front. Short for a trivial hunk; drop the objection for rote/repeated hunks.
   - Review-level (no `--target-file`): overview of the groups + **scope cuts** ("What I deliberately did NOT do") with reasons.
   - `--type`: `issue` for a problem you flag; else `note` / `suggestion` / `praise`.
   Done when every logical group is anchored to its code (file- or line-level), not only the review-level overview.
4. On trigger, `comments`:
   - `[]` → approved; stop.
   - Else address each: answer, fix code where warranted, reply via `add` near the comment, then `start` again with the SAME scope. Repeat until `comments` is `[]`.

## Gotchas
- `start` says a review is already open → ask the human to close it (press q), retry.
- `comments` returns `[]` right after the trigger → treat as approval.
- Abnormal exit sends no trigger; the human will say when they are done.
