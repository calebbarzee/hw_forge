---
description: Acquire hardware design resources: datasheets, footprint libraries, reference designs. Local machine first, then web; vendor them with a provenance manifest and two-source pin verification.
argument-hint: "<part or topic, e.g. 'nice!view display' or 'MSK12C02 switch footprint'>"
---

# /hw-research

Resource acquisition for: **$ARGUMENTS**

The goal is not "find information". It is to end with the *asset* in the project,
recorded well enough that a future session can tell where it came from and
whether to trust it.

## 1. Local machine first

Search the local disk before the web, always. Proven, already-fabbed boards on
this machine are better evidence than any datasheet excerpt or forum post,
because they are known to have worked.

- Other hardware projects in the user's directories: their `lib/` folders,
  vendored footprints, generated symbols.
- Installed KiCad libraries. If KiCad ships the part, use it: only make a part
  project-local when there is genuinely no equivalent, and say why.
- Existing reference designs: `.kicad_pcb` / `.kicad_sch` for a board using the
  same part. Parse them. A footprint's actual pads read out of a board file beat
  a specification you can't check.
- Any local vendor SDK, firmware repo or hardware-design guide.
- The knowledge base: `/hw-kb recall <topic>` may already have the answer.

Report what you found locally before you go outward. "Nothing local" is a real
finding and worth stating.

## 2. Then the web

Datasheets, official hardware repos, upstream footprint libraries, vendor docs.
Prefer primary sources: the manufacturer's datasheet, the module vendor's own
schematic, the upstream library repo at a specific commit. Forum threads are
useful for *traps* and useless for pin numbers.

## 3. Verify pin tables against two independent sources

**Do not trust a single source for a pin table, ever.** Two independent sources
must agree before a pin table enters the design. Independent means genuinely
different lineage: a vendor datasheet and a shipped reference board, not two
blog posts copying each other.

The failure this catches is silent. A symbol whose numbering disagrees with its
footprint produces a board that is fully connected, clean under DRC (design rule
check), and wired wrong on every instance.

Same part family, different variant suffix, different pin order is a real and
common trap.

Where possible, verify against physical evidence: pads parsed out of a working
board, or the module's own published footprint. Record which two sources agreed.
If they disagree, do not pick one: report the conflict, with both sources, and
ask.

Note also: **silkscreen labels are not port names.** Module pin labels are often
a compatibility naming scheme for some other footprint, and mapping them to the
MCU's (microcontroller's) real ports is a separate table that has to be written
down explicitly, or the firmware will be wired to the wrong pins.

Three doctrine rules apply here; `agents/resource-scout.md` carries them in full:

- **Four outcomes, not two.** Resolved, UNRESOLVABLE, NOT-MACHINE-RETRIEVABLE, or
  BARRIER. When no source at any tier has the fact, that fact is UNRESOLVABLE:
  hand the next phase a named, tolerance-banded parameter with a recommended
  default. Do not block, and do not guess. NOT-MACHINE-RETRIEVABLE is the
  outcome for an asset that demonstrably exists and is correctly identified, is
  not a locked-decision conflict, and whose last mile of retrieval your tools
  cannot complete: a vendor CAD (computer-aided design) portal behind a login or
  a click-through, a download that needs a browser.
- **Report conflicts on any two-source fact**, not just pin tables. Two secondary
  sources disagreeing on a mechanical number costs a case redesign; it still gets
  reported with both tiers named rather than decided by preference.
- **When the primary source is an image** (the pin table published only as a PNG,
  which no tool here can read), two independently-authored derived assets that
  both cite that image are the accepted fallback. That they were never checked
  against the primary is flagged inline in the provenance row and the report.

## 4. Vendor into the project with a provenance manifest

Copy the asset into the project. Do not depend on a path outside it, and do not
leave a bare git link with no `.gitmodules` (that is an asset already lost to
everyone but this machine). Then record, per asset:

| Field | Content |
|---|---|
| **Asset** | file(s) as vendored, and what they are |
| **Source** | URL or local path it came from |
| **Version** | release tag, or the exact upstream commit hash |
| **License** | the actual license, and whether redistribution is allowed |
| **Date** | when it was retrieved |
| **Verified against** | the two sources used for the pin table, named |
| **Modifications** | format upgrades, renames, geometry changes, and why |

Write it as `lib/PROVENANCE.md` (or extend the existing one). A vendored asset
with no provenance entry is not done.

**One file, one job.** `lib/PROVENANCE.md` is the normative, strict, per-asset
provenance **table**: the fields above, nothing else. It is what a gate checks.

Anything narrative (pin tables in context, firmware config, the local-reuse
survey, open risks) belongs in the project's own research/notes doc. That doc
may exist, and it must **link** to `PROVENANCE.md` rather than restate any row
of it.

No row appears in both. Two copies of a provenance row drift, and then neither
is trustworthy.

An orchestration prompt asking for a differently-named provenance document does
not override this file. Write the table here and link it from wherever the
prompt wanted a doc.

Vendoring also splits by purpose: production geometry (what the projects'
`fp-lib-table` / `sym-lib-table` resolve) goes in `kicad/lib/`; cross-check
evidence kept only to prove a fact goes in `lib/reference/` and nothing builds
against it.

One directory holding both is how a later phase imports the wrong footprint with
nothing to catch it.

If you upgraded a library file's format, say so and say from what. Format
upgrades are one-way, and knowing the original version is what makes a future
re-derivation possible.

## 5. Prefer generation over adoption for the risky parts

If a part's symbol and footprint can both be generated from one pin table, do
that instead of adopting two separately-authored files. They then cannot drift.
A generator plus a pin table is the deliverable, not hand-authored geometry.

## Report

- What you found locally, and what had to come from the web.
- Each asset vendored, with its provenance row.
- Pin tables established, with the two sources that agreed. State any conflict
  you could not resolve as a question rather than a guess.
- Traps discovered. **Harvest these into the KB (knowledge base)**
  (`/hw-kb harvest`) before you finish: a variant pin-order divergence or a
  footprint that mirrors the wrong way is exactly the kind of fact that is worth
  one debugging session every time it recurs.
