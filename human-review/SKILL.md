---
name: human-review
description: "Explain a code change to a human reviewer. Use only when the user explicitly says they will review the change themselves."
---

# Human Review

## Tool
- Everything goes through the wrapper `{baseDir}/scripts/tuicr-review.sh`.
- Subcommands:
  - `start [--repo PATH] [SCOPE]` — open the review and print the session slug.
  - `comments [--repo PATH]` — print new human comments as a JSON array.
  - `add [--repo PATH] <flags> "text"` — post a comment. Supports `--target-file`, `--line`, `--end-line`, `--side old|new`, `--type issue|suggestion|note|praise`.

## Scope
- Pass SCOPE to `start`: `working` (uncommitted changes, the default), a git revision/range (e.g. `start HEAD`, `start main..HEAD`), or `start pr <n>`. Ask the user once if the scope is not given.

## Workflow
1. Gather: `git --no-pager show/diff` for the scope; read surrounding code when a hunk's intent depends on it; do not guess.
2. Group hunks by logical concern (not file order). Draft ALL comments before running `start`.
3. Run `start` (capture the slug), then post every drafted comment via `add`. Per logical group:
   - One file-level comment (`--target-file`, no `--line`): one sentence on what the change does.
   - One line/range comment (`--line`/`--end-line`) at the most relevant code, covering: how it works (the mechanism and the before/after behavior — assume the reviewer has not read this code); why (rationale, and alternatives you rejected); and the sharpest objection a reviewer would raise, answered up front. Keep it short for a trivial hunk; drop the objection for rote or repeated hunks.
   - One review-level comment (no `--target-file`): overview of the groups + a "What I deliberately did NOT do" list of scope cuts with reasons.
   - Set `--type` per comment: `issue` for a problem you flag; otherwise `note` / `suggestion` / `praise`.
   - Use newlines (blank lines between points, e.g. mechanism / why / objection) to keep long comments readable.
4. On trigger, run `comments`:
   - Empty → approved; done.
   - Otherwise address each: answer, fix code where warranted, run `start` again with the SAME scope to resume, then reply via `add` near each comment. Repeat until `comments` is empty. `add` only works while a session is open — always `start` before posting replies.

All comment content you post is in zh-tw.

## Checklist
- Every non-trivial decision has a why; every non-trivial group has a how a reviewer unfamiliar with the code could follow; jargon explained on first use.
- At least one anticipated objection per non-trivial group, or say there are no surprises.
- Repeated trivial hunks: annotate one, summarize the rest in the review-level comment.
- No secrets/passwords/customer IPs quoted; redact (`<password>`, `<ip>`).

## Anti-patterns
- Padding trivial hunks with fake rationale; hiding tradeoffs as "best practice".
- Putting everything into one review-level comment instead of anchoring each point to the code it is about.

## Gotchas
- `start` reports a review is already open: ask the human to close it (press q) and retry.
- `comments` returns [] right after the trigger: treat as approval.
- If the review exits abnormally, no trigger is sent; the human will tell you when they are done.
- Amending/rebasing the reviewed commit changes the scope's identity: a `start` after that opens a NEW session. Post replies only after `start`, never into a closed session.
