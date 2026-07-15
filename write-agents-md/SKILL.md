---
name: write-agents-md
description: "AGENTS.md (or CLAUDE.md): write, scaffold, audit, or trim into a lean ownership-driven contract. Front-load project invariants and runnable quality gates; cut generic best-practice filler."
---

# Writing an AGENTS.md

An AGENTS.md is loaded **every session**. Maximum signal per token: only what a competent agent **cannot infer** about *this* repo.

## The one test

> Would a competent agent get this wrong without the line being here?

- **Yes** → keep (layout, invariants, exact commands, security boundaries).
- **No** → cut. Generic best practice is already in the model.

Every branch below is done only when every remaining line passes the one test, and removing any remaining line would cause a wrong action.

## Branches

### Scaffold / write
1. Repo identity — stack, what it does, entry point (1–3 lines).
2. Invariants — mine the codebase for multi-tenancy filters, lock order, secret handling, panic/unwrap bans; only real ones.
3. Architecture contract — `path — owns X only` where ownership is non-obvious or siblings could collide.
4. Quality gates — exact copy-pasteable commands from the repo's real tooling.
5. Commit format — one block if the repo has one.
6. Conventions — only project-specific rules; delete a whole generic section.

Done when: invariants are load-bearing and real; gates run (or handoff says why not); no section fails the one test.

### Audit / trim
Walk every line with the one test. Cut no-ops, hedged prose ("where practical"), contrapositive boundary rules that restate the layout map, and type-system lectures. Prefer rules and commands over explanations.

Done when: every remaining line passes the one test; critical invariants still sit above optional conventions.

## Ordering (load-bearing first)

An agent that stops early must still hit the rules that cause bugs, data loss, or security holes:

1. Repo identity
2. Invariants
3. Architecture contract
4. Quality gates
5. Commit format
6. Conventions (only if project-specific)

## Section content

### Invariants
Repo-specific, expensive to discover. Examples:
- `Every records/categories query must filter on owner_user_id = ?`
- `Never hold a read lock while acquiring a write lock in the same scope`
- `Do not print tokens, cookies, or credential file contents.`
- `Never .unwrap() in src/; use ? or .map_err`.

None found → keep the file short. Don't invent ceremony.

### Architecture contract
Disambiguate **where new code goes**, not what each file is.
- List a file when ownership isn't obvious from its name, or siblings could own the same thing.
- Skip files whose name already says the ownership (`config.rs`, `cli.rs` with no siblings).
- Boundary rules only for mistakes an agent would plausibly make.
- Soft cap: each file ~600 LOC max; over that, split by purpose/ownership. Avoid catch-all modules (`utils`, `helpers`, `misc`).

### Quality gates
Exact commands before handoff — prefer over "make sure tests pass".

```bash
<format>
<lint, e.g. -D warnings>
<test>
```

If a gate can't run (tooling/network/credentials), say so in the handoff; never skip silently.

### Commit format
`<type>: <imperative summary>` — allowed types, 2–3 examples, ban vague messages (`update`, `cleanup`, `wip`).

### Conventions — OPTIONAL
Only project-specific rules (e.g. raw-JSON only at a compat boundary). Generic language advice → delete the section.

## Style of the file itself

- Rules and commands over explanations. Verifiable > aspirational.
- Short sections, bullets, fenced commands.
- Match the repo's real state — no phantom tests/tooling.
- Lean 40–80 lines usually beats 200. Trim until every line passes the one test.

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
- <project-specific rule>
```
