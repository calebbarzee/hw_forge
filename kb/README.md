# hw_forge knowledge base

Accumulated hyper-specific hardware knowledge: named parts, named toolchains,
named projects, measured numbers. One fact-cluster per file.

Generic knowledge does not live here. A KiCad API behavior, a physics or
electronics rule, a mechanical formula, a printability constraint: those belong in
`skills/hw-design/references/`. The split rule:

> If a fact only makes sense once you name a part, a firmware, a vendor library, or a
> project, it is a card. If it is a rule, a formula, or a decision tree that applies
> to any board, it is a reference.

When a generic rule was learned from a specific incident, the reference states the rule
and cites the incident in one line; the card holds the specifics. If you find yourself
writing a generic rule in a card, promote it to the reference instead.

## Where a fact lives: card, library, or table?

A datasheet check or a physical measurement produces a fact. Where it goes depends on
what kind of fact it is, not on where the check ran.

| Fact learned from a datasheet or a physical check | Authoritative home |
|---|---|
| Pad or courtyard geometry that differs from a stock footprint | A project-local footprint in `kicad/lib/<project>.pretty/`, forked from the stock footprint with `scripts/kicad_fplib.py fork`. The change and its source go in the footprint's own `(descr ...)` and `(tags ...)` (`kicad_fplib.py annotate`) and in a `lib/PROVENANCE.md` row (`kicad_fplib.py provenance-row`). |
| A 3D model | `kicad/lib/3dmodels/`, with its `(model ...)` line written into the footprint (`kicad_fplib.py set-model`), the same `${KIPRJMOD}`-anchored convention every footprint in the project already uses. |
| A nominal package dimension generic to a package family (SOIC-8 wide's 7.5 mm body, SOD-123's 2.675 mm body) | `scripts/packages.json`, with a citation, so every project checking that family benefits, not only the one that found it. |
| A part-specific fact with no generic home: a pin-order variant, a marking, a supplier substitution | A `kb/` card. |
| Ordering and BOM (bill of materials) fields: manufacturer, part number, description, LCSC (LCSC Electronics, the parts distributor) number, package | `design.py`'s part table. The schematic emitter writes them into the symbol's own fields, so the BOM and the schematic cannot disagree. |

**A card alone never closes a geometry finding.** A `kicad_fpcheck.py` FAIL, or a
datasheet that disagrees with a stock footprint's pads, is closed by forking the
footprint and recording why, in the library, not by writing the disagreement down.
Where a card exists for the same part, it points at the library fork and the
provenance row instead of repeating the numbers; the numbers live once, in the
footprint and the table that checks it. This is the same discipline the 3D-model flow
already established (a resolved model goes into `kicad/lib/3dmodels/` and a `(model
...)` line, not only into a note that a model was found), stated once here so a
geometry finding follows the same rule instead of stopping at a card.

This is the split rule one level down. The split rule above says whether a fact is a
card or a reference; this table says, for a geometry or 3D-model finding specifically,
whether it is a card at all, or something a gate reads directly.

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
| `source` | where the knowledge came from: project + version, a run id, or a URL. Multiple sources: a list. |
| `date` | when the card was last verified, not when it was created. Bump it on every update. |
| `confidence` | one of the four values below. Set it accurately; a wrong confidence is worse than a missing card. |

### Confidence values

| Value | Means |
|---|---|
| `verified-in-hardware` | measured or observed on an assembled, powered board. |
| `verified-in-cad` | proven by a passing gate: a design rule check (DRC), an electrical rule check (ERC), a schematic-parity check, a `verify()` pass, a fab-check assertion, or read directly out of an as-built file. Not yet physically built. |
| `researched` | taken from a datasheet, vendor doc, or an existing routed reference design; internally consistent, not independently confirmed. |
| `needs-verification` | stated from general knowledge or inference. Must carry an explicit "what a research pass must confirm" list. |

A card may mix confidences internally. When it does, mark the weaker claims inline
(`(needs-verification)`) and set the frontmatter to the weakest load-bearing claim.

### Scoped negatives: a negative must name its own search

A card that records a negative ("no footprint for X exists locally", "no vendor figure for
Y", "no upstream example of Z") must name what was searched: the paths globbed
and the patterns tried. Not the conclusion alone. This is a requirement, not advice. A
negative without its scope is unusable, because a later reader cannot tell whether it still
holds.

The near-miss that forces the rule: `local-libraries.md` correctly said "no nice!view
footprint was observed in either foostan `kbd.pretty` or ScottoKeebs `ScottoKicad`". A
time-pressured read turns that into "no nice!view footprint exists locally", and a full
parameterized nice!view footprint generator was sitting one directory over in
`z_board/ergogen/footprints/`, outside that card's search scope entirely.

A cached negative narrower than its own phrasing causes under-searching, which is the
opposite of what the recall convention exists to buy. Write the scope so the negative can
be re-tested, or invalidated, without redoing the whole search.

### Connector cards: `mating_direction` is a required field

A connector's section must state `mating_direction: +z | -z | +x | …` in
footprint-local axes, with the two-source rule applied to it like any other
pin fact.

Which way the cable leaves is in no machine-readable place. It is not in
the footprint (a name containing `Vertical` is a convention, not data), not in
`pads_bbox` or `fab_items`, and `kicad_geom` reports `protrudes: ["top"]` for a
connector whose cable is the tall thing.

Yet a whole chain of case consequence hangs on it: one vertical top-entry receptacle
changing board faces between revisions turned a one-line note ("the lead points down into
the bay") into a ~40 mm routed channel and a locally thickened wall (`mechanical.md` §6a).

### Pin-role facts: port first, label derived

State every pin-role fact in port terms first (`P0.09`, `P1.13`) and derive the
silkscreen or compatibility label from the card's own mapping table. Never write the labels
out again by hand in prose next to the table that defines them.

Live instance: `nice-nano-v2.md`'s headline trap is "the `D` labels are pro-micro
compatibility names, not nRF ports". Its own prose then repeated the mistake it warns
about, saying "D9/D10 are on the same castellations as NFC (P0.09/P0.10)". That sat
directly beside a table mapping D10 → P0.09, D16 → P0.10, D9 → P1.06.

A pin map that trusted the prose would have skipped a good pin (D9) and used a
near-field communication (NFC) pin (D16). Prose adjacent to a correct table is where this class of error hides, because the
table's correctness reads as the paragraph's.

## Recall convention

At the start of every phase, search the KB before doing any work:

1. by domain: the directory for the phase's subject (`kb/keyboards/`, `kb/power/`, …);
2. by tag: the part numbers, net names and symptoms in the current task;
3. by grep: the part number, error string, or API symbol you are about to touch.

Read the matching cards before writing code or prompts, and carry the relevant facts
into agent prompts verbatim. A trap that is written down and then rediscovered is a
pipeline failure, not a knowledge failure.

KB roots are a configurable path list, so an external knowledge-base repo can be
searched alongside this one.

## Harvest convention

At the end of every run, harvest:

1. List every fact that cost more than a few minutes to establish, every trap hit, and
   every number measured or read out of a file.
2. For each: is it generic (→ reference file) or specific (→ card)? Apply the split rule.
3. Update an existing card rather than creating a near-duplicate. Search first. If a
   card exists, edit its body, add tags, bump `date`, and raise `confidence` if the run
   upgraded the evidence (`needs-verification` → `verified-in-cad` → `verified-in-hardware`).
4. Only create a new card when the fact-cluster is new. New cards go in the
   directory matching their `domain`.
5. A fact that was rejected on evidence is knowledge. Record it, with the evidence,
   so it is not relitigated.
6. Corrections beat additions: if a run proves an existing card wrong, fix the card in
   place and note the correction and its date in the body.
7. A card that records a design win must be amended by the revision that gives it up.
   Reporting the loss in that revision's own output is not enough. Amend it in the card,
   where the next project will read it. A win recorded as advice ("place the display
   beside the connector, not over it") is read by later runs as a rule. A later revision
   that reintroduces the clearance problem the win eliminated has to say so in the card,
   or the card keeps misleading everyone downstream with no signal that it is wrong.
   State what was given up, which locked decisions cost it, and the number. (Live
   instance: `nice-view-display.md` §2a records that win, and a later revision
   contradicted it. See the REGRESSION note convention in `skills/hw-design/SKILL.md`.)

## Concurrent edits to one card

A card that several phases touch in one run needs a rule, or every editor has to read the
whole file to find out what it is allowed to invalidate.

One card reached four phases/runs of edits: two research passes, a verification harvest,
and a re-scoping, none of them by the same agent. The last one had to read ~200 lines to
discover that its own correction was about to invalidate an existing section's numbers.
That worked only because it happened to read carefully; nothing required a full read.

The convention, in order of preference:

1. One writer per card per phase. The orchestrator assigns it; two agents in the
   same phase do not both edit one card. Where two phases both have something
   to add, they hand their additions to the orchestrator, which merges.
2. Stamp section ownership where a card is long-lived: `§2a (phase 6, 2026-08-23)`.
   A later editor can then tell what it may update silently from what it must flag.
3. Split the card once it crosses ~150 lines or three contributing phases. Keeping a
   card small enough that a full read is cheap is the real fix; the stamps are the
   mitigation until then.

And the rule that holds regardless: a number you are superseding gets an explicit
"superseded by §X" note in place, never a silent deletion and never fresh numbers left
sitting next to stale ones.

Trigger rule: an UNSURE in a project doc is a harvest trigger. Anything a project doc
marks UNSURE, or records as an open risk or a deferred decision, gets harvested at the
point the project doc is written, not left for a later run to rediscover independently.

`z_board/CLEANUP.md` recorded months earlier that `ergogen/footprints` is a submodule-mode
gitlink (`git ls-files -s` shows mode `160000`) with no `.gitmodules` anywhere in the
repo. That is the bare-gitlink trap the research doctrine already names. Nobody ran
harvest on that line, so the KB carried no warning, and a later run nearly re-vendored from
that fragile path. The knowledge existed; the harvest was missing.

## Gap logs and their numbering

A validation or dry-run project keeps one gap log document with one monotonically
increasing counter, and the orchestrator owns the numbering, not the phase agent. A
phase appends to the existing sequence; it never restarts at 1 and never opens its own
numbering.

On hexpad, phases 4 and 5 both opened at `## 29`, so `#29`–`#38` named two different gaps
each, and cross-references already written into project source (`GAPS #25`, `GAPS #40`)
became ambiguous the moment it happened. The log alone gives no way to tell which gap such
a citation means, and no way to repair it.

The acceptable alternative, for phases that run in parallel: per-phase prefixed ids
(`P4-1`, `P6-3`) allocated by the phase itself, which cannot collide. Either convention
works. One of the two has to be in place.

Corollary: whoever renumbers a gap log afterwards leaves an old → new remap in the
document. Project source files cite the old numbers, and a renumber without a remap breaks
every one of those citations silently.

## Revision regression contracts

The same idea one level up. When a project is revised rather than built fresh,
the check set is as much an artifact as the check result. "All green" says
nothing about how many checks stopped running to get there, and a net-growing
count conceals a retirement just as well as a shrinking one does. hexpad's case
suite went 215 → 239 checks across rev 2, so the total rose while checks were
being dropped underneath it. Nothing in the run distinguished the one
legitimately retired check from a quietly deleted one.

The convention: dump the check names before the revision, diff them after, and
record every retirement with its reason. A retired check with a stated geometric
reason is knowledge worth harvesting; a retired check with no reason is a
regression nobody can see.

It applies to both gate families the pipeline has:

| Gate family | Dump / compare |
|---|---|
| mechanical check names | `case_verify.py --dump-names FILE` / `--baseline FILE` |
| DRC/ERC finding classes | `report.py --by-owner` / `--baseline FILE` |

Harvest picks up the reasons, not the counts. "This check no longer applies
because the display moved 7 mm west and no longer overlaps the receptacle in plan"
is the kind of durable fact a later revision needs: it names the check to
re-add the moment the display moves back.

## Layout

```
kb/
├── README.md                  this file
├── fabs/                      per-fab capability floors and their KiCad DRC encodings
├── keyboards/                 the keyboard domain (parts, firmware, geometry, libraries)
└── projects/                  per-project pointer cards: what it is, gate state, where its docs live
```

Add directories as domains appear; keep `domain` frontmatter in step with the path.
