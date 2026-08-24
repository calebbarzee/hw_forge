# Orchestration: the wave playbook

How to run a multi-agent hardware design so that agents do not clobber each
other's files or report stale results. This is the shape a proving run used, and
the failure modes named here are ones it hit.

A **wave** is one dispatch of agents that run at the same time. A wave ends at a
gate, which you re-run yourself before opening the next one.

## 1. Recon before prompts

**Write no agent prompt from an assumption.** Before dispatching anything, spend
your own turns establishing the facts the prompt will assert. It is the
difference between an agent that starts working and an agent that spends its
first third rediscovering the repo.

What recon means concretely:

- Run the gate on the current state:
  `python3 scripts/kicad_gate.py PROJECT_DIR`. You now know the real baseline,
  which is frequently not what the documentation says.
- Read the geometry out of the artifacts rather than the spec:
  `python3 scripts/kicad_geom.py BOARD.kicad_pcb --json` gives the outline, hole
  positions, and footprint positions. Parsing a footprint's pads out of the
  board file is faster and more trustworthy than any inspection in the graphical
  editor, or any spec table.
- Grep the generator for the named constants the agent will need to touch, and
  quote their current values in the prompt.
- Read the decisions document and the previous agent's handoff report.
- Recall knowledge-base cards for the phase's domain, and fold the relevant
  facts in.

A prompt built this way states numbers. A prompt built without recon states
qualities, and the agent has to go and find the numbers anyway, with less
context than you had.

## 2. Wave sequencing

The question that decides everything: **do these agents write the same files?**

**Sequential when they share generator files.** Two agents editing the same
`gen_pcb.py` will clobber each other. Worse, each will gate against a tree the
other has changed underneath them.

Board variants driven by one generator are therefore sequential, left half then
right half. The sequencing is not pure cost: the second variant inherits the
first one's handoff report and lands faster for it.

**Parallel when the subtrees are disjoint.** That means different directories,
different generators, and no shared constants. Examples: fab exports for board A
and board B; the enclosure model while documentation is being written; research
on two unrelated part families. Dispatch these in one message so they actually
run concurrently.

**Never parallel across a gate.** Phase N+1 does not start while phase N is
un-re-verified, even if the files look disjoint. The pipeline's whole guarantee
is that each phase is entered from a verified state.

A practical wave plan for a two-variant board, where `‖` marks agents running in
parallel:

```
wave 1   resource-scout                      (libraries, provenance manifests)
  gate   every part resolves; you spot-check two pin tables yourself
wave 2   schematic-engineer                  (design.py + schematic + power doc)
  gate   you run kicad_gate.py: ERC 0
wave 3   pcb-engineer  — variant A           (shares gen_pcb.py → sequential)
  gate   you run kicad_gate.py: DRC 0 + parity, 0 unconnected
wave 4   pcb-engineer  — variant B           (inherits A's handoff)
  gate   same, on both variants (A must not have regressed)
wave 5   fab-docs-engineer ‖ case-engineer    (disjoint subtrees → parallel)
  gate   fab assertions pass; case_verify.py all-pass
wave 6   docs + hygiene + KB harvest
  gate   gates still pass after cleanup
```

Re-gate every variant after any wave that touched a shared generator, not just
the one the agent was working on. A shared-file change that fixes B and breaks A
is the normal outcome, not an unusual one.

## 3. Anatomy of an agent prompt

Four blocks, always, in this order. Missing any one of them produces a
recognisable failure mode.

**(a) State you inherit, as verified facts.** What exists, where, with numbers.
Current gate status. The named constants and their present values. The previous
agent's handoff. What is deliberately not this agent's problem.

Without this block the agent re-derives the repo and burns a third of its
budget.

**(b) Locked decisions, not to be relitigated.** Verbatim from the decisions
document, never paraphrased, plus the barrier clause spelled out.

Without this block agents substitute their own judgement on settled questions,
and you find out from a physical part.

**(c) Definition of done, as the gate.** The exact command, and the exact
numbers that count as passing. "DRC clean" is not a gate.
`python3 scripts/kicad_gate.py kicad/left` reporting DRC 0 at error severity
with schematic parity and 0 unconnected is a gate.

Without this block, "done" means whatever the agent decided it means.

**(d) Required final-report shape**, including the handoff section. Without this
block you get prose, and the next agent inherits nothing.

### The locked-decisions block, with the barrier clause

Paste this structure into every prompt:

```
LOCKED DECISIONS — do not relitigate, do not silently deviate
  - <decision, verbatim>
  - <decision, verbatim>

BARRIER CLAUSE
If one of these makes your gate impossible, or forces a materially worse
design, STOP and return:

  BARRIER
  Blocked:         what cannot be done, and which gate it fails
  Locked decision: the exact decision in conflict
  Why:             the mechanism, with evidence — violation counts, measured
                   clearances, the report file and record that shows it
  Options:         A / B / C, each with cost and what it gives up
  Recommendation:  which, and why

Then stop. Grinding against the barrier and deviating from it are both
violations. Reporting it is the correct outcome.
```

### The required final report

```
REPORT
Status:        gate command run, and its result verbatim
Changed:       files touched, and what changed in each
Numbers:       violation counts before/after, part counts, whatever the gate
               measures
Decisions:     anything you decided that was not locked, and why
Rejected:      what you tried that did not work, and the evidence
For the next agent:
  - diagnosis of the current state
  - the named constants worth touching, with file:line and present values
  - budget advice: what is tight, what has slack, what to expect
```

The "for the next agent" section is what makes symmetric work cheap the second
time. In one run it is what let a mirrored variant land clean on first
regeneration, after the first variant had cost most of a session.

## 4. Between waves: verify, do not trust

Run the gate yourself after every wave. An agent reporting "DRC 0" is reporting
its last observation, which may predate its last edit.

Read the JSON, not just the exit code. `python3 scripts/report.py FILE.json`
gives the one-line summary, and the records themselves tell you where the
problem is and which two items are involved. That is what distinguishes one
systematic error from many independent ones.

A large violation count that collapses to a single cause is common, and is good
news. In one run, 21 violations in a mirrored block were all one inherited-sign
mistake, and 295 violations across a whole board were one changed API argument.

Two diagnostic patterns worth keeping:

- **Committed artifact passes, fresh regeneration fails.** The fault is in
  generation or the toolchain, not in the rules or the design settings. Same
  rules, different geometry. Do not go looking at the DRC configuration.
- **Violation count immovable across two passes.** Your model of the failure is
  wrong, or a locked decision is the wall. Re-read the violation records before
  nudging again. If the wall is a locked decision, that is a barrier report.

If a wave produced a regression, prefer re-dispatching with the regression as
the stated diagnosis over fixing it yourself, because the agent has the context.
But make the diagnosis yours, from the report you read.

## 5. Cleanup: manifest, then execute

Repo hygiene at the end of a run is destructive, so it goes in two steps.

**Manifest first.** Produce a table with every path, a class, and a
justification. The classes are KEEP, ARCHIVE, DELETE, UNSURE, and CREATE.

The justification is the point. Examples: "regenerable from X by one command",
"the only record of which upstream commit generated version N", "668MB
committed virtualenv".

Anything genuinely uncertain is UNSURE with the question stated, and gets
resolved by the user before anything moves.

Run the cross-reference checks before classifying, and record them, because they
are what makes the classifications defensible. Grep for references between
subtrees, checksum files you suspect are duplicated, and check whether a
directory is read by anything.

**Then execute, split for permissions.** Destructive steps go as small,
separately approvable commands: one `rm -rf` per logical group, not one compound
incantation.

Order matters. Write the `.gitignore` first, or the deletions come straight
back.

**Re-run the gate after the moves.** If the design still passes, nothing
load-bearing left with the archive. That is what tests whether the cleanup was
safe.

## 6. Two condensed example prompts

Genericised from a proving run. Real prompts are longer, mostly because block
(a) carries more numbers.

### Example: PCB variant, second of two

```
ROLE  pcb-engineer. Route the B variant of <board> to the gate.

(a) STATE YOU INHERIT — verified
  - kicad/gen_pcb.py emits both variants from design.py. Variant A is DONE and
    gated: I re-ran `python3 scripts/kicad_gate.py kicad/a` — DRC 0 error
    severity with schematic parity, 0 unconnected, 101 footprints, 421 tracks /
    102 vias.
  - Variant B currently reports 21 DRC violations, all inside the module corner.
    Report: kicad/b/drc.json. I read them: every one is in the support-net block,
    none in the matrix.
  - Diagnosis from A's handoff, which I have verified against the pad table:
    the module turns end-for-end rather than mirroring, so pad-column ROLES swap
    while the key grid does NOT mirror. Band offsets expressed as module-local
    "across" values therefore land on the physically wrong side.
  - Named constants: BAND_N/BAND_S/CORRIDOR_Y in gen_pcb.py:210-240 (current
    values quoted below); mcu_xy() at :188 carries the sign for PART positions
    and is correct — do not "fix" it.
  - KB cards recalled: kicad/zones-island-removal, electronics/mirroring-traps.

(b) LOCKED DECISIONS — do not relitigate, do not silently deviate
  - Two separate boards, not one reversible board.
  - <n> layers. No autorouter. Zones filled headlessly inside the generator.
  - Module position and outer-edge overhang as specified in DECISIONS.md §2.
  [barrier clause verbatim]

(c) DEFINITION OF DONE
  `python3 scripts/kicad_gate.py kicad/b` reports ERC 0, DRC 0 at error
  severity with --schematic-parity, 0 unconnected. Variant A must still pass
  unchanged — re-run it before reporting. No hand edits to the .kicad_pcb;
  every change is in the generator, as a named constant where possible.

(d) REPORT SHAPE
  [required final report verbatim, including "for the next agent"]
```

### Example: enclosure from as-built geometry

```
ROLE  case-engineer. Build the printed enclosure for the gated board.

(a) STATE YOU INHERIT — verified
  - Boards are final and gated (0/0/0/0 on both variants, re-verified by me).
  - Geometry read from the board files, not the spec:
    `python3 scripts/kicad_geom.py kicad/a/<board>.kicad_pcb --json` →
    outline <W>x<H>, <n> mount holes at <coords>, footprint positions attached.
    Use these numbers. The spec table disagrees in two places and is stale.
  - Existing model: case/<name>.py (build123d), <n> checks, currently FAILING
    <k> of them against the new hole size and outline.
  - Tallest back-face parts and their heights: <list>. This is the air-gap
    ledger input; extend it, do not replace it.
  - KB cards recalled: mechanical/heat-set-inserts, mechanical/fdm-plate-down.

(b) LOCKED DECISIONS — do not relitigate, do not silently deviate
  - M2 heat-set inserts at the board's own hole positions; screws from below.
  - Two shells, FDM, support-free in the stated print orientations.
  - Cell: <spec>, one per assembly.
  [barrier clause verbatim]

(c) DEFINITION OF DONE
  `python3 scripts/case_verify.py case/<name>.py` — every check passes,
  including: standoff/boss clearance to EVERY component in the ledger; insert
  bore wall >= 1.2mm; computed screw length printed and matched to the BOM;
  both shells valid single solids; nothing proud of the print reference face.
  Add checks for anything you had to reason about — a number you proved on
  paper and did not assert is a number that will drift.

(d) REPORT SHAPE
  [required final report verbatim, including "for the next agent"]
```

## 7. Failure modes, named

| Failure | What it produces |
|---|---|
| Prompt without recon | The agent spends its budget rediscovering facts you already had, and asserts a wrong one. |
| Missing locked-decisions block | Silent deviation on a settled question. |
| Gate stated as a quality rather than a number | "Done" means whatever the agent decided. |
| No handoff section | The next agent starts from zero, so symmetric work costs full price twice. |
| Trusting a reported gate | You build phase N+1 on an unverified phase N. |
| Parallel agents sharing a generator | Clobbering, plus each agent gating against a tree the other changed. |
| Re-dispatching into a barrier | Turns burned against an unsatisfiable constraint. The tell is the violation count not moving. |
| Cleanup without a manifest | Something load-bearing leaves, and you find out when the gate fails and cannot say what changed. |
