---
name: write-agents-md
description: "Use when writing, scaffolding, auditing, or trimming an AGENTS.md (or CLAUDE.md). Produces a lean, ownership-driven contract that front-loads project-specific invariants and runnable quality gates over generic best-practice filler."
---

# Writing an AGENTS.md

An AGENTS.md is loaded into the agent's context **every session**. Every line costs
budget and competes for attention. The goal is maximum signal per token: tell the
agent what it **cannot infer** about *this* repo, and nothing it already knows.

## The one test for every line

> Would a competent agent get this wrong without the line being here?

- **Yes** → keep it (project layout, invariants, exact commands, security boundaries).
- **No** → cut it. Generic best practice ("prefer enums", "write tests", "name things well")
  is already in the model. Restating it wastes budget and buries the signal.

## Ordering: load-bearing first

Put the rules that cause **bugs, data loss, or security holes if violated** at the top.
An agent that stops reading early must still hit the critical constraints first.

Recommended order:

1. **One-line repo identity** — what this is, language/stack, entry point.
2. **Invariants** — the non-negotiable correctness/security rules (see below).
3. **Architecture contract** — the source-layout ownership map.
4. **Quality gates** — exact runnable commands.
5. **Commit format.**
6. Everything else (type/serde/error conventions) only if project-specific.

## Section guide

### Repo identity (1–3 lines)
Stack, what the binary/package does, the single most important file. No fluff.

### Invariants (the highest-value section)
The rules that are specific to this repo and expensive to discover. Examples from real files:
- `Every records/categories query must filter on owner_user_id = ?` (multi-tenancy).
- `Never hold a read lock while acquiring a write lock in the same scope` (deadlock).
- `Do not print tokens, cookies, or credential file contents.`
- `Never .unwrap() in src/; use ? or .map_err`.

If the repo has none of these, the file can be short — that's fine. Don't invent ceremony.

### Architecture contract (the layout map)
A `path — owns X only` list. The map's job is to disambiguate **where new code goes**, not to describe what each file is.

- List a file when its ownership boundary isn't obvious from its name, or when sibling files could plausibly own the same thing (e.g. `records/finalize.rs` vs `records/settlement.rs`).
- Skip files whose name already says what they own (`config.rs`, `cli.rs` with no siblings).
- Add boundary rules only for the mistakes an agent would plausibly make — not the contrapositive of every layout line.

### Quality gates
Exact, copy-pasteable commands the agent runs before handing off. This is the most
actionable content in the file — prefer it over prose like "make sure tests pass".

```bash
<format command>
<lint command, e.g. with -D warnings>
<test command>
```

State what to do when a gate can't run (missing tooling/network/credentials): say so in
the handoff rather than skipping silently.

### Commit format
One block. `<type>: <imperative summary>`, allowed types, 2–3 examples, ban vague messages.

### Conventions (types / serde / errors / naming) — OPTIONAL
Include a rule here **only if it is project-specific**, e.g. "`serde_json::Value` allowed
only at the raw-compat boundary, convert to typed models elsewhere." Cut anything that is
just language best practice. If a whole section is generic, delete the section.

## Things to cut (common bloat)

- Generic type-system lectures ("prefer enums over strings", "Option for real optionality").
- Hedged prose ("where practical", "when possible", "unless compatibility requires") — an
  agent can't act on soft guidance crisply. Make it a rule or drop it.
- The contrapositive boundary rules that just restate the layout map.
- Arbitrary numbers stated with sub-bullets (a soft "~600 LOC, split by ownership" is one line).

## Style rules for the file itself

- Prefer **rules and commands** over explanations. Verifiable > aspirational.
- Keep it scannable: short sections, bullets, fenced command blocks.
- Match the repo's real state — don't describe tests/tooling that don't exist.
- A lean 40–80 line file usually beats a 200-line one. Trim until every line passes the test above.

## Skeleton

```markdown
# AGENTS.md — <name>

<One line: stack, what it does, entry point and main data store.>

## Invariants
- <hard correctness/security rule that causes bugs if broken>
- <...>

## Architecture contract
- `path/a` — owns X only.
- `path/b` — owns Y only.

Boundary rules:
- <only the ones an agent would plausibly get wrong>

Avoid catch-all modules (`utils`, `helpers`, `misc`); name files by domain. Target ~600 LOC, split by ownership.

## Quality gates (run before handoff)
\```bash
<fmt>
<lint -D warnings>
<test>
\```

## Commit format
`<type>: <imperative summary>` — types: feat, fix, refactor, docs, chore.
Avoid `update`, `cleanup`, `wip`.

## Conventions  <!-- only if project-specific -->
- <project-specific rule, e.g. raw-JSON boundary, error constructor, multi-tenancy filter>
```
