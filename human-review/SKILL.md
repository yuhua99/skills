---
name: human-review
description: "Explain a code change to a human reviewer."
disable-model-invocation: true
---

# Human Review

Write comments in **zh-tw**.

## Tool
`{baseDir}/scripts/tuicr-review.sh`:
- `start [--repo PATH] [SCOPE] --comments FILE` — open a review, post FILE, then show it; prints the slug and each posted `{id, location}`.
- `comments [--repo PATH] [--mine]` — print new comments as JSON; `--mine` prints your own comments with their ids.
- `add [--repo PATH] --input FILE` — post more comments to the open review.
- `delete [--repo PATH] <comment-id>` — remove one of your comments.

Ask once if SCOPE is missing. Use `working`, a revision/range, or `pr <n>`.

Comments file: one JSON object per line, posted in order. Keys: `file`, `line`, `end_line`, `side` (`old|new`, default `new`), `comment_type` (`issue|suggestion|note|praise`), `content`. Omit `line` for a file-level comment; omit `file` too for a review-level one. Other keys are rejected.

`start` exits non-zero after printing the slug → the review is open but stderr lists comments that failed; put those in a new file and `add --input` it instead of `start` again. They land after the others.

## Workflow
1. Read the scoped `git show/diff` and surrounding code.
   Act as the change's author walking a human through the implementation, rather than conducting a separate defect review.
   Done when you can explain the old and new behavior of each meaningful changed block.

2. Group hunks by concern and draft all comments into a temp comments file.
   Split each hunk into logical blocks of one or a few adjacent lines. Explain each block's old behavior -> change -> new behavior, and why; explain intent and effects rather than paraphrasing syntax.
   Give distinct changes within a function separate comments, anchored to the relevant lines.
   Summarize tests, codegen, and pure moves in one line per logical group; still name any behavior or test-expectation changes. For copied blocks, name the source in one line; explain any differences from the source and their behavioral effects separately.
   Ground reasons in the implementation context; label inferred reasons as assumptions.
   Add a likely objection or toy before/after only when it clarifies a trade-off or a confusing change. Redact secrets.
   Done when every changed hunk is covered by block-level explanations or explicitly included in a brief-summary exception above.

3. Order the file, then run `start SCOPE --comments FILE`:
   - Review-level first: the change's purpose, which concern to read first, and why.
   - Inline: the block-level explanations and brief summaries from step 2. Anchor each to the relevant code.
   - File-level: only context not already covered by the review-level or inline comments.
   - Use `issue` only for problems.

4. Follow-up:
   - `approved` → stop.
   - `Human quit with X/Y files reviewed` → ask whether to `start` the same scope again.
   - New comments → address each, fix as needed, `delete` your comments the fix made obsolete, then `start` the same scope with a comments file holding only the reply and any new *delta*.
   - Fetch failure → run `comments` manually.

## Gotchas
- Existing open review → ask the human to press `q`, then retry.
- Abnormal exit sends no trigger.
- Amend/rebase creates a new scope identity; start a new session.
