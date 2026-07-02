# <Commit subject / change description>

**TL;DR:** <problem in 1 sentence> → <solution shape in 1 sentence>. <One line of essential context if needed; otherwise omit.>

---

## File 1: `<path>` (+X -Y)

### <Logical concern name>

```<lang>
<minimal hunk excerpt — just enough to anchor the discussion>
```

**What:** <one-sentence mechanical summary>

**Why:** <design rationale; alternatives rejected and why; constraints that forced the choice>

> **Reviewer flag:** "<anticipated objection in reviewer voice>" — <answer>

(Repeat per logical concern in this file. For repeated mechanical hunks, show one + summarize the rest in one line.)

---

## File 2: `<path>` (+X -Y)

(Same shape.)

---

## What I deliberately did NOT do

| Skipped | Reason |
|---|---|
| <thing the reviewer might ask about> | <why it is out of scope / deferred / not needed> |
| <thing> | <reason> |

---

## Known gaps (optional — only if truly present)

- <gap 1: what's missing, blast radius, when to fix>
- <gap 2>

---

## Verification (optional — only if you ran something)

- <command that proves the change works>
- <expected vs. actual output, briefly>
