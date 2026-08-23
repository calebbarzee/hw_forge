# hw_forge

A Claude Code plugin that turns hardware design into a gated, reproducible
build. You describe a device; agents write the *generators* — Python that emits
KiCad schematics and boards, and code-CAD that emits the printed enclosure — and
every phase has to clear a machine-checkable gate before the next one starts.
The deliverable is not a board file someone drew. It is a repository that
regenerates the board file, plus the evidence that the result passes.

## Quick start

Ten minutes from clone to a gated board. From a Claude Code session:

```
/plugin marketplace add /path/to/hw_forge
/plugin install hw-forge
/hw-preflight
```

Preflight is the whole first step: it finds your KiCad, checks the version, and
proves the specific operations the pipeline needs (headless `pcbnew`, zone fill,
CLI exports) actually work on your machine. If it fails it hands you the exact
fix command — do that and re-run it. Green preflight, then pick your path:

**You already have a KiCad project** (yours or anyone's):

```
/hw-validate path/to/project
```

You get one line per board — ERC, DRC with schematic parity, unconnected — and
an explicit pass/fail. If it fails, the command triages the violations for you:
grouped by cause, not listed by count. This is the fastest way to *feel* what
the pipeline is: the gate is a test suite for copper.

**You want a new board**: just describe it —

> design me a 6-key macro pad on a nice!nano with a nice!view display

The `hw-design` skill picks it up and walks the eight phases (spec lock →
research → logical design → schematic → PCB → fab outputs → enclosure → docs),
gating each one before the next opens. Expect it to lock decisions with you up
front and then work in long autonomous stretches; it stops when a gate or a
locked decision genuinely needs you.

What success looks like: a repository that **regenerates** its own board files
(`make && make check` from scratch), reports ERC 0 / DRC 0 / parity 0 /
unconnected 0, and exports a fab zip whose hole and placement counts are
asserted, not eyeballed. If any of that surprises you, read the next section —
it is the point.

## The philosophy

**Everything is code-generated.** One logical design file — nets, pin tables,
part list, topology — feeds every emitter. The schematic and the board come out
of the same source, so they cannot drift. Symbols and footprints for
project-local parts are generated from a single pin table for the same reason:
on z_board, pairing a stock `SK6812MINI` symbol with an `SK6812MINI-E` footprint
would have swapped power and data on all 22 LEDs, silently, DRC-clean. A
generated pair cannot do that.

**Every phase has a machine-checkable exit gate.** ERC 0. DRC 0 at error
severity *with schematic parity*. 0 unconnected. Fab-output assertions on hole
counts and placement counts. Numeric interference checks on the enclosure.
`kicad-cli --exit-code-violations` returns 5 when anything is wrong, which is
what makes DRC a test rather than a report — a broken board fails the build.

**Agents never hand-edit CAD files.** Copper is not text you fix; tracks carry
UUIDs, zones carry cached fills, and nothing revalidates until KiCad reopens the
file. Disputes about geometry are settled by moving a named constant in the
generator, regenerating, and reading the DRC JSON — never by arithmetic on paper.
That loop took the combined board from 374 violations to 0 in eleven passes, and
it is why the second half of a mirrored design typically lands clean on the first
regeneration once the first half's handoff report exists.

**The orchestrator re-runs every gate itself.** An agent's report that a gate
passes is a claim, not evidence. The orchestrator runs `kicad_gate.py` between
waves and reads the JSON. This is also how a toolchain regression gets caught
instead of misdiagnosed: on z_board, 295 DRC violations that looked exactly like
a geometry bug were one changed KiCad API signature, and the tell was that the
*committed* board still passed while a fresh regeneration failed. Same rules,
different geometry — so it was never the design.

**Locked decisions are not relitigable — but they have a barrier clause.** Every
agent prompt carries the user's locked choices verbatim, marked
do-not-relitigate. If one of them makes a gate impossible or forces a materially
worse design, the agent stops and returns a structured barrier report (what is
blocked, why, options with tradeoffs, a recommendation) and the orchestrator
relays it to the user as a question. Grinding against the barrier and silently
deviating from it are both violations.

## Two ways to use it

**The full pipeline** is the `hw-design` skill. Ask for the work in plain
language — "design me a 6-key macro pad on a nice!nano with a nice!view" — and
the skill takes it through eight phases: spec lock, libraries and research,
logical design, schematic, PCB, fab outputs, enclosure, then docs and knowledge
harvest. It decides what to do inline and what to delegate, writes the agent
prompts from verified facts rather than assumptions, runs the waves, and
re-verifies each gate before opening the next phase. This is the mode for new
boards and for structural changes to existing ones.

**Five slash commands** are single-phase entry points over the exact same
scripts, for when you already have a project and want one thing done:

- `/hw-preflight` — environment doctor. Is the toolchain there, the right
  version, and capable of the specific operations the pipeline needs? On failure
  it stops and hands you the exact fix command. It does not work around a broken
  toolchain, because working around one is how you spend a session debugging a
  design that was never wrong.
- `/hw-validate` — run the gate on a project and triage what fails.
- `/hw-research` — acquire datasheets, footprint libraries and reference designs,
  local machine first and the web second, vendored into the project with a
  provenance manifest and pin tables verified against two independent sources.
- `/hw-export` — regenerate fab outputs and renders, assert they are real.
- `/hw-kb` — recall from or harvest into the knowledge base.

Run `/hw-preflight` before the first design session on a new machine. The rest
you reach for as needed.

## The knowledge base, and why it compounds

Hardware knowledge is mostly small, sharp, expensive facts. A KiCad API argument
that changed meaning between versions. The pin order of one LED variant. The
arithmetic that turns a cavity depth into a screw length. That an insert bore
should be the insert's OD spec with at least 1.2mm of wall around it. That a
gated LED rail is the one topology where the data line genuinely wants a series
resistor, and that every reference board on your disk which omits one has an
ungated rail and therefore isn't evidence.

None of that is derivable, all of it is cheap to write down once, and each fact
is worth roughly one debugging session every time it comes up again. So hw_forge
keeps a knowledge base of markdown cards under `kb/`, organized by domain, and
the pipeline touches it twice per run: a **recall** step at each phase start,
which pulls the cards matching that phase's domain and tags into context before
any design work happens, and a **harvest** step at run end, which writes down
what this run learned — as new cards, or as updates to cards that were already
close.

The effect is that the system gets faster at each board family it has seen. The
first keyboard teaches it MX plate geometry, hotswap socket keepouts, ZMK's
`EXT_POWER` pin and the LED-rail reasoning. The second keyboard starts with all
of that in hand and spends its session on what is actually new. KB roots are a
path list, not a fixed directory: the plugin's own `kb/` plus anything on
`HW_FORGE_KB_ROOTS` (colon-separated), so a personal or team knowledge-base repo
plugs in without forking this one.

## Install

As a plugin, from a Claude Code session:

```
/plugin marketplace add /path/to/hw_forge
/plugin install hw-forge
```

Or, while iterating on the plugin itself, symlink the skill into your user
skills directory and get the same behaviour without the plugin machinery:

```bash
ln -s /path/to/hw_forge/skills/hw-design ~/.claude/skills/hw-design
```

The scripts and agent definitions are found relative to the skill directory
either way. Optionally set `HW_FORGE_KB_ROOTS` to point at extra knowledge-base
roots, and `KICAD_ROOT` if your KiCad lives somewhere the discovery logic does
not look (it checks the platform defaults, including
`/Applications/KiCad/KiCad.app` on macOS).

You need KiCad 10 or newer, Python 3, and — for enclosure work — build123d. The
KiCad-bundled Python interpreter is used for the operations that need `pcbnew`;
`/hw-preflight` will tell you if any of that is missing or wrong.

## Provenance

The pipeline was proven on **z_board**, a 42-key wireless split ortholinear
keyboard: two 2-layer halves plus a one-key proto slice, plus a stretch-goal
four-layer reversible board that is *both* halves — fab it twice, populate the
back face for the left and the front for the right. All four targets reach ERC 0,
DRC 0 with schematic parity, 0 unconnected; the combined board is clean at every
severity, warnings included, with both inner planes filling as a single island.
Fab outputs are generated and asserted (hole counts, placement counts,
non-emptiness). The case is a build123d model whose geometry is read out of the
as-built board files rather than a spec table, with 65 numeric checks that
include mirror-symmetry assertions and clearance from every standoff to every
component it could foul.

What hw_forge extracts is the process, the knowledge and the tools — not a
universal generator. Board topologies differ too much for that. The per-project
generator is the deliverable the pipeline teaches you to write; hw_forge ships
the skeleton, the gate runner, and the accumulated traps.

## Status and roadmap

**v0.3 — the dry run is DONE, and has been re-specced twice.** The scripts,
templates, references and knowledge cards are extracted from z_board, and they
have now been used to build something they were not written from — then to revise
it and re-spec it, which is where the pipeline's most serious gap turned out to
be hiding.

> **v0.3 changes behaviour for new projects.** `kicad_scaffold.py` now promotes
> the five KiCad schematic-parity checks to `error` in every project it
> scaffolds, and `kicad_gate.py` reports `parity UNENFORCED` (or fails, under
> `--strict-parity`) on a project whose `.kicad_pro` does not carry them. Every
> project scaffolded before this — z_board's four boards included — was gating
> `parity ok` on a check that could not fail. See below.

**The dry run** was the milestone: a 6-key macro pad with a nice!view display on
a nice!nano — **hexpad** — designed end to end using nothing but this skill.
Verdict: the board is fabbable and the enclosure is verified. ERC 0 / DRC 0 with
schematic parity / 0 unconnected on both the board and its one-key proto slice;
a 21-file fab package whose hole census, placement split and layer set are
asserted rather than eyeballed; 215 numeric enclosure checks, all passing. Not
one gap was a design failure.

The same board was then **revised** on user direction — module and display
rotated 90°, the board shrunk, the case rebuilt — which tested something a fresh
build does not: whether a *change* can be trusted. Gates green again, 239
enclosure checks.

Then it was **re-specced**: a diode matrix replacing direct-pin scan, a rotary
encoder added, a 3D model required per footprint, and — the part no doctrine
covered — a person opening pcbnew and **dragging four parts**, two of them onto
the other board face. Gates green again, 416 enclosure checks.

Together the three rounds produced **94 logged gaps** — every rediscovery,
missing statement, script shortfall and unclear instruction — of which **89 are
fixed**, 4 are deferred with reasons in [`docs/BACKLOG.md`](docs/BACKLOG.md), and
1 is works-as-intended. Not one gap was a design failure; every one was friction,
a missing statement, or a tool that could not express something true.

The highest-value catch, from the re-spec, is a process failure rather than a
design one: **the schematic-parity gate was decorative.** `--schematic-parity`
was in the gate script, in two references, in the skill's phase-4 exit contract
and in the script's own emphatic docstring — and it could not fail a build,
because KiCad ships all five parity checks at `warning` severity and the gate
filters on `--severity-error`. Measured: a green gate on a board missing eight
parts and mis-wiring twenty-one nets. Auditing the *original* fixture for the
same blind spot found it on all four z_board boards, and found two genuinely
missing components on its proto slice that a green gate had hidden for the life
of that slice. The general form is worth more than the fix: **a check whose
severity is below the severity you filter on is not a check.**

Others: a footprint courtyard can be *smaller* than the part it holds (a silent
interference every clearance check passes) — and, from the re-spec, *larger*, when
a through-hole part's own pad row inflates it and a deck window sized on the union
costs a mounting boss its seat; the fab exporter could delete its own profile and
still print `ok`; "no source anywhere has this number" needed to be a real,
documented research outcome; a rotation-sign error in a handoff table that only an
*asymmetric* feature could reveal. The revisions also added what a revision needs
and a build does not — **regression contracts**: a rev diffs its DRC finding
classes and its enclosure check *set* against the previous rev (with the baseline
now a build artifact rather than something to remember), a generated as-built
document carries a digest stamp of the board it describes, and a hand-edited board
has a defined adoption path ending in a to-the-micron placement diff. The full
verdict is [`docs/DRYRUN-HEXPAD.md`](docs/DRYRUN-HEXPAD.md).

Next: plugin packaging (including making the slash commands reachable from a
project the plugin is not installed into), then the migration off the SWIG
`pcbnew` module onto the IPC API (`kicad-python`) — forced work, because SWIG is
deprecated in KiCad 9 and removed in 11.
