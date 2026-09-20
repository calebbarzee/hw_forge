# Autorouting: when to script, when to route, and the handoff between them

Generic rules. Board-specific numbers live in `kb/`. Every claim about a
third-party tool below carries a verification status: **verified locally**
(run on this machine during this document's own research), **verified from
docs** (the project's own documentation or GitHub API, fetched but not run
locally), or **unverified** (reported by a third party, not independently
checked).

## Terms used here

| Term | Meaning |
|---|---|
| DSN | Specctra design file. What KiCad exports for an external router to read. |
| SES | Specctra session file. What a router writes back with its routing. |
| fixed wire | A DSN wire marked `(type fix)`, meaning the router must not move it. |
| headless | Runs with no graphical window, so it can be driven by a script or a build. |
| ratsnest | The unrouted-connection lines KiCad draws between a net's pads. |

## 1. The decision rule

`gen_pcb.py` routing-as-code, named-constant lanes and corridors, layer
split by net family, serpentine chains, is `references/electronics.md` §7's
subject, and it is the right tool exactly when a board's routing problem
reduces to arithmetic on a repeated cell. Autorouting is the right tool when
it does not.

**Pole 1: the keyboard matrix.** One row axis, one column axis, each on its
own face, one via per crossing at the switch. The routing problem is "solve
the corridor count once, per pitch, and repeat it." A script that computes a
lane order from a pad table beats any autorouter here: it is instant, it
never varies between runs, and the reasoning is written down as code a
reviewer can read. Autorouting a matrix is strictly worse: slower, and its
result is not a named constant anyone can nudge.

**Pole 2: the irregular many-net board.** The worked case is the blog post
this document was written in response to (a6mzero.com, "This PCB is brought
to you by Fable 5", fetched during this work): an agent-designed RP2350
board, 65 footprints, 54 nets, 118 unrouted connections after placement, no
repeated cell to write a corridor rule for. There is no lane order to derive,
because there is no regularity to derive it from. Hand-deriving one anyway is
the wrong use of a session; this is what an autorouter is for.

**The spec-driven rule.** Phase 0 (spec lock) records whether autorouting is
permitted for a board, the same way it records every other locked decision.
Absent a locked answer, decide from the topology in front of you:

| Signal | Scripted routing | Autorouting (hybrid flow, §2) |
|---|---|---|
| Repeated cell (matrix, chain, connector row) | Yes | No: script the cell |
| Net count | Low enough to name every lane | High enough that lane names would stop meaning anything |
| Placement | Regular, derived from a grid | Irregular, agent- or hand-placed |
| Critical nets (power, diff pairs, crystal, USB) | Scripted either way | Scripted either way (see §2) |
| The rest of the nets | Scripted either way | Autorouted, then adopted |

A board can be both: a keyboard with an irregular MCU/USB/display corner and
a perfectly regular switch matrix routes the matrix by script and the corner
by the hybrid flow below. The decision is per net family, not per board.

## 2. The hybrid flow

1. **The generator places everything.** Placement is never delegated to the
   autorouter; it has no opinion on courtyards, orientation, or the
   enclosure. This does not change with autorouting in scope.
2. **The generator routes the critical nets by script**, exactly as it
   already would without autorouting: power, differential pairs, the
   crystal, USB. These are the nets where topology matters (impedance,
   length matching, a specific escape direction) in a way a general-purpose
   router does not reason about.
3. **Those tracks and vias are locked** (`SetLocked(True)`, both on the
   `PCB_TRACK`/`PCB_ARC` and any `PCB_VIA` on the net) before the board is
   saved. This is the only thing that protects them from being ripped up and
   rerouted in step 4. See `references/kicad-api.md` §10 for the mechanism
   and its failure mode.
4. **Export DSN, run the autorouter, import the resulting SES.**
   `scripts/kicad_route.py export-dsn` / `route` / `import-ses`. The
   autorouter routes only what was left unrouted; the locked nets come back
   as fixed wires it did not move (assuming the lock survived export, the
   export step reports a locked-track count against a fixed-wire count in the
   DSN and warns on a mismatch).
5. **`adopt` writes the result back** as a python data module
   (`kicad/routing.py`, `SEGMENTS` / `ARCS` / `VIAS`) that `gen_pcb.py`
   imports and replays. The autorouter itself never runs inside `gen_pcb.py`;
   see `references/kicad-api.md` §10 for why that boundary is load-bearing
   for the determinism gate.
6. **Re-run the full gate.** Autorouted copper is not exempt from anything a
   scripted board owes: DRC 0 with schematic parity, 0 unconnected, zones
   filled headlessly. §4 below is the checklist.

Step 5's staleness rule, restated because it is easy to forget mid-revision:
adopted copper is positioned against the pad locations the board had at
adoption time. **Any placement change to any footprint invalidates the whole
`routing.py` file, not just the routes touching that footprint.** There is no
cheap way to prove a route untouched by a placement change short of
cross-referencing every moved pad against every route endpoint, exactly the
proof-instead-of-nudge this pipeline avoids everywhere else. Re-route in
full: export, route, import, adopt. A few minutes of autorouting is cheaper
than a track that used to land on a pad and now lands on bare board.

## 3. The design-rule handoff

An autorouter obeys whatever clearances, track widths, and via sizes the
board declares, not what the generator's own named constants say, because
the autorouter never reads `gen_pcb.py`. Everything it needs to route
correctly has to already be in the `.kicad_pro` (and any project
`.kicad_dru`) **before** DSN export, because `ExportSpecctraDSN` reads the
board's design settings into the DSN's own `(rule (width ...) (clearance
...))` block (confirmed present in a real export: see the sample in
`references/kicad-api.md` §10's neighbourhood, and this document's own
export test).

This is not new work. `kicad_scaffold.py` already writes net classes, DRC
severities, and design rules into every scaffolded project (see
`references/kicad-api.md` §2 and the scaffolder's own docstring), and
`kicad_zonefill.py` / any `SaveBoard()` call already re-patches them
afterward. The rule for the autorouting flow is narrower than it sounds:
**run `export-dsn` only against a board whose project file has already been
through the normal scaffold/repatch cycle**, i.e. after `gen_pcb.py`'s own
save-and-repatch step, never against an intermediate or hand-saved copy. If
the DSN's `rule` block looks like KiCad's raw defaults instead of the
project's own numbers, the project file was stale when you exported, not the
autorouter's fault.

Via size and drill specifically: the DSN carries a named padstack
(`"Via[0-1]_600:300_um"` in a 0.6 mm / 0.3 mm project) built from the net
class's via diameter and drill. A net class change after adoption changes
nothing about already-adopted vias, they are frozen coordinates and sizes
in `routing.py`, so a via-size change is exactly the kind of change that
belongs in §2's staleness rule: re-route, do not hand-edit the adopted table.

## 4. Post-route checks

Autorouted copper is copper like any other; it owes the same gate, plus two
checks specific to the round trip.

1. **`kicad_gate.py` on the imported, zone-refilled board.** DRC 0 at error
   severity with schematic parity, 0 unconnected. Nothing about autorouting
   changes this contract or exempts a net from it.
2. **Zone refill, always, after `import-ses`.** Specctra has no zone concept,
   so a router's session cannot touch a pour either way, but the copper it
   *did* add can pinch a pour's channel below its minimum thickness the same
   way a scripted route can (`references/kicad-api.md` §4's pinch trap).
   `kicad_route.py import-ses` calls `kicad_zonefill.py`'s own fill logic for
   exactly this reason, never treat an imported board as gate-ready before
   its zones are refilled against the new copper.
3. **The `nets_emptied` warning from `import-ses`, read and understood, not
   dismissed.** A net that had tracks before import and has none after is
   `references/kicad-api.md` §10's central trap made visible: the session
   did not mention that net, and `ImportSpecctraSES` replaced the routing
   solution rather than patching it. Every name in that list needs an
   explanation before you proceed, either the router genuinely left it
   unrouted (check its own log/pass count) or the session you imported was
   partial for a reason you need to know about.
4. **The `--by-owner` warning-class diff**, same as any other revision
   (`agents/pcb-engineer.md`'s gate criterion 6). An autorouter is at least
   as likely as a human to introduce a new warning class, a silkscreen
   clash it does not know to avoid, a courtyard graze, and the diff is what
   catches it instead of a manual re-read of every finding.
5. **Unconnected count is not the only completeness signal.** A router that
   plateaus partway (§5's first failure mode) can leave a board DRC-clean on
   everything it *did* route while still failing the unconnected count
   outright. Read the actual number, not just whether the gate exited 0.

## 5. Failure modes

**Unrouted remainder.** The pole-2 worked case: Freerouting ran 17 passes
over about 2 minutes on a 65-footprint, 54-net board and plateaued at 69 of
118 connections, leaving 49 unrouted (a6mzero.com, fetched during this work;
see §6). This is a normal outcome for a dense or oddly-shaped board, not a
tool failure. Two responses, in order: raise `--passes` and re-run once
(diminishing returns are common, a router that has plateaued rarely
improves much with more passes on the same DSN), or hand-route the
remainder the same way the blog's own agent did. What does not work is
importing a plateaued session and treating the board as done; `kicad_gate.py`
will report the unconnected count either way, so there is no way to miss
this if the gate actually runs.

**Autorouter ignoring keepouts.** `ExportSpecctraDSN` does translate KiCad
rule areas into DSN `(keepout ...)` polygons, confirmed in a real export:
mounting-hole keepouts on this project's own test board came through as
`(keepout "" (polygon signal ...))` entries. A router that still routes
through one is a router bug or a keepout that was not actually a rule area
in KiCad (a silkscreen-only exclusion zone, for instance, carries no DRC
weight and translates to nothing). Verify by re-reading the DSN's own
`keepout` section before blaming the router, not after.

**Vias under parts.** A router with no knowledge of 3D geometry can place a
via in the footprint of a through-hole part's own drill pattern, or under a
socketed module standing on standoffs. DRC's courtyard checks catch some of
this and not all of it, a via a few tenths of a millimetre inside a
courtyard boundary with no pad there to collide with is not a DRC violation
at all, only a mechanical one the enclosure or assembly phase would find
later. There is no automated check for this in the current pipeline; treat
an autorouted board's via placements as needing the same visual
render-and-look pass any placement gets (`kicad-cli pcb render`), especially
under any part with standoffs or a lower z clearance than its courtyard
implies.

**Acid traps.** An acute-angle copper wedge, typically where a router turns
a trace back on itself near a pad, that etches unevenly and can leave a
narrow bridge unremoved or eat a wider trace thinner than designed. KiCad's
DRC has no dedicated acid-trap check as of 10.0.5; a router with a 45°-only
or orthogonal routing style (KiCadRoutingTools, §6) structurally avoids most
of them, while a free-angle router (Freerouting) can produce them, especially
on a rip-up-and-reroute pass. No automated check for this exists in the
current pipeline either; a rendered top/bottom plot at high zoom over any
autorouted corner is the current mitigation, same as the vias-under-parts
case above. **Status: unverified beyond general PCB fabrication knowledge;
not something this session measured on a real board.**

## 6. Tools researched

| Tool | Headless | License | Install | Verification |
|---|---|---|---|---|
| **Freerouting** | Yes, `--gui.enabled=false` (v2.1+; a v1.9.0 jar found on this machine predates the flag and did not exit cleanly when given an unrecognised one, see below) | GPL-3.0 | `python3 scripts/hw_install.py --router` (pinned v2.4.1, SHA-256 verified, headless smoke test) | **Verified locally, 2026-09-20** (§6a): a full export-dsn / route / import-ses / gate / adopt round trip against the hexpad board, run three times (a plain route, a coordinate-fidelity check, and a lock survival test), all on a real Freerouting process, not just the DSN/SES interfaces either side of it. |
| **KiCadRoutingTools** | Yes: `route.py` / `route_diff.py` / `route_planes.py`, a Rust-accelerated A* router with its own `.kicad_pcb` reader/writer (neither `pcbnew` SWIG nor `kipy`) | MIT | `python3 scripts/hw_install.py --routing-tools` (git clone at a pinned commit, `build_router.py`, a dedicated venv) | **Verified locally, 2026-09-20** (§6a): the same hexpad board routed through `route.py`, checked with its own `check_connected.py`/`check_drc.py`, then gated with `kicad_gate.py`, then adopted. This is very likely the tool the a6mzero.com post calls "KiCADRoutingTools" (same capability class, fast, KiCad 9/10-compatible A* routing, and the post gives no repository link to confirm the exact capitalisation against); **still not independently confirmed as the exact tool that post used**, that claim is unrelated to, and unaffected by, this run's own local verification. |
| **OrthoRoute** | Yes, via an export/route/import `.ORP`/`.ORS` cycle for boards too large for local GPU memory | MIT | KiCad plugin (needs the IPC API server enabled, KiCad 10.0+) | Verified from docs: the project's own README (github.com/bbenchoff/OrthoRoute), fetched during this work. The author states it is "not a general-purpose PCB autorouter" and useful only for "a narrow class of extremely large, dense, highly regular multilayer backplanes and BGA escape patterns", not a fit for either pole in §1. Not present on this machine; not run. |
| **KiCad interactive router (GUI)** | No | Part of KiCad, GPL-3.0 | Included with KiCad | Verified from general KiCad knowledge. Not a candidate for this pipeline at all: every rule in this repository routes only through generated or externally-bridged copper, never through a GUI session. |

### 6a. Measured: both backends against the same board (verified locally, 2026-09-20)

Install both with one command each, then verify what is present without
downloading anything:

```bash
python3 scripts/hw_install.py --router --routing-tools     # each idempotent
python3 scripts/hw_install.py --check                      # report only
```

The board: hexpad (a small keyboard, 41 footprints, two zones, VCC on F.Cu,
GND on B.Cu), copied into a scratch directory, every track and via stripped
(footprints and zones kept), 59 nets left to route. Both backends read that
same unrouted board. Numbers below are `kicad_route.py`'s own reports and
each tool's own log, not estimates.

| Metric | Freerouting v2.4.1 | KiCadRoutingTools @ `ab8d0c3648` |
|---|---|---|
| Command | `export-dsn` / `route` / `import-ses` | `route-krt` (one step: routes, then refills zones) |
| Wall time (whole `kicad_route.py` call, incl. JVM/interpreter startup) | 7–9 s | 12–16 s |
| Tool's own reported routing time | 6.06 s (1.64 s fanout + 5.72 s auto-route) | 1.68 s (2,933,542 A\* iterations) |
| Tool's own completion report | 0 unrouted, 0 violations, score 999.99/1000 | single-ended 33/33 routed, multi-point 63/63 pads (8 nets), 0 failed |
| Segments / vias adopted | 267 / 37 | 262 / 59 |
| Total track length (`kicad_geom`-derived) | 911.3 mm | 927.9 mm |
| Tool's own post-route checker | (none; DSN/SES has no notion of the target DRC floors) | `check_connected.py`: all nets fully connected. `check_drc.py`: 0 violations at 0.2 mm clearance |
| `kicad_gate.py` after the mandatory zone refill | **FAIL**: `track_width` ×20, `copper_edge_clearance` ×11, `unconnected_items` ×3 | **PASS** as first measured, but against rules the router had loosened; see §6b for the trap and the corrected re-run, which also passes with the rules preserved |
| Lock survival (2 tracks `SetLocked(True)` before export) | **PASS**: both tracks came back byte-identical (same net, endpoints, width, layer) | not applicable, KRT reads the board directly and does not go through a lock-sensitive export/import boundary |

What the `kicad_gate.py` failure rows mean, read from `drc.json`:

- **`track_width` ×20**, across six nets (`LED_D0` ×7, `L01`/`L02`/`L04`
  ×3 each, `R1` ×2, `c1_top` ×2): every one of them delivered at
  0.1874 mm against the project's 0.2 mm floor, despite the DSN's own
  declared class width being 0.25 mm. Freerouting's fanout stage (escaping
  dense LED and matrix pads) chose a narrower width than the declared net
  class on these six nets specifically; every other net came out at the
  declared width. Not previously documented; added here as a new,
  measured failure mode.
- **`copper_edge_clearance` ×11**, all against four LED footprints
  (`LED1`, `LED3`, `LED4`, `LED6`), each of which carries its own
  `Edge.Cuts` cutout for the light path. Freerouting has no notion of an
  interior board cutout belonging to a footprint and routed tracks/vias
  through the 0.5 mm clearance band around it; the original hand-routed
  board (DRC 0) had routed around these same cutouts by construction.
- **`unconnected_items` ×3**, all the same GND zone corner: a real pinch,
  the exact `SetMinThickness` trap `references/kicad-api.md` §4 already
  documents for scripted routing, reproduced here for an autorouter's
  copper. Freerouting's own log reported 0 unrouted and 0 violations for
  this run, because it has no zone concept at all (§4 item 5's "the
  unrouted count is not the only completeness signal" made concrete).

The KiCadRoutingTools row's `kicad_gate.py` PASS is conditioned on a step
that is easy to skip and silently wrong without it: **`route.py`'s own
output is not DRC-ready.** Checked before any refill, the same board
reported 251 `clearance` violations and 76 `hole_clearance` violations, every
one at `actual 0.0000 mm` against a stale cached zone fill, the identical
"zones carry a cached `filled_polygon`, stale the instant anything moves"
trap `references/kicad-api.md` §4 documents, hit by a second tool. KRT's own
"plane finalize" step taps nets into a plane; it does not recompute the
`filled_polygon` `kicad-cli`'s DRC reads. `kicad_zonefill.py --island-mode
area` after `route.py` (which `route-krt`, below, does automatically) is
what closes the gap; the row above already reflects the refilled result.

A hand-built Specctra session's 10× coordinate scaling trap
(`references/kicad-api.md` §10) does **not** reproduce on real Freerouting
output: reading the imported board back with `kicad_geom.py`, 107 of 534
track endpoints land exactly on a pad centre (0.0000 mm), confirming the
real router-to-KiCad round trip is coordinate-correct. That trap remains
real for a hand-built or replayed session; it was never a risk for a real
router's own output, and this is now measured, not inferred.

### 6b. The DRC-settings trap, and the corrected KiCadRoutingTools numbers

The §6a KiCadRoutingTools gate result was measured against rules the router
had loosened. `route.py` by default rewrites the output's `.kicad_pro` Board
Setup floors down to the values it routed (its `--no-fix-drc-settings` flag
describes this as making KiCad's DRC "only flag genuine problems"). On this
board it lowered `min_hole_clearance` from 0.25 mm to 0.20 mm. Gated under the
project's own rules instead, the same routed copper carried 70
`hole_clearance` violations: tracks at 0.244 mm from switch NPTH holes, and
the refilled VCC zone at 0.2005 mm from mounting holes, because the refill had
also run under the loosened project file. That is the rule demotion
`references/kicad-api.md` §4 forbids, performed by a tool rather than an agent,
and it is why the orchestrator re-runs the gate against the project's rules
rather than trusting any tool's own "clean".

`kicad_route.py route-krt` now always passes `--no-fix-drc-settings`,
`--escalation board` (never below the project's declared floors; the default
`fab` goes below them), and `--strict-sizes` (reported as a warning, not a
failure, when a feature lands between its requested size and the floor). It
routes at the larger of the project's copper and hole clearance, because the
router has no separate copper-to-hole rule, and it copies the input's
`.kicad_pro` and `.kicad_prl` beside the output before the refill.

Re-measured with those flags, same stripped hexpad board, 2026-09-20:

| Metric | KiCadRoutingTools, rules preserved |
|---|---|
| Nets routed | 33 of 33, 0 failed |
| Clearance routed at | 0.25 mm (the project's hole clearance) |
| Wall time (whole `route-krt` call, refill included) | 9.9 s |
| Segments / vias | 271 / 58 |
| Router warning | 3 features on 1 net delivered at 0.2044 mm against a wider requested width; still above the 0.20 mm floor |
| Rules beside the output | min_clearance 0.20, min_hole_clearance 0.25, min_track_width 0.20 (unchanged) |
| `kicad_gate.py` | **PASS**: ERC ok, DRC ok, parity ok (enforced 5/5), unconnected ok, no findings at any severity |

So the recommendation below stands, on honest numbers: the router completes
the board and the gate passes under the project's rules, provided the wrapper
keeps the rules out of the router's hands.

**Default recommendation, from this one board:** prefer KiCadRoutingTools
(`route-krt`) as the default backend. On the board measured here it produced
a board that passed `kicad_gate.py` outright once the (mandatory, scripted)
zone refill ran, while Freerouting left three real DRC classes needing
investigation before `adopt`. Both backends are fast enough on a board this
size that speed is not the deciding factor (low tens of seconds either way,
dominated by process startup, not routing). Keep Freerouting available as a
fallback and a second opinion; it is the more established, more widely
used tool of the two, and a board where KiCadRoutingTools plateaus or fails
is exactly the case for trying the other backend, not for declaring the
board unroutable. This is one small, two-layer board; it is not a claim
about dense BGAs, RF layouts, or anything KiCadRoutingTools' own docs do not
already scope themselves to. `references/kicad-ecosystem.md` §3's verdict
for KiCadRoutingTools is updated from "evaluate" to "adopt" on this
evidence; Freerouting's "adopt (fallback)" verdict is unchanged.

`kicad_route.py route-krt BOARD.kicad_pcb --power-nets GND VCC` runs the
KiCadRoutingTools backend end to end (route, then the mandatory zone refill)
in one command; `kicad_route.py adopt` is identical afterward regardless of
which backend routed the board. Full numbers, per-command output, and the
kb card recording this run: `kb/runs/hexpad-autoroute-2026-09-20.md`.

Two things worth naming rather than leaving implicit:

- **The KiCad 10 IPC API cannot do this today.** `kicad-python`'s published
  documentation shows no DSN/SES import or export, and no documented
  track/via creation call (verified from docs.kicad.org/kicad-python-main,
  fetched during this work). OrthoRoute routes IPC-natively by placing
  tracks through calls the public docs do not show, which means either the
  API has grown past what is documented or OrthoRoute uses an
  undocumented/internal path, not confirmed either way. Until `kipy`
  documents track/via creation, `pcbnew` SWIG remains the only route into a
  Specctra bridge, which is a second, independent reason (besides SWIG's
  removal in KiCad 11) that `references/kicad-api.md` §7's migration note
  matters for this exact area of the pipeline.
- **A hand-built Specctra session is not a substitute for a real router's
  output**, even for testing. `references/kicad-api.md` §10 documents an
  10× coordinate scaling found while trying exactly that: the importer
  divides by the session's declared resolution, and a hand-built session
  copying DSN numbers verbatim is off by exactly that factor.
  Use `kicad_route.py`'s DSN export to confirm the bridge is reachable; use
  a real router's SES for anything that has to be geometrically correct.
