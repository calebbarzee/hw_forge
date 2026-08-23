---
name: hw-design
description: Design hardware end to end as a gated, code-generated build - PCBs, schematics, electronics, and 3D-printed enclosures. Use when starting a new board or device from scratch (keyboard, macro pad, sensor board, carrier board, breakout, printed case), when evolving or fixing an existing KiCad or code-CAD hardware project, when a board needs to pass ERC/DRC/parity gates headlessly, when fab outputs or an enclosure must be generated from an as-built board, or when orchestrating multiple agents across schematic, PCB, and mechanical work.
---

# hw-design

Hardware design as a build, not a drawing session. One logical design file feeds
every emitter; every phase ends at a machine-checkable gate; agents never
hand-edit CAD files; the orchestrator re-runs every gate itself before believing
any report.

You are the orchestrator. Your job is to run the phases in order, delegate the
design-critical ones with precise prompts, and independently verify each gate.

## Before anything else

1. **Smoke-test the toolchain.** `python3 scripts/preflight.py [--project DIR]`.
   Nonzero exit means stop — see *Failure policy*. Never begin design work on an
   unverified toolchain: a broken generator and a broken design look identical
   from the outside, and a whole session can go into debugging a design that was
   never wrong.
2. **Recall from the KB.** See *Knowledge base protocol*. Do this before writing
   any prompt, at every phase start.
3. **Locate the project.** New build → scaffold with
   `python3 scripts/kicad_scaffold.py DIR NAME`. Existing project → run
   `python3 scripts/kicad_gate.py PROJECT_DIR` first, so you know its true
   starting state rather than what its docs claim.

## The phases

No phase starts until the previous gate passes **as re-verified by you**, not as
reported.

| # | Phase | Entry contract | Owner | Exit gate |
|---|---|---|---|---|
| 0 | **Spec lock** | a device idea | you + user | decisions doc: locked choices verbatim, numbered open questions each with a recommendation; user answers or explicitly delegates every one |
| 1 | **Libraries + research** | locked spec | `resource-scout` | every part resolves; provenance manifest per vendored asset; pin tables verified against two independent sources; zero hand-authored geometry |
| 2 | **Logical design** | resolved part list | agent (or you, if small) | `design.py` imports clean under **both** system Python and the CAD Python; every net, pin map and topology fact derives from it |
| 3 | **Schematic** | clean `design.py` | `schematic-engineer` | ERC 0 (`kicad_gate.py DIR --sch-only`, exit 0 — there is no board yet and a missing one is skipped, not failed); power-design decision record written |
| 4 | **PCB** | ERC-clean schematic | `pcb-engineer`, one per board variant | DRC 0 at error severity **with schematic parity ENFORCED** (the flag is not enough — the five parity checks ship at *warning* and `--severity-error` filters them out; `kicad_gate.py` must print `parity enforced`, not `parity UNENFORCED`), 0 unconnected, zones filled headlessly inside the generator, and a wipe-and-rebuild reproducing the same canonical geometry (`kicad_digest.py`) |
| 5 | **Fab outputs** | gated board | `fab-docs-engineer` | export assertions pass; renders eyeballed |
| 6 | **Enclosure** | gated board files | `case-engineer` | all numeric `verify()` checks pass; shells are valid single solids; printability rules hold |
| 7 | **Docs + hygiene + harvest** | everything green | agent + you | docs describe the as-built state; gates still pass after cleanup; new lessons written into KB cards |

Two ordering facts that are easy to get wrong:

- **Power design belongs to phase 3.** It changes the netlist — adding a series
  resistor splits a net in two and moves where a feed terminates. Discovering
  that during PCB work is a rework; discovering it at ERC time is free.
- **The enclosure reads geometry out of the board files**, via
  `python3 scripts/kicad_geom.py BOARD.kicad_pcb --json` — outline, hole
  positions, footprint positions, courtyards, and which face each part's
  hardware really protrudes on. Never from a spec table alone. A spec table is
  what the board was *supposed* to be.

**What legitimately round-trips backwards.** Phases own their files, with one
carve-out: geometry whose **count** the netlist sees but whose **position** it
does not — mounting holes, fiducials, test points, keepout markers — is
declared in `design.py` and its coordinates may be nudged by the PCB phase,
which says so in its report. Changing the *count* of anything, or any net, part
or pin map, is a barrier. State the permission in `design.py` next to the
table, so a later agent does not have to file a barrier report over four
numbers.

## Project layout

One convention, stated once, because phase 1 and phase 3 will otherwise each
invent their own and the repo ends up with two directories called `lib`:

```
PROJECT/
├── SPEC.md                    the decisions doc (phase 0) — the arbiter
├── kicad/
│   ├── design.py              the single logical source (phase 2)
│   ├── gen_sch.py gen_pcb.py  the emitters
│   ├── Makefile               from templates/Makefile
│   ├── fab-profile.json       export assertions, NEXT TO the board it gates
│   ├── lib/                   THE PRODUCTION LIBRARY: *.kicad_sym, *.pretty
│   │                          — what fp-lib-table/sym-lib-table resolve
│   ├── <board>.kicad_sch/pcb  a single-board project lives right here
│   ├── <variant>/             …or one subdirectory per board variant
│   └── proto/                 the gate slice: built and gated, never fabbed
├── lib/
│   ├── PROVENANCE.md          the per-asset provenance table (phase 1)
│   └── reference/             vendored CROSS-CHECK EVIDENCE, built against by
│                              nothing — keeping it next to production
│                              geometry is how a later phase imports the wrong
│                              file and nothing catches it
├── case/                      the enclosure generator + checks.py
├── fab/                       generated export packages
└── .gitignore                 from templates/.gitignore, written at phase 0
```

`kicad_scaffold.py` discovers a library at `<project>/lib` or
`<project>/../lib`, so both the single-board and the per-variant layout resolve
`kicad/lib/` with no flags. A **verified pin table has exactly one home**:
`design.py`. Phase 1 writes its tables there rather than into a scout-local
generator, or two copies exist and can drift — which is the failure the
one-table doctrine exists to prevent.

**ONE library directory and ONE model directory per project, at a FIXED depth
relative to every board variant.** `kicad/lib/` and `kicad/lib/3dmodels/` above:
every board project sits exactly one level below them (`kicad/` for a
single-board project, `kicad/<variant>/` otherwise). A variant at any other
depth breaks every `${KIPRJMOD}`-anchored path in the shared library, and that
is not fixable inside a footprint: `${KIPRJMOD}/../lib/3dmodels/x.step` resolves
for a project at `kicad/` and lands one level off for one at `kicad/proto/`;
there is no `${KIFPMOD}`-style anchor relative to the footprint library (which
is where a shared model store logically hangs); and KiCad's own path variables
are **user-global**, i.e. exactly what a portable repo cannot use. So the
layout *is* the fix — and `preflight.py --project` resolves every `(model ...)`
link in the project's library, so a violation is a failing check rather than an
empty 3D view three phases later.

### Phase 0 in more detail

Produce a decisions doc in the project and keep it as the arbiter. Two sections:

- **Locked** — the user's choices, verbatim, no paraphrase. These become the
  locked-decisions block in every agent prompt.
- **Open (D1, D2, …)** — each with the options, the tradeoff, and *your*
  recommendation. Ask them all at once; do not start phase 1 with an unanswered
  D. "Use your judgement on D3" is a valid answer, and then D3 becomes locked
  with your recommendation as its value, recorded as delegated.

When the spec and the code later disagree, the decisions doc wins.

## Cross-cutting rules

**Proto slice first.** Anything that repeats — a key cell, an LED, a fastener
boss — gets a one-instance version built and gated before you instantiate N of
them. Make it a real target (`proto/`) and run it first in the gate loop. A
mistake in the cell costs one fix at N=1 and N fixes at N=22.

**Nudge, don't prove.** Settle geometry by regenerating and reading the DRC or
verify JSON — never by hand arithmetic. Requirements: every lane, offset and
clearance is a **named constant** in the generator, and regeneration is one
command. Then the loop is: generate → read the JSON report → move one named
constant → regenerate. This is not a fallback; it is the primary method, and it
reliably beats reasoning about clearance inequalities on paper.

**Never hand-edit CAD files.** Tracks carry UUIDs, zones carry cached fills, and
nothing revalidates until KiCad reopens the file. Text edits are acceptable for
metadata and placement coordinates you can prove local; copper, never. If the fix
is not expressible in the generator, the generator is what needs the fix.

**Generate symbol and footprint from one pin table.** The dangerous class of bug
is the silent one: a symbol whose pin numbering disagrees with its footprint
swaps power and data across every instance, and DRC is clean because everything
is connected exactly as the (wrong) netlist says. A generated pair cannot drift.
This trap is real and has bitten this pipeline (`SK6812MINI` vs `SK6812MINI-E`:
same part family, different pin order).

**Handoff reports.** Every agent ends with a "for the next agent" section:
diagnosis, the named constants worth touching, budget advice, what it tried that
did not work. Mirrored or repeated variants get dramatically cheaper this way —
the second half of a symmetric design typically lands clean on the first
regeneration when it inherits the first half's handoff.

**You re-run every gate.** An agent's claim that a gate passes is a claim. Run
`kicad_gate.py` yourself between waves and read the summary. This is also your
regression detector: if a committed artifact still passes while a fresh
regeneration fails, the fault is in generation or the toolchain, not in the rules
or the design settings.

**Sequential when agents share generator files; parallel only when their
subtrees are disjoint.** See `references/orchestration.md`.

## Locked decisions and the barrier clause

Every agent prompt carries the **same verbatim locked-decisions block**, marked
do-not-relitigate. An agent may not re-argue a locked decision, and may not
quietly substitute its own.

**The barrier clause.** If a locked decision makes a gate impossible, or forces a
materially worse design, the agent **stops and returns a barrier report**:

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
You do not overrule it, and you do not re-dispatch the same agent against the
same wall hoping for a different result. Both failure modes are violations:

- **Grinding** — burning turns trying to satisfy a constraint that cannot be
  satisfied. The tell is the same violation count not moving across passes.
- **Silent deviation** — changing the locked decision without saying so. This is
  worse, because it corrupts the decisions doc as an arbiter and the user finds
  out from a physical part.

A rejected-on-evidence decision is legitimate *only* when it went through this
path and got recorded. Keep the record: the reasoning is the reason the same
question does not get reopened next session.

**The REGRESSION note — the third outcome.** BARRIER covers *impossible*; the
deviation report covers *one locked decision bent*. Neither covers the case that
actually happens most: **two locked decisions, each individually satisfiable,
that jointly cost you a property you already had.** Nothing fails, nothing is
bent, no gate objects — and the phase's real output is a set of numbers a human
has to accept, whose only channel is a final report, which is prose.

```
REGRESSION
Lost:           the property that no longer holds, and what had established it
Decisions:      the two or more locked decisions whose INTERACTION lost it
Numbers:        what it costs, measured
To get it back: which decision would have to move, and what that costs
```

Cite: one revision's display placement and encoder position were each
satisfiable, and together (a) put the display body over the USB-C receptacle in
plan, reintroducing a z clearance the *previous* revision had eliminated, (b)
moved the encoder shaft 10.75 mm off its nominal x, and (c) hung the display
glass 0.600 mm past the board edge. None failed a gate. None was a barrier —
one decision explicitly permitted a reported deviation and the overhang was
pre-authorised.

Two obligations follow, and they are the whole point:

- **You write the regression note back into the decisions doc**, under the
  decisions it names, so the next revision's agent reads it as a constraint
  instead of rediscovering it. A report nobody folds back into `SPEC.md` is a
  finding with a half-life of one session.
- **If the lost property was recorded as a KB win, the card gets amended too**
  (`kb/README.md`, harvest rule 7). Otherwise the card keeps advising the thing
  the design just stopped doing.

## Knowledge base protocol

**Roots.** The plugin's own `kb/` plus every path in `HW_FORGE_KB_ROOTS`
(colon-separated). Read `kb/README.md` for the card format and index
conventions before writing anything into it.

**RECALL — at every phase start.** Before writing a prompt or a line of
generator code, search the KB roots for cards matching this phase's domain and
tags (e.g. `electronics` + `led`, `mechanical` + `inserts`, `kicad` + `zones`).
Read what matches and fold the relevant facts into the prompt you are about to
write, or into your own work. Cards are cheap to read and each one is worth about
one debugging session. Skipping recall is how a known trap gets rediscovered at
full price.

**HARVEST — at run end (phase 7), and immediately after any expensive
surprise.** Anything this run learned that was not already in a card becomes one:
a trap, a formula, a number that mattered, a decision and its reasoning, a "looks
like a bug and is not". Check for an existing card to update before creating a
new one — a sharpened card beats two overlapping ones. Harvest also from agent
handoff reports; that is where the expensive lessons are written down first.

Respect `kb/README.md`'s split rule: a fact that only makes sense once you name a
part, a firmware, a vendor library or a project is a **card**; a rule, formula or
decision tree that applies to any board belongs in a **reference** instead. When a
generic rule was learned from a specific incident, the reference states the rule
and the card holds the specifics.

The test of a good card: the next session hits the same situation and does not
have to rediscover anything.

**Gap logs.** When a run is also validating the pipeline (a dry run, a new
domain, a first board on an unfamiliar fab), it keeps a gap log — and **you own
its numbering**: one document, one monotonically increasing counter, each phase
appending to the existing sequence. A phase that opens its own numbering
collides with another phase's, and every cross-reference written into project
source becomes ambiguous the moment it happens. See `kb/README.md`, "Gap logs
and their numbering".

## Model policy

Encoded in `agents/*.md`, restated here so you know what you are dispatching:

- **Opus** — `schematic-engineer`, `pcb-engineer`, `case-engineer`. These are
  design-critical: their mistakes are silent, expensive, and often only visible
  after a fab order or a print.
- **Sonnet** — `resource-scout`, `fab-docs-engineer`. Search, vendoring,
  exports, documentation and hygiene. Mechanical work in the other sense: the
  gates catch the mistakes.

Do not economize on the three design roles.

## When to load which reference

Load on demand. Do not read all of these up front.

| Reference | Load when |
|---|---|
| `references/orchestration.md` | before writing any agent prompt, or planning waves — the prompt template and the wave rules live here |
| `references/kicad-api.md` | any phase 2–5 work: `kicad-cli` invocations and flags, headless `pcbnew`, zone filling and island removal, project-file severity patching, s-expr parsing gotchas, the SWIG→IPC migration note |
| `references/electronics.md` | phase 3 (power topology, decoupling policy, current budget, level-shift rule) and phase 4 (matrix/chain routing patterns, layer split, the mirroring traps, reversible-board schemes) |
| `references/mechanical.md` | phase 6: heat-set inserts, screw-length stack-up arithmetic, air-gap ledgers, clamp vs pass-through fastening, FDM printability rules, tolerance defaults |
| `references/batteries.md` | phase 0 or 3 when a cell is in scope: LiPo naming and size tables, capacity, connectors and mated heights, swell allowance |

Domain specifics — MX key geometry, ZMK pin quirks, a particular module's
pinout — are **not** in the references. They are KB cards. Recall them.

## Failure policy

Two kinds of failure, two different responses. Telling them apart is the whole
skill here.

**Environment and tooling failures — STOP.** Missing KiCad, wrong version,
missing Python package, a `pcbnew` import that fails, a script that cannot find
`kicad-cli`. Report it to the user with the **exact fix command** and stop. Do
not work around it: not by skipping the gate, not by a hand-edit, not by
substituting a different tool, not by "proceeding without zone fills for now". A
worked-around gate is an ungated phase, and the pipeline's only guarantee is that
the gates ran. `preflight.py` already prints exact fix commands; relay them
verbatim.

**Design failures — iterate.** Violations, failed assertions, failed `verify()`
checks. These are the loop working. Read the report, form one hypothesis, move
one named constant, regenerate, re-read. Report progress by violation count.
Two guardrails:

- If the count does not move across two passes, your model of the failure is
  wrong. Re-read the actual violation records — location, layer, the two items
  involved — rather than nudging harder.
- If a locked decision is what makes the count immovable, that is a barrier, not
  a design failure. File the barrier report.

**Ambiguity — ask.** An unanswered phase-0 question found mid-run is not
something to decide silently. Add it to the decisions doc as a D, with a
recommendation, and ask.

## Script contract

Everything the pipeline verifies goes through these. Exit nonzero = failed gate.

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

`kicad_gate.py --sch-only` is the phase-3 gate; a project with no board yet is
also auto-detected and prints a PARTIAL verdict rather than failing. Run
`case_verify.py` with the python your CAD library lives in.

`KIPY` is KiCad's bundled Python — required wherever `pcbnew` is imported.
Scripts discover `kicad-cli` and `pcbnew` on their own (platform defaults,
including `/Applications/KiCad/KiCad.app/...` on darwin); `KICAD_ROOT` overrides.

`templates/Makefile` wires these into per-project `make` / `make check` /
`make fab` targets. Give every project one, so regeneration and validation are
each a single command — that is what makes the nudge loop cheap enough to be the
primary method.

## Single-phase entry points

When the user wants one thing rather than a pipeline, these run the same scripts:
`/hw-preflight`, `/hw-validate`, `/hw-research`, `/hw-export`, `/hw-kb`. Use them
inside a full run too — they are the same operations you would perform inline.
