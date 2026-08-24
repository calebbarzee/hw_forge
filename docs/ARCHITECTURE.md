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
│   └── DRYRUN-HEXPAD.md            # validation record for a proving run
├── skills/hw-design/
│   ├── SKILL.md                    # the orchestrator: phases, gates, protocols
│   └── references/
│       ├── orchestration.md        # wave playbook + agent prompt templates
│       ├── kicad-api.md            # kicad-cli + headless pcbnew, every known trap
│       ├── electronics.md          # power topology, matrix routing, mirroring traps
│       ├── mechanical.md           # inserts, screws, stack-ups, printability
│       └── batteries.md            # cell tables, connectors, swell allowances
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

`kb/` lives inside the plugin repository for now, but knowledge-base roots are a
configurable path list: the plugin's `kb/` plus every entry in
`HW_FORGE_KB_ROOTS`, which is colon-separated. A separate personal or team
knowledge-base repository can plug in later without forking this one.

## 3. The eight-phase pipeline

Each phase has an entry contract, an owner (either the orchestrator inline or a
delegated agent), and a machine-checked exit gate. No phase starts until the
previous gate passes as re-verified by the orchestrator, rather than as
reported.

| # | Phase | Entry contract | Owner | Exit gate |
|---|---|---|---|---|
| 0 | **Spec lock** | a device idea | orchestrator + user | A decisions doc: locked choices verbatim, plus numbered open questions each carrying a recommendation. The user answers or explicitly delegates every one. |
| 1 | **Libraries + research** | locked spec | `resource-scout` | Every part resolves. A provenance manifest exists for each vendored asset. Pin tables are verified against two independent sources. Zero hand-authored geometry. |
| 2 | **Logical design** | resolved part list | agent | `design.py` imports clean under both the system Python and the CAD Python. Nets, pin maps, and topology all derive from it. |
| 3 | **Schematic** | clean `design.py` | `schematic-engineer` | ERC 0 (`kicad_gate.py --sch-only`, exit 0; a board-less project reports DRC as SKIPPED). A power-design decision record is written, meaning a decision document rather than a citation list. |
| 4 | **PCB** | ERC-clean schematic | `pcb-engineer`, one per board variant | DRC 0 at error severity with schematic parity enforced, 0 unconnected, zones filled headlessly inside the generator, and a wipe-and-rebuild reproducing the same canonical digest. |
| 5 | **Fab outputs** | gated board | `fab-docs-engineer` | Export assertions pass: every artifact non-empty, hole counts, the per-side placement split, declared-empty layers. A manifest stamps the export's provenance. Renders are inspected. |
| 6 | **Enclosure** | gated board files | `case-engineer` | All numeric `verify()` checks pass. Shells are valid single solids. Printability rules hold. |
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

**Locked decisions, with a barrier clause.** Every agent prompt carries the same
verbatim list of user-locked choices, marked as not open for relitigation.

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

**Model policy.** Opus for the design-critical roles, meaning schematic, PCB,
and case, encoded in the agent definitions themselves. Cheaper models are
adequate for resource scouting, fab exports, and documentation work.

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
| `scripts/preflight.py` | The smoke-test rule made executable | done |

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
   logged 94 shortfalls, of which 89 are fixed, 4 are deferred
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
python3 scripts/case_verify.py CHECKS.py [--suite NAME] [--dump-names FILE]
                                          [--baseline FILE] [--strict-baseline]
                                          [--map-suite] [--suite-blind]
                                          [--json] [--quiet]
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
