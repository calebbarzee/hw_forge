---
description: Recall from or harvest into the hardware knowledge base: search cards by keyword and domain, or capture a lesson as a new card.
argument-hint: "recall <topic|domain> | harvest <lesson>"
---

# /hw-kb

Two modes. `$ARGUMENTS` starts with `recall` or `harvest`. If it starts with
neither, infer: a question is a recall, a statement of something learned is a
harvest. Say which you chose.

## KB (knowledge base) roots

Search **all** roots, in order:

1. the plugin's own `kb/` (`${CLAUDE_PLUGIN_ROOT}/kb/`)
2. every path in `HW_FORGE_KB_ROOTS`, colon-separated

```bash
echo "${HW_FORGE_KB_ROOTS:-<unset>}"
```

Read `kb/README.md` first. It defines the card format, the domain directories
and the index conventions, and it is the authority over anything here.

## Mode: recall

Find and synthesize; do not dump files.

1. **Search wide.** Match on the topic, on domain directory names, and on card
   tags. Hardware vocabulary is inconsistent, so try synonyms and both the
   generic and the specific term (`zone` / `pour` / `plane`; `insert` /
   `heat-set` / `boss`; `LED` / `addressable` / `WS2812`). Grep card bodies too,
   not just titles.
2. **Read what matches**, then **synthesize into an answer**: the facts that
   apply to the situation at hand, with the numbers, in your own words. Cite each
   card by path so it can be read in full.
3. **Say what you did not find.** A gap is actionable information: it tells the
   user this run is about to pay full price for something, and it is a candidate
   for harvest at the end.

Recall is also a pipeline step, not just a command. Run it at the start of every
phase, filtered to that phase's domain, before writing prompts or generator code.

## Mode: harvest

Capture the lesson in `$ARGUMENTS` as a card.

1. **Check for an existing card first.** Search the roots for anything covering
   this ground. A sharpened existing card beats two overlapping ones, because a
   search that returns both leaves the reader to reconcile them. If one exists:
   update it, and note what changed.
2. **Check it is a card at all.** `kb/README.md`'s split rule governs: if the fact
   only makes sense once you name a part, a firmware, a vendor library or a
   project, it is a card. If it is a rule, a formula or a decision tree that
   applies to any board, it belongs in `skills/hw-design/references/` instead:
   promote it there and let the card hold only the specifics. Then pick the
   domain and file location per `kb/README.md`. Follow its format exactly:
   frontmatter fields, tags, section order, and an honest `confidence` value set
   to the weakest load-bearing claim in the card.
3. **Write the card to be useful, not to be complete.**

   What earns a card:
   - a **trap**: something that looks correct, passes checks, and is wrong,
     including how it presents, because that is how it gets recognized next time.
   - a **number** that mattered, with the reasoning that produced it.
   - a **formula** or stack-up, worked, not just stated.
   - a **decision** and its evidence, so the question is not reopened.
   - a **"looks like a bug and is not"**, so nobody spends a session fixing it.

   What does not earn a card:
   - anything derivable in a moment.
   - anything a datasheet lookup answers.
   - narrative about what happened this run (that belongs in the project's
     history doc).
4. **Name the specifics, but write for a stranger.** Cards are deliberately
   hyper-specific (part numbers, module names, firmware, measured values), so
   keep those. What to strip is the *dependence on the source repo*: a reader who
   has never opened that project must still be able to use the card, so translate
   bare coordinates and internal variable names into the fact they encode.
5. **State the evidence, and set `confidence` to match.** Say how this was
   established: a violation count that went away, a passing gate, two sources
   that agreed, a measurement on a powered board. Every card states its evidence,
   and `confidence` never claims more than that evidence supports.

Then report the path written or updated, and a one-line summary of the card.

## The test

A card passes if the next session hitting the same situation can act from the
card alone, without rediscovering the fact.
