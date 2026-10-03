# hw_forge

A Claude Code plugin that runs hardware design as a gated build.

You describe a device. Agents write generators: Python that emits KiCad
schematics and boards, and code-CAD that emits a printed enclosure. Each phase
must clear a machine-checkable gate before the next one starts.

The deliverable is not a board file that someone drew. It is a repository that
regenerates its own board files with `make && make check`, together with the
evidence that the result passes.

## Quick start

From a Claude Code session:

```
/plugin marketplace add /path/to/hw_forge
/plugin install hw-forge@hw-forge
/hw-preflight
```

`/hw-preflight` locates your KiCad install, checks its version, and runs the
specific operations the pipeline depends on: headless `pcbnew`, zone fill, and
the `kicad-cli` exports. On failure it prints the fix command and stops.

Once preflight exits 0, there are two entry points.

To check a KiCad project you already have:

```
/hw-validate path/to/project
```

This reports ERC, DRC with schematic parity, and unconnected nets, one line per
board, with an explicit pass or fail. On failure it groups the violations by
cause rather than listing them by count.

To design a new board, describe it in plain language:

> design me a 6-key macro pad on a nice!nano with a nice!view display

The `hw-design` skill takes it from there. Expect it to settle decisions with
you first, then work in long autonomous stretches, stopping when a gate fails or
a locked decision needs your input.

## How it works

Five rules govern the pipeline.

**Every artifact is code-generated.** One logical design file holds the nets,
pin tables, part list, and topology. The schematic emitter and the board emitter
both read it, so the two cannot drift apart. Symbols and footprints for
project-local parts are generated from that same pin table, so a symbol and a
footprint for one part cannot disagree about which pad is pin 1.

**Every phase ends at a machine-checkable gate.** ERC 0. DRC 0 at error severity
with schematic parity enforced. 0 unconnected nets. Fab exports assert their
hole counts and placement counts. The enclosure passes numeric interference
checks. `kicad-cli --exit-code-violations` returns 5 when a check fails, which
is what makes DRC part of the build rather than a report.

**Agents never hand-edit CAD files.** Tracks carry unique identifiers, zones
carry cached fills, and nothing revalidates until KiCad reopens the file. A
question about geometry is settled by changing a named constant in the
generator, regenerating, and reading the DRC JSON output, not by arithmetic on
paper.

**The orchestrator re-runs every gate itself.** An agent's report that a gate
passed is a claim, not evidence. The orchestrator runs `kicad_gate.py` between
waves and reads the JSON.

**Locked decisions carry a barrier clause, and mid-run choices climb an
escalation ladder.** Every agent prompt repeats the
user's locked choices verbatim and marks them as not open for renegotiation. If
a locked choice makes a gate unreachable or forces a materially worse design,
the agent stops and returns a barrier report: what is blocked, why, the options
with their tradeoffs, and a recommendation. The orchestrator relays that to the
user as a question. Grinding against a locked decision and quietly working
around it are both violations.

## Two ways to use it

**The `hw-design` skill** runs the full pipeline. It works through eight phases:
spec lock, libraries and research, logical design, schematic, PCB, fab outputs,
enclosure, then documentation and knowledge harvest. It decides what to run
inline and what to delegate, writes the agent prompts, runs the waves, and
re-verifies each gate before opening the next phase. Use it for new boards and
for structural changes to existing ones.

Spec lock is an intake, not a summary. The skill asks a question bank in one
batch, covering the device's objective, where each part goes and what the user
touches, the rules the board must follow, and the package of every part that is
not a fixed module. Each question carries a default or is marked as needing an
answer, so "take the defaults" is a complete reply. After that the run is
autonomous, with research and bounded implementation fanned out to parallel
agents, until a decision meets the escalation ladder: small choices are logged,
choices a user would care about are flagged at the next phase boundary, and
anything that changes a locked decision, adds or removes a part, moves the
outline, layer count, or cost past a threshold, or blocks fab stops and asks.

**Six slash commands** are single-phase entry points over the same scripts, for
when you have a project already and want one thing done.

| Command | What it does |
|---|---|
| `/hw-preflight` | Checks the toolchain is present, correct, and capable of the operations the pipeline needs. Prints the exact fix command on failure. It does not work around a broken toolchain. |
| `/hw-validate` | Runs the gate on a project and groups any failures by cause. |
| `/hw-research` | Acquires datasheets, footprint libraries, and reference designs, searching the local machine before the web. Vendors them with a provenance manifest and verifies pin tables against two independent sources. |
| `/hw-export` | Regenerates fab outputs and renders, and asserts the artifacts are real. |
| `/hw-bom` | Audits a schematic's bill-of-materials fields, fills them from researched sources through `design.py`, and keeps board-inherent geometry such as mounting holes and fiducials off the parts list. |
| `/hw-kb` | Searches the knowledge base, or writes a lesson into it. |

Run `/hw-preflight` once on a new machine. Reach for the others as needed.

## The knowledge base

Hardware work depends on many small, specific facts. A KiCad API argument whose
meaning changed between versions. The pin order of one part variant. The
arithmetic that turns a cavity depth into a screw length. None of these can be
derived, and each one costs debugging time every time it is rediscovered.

hw_forge stores them as markdown cards under `kb/`, organized by domain. The
pipeline reads and writes the knowledge base twice per run. At each phase start,
a recall step pulls the cards matching that phase's domain and tags into context
before any design work begins. At the end of the run, a harvest step records
what the run learned, either as new cards or as edits to existing ones.

Knowledge-base roots are a path list rather than a fixed directory. The list is
the plugin's own `kb/` plus every directory named in `HW_FORGE_KB_ROOTS`, which
is colon-separated. A personal or team knowledge base plugs in without forking
this repository.

`kb/README.md` defines the card format, and the rule for what belongs in a card
rather than in a reference document.

## Install

As a plugin, from a Claude Code session:

```
/plugin marketplace add /path/to/hw_forge
/plugin install hw-forge@hw-forge
```

Then the optional tools, in one command that reports first and installs only
when asked:

```bash
python3 scripts/hw_install.py --check
```

```bash
python3 scripts/hw_install.py --all
```

To work on the plugin itself, symlink the skill into your user skills directory
instead:

```bash
ln -s /path/to/hw_forge/skills/hw-design ~/.claude/skills/hw-design
```

The two installs put `scripts/` in different places. As a plugin it is
`${CLAUDE_PLUGIN_ROOT}/scripts/`. Symlinked, it is the `scripts/` directory
beside the `hw-design` skill. The skill states the rule, and the orchestrator
resolves the root once and passes it into every agent prompt.

Two environment variables are optional. `HW_FORGE_KB_ROOTS` adds knowledge-base
roots. `KICAD_ROOT` points at a KiCad install that the discovery logic does not
find on its own; discovery checks the platform defaults first, including
`/Applications/KiCad/KiCad.app` on macOS.

## Requirements

- KiCad 10 or newer. Its bundled Python interpreter is used wherever `pcbnew` is
  imported.
- Python 3.
- build123d, for enclosure work only.
- For boards that use the autorouting bridge: KiCadRoutingTools (the default
  backend, MIT, with its own small Python environment) and, as a fallback,
  Freerouting with a Java 25 runtime. For JLCPCB assembly files: the
  Fabrication Toolkit plugin. `python3 scripts/hw_install.py --check` reports
  which are present; `--all` installs all three, pinned to a version and a
  SHA-256. `/hw-preflight` reports a missing router as a warning, not a
  failure. Nothing installs on its own.

`/hw-preflight` reports which of these is missing or wrong.

## Checks the four gates cannot make

ERC, DRC, schematic parity, and the unconnected count prove a board is
consistent with its schematic. They do not prove a footprint is the right one
for the part in the bill of materials. A flash chip chosen in a wide SOIC-8 with
narrow SOP-8 pads passes all four and is caught by the assembly house, after
every other file agrees with the wrong footprint (`kb/runs/`). So
`kicad_fpcheck.py` checks every footprint's pad geometry against the package
the design declares in `design.py`, with a cited table of nominal dimensions in
`scripts/packages.json`, and `make fab` depends on it.

Fit and connection follow the same reasoning. `kicad_geom.py --contract`
writes the board-to-enclosure fit contract and fails a connector whose mating
face points inboard, `kicad_ifcheck.py` checks each declared connector against
its standard (a USB-C device port's CC pulldowns, a battery connector's
polarity), and `case_verify.py` checks the case against the contract.
`hw_review.py` runs every check as one pre-order table, and `make fab` depends
on it. [`docs/QUALITY.md`](docs/QUALITY.md) lists the property each check
proves.

Routing follows the same split. Regular repeated cells such as a key matrix are
routed by the generator as named constants. Irregular placement with many nets
routes the critical nets by script, locks them, hands the rest to an external
autorouter through `kicad_route.py`, and adopts the result back into the
generator as a committed routing file, so the board stays a function of
`design.py` and that file. `skills/hw-design/references/autorouting.md` has the
decision rule.

## The extension ecosystem

KiCad has a large plugin and MCP server ecosystem, and hw_forge's own scripts
already cover the surface most of it exposes: `kicad-cli`, headless `pcbnew`,
and project-file patching. `skills/hw-design/references/kicad-ecosystem.md`
surveys what exists with a verdict for each: adopt, evaluate, or skip. Adopted:
`kicad-cli` for every check and export, the Fabrication Toolkit plugin for
JLCPCB assembly files, and Freerouting as the autorouting bridge. Generic KiCad
MCP servers are a deliberate skip. They duplicate the scripts and open a channel
for an agent to edit CAD files live, which is the rule this pipeline exists to
prevent.

## Status

Version 0.3.

**v0.3 changes behaviour for new projects.** `kicad_scaffold.py` now sets the
five KiCad schematic-parity checks to `error` severity in every project it
scaffolds. `kicad_gate.py` reports `parity UNENFORCED` on a project whose
`.kicad_pro` does not carry them, and fails outright under `--strict-parity`.

The reason: KiCad ships all five parity checks at `warning` severity, and the
gate filters on `--severity-error`. Passing `--schematic-parity` therefore could
not fail a build. Any project scaffolded before v0.3 reports `parity ok` from a
check that cannot fail. Stated generally, a check whose severity is below the
severity you filter on is not a check.

Deferred work, with the reason for each item and what would close it, is in
[`docs/BACKLOG.md`](docs/BACKLOG.md). The pipeline's structure and its phase
contracts are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Next is plugin packaging, including making the slash commands reachable from a
project that does not have the plugin installed. After that comes the migration
from the SWIG `pcbnew` module to the IPC API (`kicad-python`). That migration is
forced work: SWIG is deprecated in KiCad 9 and removed in KiCad 11.

## Appendix: terms

| Term | Meaning |
|---|---|
| BOM | Bill of materials. The part list an assembler orders from. |
| CAD | Computer-aided design. Here, the board and enclosure model files. |
| code-CAD | A 3D model defined by a program rather than drawn by hand. hw_forge uses build123d. |
| DRC | Design rule check. KiCad's check that a board's geometry obeys its rules. |
| ERC | Electrical rule check. KiCad's check that a schematic is electrically consistent. |
| fab outputs | The files a board house needs: gerbers, drill files, placement files, and a BOM. |
| gate | A check that exits nonzero on failure, so a build stops rather than warns. |
| IPC API | KiCad's supported scripting interface, distributed as `kicad-python`. Replaces SWIG. |
| KiCad | The open-source electronics design suite this pipeline drives. |
| PCB | Printed circuit board. |
| pcbnew | KiCad's board editor, and the Python module that exposes it. |
| schematic parity | A DRC check that the board's netlist matches the schematic's. |
| SWIG | The older generated Python binding for `pcbnew`. Deprecated in KiCad 9, removed in 11. |
| unconnected | A net the board declares but does not route. |
