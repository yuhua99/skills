---
name: write-agents-md
description: "Write or audit an AGENTS.md or CLAUDE.md: mine repository-specific invariants, ownership boundaries, and runnable quality gates; remove stale or generic guidance."
---

# Writing repository instructions

Produce or revise the requested `AGENTS.md` or `CLAUDE.md`. Keep only repository-specific guidance that changes how a coding agent should act.

## 1. Mine the repository

Read the existing instruction file when present. Inspect entry points, source layout, build and package configuration, scripts, tests, and project documentation. Extract:

- correctness, security, data, concurrency, and error-handling invariants;
- ambiguous ownership boundaries that determine where code belongs;
- exact format, lint, test, and build commands;
- demonstrated commit rules and project-specific conventions.

**Done when:** every retained repository claim has a concrete source, and unsupported categories are empty.

## 2. Write the contract

Put load-bearing guidance first:

1. Repository identity: stack, purpose, entry point, and primary data store when relevant.
2. Invariants: exact rules whose violation causes incorrect behavior, data loss, or security risk.
3. Architecture contract: list paths only where ownership is ambiguous. Target about 600 LOC per source file; split larger files by ownership rather than into catch-all modules.
4. Quality gates: copy-pasteable commands discovered from repository tooling.
5. Commit format and conventions: include only those demonstrated by the repository.

Prefer direct rules and commands over explanations.

**Done when:** the file has no placeholders, phantom tooling, duplicate meanings, or unsupported repository claims; critical invariants precede optional conventions.

## 3. Run the gates

Execute every listed quality gate. Record each as passed, failed, or unavailable; give a concrete reason for every failure or unavailable gate.

**Done when:** every listed gate has an explicit result.

## 4. Apply the one test

Walk every line, including headings, examples, comments, and fenced commands:

> Would a competent agent get this wrong without the line being here?

Keep the line when the answer is yes; remove it when the answer is no.

**Done when:** every remaining line passes the test.
