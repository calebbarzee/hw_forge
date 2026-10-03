# hw_forge architecture

What this repository is, how it is laid out, and what contract each piece holds
to. For what hw_forge does and how to run it, see [`../README.md`](../README.md).

The pipeline described here is the generalised form of a completed hardware run.
It has since been exercised forwards as well: a separate proving run built a
different board with a different topology from this repository alone, reached
every gate, and produced the shortfall log that `docs/BACKLOG.md` triages. The
validation record for that run is in `docs/DRYRUN-HEXPAD.md`.

## 1. Three asset classes, three containers

A hardware run produces three kinds of reusable thing, and they need different
homes.

| Asset class | Examples | Container |
|---|---|---|
| **Process** | Schematic-first ordering. Gates as the build contract. The generate, read report, nudge one constant, regenerate loop. Wave orchestration with handoff reports. Manifest-then-execute cleanup. | Skill instructions: `skills/hw-design/SKILL.md` and `references/orchestration.md` |
| **Knowledge** | The KiCad 10 `Flip()` enum trap. Divergent pin order between two variants of one part family. Gated-rail topology and the series-resistor reasoning. Insert bore, wall, and screw-length stack-up arithmetic. Printability rules for a plate-down orientation. Cell size and capacity tables. | Reference documents loaded on demand, plus `kb/` cards |
| **Tools** | The gate runner. Headless zone fill. Fab-export assertions. BOM regrouping. The s-expression geometry parser. The case `verify()` framework. The project scaffolder. | `scripts/`, runnable as-is |

The process fact everything else follows from: **every artifact is
code-generated, and every phase has a machine-checkable exit gate.** Agents
never hand-edit CAD files, and the orchestrator independently re-runs gates
before trusting any agent's report.

The split between the last two rows is a resolved decision. hw_forge is a
**generic hardware-design skill**. Domain knowledge, such as keyboard geometry
or a particular firmware's pin quirks, does not live in the skill. It lives in
the knowledge base as markdown cards, recalled by domain and tag at each phase
start.

The reference documents carry only knowledge that is generic to the tool or the
physics: the KiCad API, power-topology reasoning, mechanical stack-ups, and cell
tables.

## 2. Repository layout

The repository is plugin-shaped, so it versions in git, carries its scripts and
agent definitions alongside the skill, and installs once for use from any
project. Pre-plugin use still works: symlink `skills/hw-design` into
`~/.claude/skills/`.

```
hw_forge/
├── .claude-plugin/plugin.json
├── README.md
├── docs/
│   ├── ARCHITECTURE.md             # this file
│   ├── BACKLOG.md                  # deferred work, with why and what closes it
│   ├── QUALITY.md                  # the property sequence the pipeline proves, check by check
│   └── DRYRUN-HEXPAD.md            # validation record for a proving run
├── skills/hw-design/
│   ├── SKILL.md                    # the orchestrator: phases, gates, protocols
│   └── references/
│       ├── intake.md               # phase-0 question bank, defaults, the worked case
│       ├── orchestration.md        # wave playbook + agent prompt templates
│       ├── kicad-api.md            # kicad-cli + headless pcbnew, every known trap
│       ├── autorouting.md          # scripted vs autorouted copper, the hybrid flow
│       ├── kicad-ecosystem.md      # plugins, MCP servers, tools: adopt/evaluate/skip
│       ├── electronics.md          # power topology, matrix routing, mirroring traps
│       ├── mechanical.md           # inserts, screws, stack-ups, printability
│       ├── batteries.md            # cell tables, connectors, swell allowances
│       ├── silkscreen.md           # readability rules, placement algorithm, the phase-4 gate
│       ├── domains.md              # per electrical domain: failure modes the gates cannot see
│       └── interfaces.md           # per connector standard: pinout, circuit, mating, rule ids
├── scripts/                        # genericized, no project constants
│   ├── preflight.py                # environment doctor + capability smoke test
│   ├── kicad_gate.py               # ERC + DRC(parity) + unconnected, JSON, exit codes
│   ├── kicad_zonefill.py           # headless ZONE_FILLER wrapper
│   ├── kicad_fab.py                # gerbers/drill/pos/BOM + assertion profile
│   ├── kicad_geom.py               # s-expr parser: outline, holes, positions; --contract: the fit contract
│   ├── kicad_scaffold.py           # project + lib-tables + .kicad_pro severity patching
│   ├── kicad_digest.py             # canonical KIID-free digest: the determinism check
│   ├── kicad_3d.py                 # STEP assembly export, verify, render
│   ├── kicad_fpcheck.py            # pad geometry vs the declared package
│   ├── packages.json               # nominal package dimensions, every number cited
│   ├── kicad_silkcheck.py          # silk readability: floors, overlaps, orientation, labels
│   ├── kicad_fplib.py              # fork and edit a project-local footprint: the fpcheck fix
│   ├── kicad_bom.py                # BOM field audit + export; board-inherent items excluded
│   ├── kicad_schrules.py           # schematic rules ERC does not cover: decoupling, bulk, pull-ups
│   ├── kicad_route.py              # autorouter bridge (Freerouting DSN/SES, KiCadRoutingTools) + adopt
│   ├── hw_install.py               # one-command install of the optional tools, pinned and checksummed
│   ├── case_verify.py              # numeric interference-check runner + contract-driven fit checks
│   ├── kicad_ifcheck.py            # connectors against their interface standards
│   ├── interfaces.schema.json      # the interface-definition format
│   ├── interfaces/                 # worked definitions: usb-c-device, power-2pin, header-2.54-swd
│   ├── hw_review.py                # the pre-order gate: every check, one readiness table
│   ├── gerber_diff.py              # are two exports geometrically identical?
│   └── report.py                   # one-line summary of any kicad-cli JSON report
├── templates/
│   ├── design.py                   # logical-design skeleton, with the PACKAGES table
│   ├── SPEC.md                     # decisions-doc skeleton: Locked, Delegated, Design intent
│   ├── Makefile                    # the gate-loop contract; fab depends on review
│   ├── drc-baseline.kicad_dru      # stock-safe custom DRC rules, installed by the scaffolder
│   ├── drc-fork.kicad_dru          # rules only the forked kicad-cli compiles, probe-gated
│   ├── sch-rules.json              # kicad_schrules.py defaults, every key documented
│   ├── .gitignore                  # what a generated hardware repo keeps
│   └── prompts/                    # role prompts with locked-decision slots
├── commands/                       # single-phase slash entry points
│   ├── hw-preflight.md  hw-validate.md  hw-research.md
│   └── hw-export.md     hw-bom.md        hw-kb.md
├── agents/                         # role definitions, model policy encoded
│   ├── schematic-engineer.md  pcb-engineer.md  case-engineer.md
│   └── fab-docs-engineer.md   resource-scout.md
└── kb/                             # knowledge cards, by domain
    └── README.md                   # card format + index conventions
```

`kb/` lives inside the plugin repository for now, but knowledge-base roots are a
configurable path list: the plugin's `kb/` plus every entry in
`HW_FORGE_KB_ROOTS`, which is colon-separated. A separate personal or team
knowledge-base repository can plug in later without forking this one.

## 3. The pipeline: eight phases and the pre-order review

Each phase has an entry contract, an owner (either the orchestrator inline or a
delegated agent), and a machine-checked exit gate. No phase starts until the
previous gate passes as re-verified by the orchestrator, rather than as
reported.

| # | Phase | Entry contract | Owner | Exit gate |
|---|---|---|---|---|
| 0 | **Spec lock** | a device idea | orchestrator + user | `SPEC.md` from the intake question bank (`references/intake.md`), asked in one batch: locked choices verbatim, delegated defaults recorded, a placement-intent table and a rules list that every agent prompt carries. Every question with no safe default is answered or explicitly delegated. |
| 1 | **Libraries + research** | locked spec | `resource-scout` | Every part resolves. A provenance manifest exists for each vendored asset. Pin tables are verified against two independent sources. Zero hand-authored geometry, 3D models included. Every resolved footprint is checked against the part's declared package with `kicad_fpcheck.py`. |
| 2 | **Logical design** | resolved part list | agent | `design.py` imports clean under both the system Python and the CAD Python. Nets, pin maps, and topology all derive from it. |
| 3 | **Schematic** | clean `design.py` | `schematic-engineer` | ERC 0 (`kicad_gate.py --sch-only`, exit 0; a board-less project reports DRC as SKIPPED). A power-design decision record is written, meaning a decision document rather than a citation list. `kicad_bom.py audit` exits 0: every sourced part carries its sourcing fields and every board-inherent symbol is excluded from the BOM. `kicad_schrules.py` exits 0: no error-severity finding for decoupling, bulk capacitance, LED data resistor or pull-ups (connector input protection is a warning, fixed or waived with a reason). |
| 4 | **PCB** | ERC-clean schematic | `pcb-engineer`, one per board variant | DRC 0 at error severity with schematic parity enforced, 0 unconnected, zones filled headlessly inside the generator, and a wipe-and-rebuild reproducing the same canonical digest. Autorouted copper, where the spec permits it, is adopted back into the generator as a committed routing file (`kicad_route.py adopt`). Silk passes `kicad_silkcheck.py`. Every declared connector passes `kicad_ifcheck.py`, and the fit contract (`kicad_geom.py --contract`) exits 0: every connector declares a mating direction and its face points out through its edge. `make check` is the DRC half of this gate; `make review` runs the whole of it. |
| 5 | **Fab outputs** | gated board that has passed the pre-order review (5a) | `fab-docs-engineer` | Export assertions pass: every artifact non-empty, hole counts, the per-side placement split, declared-empty layers. A manifest stamps the export's provenance. Renders are inspected. `kicad_fpcheck.py` runs clean before any export. `kicad_bom.py audit` re-runs clean, and the BOM step fails on any empty required cell. |
| 5a | **Pre-order review** | gated board plus fab profile. Runs after phase 4 and before the phase 5 fab export, and again after phase 6 when there is an enclosure | orchestrator | `hw_review.py PROJECT_DIR` exits 0: preflight, gate, package check, BOM audit, schematic rules (`kicad_schrules.py`), silk, interface check, fit contract, case suite, fab assertions (into a scratch directory) and 3D assembly, as one readiness table. Every SKIP or WARN is relayed as a property not proven. `make fab` depends on it. |
| 6 | **Enclosure** | gated board files and the fit contract | `case-engineer` | All numeric `verify()` checks pass, including the contract-driven fit checks (board in cavity, part clearance, connector openings, minimum wall, fastener stack-up). Shells are valid single solids. Printability rules hold. |
| 7 | **Docs + hygiene + harvest** | everything above green | agent + orchestrator | Docs describe the as-built state. Gates still pass after cleanup. New lessons are written into knowledge-base cards. |

Two phase-ordering facts are worth stating because they are not obvious.

**Power design belongs to phase 3, not phase 4.** It changes the netlist. In one
run a power review added a series resistor on an addressable-LED data line,
which split one net into two and moved where the chain feed terminates. That is
a schematic change discovered during what could have been a PCB-phase review,
and it is much cheaper found early.

**The enclosure reads geometry out of the board files, never from a spec table
alone.** `kicad_geom.py` exists for exactly this. A case model transcribes its
outline, its mount-hole positions, and its component obstacles from the
as-built, gate-passing boards.

One of its checks asserts that a mirrored variant really is the mirror of its
sibling about the board centre, which is what licenses one model to serve both
halves.

## 4. Cross-cutting rules

These live in `SKILL.md`'s body rather than a reference file, because they apply
to every phase.

**Proto slice first.** Build a one-cell version of anything that repeats, such
as one key, one LED, or one fastener, and gate it before instantiating N. A
project's `proto/` target is that one-cell board, and it is the first thing
`make check` runs.

**Nudge, do not prove.** Geometry disputes are settled by regenerating and
reading the DRC or `verify()` JSON, never by hand arithmetic. Every lane,
offset, and clearance is a named constant so the loop is cheap.

The evidence is direct. In one run, a board's first module corner took most of a
session proving clearance inequalities on paper, while the mirrored corner was
laid out from the pad table and passed DRC on the first regeneration. Another
board went from 374 violations to 0 in eleven passes of exactly this loop.

**Toolchain smoke test before design work.** Version checks, plus one throwaway
regeneration diffed against a known-good artifact.

This is how a `Flip()` regression was isolated to the toolchain instead of
burning a design session. The committed board still passed DRC under the new
KiCad while a fresh regeneration produced 295 violations, which localises the
fault to generation rather than to rules or design settings. `preflight.py` is
this rule made executable, and it runs first.

**Handoff reports.** Every agent ends with a "for the next agent" section:
diagnosis, the named constants worth touching, and budget advice. A mirrored
variant landing clean on first regeneration comes directly out of its sibling's
handoff.

**Locked decisions, with an escalation ladder.** Every agent prompt carries the
same verbatim list of user-locked choices, marked as not open for relitigation,
plus the placement-intent and rules blocks from `SPEC.md`.

Mid-run choices the spec did not name sit on a three-tier ladder
(`SKILL.md`, "Locked decisions and the escalation ladder"). Tier 1 is decided
and logged. Tier 2 is decided, then flagged for review at the next phase
boundary. Tier 3 stops and asks: anything that changes a locked decision, adds
or removes a part, interface, or board, moves the outline, layer count, or unit
cost past the threshold in `SPEC.md` (20% by default), blocks fab or assembly,
or touches safety. Tier 3 questions are batched into one DECISION REQUEST per
wave unless one blocks all further work.

When one of them makes a gate impossible or forces a materially worse design,
the agent stops and returns a structured barrier report stating what is blocked,
why, the options with their tradeoffs, and a recommendation. The orchestrator
relays that to the user as a question. Grinding against the barrier and silently
deviating from it are both violations.

This is the resolved form of a real tension. One run rejected a planned change
on evidence: per-row LED rotation turned out not to be removable, because
without it every westbound chain link crosses its own cell, giving 58
`shorting_items` on the first attempt. That rejection is legitimate only because
it was reported and recorded rather than quietly enacted.

**Model policy.** A dial. Sonnet for research, vendoring, exports,
documentation, and bounded implementation with a machine-checkable gate; these
fan out in parallel, one agent per disjoint subtree, and the orchestrator
re-runs every gate itself (`references/orchestration.md` §2). Opus, by default,
for the design-critical roles, meaning schematic, PCB, and case, encoded in the
agent definitions themselves. Lowering the design roles is the user's explicit
call, never a cost optimisation the orchestrator makes on its own.

## 5. Component inventory

What each piece of hw_forge is, and its state.

| Component | Purpose | State |
|---|---|---|
| `skills/hw-design/SKILL.md` | The process layer: phases, gates, protocols, failure policy | done |
| `references/orchestration.md` | Wave playbook and agent prompt templates | done |
| `docs/ARCHITECTURE.md` | This file: structure and contracts | done |
| `commands/*.md`, `agents/*.md` | Single-phase entry points, and role definitions with model policy | done |
| `scripts/report.py` | One-line summary of any `kicad-cli` JSON report | done |
| `templates/Makefile` | The gate-loop contract, with a parameterised project list | done |
| `scripts/kicad_fab.py` | Fab export plus assertions, driven by a per-project profile file | done |
| `scripts/kicad_zonefill.py`, `scripts/kicad_scaffold.py` | Headless zone fill and project scaffolding, extracted from generator code into standalone tools | done |
| `scripts/kicad_geom.py`, `scripts/case_verify.py` | S-expression geometry reader, and the numeric check runner with generic check registration | done |
| `templates/design.py` | Logical-design skeleton, reduced to structure plus comments | done |
| `references/kicad-api.md` | KiCad API surface and traps, written as rules with no project coordinates | done |
| `references/electronics.md` | Power topology, routing, and mirroring, written as rules and decision trees | done |
| `references/mechanical.md`, `references/batteries.md` | Fastening and printability, and cell tables, written as formulas and tables | done |
| `kb/` cards | One card per domain-specific fact, tagged by domain | done |
| `scripts/preflight.py` | The smoke-test rule made executable; reports whether an autorouter is reachable, non-fatally | done |
| `scripts/kicad_fpcheck.py`, `scripts/packages.json` | Pad geometry against the declared package, with a cited nominal-dimension table | done |
| `scripts/kicad_silkcheck.py`, `references/silkscreen.md` | Silk readability against the fab's floors: size/stroke, pad/text overlap, reading orientation, refdes distance, required labels by part class | done |
| `scripts/kicad_bom.py` | BOM field completeness audit and export, with the board-inherent exclusion rule | done |
| `scripts/kicad_schrules.py`, `templates/sch-rules.json` | Schematic rules ERC does not cover: decoupling, bulk capacitance, LED data resistor, pull-up windows per net class, connector input protection; DNP parts excluded | done; connectivity only, placement distance is a board check |
| `scripts/kicad_fplib.py` | Fork a stock footprint into the project library and edit pads, model link, and provenance fields; the path from a finding to a fabbed change | done |
| `scripts/hw_install.py` | Pinned, checksummed install of Freerouting, the Fabrication Toolkit, and KiCadRoutingTools; `--check` reports without downloading | done |
| `scripts/kicad_route.py` | The Specctra DSN/SES bridge to an external autorouter, and the adopt step that freezes routes into `kicad/routing.py` | done; both backends (Freerouting, KiCadRoutingTools) run end to end on a test board, see `kb/runs/hexpad-autoroute-2026-09-20.md` |
| `references/intake.md`, `templates/SPEC.md` | The phase-0 question bank and the decisions-doc skeleton | done |
| `docs/QUALITY.md` | The generic quality process: the property sequence, the check that proves each, the three failure classes | done |
| `kicad_geom.py --contract` | The board-to-enclosure fit contract, versioned schema; fails a connector with no mating direction, and a mating face that does not point out through its edge (B8) | done |
| `case_verify.py` fit checks | `board_in_cavity`, `cavity_clearance`, `connector_openings`, `min_wall` (B9), `fastener_stackup`, solid mode in build123d or numeric mode | done; part bodies are boxes, see `QUALITY.md` §3 |
| `scripts/kicad_ifcheck.py`, `interfaces.schema.json`, `scripts/interfaces/` | Connectors against their standards, with the rule ids of `references/interfaces.md` | done for USB-C device, generic 2-pin power and 2.54 mm SWD headers; other standards need a definition file |
| `references/domains.md`, `references/interfaces.md`, `kb/interfaces/` | Per-domain failure modes and per-connector requirements, written for any EE design | done |
| `scripts/hw_review.py` | The pre-order gate, one readiness table | done |
| `templates/drc-baseline.kicad_dru`, `templates/drc-fork.kicad_dru` | Fab-floor custom DRC rules for every project, written once and never overwritten; fork-only rules a marked block, inserted only behind the preflight probe and removed on a stock binary | done |
| `references/autorouting.md` | Scripted against autorouted copper: the decision rule, hybrid flow, and tool comparison | done |
| `references/kicad-ecosystem.md` | Plugins, MCP servers, and tools for headless KiCad, with adopt, evaluate, or skip verdicts | done |

`design.py` and `gen_pcb.py` themselves stay **project code**. hw_forge ships
the skeleton and the tools, not a universal generator. Board topologies differ
too much, and the generator is the per-project deliverable the skill teaches you
to write.

## 6. Build phasing

1. **Scaffold and extraction.** Repository, plugin manifest, scripts and
   templates arranged per §5, first-pass reference documents, and the process
   layer written. **Done.**
2. **Genericise and self-test.** Run the scripts against a completed project
   from the outside, so that project becomes hw_forge's regression fixture and
   `kicad_gate.py` must reproduce its 0 / 0 / 0 / 0 across every board variant.
   **Done**, and now run as a regression gate before and after every change to
   `scripts/`.
3. **Proving run.** A fresh session designs a small board using only the skill.
   Deliberately trivial, so that anything the session has to ask about or
   rediscover is a gap in the skill, a missing knowledge card, or a script bug.
   **Done.** The run and two user-directed revisions reached every gate and
   logged 94 shortfalls, of which 90 are fixed, 3 are deferred
   (`docs/BACKLOG.md`), and 1 works as intended. None was a design failure.
   Full record in `docs/DRYRUN-HEXPAD.md`.
4. **Harden.** Refine the agent definitions from what the proving run exposed.
   **Done for that run's findings**, covering per-phase report templates, the
   `design.py` round-trip carve-out, the research doctrine's third outcome, and
   the stated project layout.

   Remaining: plugin packaging, including slash-command reachability from a
   project the plugin is not installed into (`docs/BACKLOG.md` B4). *Current
   stage.*
5. **Port off SWIG.** Migrate from the SWIG `pcbnew` module to the IPC API
   (`kicad-python` / `kipy`). This is forced work, because SWIG is deprecated in
   KiCad 9 and removed in 11. Keep generators structured so the geometry layer
   is pure python and only a thin adapter touches `pcbnew`. That adapter is the
   port.

## 7. Interface contracts

The scripts are the stable surface. Commands, agents, and the skill all invoke
them by these signatures, so the process layer and the tool layer can change
independently.

```
python3 scripts/preflight.py [--project DIR] [--smoke]
python3 scripts/kicad_gate.py PROJECT_DIR [--name NAME] [--sch-only]
                                          [--require-board] [--strict-parity]
                                          [--quiet]
KIPY   scripts/kicad_zonefill.py BOARD.kicad_pcb [-o OUT] [--island-mode MODE]
                                          [--min-island MM2] [--no-repatch]
python3 scripts/kicad_fab.py PROJECT_DIR -o OUTDIR [--profile PROFILE.json]
                                          [--name NAME] [--no-x2] [--keep]
python3 scripts/kicad_geom.py BOARD.kicad_pcb [--json] [--max-rows N]
                                          [--diff OLD NEW] [--as-constants]
                                          [--strict]
python3 scripts/kicad_digest.py BOARD.kicad_pcb [--compare A B] [--expect SHA1]
                                          [--stamp DOC [--write]] [--json]
python3 scripts/kicad_scaffold.py DIR NAME | DIR --repatch
                                          [--severity RULE=LEVEL] [--design-rule K=V]
                                          [--net-class ...] [--sym-lib ...] [--fp-lib ...]
                                          [--fork-rules] [--reinstall-rules] [--no-rules]
python3 scripts/kicad_schrules.py SCH [--rules FILE] [--set RULE.KEY=VALUE]
                                          [--netlist XML] [--json] [--selftest]
python3 scripts/kicad_geom.py BOARD.kicad_pcb --contract FIT.json
                                          [--design design.py] [--no-models]
python3 scripts/case_verify.py CHECKS.py [--suite NAME] [--dump-names FILE]
                                          [--baseline FILE] [--strict-baseline]
                                          [--map-suite] [--suite-blind]
                                          [--contract FIT.json]
                                          [--json] [--quiet]
python3 scripts/kicad_ifcheck.py SCH [--design design.py] [--board BOARD]
                                          [--netlist NET] [--allow-undefined]
                                          [--list] [--json]
python3 scripts/hw_review.py PROJECT_DIR [--name NAME] [--design design.py]
                                          [--case CHECKS.py] [--case-python PY]
                                          [--fab PROFILE] [--assembly jlcpcb|none]
                                          [--rules FILE] [--strict-interfaces]
                                          [--no-3d] [--keep DIR] [--json]
python3 scripts/gerber_diff.py OLD_FAB_DIR NEW_FAB_DIR
python3 scripts/report.py FILE.json [--strict] [--by-owner] [--baseline FILE]
                                          [--indent N]
```

Run any script with `--help` for the authoritative flag list, including
defaults and metavars.

Two contract notes came out of the proving run.

`kicad_gate.py` treats a **missing board as a skipped check, not a failed one**,
either via `--sch-only` or by auto-detection, so the schematic phase's gate can
pass in the phase that names it. A partial gate always prints an explicit
PARTIAL verdict, and `--require-board` restores the hard failure.

`kicad_fab.py` **refuses to start when its profile resolves inside the output
directory**, because it wipes that directory and would otherwise delete its own
configuration mid-run and still exit 0.

`KIPY` is KiCad's bundled Python, needed wherever `pcbnew` is imported. Scripts
discover `kicad-cli` and `pcbnew` themselves, from platform defaults including
`/Applications/KiCad/KiCad.app/...` on darwin, overridable with `KICAD_ROOT`.

Every gate script exits nonzero on failure and prints a per-check summary. That
is what lets a Makefile, a slash command, and an agent all treat it as a test.
