---
name: human-review
description: "Explain a code change to a human reviewer. Use only when the user explicitly says they will review the change themselves."
---

# Human Review

## Scope

- Default target: `HEAD`. Other modes: `--commit <sha>`, `--range a..b`, `--staged`, `--working`.
- Ask once only if ambiguous.

## Workflow

1. **Gather**:
   - `git --no-pager show --stat <ref>` then `git --no-pager show <ref>`.
   - For uncommitted, use `git diff [--cached]`.
   - Read surrounding code if a hunk's intent depends on it; do not guess.
2. **Group hunks by logical concern**, not by file order.
   - Repeated mechanical hunks: show one + summarize the rest in a line.
3. **For each group, write WHAT / WHY / REVIEWER FLAG**:
   - **WHAT**: one-sentence mechanical summary. Skip line-by-line narration.
   - **WHY**: design rationale; name alternatives rejected;
     say "forced choice" if there was none.
   - **REVIEWER FLAG**: the sharp objection a reviewer would raise,
     phrased and answered up front. Skip only for truly mechanical hunks.
4. **Render** following `references/template.md`. Cut empty sections; do not pad.
5. **End with "What I deliberately did NOT do"** — table of scope cuts with reasons.
6. **Self-check** the checklist below before sending.

## Checklist

- [ ] Every non-mechanical decision has a WHY.
- [ ] ≥1 REVIEWER FLAG per non-trivial group (or explicit "no surprises").
- [ ] Repeated hunks summarized, not pasted.
- [ ] "What I did NOT do" section present.
- [ ] No secrets / passwords / customer IPs quoted from the diff; redact (`<password>`, `<ip>`).
- [ ] Output in zh-tw.
- [ ] No overly long lines; wrap for human readability (aim ≤200 chars).

## Anti-patterns

- Narrating the diff line-by-line (reviewer can read it).
- Padding trivial hunks with fake rationale.
- Hiding tradeoffs as "best practice".
- Per-file walk instead of per-concern walk.
- Skipping "what I didn't do".

## Output

- Write to `./review-<ref>.md` in the current working directory by default.
  - Examples: `./review-10d9caa3.md`, `./review-staged.md`, `./review-working.md`.
  - Overwrite if the file exists.
- After writing, reply in chat with just the file path and a 2-3 line summary.
  - Inline in chat only if the user asks.
- If >500 diff lines or >5 files, still write the full file,
  but in chat offer to walk through it section by section.
