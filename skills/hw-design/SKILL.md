---
name: hw-design
description: Design hardware end to end as a gated, code-generated build: PCBs, schematics, electronics, and 3D-printed enclosures. Use when starting a new board or device from scratch (keyboard, macro pad, sensor board, carrier board, breakout, printed case), when evolving or fixing an existing KiCad or code-CAD hardware project, when a board needs to pass ERC/DRC/parity gates headlessly, when fab outputs or an enclosure must be generated from an as-built board, or when orchestrating multiple agents across schematic, PCB, and mechanical work.
---

# hw-design

Hardware design as a build, not a drawing session. One logical design file feeds
every emitter. Every phase ends at a machine-checkable gate. Agents never
hand-edit computer-aided design (CAD) files. The orchestrator re-runs every gate
itself before believing any report.

You are the orchestrator. Run the phases in order, delegate the design-critical
ones with precise prompts, and independently verify each gate.

Throughout: ERC is KiCad's electrical rule check on a schematic, DRC is its
design rule check on a board, and the knowledge base (KB) is the card collection
under `kb/`.

## Before anything else

1. **Smoke-test the toolchain.** Run
   `python3 scripts/preflight.py [--project DIR]`. A nonzero exit means stop;
   see *Failure policy*. Never begin design work on an unverified toolchain,
   because a broken generator and a broken design look identical from the
   outside.
2. **Recall from the knowledge base.** See *Knowledge base protocol*. Do this
   before writing any prompt, at every phase start.
3. **Locate the project.** For a new build, scaffold with
   `python3 scripts/kicad_scaffold.py DIR NAME`. For an existing project, run
   `python3 scripts/kicad_gate.py PROJECT_DIR` first, so you know its true
   starting state rather than what its documentation claims.

## The phases

No phase starts until the previous gate passes **as re-verified by you**, not as
reported.

| # | Phase | Entry contract | Owner | Exit gate |
|---|---|---|---|---|
| 0 | **Spec lock** | a device idea | you + user | decisions doc: locked choices verbatim, numbered open questions each with a recommendation; user answers or explicitly delegates every one |
| 1 | **Libraries + research** | locked spec | `resource-scout` | every part resolves; provenance manifest per vendored asset; pin tables verified against two independent sources; zero hand-authored geometry |
| 2 | **Logical design** | resolved part list | agent (or you, if small) | `design.py` imports clean under **both** system Python and the CAD Python; every net, pin map and topology fact derives from it |
| 3 | **Schematic** | clean `design.py` | `schematic-engineer` | ERC 0 (`kicad_gate.py DIR --sch-only`, exit 0; there is no board yet, and a missing one is skipped rather than failed); power-design decision record written |
| 4 | **PCB** | ERC-clean schematic | `pcb-engineer`, one per board variant | DRC 0 at error severity **with schematic parity enforced**; 0 unconnected; zones filled headlessly inside the generator; and a wipe-and-rebuild reproducing the same canonical geometry (`kicad_digest.py`) |
| 5 | **Fab outputs** | gated board | `fab-docs-engineer` | export assertions pass; renders inspected |
| 6 | **Enclosure** | gated board files | `case-engineer` | all numeric `verify()` checks pass; shells are valid single solids; printability rules hold |
| 7 | **Docs + hygiene + harvest** | everything green | agent + you | docs describe the as-built state; gates still pass after cleanup; new lessons written into KB cards |

**Phase 4's parity requirement needs its own sentence, because passing the flag
is not enough.** `kicad_gate.py` must print `parity enforced`, not
`parity UNENFORCED`. The five parity checks ship at `warning` severity and
`--severity-error` filters them out, so a project that has not promoted them
reports a parity pass from a check that cannot fail. The mechanism and the
measurement are in `references/kicad-api.md` §2.

Two ordering facts that are easy to get wrong:

- **Power design belongs to phase 3.** It changes the netlist. Adding a series
  resistor splits a net in two and moves where a feed terminates. Discovering
  that during PCB work is rework; discovering it at ERC time costs nothing.
- **The enclosure reads geometry out of the board files**, via
  `python3 scripts/kicad_geom.py BOARD.kicad_pcb --json`. That gives the
  outline, hole positions, footprint positions, courtyards, and which face each
  part's hardware actually protrudes on. Never work from a spec table alone. A
  spec table records what the board was supposed to be.

**What legitimately round-trips backwards.** Phases own their files, with one
carve-out.

Geometry whose count the netlist sees, but whose position it does not, may be
nudged backwards. That means mounting holes, fiducials, test points, and keepout
markers. Such geometry is declared in `design.py`, and the PCB phase may change
its coordinates, saying so in its report.

Changing the count of anything, or any net, part, or pin map, is a barrier.
State the permission in `design.py` next to the table, so a later agent does not
have to file a barrier report over four numbers.

## Project layout

One convention, stated once, because phase 1 and phase 3 will otherwise each
invent their own and the repo ends up with two directories called `lib`.

```
PROJECT/
├── SPEC.md                    the decisions doc (phase 0), the arbiter
├── kicad/
│   ├── design.py              the single logical source (phase 2)
│   ├── gen_sch.py gen_pcb.py  the emitters
│   ├── Makefile               from templates/Makefile
│   ├── fab-profile.json       export assertions, next to the board it gates
│   ├── lib/                   the production library: *.kicad_sym, *.pretty
│   │                            what fp-lib-table/sym-lib-table resolve
│   ├── <board>.kicad_sch/pcb  a single-board project lives right here
│   ├── <variant>/             …or one subdirectory per board variant
│   └── proto/                 the gate slice: built and gated, never fabbed
├── lib/
│   ├── PROVENANCE.md          the per-asset provenance table (phase 1)
│   └── reference/             vendored cross-check evidence, built against by
│                              nothing. Keeping it next to production
│                              geometry is how a later phase imports the wrong
│                              file and nothing catches it
├── case/                      the enclosure generator + checks.py
├── fab/                       generated export packages
└── .gitignore                 from templates/.gitignore, written at phase 0
```

`kicad_scaffold.py` discovers a library at `<project>/lib` or
`<project>/../lib`, so both the single-board and the per-variant layout resolve
`kicad/lib/` with no flags.

**A verified pin table has exactly one home: `design.py`.** Phase 1 writes its
tables there rather than into a scout-local generator. Otherwise two copies
exist and can drift, which is the failure the one-table doctrine exists to
prevent.

### One library directory and one model directory, at a fixed depth

Use `kicad/lib/` and `kicad/lib/3dmodels/` as shown above, with every board
project exactly one level below them: `kicad/` for a single-board project,
`kicad/<variant>/` otherwise.

A variant at any other depth breaks every `${KIPRJMOD}`-anchored path in the
shared library, and that is not fixable inside a footprint. Three reasons
compound:

1. `${KIPRJMOD}/../lib/3dmodels/x.step` resolves for a project at `kicad/` and
   lands one level off for one at `kicad/proto/`.
2. There is no `${KIFPMOD}`-style anchor relative to the footprint library,
   which is where a shared model store logically hangs.
3. KiCad's own path variables are user-global, which is exactly what a portable
   repository cannot use.

So the layout is the fix. `preflight.py --project` resolves every `(model ...)`
link in the project's library, so a violation is a failing check rather than an
empty 3D view three phases later.

### Phase 0 in more detail

Produce a decisions doc in the project and keep it as the arbiter. It has two
sections:

- **Locked.** The user's choices, verbatim, with no paraphrase. These become the
  locked-decisions block in every agent prompt.
- **Open (D1, D2, and so on).** Each with the options, the tradeoff, and your
  recommendation. Ask them all at once, and do not start phase 1 with an
  unanswered D. "Use your judgement on D3" is a valid answer; D3 then becomes
  locked with your recommendation as its value, recorded as delegated.

When the spec and the code later disagree, the decisions doc wins.

## Cross-cutting rules

**Proto slice first.** Anything that repeats, such as a key cell, an LED, or a
fastener boss, gets a one-instance version built and gated before you
instantiate N of them. Make it a real target (`proto/`) and run it first in the
gate loop. A mistake in the cell costs one fix at N=1 and N fixes at N=22. See
`references/electronics.md` §10.

**Nudge, do not prove.** Settle geometry by regenerating and reading the DRC or
`verify()` JSON, never by hand arithmetic. This requires that every lane, offset,
and clearance is a named constant in the generator, and that regeneration is one
command. The loop is then: generate, read the JSON report, move one named
constant, regenerate. This is the primary method, not a fallback.

**Never hand-edit CAD files.** Tracks carry unique identifiers, zones carry
cached fills, and nothing revalidates until KiCad reopens the file. Text edits
are acceptable for metadata and for placement coordinates you can prove local.
Copper, never. If the fix is not expressible in the generator, the generator is
what needs fixing. See `references/kicad-api.md` §1.

**Generate symbol and footprint from one pin table.** A symbol whose pin
numbering disagrees with its footprint swaps power and data across every
instance of the part, and DRC stays clean because everything is connected
exactly as the wrong netlist says. A generated pair cannot drift. The doctrine,
and what to do when both halves are stock parts, is in
`references/kicad-api.md` §8.

**Handoff reports.** Every agent ends with a "for the next agent" section:
diagnosis, the named constants worth touching, budget advice, and what it tried
that did not work. This is what makes a mirrored or repeated variant cheap the
second time. The report shape is in `references/orchestration.md` §3.

**You re-run every gate.** An agent's claim that a gate passes is a claim. Run
`kicad_gate.py` yourself between waves and read the summary.

This is also your regression detector. If a committed artifact still passes
while a fresh regeneration fails, the fault is in generation or the toolchain,
not in the rules or the design settings.

**Sequential when agents share generator files; parallel only when their
subtrees are disjoint.** See `references/orchestration.md` §2.

## Locked decisions and the barrier clause

Every agent prompt carries the same verbatim locked-decisions block, marked as
not open for relitigation. An agent may not re-argue a locked decision, and may
not quietly substitute its own.

**The barrier clause.** If a locked decision makes a gate impossible, or forces
a materially worse design, the agent stops and returns a barrier report:

```
BARRIER
Blocked:        what cannot be done, and which gate it fails
Locked decision: the exact decision in conflict
Why:            the mechanism, with evidence (violation counts, measured
                clearances, the report file that shows it)
Options:        A / B / C — each with its cost and what it gives up
Recommendation: which, and why
```

Then it stops. It does not grind, and it does not deviate.

You relay a barrier report to the user as a question, with the recommendation.
Do not overrule it, and do not re-dispatch the same agent against the same wall
hoping for a different result. Both failure modes are violations:

- **Grinding.** Burning turns trying to satisfy a constraint that cannot be
  satisfied. The tell is the same violation count not moving across passes.
- **Silent deviation.** Changing the locked decision without saying so. This is
  worse, because it corrupts the decisions doc as an arbiter, and the user finds
  out from a physical part.

A rejected-on-evidence decision is legitimate only when it went through this
path and got recorded. Keep the record, because the reasoning is what stops the
same question being reopened next session.

### The regression note, which is the third outcome

BARRIER covers the impossible. The deviation report covers one locked decision
being bent. Neither covers the case that happens most often: **two locked
decisions, each individually satisfiable, that jointly cost you a property you
already had.**

Nothing fails, nothing is bent, and no gate objects. The phase's real output is
a set of numbers a human has to accept, whose only channel is a final report,
which is prose.

```
REGRESSION
Lost:           the property that no longer holds, and what had established it
Decisions:      the two or more locked decisions whose INTERACTION lost it
Numbers:        what it costs, measured
To get it back: which decision would have to move, and what that costs
```

Worked case: one revision's display placement and encoder position were each
satisfiable. Together they (a) put the display body over the USB-C receptacle in
plan, reintroducing a z clearance the previous revision had eliminated, (b)
moved the encoder shaft 10.75 mm off its nominal x, and (c) hung the display
glass 0.600 mm past the board edge. None failed a gate, and none was a barrier,
because one decision explicitly permitted a reported deviation and the overhang
was pre-authorised.

Two obligations follow:

- **Write the regression note back into the decisions doc**, under the decisions
  it names, so the next revision's agent reads it as a constraint instead of
  rediscovering it. A report nobody folds back into `SPEC.md` is a finding with
  a half-life of one session.
- **If the lost property was recorded as a knowledge-base win, amend that card
  too** (`kb/README.md`, harvest rule 7). Otherwise the card keeps advising the
  thing the design has just stopped doing.

## Knowledge base protocol

**Roots.** The plugin's own `kb/`, plus every path in `HW_FORGE_KB_ROOTS`, which
is colon-separated. Read `kb/README.md` for the card format and index
conventions before writing anything into it.

**Recall, at every phase start.** Before writing a prompt or a line of generator
code, search the knowledge-base roots for cards matching this phase's domain and
tags, such as `electronics` plus `led`, `mechanical` plus `inserts`, or `kicad`
plus `zones`. Read what matches, and fold the relevant facts into the prompt you
are about to write, or into your own work. Skipping recall is how a known trap
gets rediscovered at full price.

**Harvest, at run end (phase 7), and immediately after any expensive surprise.**
Anything this run learned that was not already in a card becomes one: a trap, a
formula, a number that mattered, a decision and its reasoning, or something that
looks like a bug and is not.

Check for an existing card to update before creating a new one. A sharpened card
beats two overlapping ones. Harvest from agent handoff reports too, because that
is where the expensive lessons get written down first.

Respect `kb/README.md`'s split rule. A fact that only makes sense once you name
a part, a firmware, a vendor library, or a project is a **card**. A rule,
formula, or decision tree that applies to any board belongs in a **reference**
instead. When a generic rule was learned from a specific incident, the reference
states the rule and the card holds the specifics.

The test of a good card: the next session hits the same situation and does not
have to rediscover anything.

**Gap logs.** When a run is also validating the pipeline, as in a dry run, a new
domain, or a first board on an unfamiliar fab, it keeps a gap log.

**You own its numbering:** one document, one monotonically increasing counter,
with each phase appending to the existing sequence. A phase that opens its own
numbering collides with another phase's, and every cross-reference written into
project source becomes ambiguous the moment that happens. See `kb/README.md`,
"Gap logs and their numbering".

## Model policy

Encoded in `agents/*.md`, and restated here so you know what you are
dispatching.

- **Opus:** `schematic-engineer`, `pcb-engineer`, `case-engineer`. These are
  design-critical. Their mistakes are silent, expensive, and often only visible
  after a fab order or a print.
- **Sonnet:** `resource-scout`, `fab-docs-engineer`. Search, vendoring, exports,
  documentation, and hygiene. The gates catch the mistakes in this work.

Do not economise on the three design roles.

## When to load which reference

Load on demand. Do not read all of these up front.

| Reference | Load when |
|---|---|
| `references/orchestration.md` | Before writing any agent prompt, or planning waves. The prompt template and the wave rules live here. |
| `references/kicad-api.md` | Any phase 2 to 5 work: `kicad-cli` invocations and flags, headless `pcbnew`, zone filling and island removal, project-file severity patching, s-expression parsing gotchas, and the SWIG to IPC migration note. |
| `references/electronics.md` | Phase 3, for power topology, decoupling policy, current budget, and the level-shift rule. Phase 4, for matrix and chain routing patterns, layer split, the mirroring traps, and reversible-board schemes. |
| `references/mechanical.md` | Phase 6: heat-set inserts, screw-length stack-up arithmetic, air-gap ledgers, clamp against pass-through fastening, printability rules, and tolerance defaults. |
| `references/batteries.md` | Phase 0 or 3, when a cell is in scope: cell naming and size tables, capacity, connectors and mated heights, and swell allowance. |

Domain specifics, such as key-switch geometry, a firmware's pin quirks, or a
particular module's pinout, are not in the references. They are knowledge-base
cards. Recall them.

## Failure policy

Two kinds of failure need two different responses, and telling them apart is the
main judgement this section asks for.

**Environment and tooling failures: stop.** That covers missing KiCad, a wrong
version, a missing Python package, a `pcbnew` import that fails, or a script
that cannot find `kicad-cli`.

Report it to the user with the exact fix command, and stop. Do not work around
it: not by skipping the gate, not by a hand-edit, not by substituting a
different tool, and not by proceeding without zone fills for now. A worked-around
gate is an ungated phase, and the pipeline's only guarantee is that the gates
ran. `preflight.py` already prints exact fix commands; relay them verbatim.

**Design failures: iterate.** That covers violations, failed assertions, and
failed `verify()` checks. These are the loop working. Read the report, form one
hypothesis, move one named constant, regenerate, and re-read. Report progress by
violation count.

Two guardrails:

- If the count does not move across two passes, your model of the failure is
  wrong. Re-read the actual violation records, including location, layer, and
  the two items involved, rather than nudging harder.
- If a locked decision is what makes the count immovable, that is a barrier, not
  a design failure. File the barrier report.

**Ambiguity: ask.** An unanswered phase-0 question found mid-run is not
something to decide silently. Add it to the decisions doc as a D, with a
recommendation, and ask.

## Script contract

Everything the pipeline verifies goes through these. A nonzero exit means a
failed gate.

```bash
python3 scripts/preflight.py [--project DIR]        # env doctor; exact fixes on failure
python3 scripts/kicad_gate.py PROJECT_DIR [--name NAME] [--sch-only]
                                                    # ERC + DRC(parity) + unconnected
KIPY    scripts/kicad_zonefill.py BOARD.kicad_pcb [-o OUT] # headless zone fill
python3 scripts/kicad_fab.py PROJECT_DIR -o OUTDIR [--profile PROFILE.json]
python3 scripts/kicad_geom.py BOARD.kicad_pcb [--json]     # outline, holes, positions,
                                                    # courtyards, pad-side truth
python3 scripts/kicad_digest.py BOARD.kicad_pcb [--compare A B]
                                                    # canonical KIID-free digest:
                                                    # the determinism check
python3 scripts/kicad_scaffold.py DIR NAME          # project + lib tables + severities
python3 scripts/case_verify.py CHECKS.py            # numeric interference checks
python3 scripts/report.py FILE.json                 # one-line summary of a kicad-cli report
```

`kicad_gate.py --sch-only` is the phase-3 gate. A project with no board yet is
also auto-detected, and prints a PARTIAL verdict rather than failing. Run
`case_verify.py` with the python your CAD library lives in.

`KIPY` is KiCad's bundled Python, required wherever `pcbnew` is imported.
Scripts discover `kicad-cli` and `pcbnew` on their own, from platform defaults
including `/Applications/KiCad/KiCad.app/...` on darwin. `KICAD_ROOT` overrides
that discovery.

`templates/Makefile` wires these into per-project `make`, `make check`, and
`make fab` targets. Give every project one, so that regeneration and validation
are each a single command. That is what makes the nudge loop cheap enough to be
the primary method.

## Single-phase entry points

When the user wants one thing rather than a pipeline, these run the same
scripts: `/hw-preflight`, `/hw-validate`, `/hw-research`, `/hw-export`, and
`/hw-kb`. Use them inside a full run too, since they are the same operations you
would perform inline.
