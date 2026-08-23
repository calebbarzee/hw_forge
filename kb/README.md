# hw_forge knowledge base

Accumulated **hyper-specific** hardware knowledge: named parts, named toolchains,
named projects, measured numbers. One fact-cluster per file.

Generic knowledge does **not** live here. A KiCad API behaviour, a physics or
electronics rule, a mechanical formula, a printability constraint — those belong in
`skills/hw-design/references/`. The split rule:

> If a fact only makes sense once you name a part, a firmware, a vendor library, or a
> project, it is a **card**. If it is a rule, a formula, or a decision tree that applies
> to any board, it is a **reference**.

When a generic rule was learned from a specific incident, the reference states the rule
and cites the incident in one line; the card holds the specifics. If you find yourself
writing a generic rule in a card, promote it to the reference instead.

## Card format

```markdown
---
domain: keyboards/zmk          # path-like, mirrors the directory layout
tags: [ext-power, spi, underglow, nrf52840]
source: z_board v0.4           # project/run name, or a URL
date: 2026-08-22
confidence: verified-in-hardware
---

# Short title naming the thing

Body: the knowledge, stated for reuse by someone who has not seen the source project.
Numbers with units. Traps stated as "X, not Y". Cross-reference sibling cards and the
relevant reference section.
```

### Frontmatter fields

| Field | Meaning |
|---|---|
| `domain` | path-like scope, mirroring the directory (`keyboards/zmk`, `power/lipo`, `projects/…`). One value. |
| `tags` | flat list of search terms: part numbers, signal names, symptoms. Lowercase. |
| `source` | where the knowledge came from — project + version, a run id, or a URL. Multiple sources: a list. |
| `date` | when the card was last *verified*, not created. Bump it on every update. |
| `confidence` | one of the four values below. Set it honestly; a wrong confidence is worse than a missing card. |

### Confidence values

| Value | Means |
|---|---|
| `verified-in-hardware` | measured or observed on an assembled, powered board. |
| `verified-in-cad` | proven by a passing gate — DRC/ERC/parity, a `verify()` pass, a fab-check assertion, or read directly out of an as-built file. Not yet physically built. |
| `researched` | taken from a datasheet, vendor doc, or an existing routed reference design; internally consistent, not independently confirmed. |
| `needs-verification` | stated from general knowledge or inference. **Must** carry an explicit "what a research pass must confirm" list. |

A card may mix confidences internally; when it does, mark the weaker claims inline
(`(needs-verification)`) and set the frontmatter to the **weakest** load-bearing claim.

## Recall convention

At the **start of every phase**, search the KB before doing any work:

1. by domain — the directory for the phase's subject (`kb/keyboards/`, `kb/power/`, …);
2. by tag — the part numbers, net names and symptoms in the current task;
3. by grep — the exact part number, error string, or API symbol you are about to touch.

Read the matching cards *before* writing code or prompts, and carry the relevant facts
into agent prompts verbatim. A trap that is written down and then rediscovered is a
pipeline failure, not a knowledge failure.

KB roots are a configurable path list, so an external knowledge-base repo can be
searched alongside this one.

## Harvest convention

At the **end of every run**, harvest:

1. List every fact that cost more than a few minutes to establish, every trap hit, and
   every number measured or read out of a file.
2. For each: is it generic (→ reference file) or specific (→ card)? Apply the split rule.
3. **Update an existing card rather than creating a near-duplicate.** Search first. If a
   card exists, edit its body, add tags, bump `date`, and raise `confidence` if the run
   upgraded the evidence (`needs-verification` → `verified-in-cad` → `verified-in-hardware`).
4. Only create a new card when the fact-cluster is genuinely new. New cards go in the
   directory matching their `domain`.
5. A fact that was *rejected on evidence* is knowledge — record it, with the evidence,
   so it is not relitigated.
6. Corrections beat additions: if a run proves an existing card wrong, fix the card in
   place and note the correction and its date in the body.

## Layout

```
kb/
├── README.md                  this file
├── keyboards/                 the keyboard domain (parts, firmware, geometry, libraries)
└── projects/                  per-project pointer cards: what it is, gate state, where its docs live
```

Add directories as domains appear; keep `domain` frontmatter in step with the path.
