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
   outside. If it reports the autorouter or KiCadRoutingTools missing and the
   spec calls for the hybrid routing flow, run
   `python3 scripts/hw_install.py --check`, or `--all` to install. Neither
   runs on its own, and an install is the user's call.
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
| 0 | **Spec lock** | a device idea | you + user | `SPEC.md`: the intake question bank (`references/intake.md`) asked in one batch, locked choices and delegated defaults both recorded verbatim, placement intent and rules recorded as blocks; every "must answer" question is answered or explicitly delegated |
| 1 | **Libraries + research** | locked spec | `resource-scout` | every part resolves; provenance manifest per vendored asset; pin tables verified against two independent sources; zero hand-authored geometry — symbols, footprints, **and 3D models**: a resolved, render-verified 3D model per part, with provenance and license, or an explicit recorded negative for parts where none exists; every resolved footprint checked against the part's declared package with `kicad_fpcheck.py` (`agents/resource-scout.md` gate 7) |
| 2 | **Logical design** | resolved part list | agent (or you, if small) | `design.py` imports clean under **both** system Python and the CAD Python; every net, pin map and topology fact derives from it |
| 3 | **Schematic** | clean `design.py` | `schematic-engineer` | ERC 0 (`kicad_gate.py DIR --sch-only`, exit 0; there is no board yet, and a missing one is skipped rather than failed); `kicad_bom.py audit` exit 0: every sourced part carries description, manufacturer, MPN, package, datasheet, and LCSC where the assembly service needs it, and every board-inherent symbol is `in_bom no`; power-design decision record written |
| 4 | **PCB** | ERC-clean schematic | `pcb-engineer`, one per board variant | DRC 0 at error severity **with schematic parity enforced**; 0 unconnected; zones filled headlessly inside the generator; and a wipe-and-rebuild reproducing the same canonical geometry (`kicad_digest.py`); autorouted copper, where the spec permits it, follows the hybrid flow in `references/autorouting.md` and is adopted back into the generator with `kicad_route.py adopt` |
| 5 | **Fab outputs** | gated board | `fab-docs-engineer` | export assertions pass; renders inspected; the populated 3D assembly exported as its own mechanical-review artifact, distinct from the fab package; `kicad_fpcheck.py` re-run clean before any export; `kicad_bom.py audit` re-run clean, and `kicad_fab.py`'s BOM step fails on any empty required cell for a sourced part |
| 6 | **Enclosure** | gated board files | `case-engineer` | all numeric `verify()` checks pass; shells are valid single solids; printability rules hold |
| 7 | **Docs + hygiene + harvest** | everything green | agent + you | docs describe the as-built state; gates still pass after cleanup; new lessons written into KB cards |

**Phase 4's parity requirement needs its own sentence, because passing the flag
is not enough.** `kicad_gate.py` must print `parity enforced`, not
`parity UNENFORCED`. The five parity checks ship at `warning` severity and
`--severity-error` filters them out, so a project that has not promoted them
reports a parity pass from a check that cannot fail. The mechanism and the
measurement are in `references/kicad-api.md` §2.

**Phase 1's "zero hand-authored geometry" gate needs its own sentence too,
because it was being read as covering symbols and footprints only.** It covers
3D models with the same force. A run built mock-up STEP solids for four parts
while real, correctly-licensed models sat unused in a sibling project on the
same disk, because nobody read the rule as reaching that far. The rule did not
need changing; it needed to say "and 3D models" out loud. Phase 1 resolves and
verifies a model per part alongside the symbol and footprint, with provenance
and license recorded, same as any other vendored asset.

Two ordering facts that are easy to get wrong:

- **Power design belongs to phase 3.** It changes the netlist. Adding a series
  resistor splits a net in two and moves where a feed terminates. Discovering
  that during PCB work is rework; discovering it at ERC time costs nothing.
- **The enclosure reads geometry out of the board files**, via
  `python3 scripts/kicad_geom.py BOARD.kicad_pcb --json`. That gives the
  outline, hole positions, footprint positions, courtyards, and which face each
  part's hardware actually protrudes on. Never work from a spec table alone. A
  spec table records what the board was supposed to be.
- **The populated 3D assembly is the other half of that geometry read.**
  `kicad_geom.py` gives coordinates; the assembly, produced in phase 5 and
  consumed in phase 6, is what lets a human see a part on the wrong face or a
  connector fouling a wall, before either becomes a print. See
  `references/kicad-api.md` §9 and `commands/hw-export.md` §5.

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

Run the intake before writing anything else. Load `references/intake.md` and
ask its question bank in one batch, organized by domain: the device's
objective and who uses it, component placement, the general rules the design
must follow, and anything else needed to intuit design decisions later. Mark
each question with its default, or with "no default, must answer," exactly
as the bank states it, so the user can accept every default in one line and
still see which questions have no safe answer.

Produce `SPEC.md` from the answers (skeleton at `templates/SPEC.md`), and keep
it as the arbiter. It has three sections:

- **Locked.** The user's choices, verbatim, with no paraphrase. These become
  the locked-decisions block in every agent prompt.
- **Delegated.** Questions the user answered "your call" or "take the
  defaults" rather than choosing a value. Record the question and the
  recommendation adopted. A delegated item carries the same force as a locked
  one. It is not open for relitigation just because nobody chose it by hand.
- **Design intent.** A placement intent table (which part, which face, which
  edge or zone, what the user touches or sees) and a rules list (layer count,
  fab and assembly service, part sourcing, trace and clearance class,
  autorouter permission, enclosure and mounting, power source, interfaces).
  Both are blocks, pasted into every agent prompt the same way the
  locked-decisions block already is.

Do not start phase 1 with an unanswered "must answer" question. Everything
else may default; these may not.

When the spec and the code later disagree, `SPEC.md` wins.

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

**A datasheet or geometry finding closes in the library, not in a card.** A
`kicad_fpcheck.py` FAIL, or a stock footprint a datasheet disagrees with, is
fixed by forking it into the project library with `scripts/kicad_fplib.py`
and recording the source in the fork's own `(descr)` and `(tags)` and in
`lib/PROVENANCE.md`, never by writing the disagreement into a `kb/` card
alone. `kb/README.md`'s "where a fact lives" table gives every kind of fact
its one home.

**The mechanical-review export and the fab export are different exports.** They
use different `kicad-cli` flags, get verified differently, and are read by
different people: an enclosure model and a human on the review export, a fab
house on the other. Do not conflate them, and do not let one stand in for the
other. See `commands/hw-export.md` §5.

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

## Locked decisions and the escalation ladder

Every agent prompt carries the same verbatim locked-decisions block, marked as
not open for relitigation. An agent may not re-argue a locked decision, and may
not quietly substitute its own.

Design work constantly meets small choices `SPEC.md` never named: a resistor
value, which spare pin becomes a test point, whether a corridor is 1.2 mm or
1.4 mm. Stopping to ask about every one of these would make the pipeline
slower than a human doing the work by hand. Stopping to ask about none of them
is how a physical part surprises the user. The ladder below is the balance:
stay as autonomous as possible, and escalate exactly the things a user would
plausibly want to weigh in on before they become a physical part.

### The three tiers

**Tier 1: decide and log.** Reversible, inside the locked constraints, cheap
to redo. A resistor value inside a stated tolerance, a spare pin's function, a
silkscreen label's wording. Decide it, record it in the report's `Decisions:`
line, and keep working. Do not ask about a tier-1 item. Deciding it without
asking is the autonomous half of the job.

**Tier 2: decide, proceed, and flag for the next phase boundary.** A design
choice a user would plausibly care about, but still cheap to reverse: a
connector's exact position inside an already-locked edge, a trace-width bump
that stays inside the locked clearance class, a silkscreen layout change. Make
the call, keep working, and put it in the report under a named "flagged for
review" line. It gets surfaced and confirmed at the next phase boundary, when
you relay that phase's gate result to the user, not mid-wave, and not by
pausing the agent that made the call.

**Tier 3: stop and ask now.** Anything on this list, no exceptions:

- Changes a locked decision (`SPEC.md` §1 or §2).
- Adds or removes a part, an interface, a connector, or a board.
- Changes the board outline, the layer count, or the unit cost beyond the
  percentage stated in `SPEC.md` R9 (20% if none was stated).
- A fab or assembly blocker: an unavailable part, a footprint the assembly
  service will not place, a service that does not stock a locked part.
- A safety-relevant choice, such as anything touching battery charging.
- A barrier: a locked decision makes a gate impossible, or forces a materially
  worse design.

### Batching the ladder

**Tier 3 questions are collected and asked together**, exactly like the
phase-0 batch, unless one of them blocks all further work. In that case ask
it immediately rather than waiting to accumulate a batch that cannot be
reached. A wave that surfaces three tier-3 items produces one message with
three questions, each in the DECISION REQUEST shape below, not three separate
round trips.

**Tier 2 items are reviewed at phase boundaries, not mid-wave.** Collect them
across the phase, relay the list when you report that phase's gate result, and
move on once the user has seen it, even if the answer is only "fine."

### Anti-patterns

- **Asking one question at a time.** Burns the user's attention on process
  instead of content. `references/intake.md` §1 states the same rule for
  phase 0; it holds for every tier-3 batch after that too.
- **Asking about a tier-1 item.** If it is reversible, inside the locked
  constraints, and cheap, deciding it is the job. Asking about it is not extra
  caution, it is skipping the autonomous half of the work.
- **Silently deciding a tier-3 item.** This is silent deviation, below, and it
  is the more expensive of the two failure modes: the user finds out from a
  physical part instead of from a question.

### The barrier clause

If a locked decision makes a gate impossible, or forces a materially worse
design, the agent stops and returns a barrier report:

```
BARRIER
Blocked:        what cannot be done, and which gate it fails
Locked decision: the exact decision in conflict
Why:            the mechanism, with evidence (violation counts, measured
                clearances, the report file that shows it)
Options:        A / B / C, each with its cost and what it gives up
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

### DECISION REQUEST: the other tier-3 report

BARRIER is the specific case where a locked decision makes a gate impossible.
Everything else on the tier-3 list, an added or removed part, an unavailable
component, a safety-relevant choice, a cost change past the threshold, uses
this report instead, because nothing has failed a gate. A choice just needs a
human before it becomes a physical part.

```
DECISION REQUEST
Question:       what needs deciding, in one sentence
Options:        A / B / C, each with its cost
Recommendation: which, and why
Meanwhile:      what proceeds while this is open, and what is blocked on it
```

Relay it to the user the same way as a barrier: the question, the options with
their cost, and your recommendation. State plainly what keeps running while
the question is open, so a tier-3 stop on one part family does not read as the
whole run being paused when it is not.

Once answered, write the answer into `SPEC.md` §1 or §2, same as any other
locked decision, so the next agent reads it as settled rather than
rediscovering it.

### The regression note, a fourth outcome

BARRIER covers the impossible. DECISION REQUEST covers a choice that needs a
human before it becomes physical. Neither covers the case that happens most
often: **two locked decisions, each individually satisfiable, that jointly
cost you a property you already had.**

This one does not fit the tiers above, because nothing was decided badly and
no gate objected. It is discovered after the fact, by reading the numbers, not
by a choice sitting on the table. Nothing fails, nothing is bent, and no gate
objects. The phase's real output is a set of numbers a human has to accept,
whose only channel is a final report, which is prose.

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
dispatching. Model choice is a dial, not a fixed two-role list.

- **Sonnet:** research, vendoring, exports, documentation, and bounded
  implementation work that has a machine-checkable gate, meaning a script
  verifies the output rather than a reviewer's judgement. This covers
  `resource-scout` and `fab-docs-engineer` by default, and it also covers a
  fanned-out phase-1 research task or a disjoint implementation subtask,
  wherever one exists, for example a part-family research agent whose output is a
  provenance fragment `preflight.py` can resolve, or an implementation slice
  gated by `kicad_gate.py` or `case_verify.py`. See
  `references/orchestration.md` §2 for how these fan out in parallel.
- **Opus, retained by default:** `schematic-engineer`, `pcb-engineer`,
  `case-engineer`. These three are design-critical. Their mistakes are silent,
  expensive, and often only visible after a fab order or a print, which is a
  different risk profile from work a gate can catch outright.

**Do not economise on the three design roles by default.** Lowering this is
the user's call to make explicitly, not a cost optimisation you make on your
own. If a request would move `schematic-engineer`, `pcb-engineer`, or
`case-engineer` off Opus, whether asked directly or implied by a general
"use cheaper models" request, say plainly which roles that touches and get an
explicit yes before dispatching that way, even mid-run.

## When to load which reference

Load on demand. Do not read all of these up front.

| Reference | Load when |
|---|---|
| `references/intake.md` | At phase 0, before drafting the question batch. The question bank by domain, the safe-default convention, and the worked case for why a package question is not optional. |
| `references/orchestration.md` | Before writing any agent prompt, or planning waves. The prompt template and the wave rules live here. |
| `references/autorouting.md` | Phase 4, when placement is irregular or the net count is high: the decision rule for scripted against autorouted copper, the hybrid flow with locked critical nets, the design-rule handoff before DSN export, post-route checks, and the tool comparison. |
| `references/kicad-ecosystem.md` | Before adopting any KiCad plugin, MCP server, or third-party tool: what runs headless, install method, license, maintenance status, and an adopt, evaluate, or skip verdict. |
| `references/kicad-api.md` | Any phase 1 to 5 work: `kicad-cli` invocations and flags, headless `pcbnew`, zone filling and island removal, project-file severity patching, s-expression parsing gotchas, the SWIG to IPC migration note, and STEP export (the AP214 assembly structure, `(model ...)` sign conventions, and proving a model change moved no copper). |
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
something to decide silently. Raise it as a tier-3 DECISION REQUEST, with a
recommendation ("Locked decisions and the escalation ladder"), and write the
answer into `SPEC.md` once it comes back.

## Script contract

Everything the pipeline verifies goes through these. A nonzero exit means a
failed gate.

**Where `scripts/` lives.** The paths below are written relative to the hw_forge
root, not to your working directory. Resolve them once, before the first call,
and use the resolved absolute path everywhere after that, including in every
prompt you hand to a subagent:

- Installed as a plugin: `${CLAUDE_PLUGIN_ROOT}/scripts/...`.
- Installed by symlinking the skill: the `scripts/` directory that sits beside
  the `hw-design` skill directory.
- Working on hw_forge itself: `scripts/` in the repository.

A bare `python3 scripts/preflight.py` runs from the user's project directory and
fails there. Treat "`No such file or directory: scripts/...`" as an unresolved
root, not a broken toolchain.

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
python3 scripts/kicad_fpcheck.py BOARD.kicad_pcb --design design.py
                                                    # pad geometry against the declared
                                                    # package; exit 1 on a FAIL
python3 scripts/kicad_bom.py audit SCHEMATIC.kicad_sch [--board BOARD.kicad_pcb]
                                       [--design design.py] [--assembly jlcpcb]
                                                    # BOM field completeness and the
                                                    # board-inherent exclusion; exit 1
                                                    # on a FAIL
python3 scripts/kicad_bom.py export SCHEMATIC.kicad_sch -o OUT.csv [--assembly jlcpcb]
                                                    # the kicad-cli BOM export, re-checked
                                                    # for empty required cells
python3 scripts/kicad_fplib.py fork LIB:NAME --into kicad/lib/<proj>.pretty
                                                    # fork and edit a project-local
                                                    # footprint: the path from a
                                                    # fpcheck FAIL to a fabbed change
KIPY    scripts/kicad_route.py export-dsn|import-ses|route-krt BOARD.kicad_pcb
python3 scripts/kicad_route.py route DSN | adopt BOARD.kicad_pcb
                                                    # two backends: Freerouting via
                                                    # DSN/SES, KiCadRoutingTools via
                                                    # route-krt; adopt freezes routes
                                                    # into kicad/routing.py either way
python3 scripts/hw_install.py --check|--router|--jlc-plugin|--routing-tools|--all
                                                    # pinned, checksummed installs of
                                                    # the optional tools; --check only
                                                    # reports
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
scripts: `/hw-preflight`, `/hw-validate`, `/hw-research`, `/hw-export`,
`/hw-bom`, and `/hw-kb`. Use them inside a full run too, since they are the same operations you
would perform inline.
