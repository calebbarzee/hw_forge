# The KiCad extension ecosystem: what runs headless, and what does not

A survey of the plugins, servers, and standalone tools that plausibly matter
for an agent-driven, headless KiCad build. Generic knowledge: which tool does
what, whether it needs a KiCad GUI running, how it installs, and a verdict.
Project-specific facts belong in `kb/`, not here; the JLCPCB-specific detail on
the Fabrication Toolkit plugin, for example, lives in `kb/fabs/jlcpcb.md`
because it is a per-fab fact, not a generic one.

Verified against KiCad 10.0.5 unless a version is named. "Verified locally"
below means run on this machine, 2026-09-20; everything else is marked with
its source and read date, and an unconfirmed claim is marked as such rather
than stated flatly.

## Terms used here

| Term | Meaning |
|---|---|
| BOM | Bill of materials. |
| CPL | Component placement list, sometimes called a position or "pos" file: where every part sits and how it is rotated. |
| DFM | Design for manufacturing: checks aimed at whether a board can actually be built and assembled, not just whether its geometry is internally consistent. |
| IPC API | KiCad's supported scripting interface, distributed as the `kicad-python` package and imported as `kipy`. Replaces SWIG. |
| LCSC | The parts distributor JLCPCB's assembly service sources components from; a part is identified by its LCSC part number. |
| MCP | Model Context Protocol: a standard that lets an AI agent call a tool server directly, the same mechanism this document's own author is built on. |
| PCM | KiCad's Plugin and Content Manager, the built-in installer for third-party plugins. |
| SWIG | The older generated Python binding for `pcbnew`. Deprecated in KiCad 9, removed in 11. |

## 1. KiCad's own interfaces

See `kicad-api.md` §1 for the full pick-the-right-interface table and its
rules; this section only adds ecosystem framing.

### 1a. `kicad-cli`

Verified locally by running `--help` on every relevant subcommand
(`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`, version 10.0.5).
The subcommand tree:

```
kicad-cli {fp, jobset, pcb, sch, sym, version}
  fp     {export, upgrade}
  jobset {run}
  pcb    {drc, export, import, render, upgrade}
    export {3dpdf, brep, drill, dxf, gencad, gerbers, glb, hpgl, ipc2581,
            ipcd356, odb, pdf, ply, pos, ps, stats, step, stl, stpz, svg,
            u3d, vrml, xao}
  sch    {erc, export, upgrade}
    export {bom, netlist, ...}
  sym    {export, upgrade}
```

`pcb export hpgl` prints "No longer supported as of KiCad 10.0." when run with
`--help`; it is a listed subcommand that no longer does anything, not a
removed one. `pcb drc` and `sch erc` both take `--exit-code-violations`,
`--severity-error`/`--severity-all`/`--severity-warning`, and
`--schematic-parity` is a `pcb drc`-only flag, matching `kicad-api.md` §2.
`pcb export gerbers` alone takes 20-plus flags (DNP handling, X2 format,
soldermask subtraction, precision, per-variant output); run `--help` on the
specific export subcommand before scripting it rather than assuming a flag
set from another KiCad version.

Verdict: **adopt.** Already the backbone of every verification and export path
in this pipeline (`kicad-api.md` §1, "verification is always `kicad-cli`").

### 1b. SWIG `pcbnew`

Deprecated in KiCad 9, removed in 11. hw_forge depends on it today for
headless board generation because it is the only interface, among the three,
that can both write geometry and run with no GUI (`kicad-api.md` §1). Verified
locally: importable under KiCad's bundled interpreter
(`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`,
Python 3.9.13), reporting `pcbnew.Version() == "10.0.5"`. Not importable under
the system interpreter, by design (`kicad-api.md` §4).

Verdict: **adopt, with a migration deadline already tracked.**
`docs/ARCHITECTURE.md` §6 phase 5 names the port to IPC as forced work; this
entry exists only to confirm the deprecation status from the tool's own
behavior, not to reopen the decision.

### 1c. IPC API (`kicad-python` / `kipy`)

The official PyPI package is `kicad-python`; latest version 0.8.0, released
2026-08-30 (pypi.org/project/kicad-python/, read 2026-09-20), MIT license. Its
canonical source is KiCad's own GitLab project, `gitlab.com/kicad/code/kicad-
python`, whose last recorded activity is 2026-09-20 (read via the GitLab API
the same day) meaning it is under active, same-day development, consistent
with being KiCad's own supported migration path rather than a third-party
project.

The IPC API requires a running KiCad instance with the API server enabled
under Preferences, Plugins; its own documentation states plainly that "it is
not possible to use kicad-python to manipulate KiCad design files without
KiCad running" (pypi.org/project/kicad-python/, read 2026-09-20). Verified
locally: `kipy` is not importable under either the system Python (3.13.15) or
KiCad's bundled Python (3.9.13) on this machine, because the package is not
installed; per this task's constraints, it was not installed to test further.
That "needs a running instance" requirement is the load-bearing fact for
hw_forge: it means the IPC API cannot directly replace SWIG in today's
headless, no-GUI generation pattern. A future port needs either a way to run
KiCad itself headlessly with its API server up, or to keep IPC scoped to
interactive/live-editing workflows and leave batch generation elsewhere.
`Board` exposes `get_footprints/tracks/vias/pads/nets/zones/selection`,
`create_items/update_items/remove_items`,
`begin_commit/push_commit/drop_commit`, `refill_zones()`, and `save()`
(`kicad-api.md` §7); plotting and export are not in the 9 or 10 API, so CLI
still owns that surface regardless of the SWIG-to-IPC migration.

Verdict: **evaluate.** It is the forced migration target and is actively
maintained by KiCad itself, but "GUI must be running" is a real architectural
constraint on a build meant to run with no display; the port is not a
drop-in replacement, it is a redesign of the write path, and that redesign is
not scoped yet.

## 2. MCP servers for KiCad

Several projects share close variants of the name "kicad-mcp." The table
below lists what a search actually turned up, each independently verified to
exist via the GitHub API on 2026-09-20 (stars, license, last push date).

| Project | Stars | License | Last push | Drives |
|---|---|---|---|---|
| `mixelpixx/KiCAD-MCP-Server` | 2367 | MIT | 2026-09-10 | files + `pcbnew`-style project state |
| `lamaalrajih/kicad-mcp` | 523 | MIT | 2025-10-17 | files, shells out to `kicad-cli` for DRC |
| `Seeed-Studio/kicad-mcp-server` | 131 | none detected | 2026-09-09 | files, including hand-edited s-expressions for schematics |
| `blwfish/kicad-mcp` | 19 | MIT | 2026-09-20 | files, no KiCad install required to run its own test suite |
| `Finerestaurant/kicad-mcp-python` | 40 | none detected | 2025-07-15 | the official IPC API (`kipy`) |
| `oaslananka/kicad-mcp-pro` | 96 | MIT | 2026-09-18 | files, with DFM/manufacturing-review framing |

`lamaalrajih/kicad-mcp`'s own README states it is "compatible with any
MCP-compliant client" and works primarily on project files, invoking
`kicad-cli` for checks such as DRC, rather than driving the GUI
(github.com/lamaalrajih/kicad-mcp, read 2026-09-20). It states support for
"KiCad 9.0 or higher." `Seeed-Studio/kicad-mcp-server` explicitly notes "KiCad
must be closed and reopened to see file changes (no hot-reload)" and that it
edits schematic s-expression files by hand because no Python API exists for
that operation (github.com/Seeed-Studio/kicad-mcp-server, read 2026-09-20);
requires KiCad 8.0 or newer, `kicad-cli` on the system `PATH`, and exposes
roughly 30 tools across six categories (schematic analysis, PCB analysis,
netlist operations, validation, editing, code generation).
`Finerestaurant/kicad-mcp-python` is the one server in this set built on the
official IPC API rather than files or `kicad-cli`, which ties its
capabilities to whatever `kipy` exposes today (§1c) and to a running KiCad
instance.

Which one the blog author used (`kb/runs/a6mzero-fable5-rp2350.md`) cannot be
confirmed; the post names only "the kicad mcp," with no link or repository.
Given the described workflow, schematic plus placement plus DRC-driven fixes
plus a separate Freerouting invocation, a file-and-`kicad-cli`-driving server
such as `lamaalrajih/kicad-mcp` or `mixelpixx/KiCAD-MCP-Server` is the more
consistent match than the IPC-only `Finerestaurant` project, but this is
inference from the workflow shape, not a verified fact.

Every one of these servers exposes roughly the same underlying surface hw_forge's own
scripts already wrap: `kicad-cli` invocations, `pcbnew` or `kipy` operations, file reads.
The difference is what sits on top. hw_forge's scripts (`kicad_gate.py`, `kicad_fab.py`,
and the rest) add hw_forge-specific assertions no generic MCP server provides: schematic
parity severity enforcement, canonical-digest determinism checks, fab hole-count and
placement-count assertions. More importantly, an MCP server that lets a chat agent issue
live edits is a channel for exactly the failure mode hw_forge's process rules exist to
prevent: "agents never hand-edit CAD files" (`README.md`). Routing agent actions through
one of these servers instead of through the gated generate-and-check loop would reopen
that door.

Verdict: **skip**, as a dependency of hw_forge's own pipeline. The file and `kicad-cli`
surface these servers expose is already covered by hw_forge's own scripts, with stronger,
project-specific assertions, and giving an agent a live-edit channel undermines the
gate-before-trust rule the architecture is built on. A narrow **evaluate** remains for a
future convenience feature, such as letting a user watch a live GUI session update, never
as a design-authority channel.

## 3. Routing

This is the ecosystem-level entry only. The deep evaluation, and the wrapper script, are
in `references/autorouting.md`.

**Freerouting**, available as a KiCad plugin and as a standalone jar
(github.com/freerouting/freerouting), GPL-3.0 license, 2005 stars, latest release v2.4.1
published 2026-09-03 (repository releases page, read 2026-09-20). Genuinely headless:
`java -jar freerouting-executable.jar --gui.enabled=false --api_server.enabled=true` is
documented as a real invocation. Several small community plugins wrap the KiCad-side round
trip of exporting a `.dsn`, running the jar, and importing the resulting `.ses`
(`taotieren/kicad_freerouting-plugin`, `random-builder/kicad_freerouting-plugin`,
`jharris2268/kicad-freerouting-plugin-alt`); their existence was confirmed by search, not
their behavior individually.

Verdict: **adopt as a fallback.** Verified locally 2026-09-20 (`kb/runs/hexpad-autoroute-2026-09-20.md`): on a stripped 59-net board it reported 0 unrouted in 6.06 s, and `kicad_gate.py` then failed it on three DRC classes (track width under the floor on six nets, copper-to-edge clearance through four cutouts, one pinched zone). Mature, actively released, and genuinely
headless, but on the one measured case available
(`kb/runs/a6mzero-fable5-rp2350.md` §5: 65 footprints, 54 nets, 118 unrouted connections,
17 passes in 2 minutes) it routed 69 of 118 connections, 58%, and left the rest for hand
routing. Plan for a hand-routing or second-pass step after it, not a single autorouter
call as the whole story.

**KiCadRoutingTools** (github.com/drandyhaas/KiCadRoutingTools), MIT license, 476 stars,
pushed 2026-09-20 (read via the GitHub API the same day, confirming active maintenance).
This is the real repository behind the tool the blog post calls "KiCADRoutingTools." Grid-
based A* routing with a Rust-accelerated core, described by its own README as roughly 10
times faster than a pure-Python implementation, octilinear (horizontal, vertical, 45
degree) multi-layer routing with automatic via placement, available both as a KiCad GUI
plugin and as a command-line tool for scripting, supporting KiCad 9 and 10. Installed
through a PCM package zip attached to each GitHub release, or by git checkout plus
`python install_plugin.py`.

Verdict: **adopt**, as the default backend. Verified locally 2026-09-20 (`kb/runs/hexpad-autoroute-2026-09-20.md`): the same stripped board routed 33 of 33 nets in 1.68 s of engine time, and after the mandatory zone refill `kicad_gate.py` passed it clean (ERC, DRC with parity, unconnected all 0), once the wrapper stopped the router from rewriting the project's DRC floors (`autorouting.md` §6b). `scripts/kicad_route.py route-krt` wraps it with those flags. Actively maintained, genuinely CLI-capable, and the one number
available from outside use was already compelling (`kb/runs/a6mzero-fable5-rp2350.md` §5: reported
1.25 seconds to route everything Freerouting left unrouted, run after the board had
already been ordered, so not a controlled comparison on identical conditions). The local trial and its numbers are in
`references/autorouting.md` §6a.

Search also turned up `bbenchoff/OrthoRoute`, described as a GPU-accelerated autorouter
for KiCad. Not evaluated here; flagged for `references/autorouting.md` if GPU-dependent
tooling is in scope there.

## 4. Fabrication and BOM

**Fabrication Toolkit** (formerly "JLC-Plugin-for-KiCad," `bennymeg`), Apache-2.0 license.
Installed locally for KiCad 10.0 at version 5.3.1 (2026-09-20, by `hw_install.py
--jlc-plugin`, pinned SHA-256 in that script); an older 5.2.0 remains under the 8.0 tree.
Genuinely headless via `cli.py --nonInteractive`, run as a module with `runpy` because
its imports are relative. Full
detail on what it exports and how it derives CPL rotation is in `kb/fabs/jlcpcb.md`
"Pre-upload checks", because those are JLCPCB-specific facts, not generic ones.

Verdict: **adopt**, generically: it is the installed, headless-capable path from a board
file to a JLCPCB-ready archive. `python3 scripts/hw_install.py --check` confirms the
10.0 install; an 8.0 install never carries forward on its own.

**kicad-jlcpcb-tools** (`Bouni/kicad-jlcpcb-tools`), MIT license, 2075 stars, pushed
2026-09-20. A different job from Fabrication Toolkit: primarily an interactive
parts-search and assignment tool, querying the JLCPCB parts database and assigning LCSC
numbers from inside pcbnew, generating BOM and CPL files from those assignments
(github.com/Bouni/kicad-jlcpcb-tools, read 2026-09-20). Runs as a GUI tool under Tools,
External Plugins; its own documentation describes a standalone debugging mode as
experimental, so it is not headless-reliable today.

Verdict: **evaluate.** Its live parts-database query is exactly the mechanism a pre-upload
stock and package check needs (`kb/fabs/jlcpcb.md` "Pre-upload checks" items 3 and 4), but
its non-headless nature fits a human-in-the-loop part-selection step, not an unattended
gate.

**KiBot** (`INTI-CMNB/KiBot`), AGPL-3.0 license, 743 stars, pushed 2026-09-11. Built to be
CLI and CI-first: its own documentation frames it as usable "in a Makefile" and "in a
CI/CD environment" (github.com/INTI-CMNB/KiBot, read 2026-09-20). Generates gerbers, BOM,
position files, drill files, and 3D outputs from a scripted configuration; whether it
wraps `kicad-cli` internally or calls `pcbnew`/`kipy` directly, and whether it ships
ready-made JLCPCB- or PCBWay-specific output presets, was not confirmed from the page
content read in this pass.

Verdict: **evaluate.** The closest general-purpose competitor to hw_forge's own
`kicad_fab.py`, worth a side-by-side comparison to see whether it subsumes any hand-rolled
export logic, but its AGPL-3.0 license needs a check against how hw_forge intends to be
distributed before adoption, and it is not known to provide the export-time assertions
(hole-count, placement-count) `kicad_fab.py` already asserts.

**KiKit** (`yaqwsx/KiKit`), MIT license, 2027 stars, pushed 2026-08-05. Panelization and
fab-export automation.

Verdict: **evaluate**, specifically for panelization, once a project needs multi-board
panels; not otherwise duplicative of hw_forge's single-board export path.

**InteractiveHtmlBom** (`openscopeproject/InteractiveHtmlBom`), MIT license, 4572 stars,
pushed 2026-09-10. Generates a browsable, clickable BOM and placement map from a board
file. Mature and widely used.

Verdict: **adopt.** Low-risk, high-value for hand-assembly and review documentation, and
it is a pure downstream export that sits after the gate rather than inside it.

**jlcparts** (`yaqwsx/jlcparts`), MIT license, 831 stars, pushed 2026-09-20 (same day as
this reading, so under active maintenance). A self-hosted dataset and search tool over
JLCPCB's basic and extended parts catalog and current LCSC stock.

Verdict: **evaluate.** The right shape of tool for a scripted pre-upload availability
check (`kb/fabs/jlcpcb.md` "Pre-upload checks" item 3), since it queries a real stock
dataset rather than hitting jlcpcb.com interactively, but it requires standing up and
periodically refreshing a local database, which is infrastructure beyond a single script.
Worth prototyping once `scripts/kicad_fpcheck.py` exists and a companion availability
check is scoped.

## 5. Anything else

Brief, per scope.

**DRC extensions.** No separate plugin ecosystem was found beyond KiCad's own DRC plus
fab-specific `.kicad_dru` rule authoring, which hw_forge already does per fab
(`kb/fabs/*.md`, `kicad-api.md` "Custom rules"). Nothing to adopt here beyond what is
already in place.

**Footprint generators.** `kicad-footprint-generator` is KiCad's own project; its
canonical location moved to `gitlab.com/kicad/libraries/kicad-library-tools` (the former
`kicad-footprint-generator` path now redirects there, confirmed via the GitLab API,
2026-09-20), active as of the same day. Two components: `kilibs` (generic utilities for
library generators) and `KicadModTree` (the footprint-generation framework itself).

Verdict: **evaluate.** Relevant only if hw_forge starts generating standard-family
footprints (SOIC, QFN, and similar) programmatically rather than vendoring them; today's
doctrine is project-part-specific generation from a single pin table
(`kicad-api.md` §8), a narrower problem this library does not directly solve.

**Library management.** Out of scope for deep coverage here. hw_forge's own
`kicad_scaffold.py` already writes each project's `fp-lib-table` and `sym-lib-table`, which
is KiCad's own mechanism; no third-party tool changes that picture.

**3D model sources.** Not separately surveyed; `kicad-api.md` §9 already covers STEP/AP214
handling once a model is sourced, which is the load-bearing knowledge for this pipeline.

**Schematic generation libraries.** `skidl` (`devbisme/skidl`), MIT license, 1663 stars,
pushed 2026-08-20, active: lets Python code define a circuit and emit a KiCad netlist.
`kicad-skip` (`psychogenic/kicad-skip`), LGPL-2.1 license, 229 stars, pushed 2024-05-26,
meaning no push in roughly sixteen months as of 2026-09-20: reads and edits an existing
`.kicad_sch` file programmatically, rather than generating one from nothing.

Verdict: **skip** for schematic generation itself; hw_forge already owns that layer
through its own generator pattern (`README.md`, "every artifact is code-generated").
**Evaluate**, narrowly, `kicad-skip` only if a future phase needs to script edits to an
existing hand-drawn schematic rather than generate one, and weigh its staleness before
depending on it.

## Verdict summary

| Item | Verdict | Why, in one line |
|---|---|---|
| `kicad-cli` | adopt | Already the verification and export backbone; confirmed present with the full subcommand set at 10.0.5. |
| SWIG `pcbnew` | adopt, migrating | Only headless write path today; deprecation and removal dates are already tracked, not new information. |
| IPC API (`kicad-python`/`kipy`) | evaluate | Official and actively maintained, but needs a running KiCad instance, which today's headless build does not have. |
| MCP servers for KiCad (all variants) | skip | Duplicate hw_forge's own scripts and risk a live-edit channel the architecture is built to prevent. |
| Freerouting | adopt (fallback) | Mature and headless; routed the local test board fully but left three DRC classes to fix, and left 42% unrouted in the outside case. |
| KiCadRoutingTools | adopt | Default autorouting backend: 100% routed and a clean gate after the zone refill on the local test board; MIT, CLI, KiCad 9 and 10. |
| Fabrication Toolkit | adopt | Installed, headless, generates the full JLCPCB archive; needs reinstall for KiCad 10. |
| kicad-jlcpcb-tools | evaluate | Right data source for pre-upload checks, but not headless-reliable today. |
| KiBot | evaluate | Plausible competitor to `kicad_fab.py`; license and feature parity not yet checked. |
| KiKit | evaluate | Useful specifically for panelization, when that need arises. |
| InteractiveHtmlBom | adopt | Mature, low-risk, downstream-only documentation tool. |
| jlcparts | evaluate | Right shape for a scripted availability check; needs standing infrastructure. |
| kicad-footprint-generator / Library Tools | evaluate | Only relevant if standard-family footprint generation becomes in-scope. |
| skidl | skip | hw_forge already owns code-generated schematics. |
| kicad-skip | evaluate, narrowly | Only for scripted edits to a pre-existing schematic; over a year stale. |
