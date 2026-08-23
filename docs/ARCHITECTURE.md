# hw_forge — architecture

What this repo is, how it is laid out, and where each piece came from. The
pipeline described here is not a proposal: it is the generalized form of the
z_board v0.4 run, which produced three DRC-clean PCBs, a four-layer reversible
board, gated fab outputs and a verified printed case entirely by code
generation. Anything below that reads like process advice is process that
already ran.

It has since run **forwards** as well as backwards: the hexpad dry run
(`docs/DRYRUN-HEXPAD.md`) built a different board with a different topology from
this repo alone, reached every gate, and — across the original build and two
user-directed revisions — logged **94 shortfalls, of which 89 are fixed** as of
v0.3. z_board is where the pipeline came from; hexpad is the evidence that it
transfers.

The traffic now runs both ways, which is the point of keeping two fixtures:
hexpad's re-spec found that the schematic-parity gate had **never been
enforceable** in any project this repo scaffolded, and the audit that finding
demanded found the same blind spot on all four z_board boards — hiding two
missing components on one of them. A gap found forwards fixed a defect
backwards.

## 1. Three asset classes, three containers

The run produced three kinds of reusable thing, and they want different homes.

| Asset class | Examples | Container |
|---|---|---|
| **Process** | schematic-first ordering; gates as the build contract; the generate → read report → nudge one constant → regenerate loop; wave orchestration with handoff reports; manifest-then-execute cleanup | skill instructions (`skills/hw-design/SKILL.md` + `references/orchestration.md`) |
| **Knowledge** | the KiCad 10 `Flip()` enum trap; `SK6812MINI` vs `-E` pin-order divergence; VCC-gated LED rail and the series-R reasoning; insert bore / wall / screw-length stack-up arithmetic; FDM plate-down printability rules; LiPo size and capacity tables | reference docs loaded on demand, plus `kb/` cards |
| **Tools** | the gate runner; headless zone fill; fab-export assertions; BOM regrouping; s-expression geometry parser; the case `verify()` framework; project scaffolder | `scripts/`, runnable as-is |

The single most important process fact, restated because everything else follows
from it: **every artifact is code-generated and every phase has a
machine-checkable exit gate.** Agents never hand-edit CAD files, and the
orchestrator independently re-runs gates before trusting any agent's report.

The scope split between the last two rows is a resolved decision: hw_forge is a
**fully generic hardware-design skill**. Domain knowledge — keyboards, MX
geometry, ZMK specifics — does not live in the skill. It lives in the knowledge
base as markdown cards, recalled by domain and tag at each phase start. The
reference docs carry only knowledge that is generic to the tool or the physics:
the KiCad API, power-topology reasoning, mechanical stack-ups, cell tables.

## 2. Repo layout

Plugin-shaped from day one, so it versions in git, carries its scripts and agent
definitions alongside the skill, and installs once for use from any project.
Pre-plugin use still works: symlink `skills/hw-design` into `~/.claude/skills/`.

```
hw_forge/
├── .claude-plugin/plugin.json
├── README.md
├── docs/
│   ├── ARCHITECTURE.md             # this file
│   ├── BACKLOG.md                  # deferred work, with why and what closes it
│   └── DRYRUN-HEXPAD.md            # the validation verdict for the dry run
├── skills/hw-design/
│   ├── SKILL.md                    # the orchestrator: phases, gates, protocols
│   └── references/
│       ├── orchestration.md        # wave playbook + agent prompt templates
│       ├── kicad-api.md            # kicad-cli + headless pcbnew, every known trap
│       ├── electronics.md          # power topology, matrix routing, mirroring traps
│       ├── mechanical.md           # inserts, screws, stack-ups, printability
│       └── batteries.md            # LiPo tables, connectors, swell allowances
├── scripts/                        # genericized, no project constants
│   ├── preflight.py                # environment doctor + capability smoke test
│   ├── kicad_gate.py               # ERC + DRC(parity) + unconnected, JSON, exit codes
│   ├── kicad_zonefill.py           # headless ZONE_FILLER wrapper
│   ├── kicad_fab.py                # gerbers/drill/pos/BOM + assertion profile
│   ├── kicad_geom.py               # s-expr parser: outline, holes, footprint positions
│   ├── kicad_scaffold.py           # project + lib-tables + .kicad_pro severity patching
│   ├── kicad_digest.py             # canonical KIID-free digest: the determinism check
│   ├── case_verify.py              # numeric interference-check runner
│   ├── gerber_diff.py              # are two exports geometrically identical?
│   └── report.py                   # one-line summary of any kicad-cli JSON report
├── templates/
│   ├── design.py                   # logical-design skeleton
│   ├── Makefile                    # the gate-loop contract
│   ├── .gitignore                  # what a generated hardware repo keeps
│   └── prompts/                    # role prompts with locked-decision slots
├── commands/                       # single-phase slash entry points
│   ├── hw-preflight.md  hw-validate.md  hw-research.md
│   └── hw-export.md     hw-kb.md
├── agents/                         # role definitions, model policy encoded
│   ├── schematic-engineer.md  pcb-engineer.md  case-engineer.md
│   └── fab-docs-engineer.md   resource-scout.md
└── kb/                             # knowledge cards, by domain
    └── README.md                   # card format + index conventions
```

`kb/` lives inside the plugin repo for now, but KB **roots are a configurable
path list** — the plugin's `kb/` plus every entry in `HW_FORGE_KB_ROOTS`
(colon-separated) — so a separate personal or team knowledge-base repo plugs in
later without forking this one.

## 3. The eight-phase pipeline

Each phase has an **entry contract**, an **owner** (orchestrator inline vs
delegated agent), and a **machine-checked exit gate**. No phase starts until the
previous gate passes *as re-verified by the orchestrator*, not as reported.

| # | Phase | Entry contract | Owner | Exit gate |
|---|---|---|---|---|
| 0 | **Spec lock** | a device idea | orchestrator + user | a decisions doc: locked choices verbatim, plus numbered open questions each carrying a recommendation. User answers or explicitly delegates every one. |
| 1 | **Libraries + research** | locked spec | `resource-scout` | every part resolves; provenance manifest for each vendored asset; pin tables verified against two independent sources; zero hand-authored geometry |
| 2 | **Logical design** | resolved part list | agent | `design.py` imports clean under *both* the system Python and the CAD Python; nets, pin maps and topology all derive from it |
| 3 | **Schematic** | clean `design.py` | `schematic-engineer` | ERC 0 (`kicad_gate.py --sch-only`, exit 0 — a board-less project reports DRC as SKIPPED); power-design decision record written (a decision doc, not a citation list) |
| 4 | **PCB** | ERC-clean schematic | `pcb-engineer`, one per board variant | DRC 0 at error severity **with schematic parity**, 0 unconnected, zones filled headlessly inside the generator, and a wipe-and-rebuild reproducing the same canonical digest |
| 5 | **Fab outputs** | gated board | `fab-docs-engineer` | export assertions pass (every artifact non-empty, hole counts, the **per-side** placement split, declared-empty layers); a manifest stamping the export's provenance; renders eyeballed |
| 6 | **Enclosure** | gated board files | `case-engineer` | all numeric `verify()` checks pass; shells are valid single solids; printability rules hold |
| 7 | **Docs + hygiene + harvest** | everything above green | agent + orchestrator | docs describe the as-built state; gates still pass after cleanup; new lessons written into KB cards |

Two phase-ordering facts worth stating because they are not obvious:

**Power design belongs to phase 3, not phase 4.** It changes the netlist. On
z_board the power review added a series resistor on the LED data line, which
split one net into two and moved where the chain feed terminates — a schematic
change discovered during what could have been a PCB-phase review, and much
cheaper found early.

**The enclosure reads geometry out of the board files, never from a spec table
alone.** `kicad_geom.py` exists for exactly this. z_board's case model
transcribes its outline, its six mount-hole positions and its component
obstacles from the as-built DRC-clean boards, and one of its checks asserts that
the right half really is the mirror of the left about the board centre — which is
what licenses one model to serve both halves.

## 4. Cross-cutting rules

These live in `SKILL.md`'s body rather than a reference file, because they apply
to every phase.

**Proto slice first.** Build a one-cell version of anything that repeats — one
key, one LED, one fastener — and gate it before instantiating N. z_board's
`proto/` target is a one-key board and it is the first thing `make check` runs.

**Nudge, don't prove.** Geometry disputes are settled by regenerating and reading
the DRC or verify JSON, never by hand arithmetic. Every lane, offset and
clearance is a named constant so the loop is cheap. The evidence is direct: the
left half's MCU corner took most of a session proving clearance inequalities on
paper; the right half's was laid out from the pad table and passed DRC on the
first regeneration. The combined board went 374 violations → 0 in eleven passes
of exactly this loop.

**Toolchain smoke test before design work.** Version checks plus one throwaway
regeneration diffed against a known-good artifact. This is how the `Flip()`
regression was isolated to the toolchain instead of burning a design session: the
committed board still passed DRC under the new KiCad while a fresh regeneration
produced 295 violations, which localizes the fault to generation, not to rules or
design settings. `preflight.py` is this rule made executable, and it runs *first*.

**Handoff reports.** Every agent ends with a "for the next agent" section:
diagnosis, the named constants worth touching, budget advice. The right half's
fix landing clean on first regeneration came directly out of the left half's
handoff.

**Locked decisions, with a barrier clause.** Every agent prompt carries the same
verbatim list of user-locked choices, marked do-not-relitigate. When one of them
makes a gate impossible or forces a materially worse design, the agent **stops**
and returns a structured barrier report — what is blocked, why, options with
tradeoffs, a recommendation — which the orchestrator relays to the user as a
question. Grinding against the barrier and silently deviating are both
violations. This is the resolved form of a real tension: z_board rejected one
planned change *on evidence* (per-row LED rotation is not removable — without it
every westbound chain link crosses its own cell, 58 `shorting_items` on the first
attempt), and that rejection is only legitimate because it was reported and
recorded rather than quietly enacted.

**Model policy.** Opus for the design-critical roles — schematic, PCB, case —
encoded in the agent definitions themselves. Cheaper models are fine for
resource scouting, fab exports and documentation work.

## 5. Extraction map

Where each piece of hw_forge comes from in z_board, and its state.

| Source | Becomes | Work | State |
|---|---|---|---|
| the run's process, `NOTES.md` method notes, `HISTORY.md` phase structure | `skills/hw-design/SKILL.md` | generalize; strip the keyboard | **done** |
| the run's wave structure and agent prompts | `references/orchestration.md` | parameterize | **done** |
| `PIPELINE.md` | `docs/ARCHITECTURE.md` | fold resolved decisions into the body | **done** |
| — | `commands/*.md`, `agents/*.md` | new: single-phase entry points, role definitions with model policy | **done** |
| `kicad/report.py` | `scripts/report.py` | none — already generic | **done** |
| `kicad/Makefile` | `templates/Makefile` | strip project names; parameterize the project list | **done** |
| `kicad/fabcheck.py`, `kicad/mkbom.py` | `scripts/kicad_fab.py` | merge; assertions become a per-project profile file | **done** |
| `gen_pcb.py`'s zone-fill and severity-patch blocks | `scripts/kicad_zonefill.py`, `scripts/kicad_scaffold.py` | extract from the generator into standalone tools | **done** |
| the case agent's s-expr parser and `verify()` | `scripts/kicad_geom.py`, `scripts/case_verify.py` | genericize check registration | **done** |
| `kicad/design.py`'s shape | `templates/design.py` | reduce to skeleton plus comments | **done** |
| `kicad-agent-workflow.md`, `NOTES.md`'s KiCad-10 sections | `references/kicad-api.md` | rewrite as rules; strip project coordinates | **done** |
| `POWER.md`, `NOTES.md`'s routing and mirroring sections | `references/electronics.md` | rewrite as rules and decision trees | **done** |
| `case/README.md`, the case agent's report | `references/mechanical.md`, `references/batteries.md` | rewrite as formulas and tables | **done** |
| keyboard-specific facts from all of the above | `kb/` cards | one card per fact, tagged by domain | **done** |
| — | `scripts/preflight.py` | new: the smoke-test rule made executable | **done** |

`design.py` and `gen_pcb.py` themselves stay **project code**. hw_forge ships the
skeleton and the tools, not a universal generator: board topologies differ too
much, and the generator is the per-project deliverable the skill teaches you to
write.

## 6. Build phasing

1. **Scaffold + extraction.** Repo, plugin manifest, scripts and templates moved
   per §5, first-pass reference docs from existing material, process layer
   written. z_board is the source. **done**
2. **Genericize + self-test.** Run the scripts against z_board from the outside —
   the repo becomes hw_forge's regression fixture, and `kicad_gate.py` must
   reproduce its 0 / 0 / 0 / 0 on `proto`, `left`, `right` and `combo`.
   **done**, and it is now run as a regression gate before and after every
   change to `scripts/`.
3. **Dry run.** A fresh session designs a **6-key macro pad with a nice!view
   display on a nice!nano** using only the skill. Deliberately trivial: nothing
   about it should be hard, so everything the session has to ask about or
   rediscover is a gap in the skill, a missing knowledge card, or a script bug.
   **done — see `docs/DRYRUN-HEXPAD.md`.** hexpad reached ERC 0 / DRC 0 with
   parity / 0 unconnected on both the board and its proto slice, an asserted
   21-file fab package, and 215 passing enclosure checks. A user-directed **rev
   2** (module and display rotated 90°, board shrunk, case rebuilt) then reached
   the same gates at 239 enclosure checks, testing whether a *change* can be
   trusted rather than whether a board can be designed. A **rev 3 / 3.1
   re-spec** (diode matrix, rotary encoder, a 3D model per footprint, and four
   parts hand-dragged in pcbnew — two onto the other face) reached them again at
   416 enclosure checks, and tested the two things neither earlier round did:
   whether a change of *requirements* can be absorbed, and whether a **human
   edit** can be adopted back into a generate-only pipeline. Together they
   logged **94 gaps**: 89 fixed by v0.3, 4 deferred (`docs/BACKLOG.md`), 1
   works-as-intended. None was a design failure — every one was friction, a
   missing statement, or a tool that could not express something true. The macro
   pad exercised the whole spine once (direct-wire keys, an SPI display
   peripheral, a module on sockets, a battery, an enclosure with a plate and
   inserts) at a scale where a wrong answer cost minutes — and the re-spec
   proved the more valuable property: **the cheapest place to find a decorative
   gate is a board small enough that you notice its output is impossible.**
4. **Harden.** Agent definitions refined from what the dry run exposed —
   **done for the dry run's findings** (per-phase report templates, the
   `design.py` round-trip carve-out, the research doctrine's third outcome, the
   stated project layout) — then plugin packaging, including slash-command
   reachability from a project the plugin is not installed into
   (`docs/BACKLOG.md` B4). *(current)*
5. **Port off SWIG.** The migration path from SWIG `pcbnew` onto the IPC API
   (`kicad-python` / `kipy`). Forced work: SWIG is deprecated in KiCad 9 and
   removed in 11. Keep generators structured so the geometry layer is pure
   python and only a thin adapter touches `pcbnew` — that adapter is the port.

## 7. Interface contracts

The scripts are the stable surface. Commands, agents and the skill all invoke
them by these exact signatures, so the process layer and the tool layer can
change independently.

```
python3 scripts/preflight.py [--project DIR]
python3 scripts/kicad_gate.py PROJECT_DIR [--name NAME] [--sch-only]
                                          [--require-board]
KIPY   scripts/kicad_zonefill.py BOARD.kicad_pcb [-o OUT]
python3 scripts/kicad_fab.py PROJECT_DIR -o OUTDIR [--profile PROFILE.json]
python3 scripts/kicad_geom.py BOARD.kicad_pcb [--json]
python3 scripts/kicad_digest.py BOARD.kicad_pcb [--compare A B] [--expect SHA1]
python3 scripts/kicad_scaffold.py DIR NAME | DIR --repatch
python3 scripts/case_verify.py CHECKS.py
python3 scripts/gerber_diff.py OLD_FAB_DIR NEW_FAB_DIR
python3 scripts/report.py FILE.json
```

Two contract notes the dry run added. `kicad_gate.py` treats a **missing board
as a skipped check, not a failed one** (`--sch-only`, or auto-detected), so the
schematic phase's gate can pass in the phase that names it; a partial gate always
prints an explicit `PARTIAL` verdict, and `--require-board` restores the hard
failure. `kicad_fab.py` **refuses to start when its profile resolves inside the
output directory**, because it wipes that directory and would otherwise delete
its own configuration mid-run and still exit 0.

`KIPY` is KiCad's bundled Python, needed wherever `pcbnew` is imported. Scripts
discover `kicad-cli` and `pcbnew` themselves — platform defaults, including
`/Applications/KiCad/KiCad.app/...` on darwin — overridable with `KICAD_ROOT`.
Every gate script exits nonzero on failure and prints a per-check summary, which
is what lets a Makefile, a slash command and an agent all treat it as a test.
