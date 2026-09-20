---
domain: runs/hexpad-autoroute-2026-09-20
tags: [hexpad, freerouting, kicadroutingtools, autorouting, kicad_route,
       specctra, dsn, ses, zone-refill, track-width, copper-edge-clearance,
       java, openjdk, drc]
source: local run, this machine, 2026-09-20 (scripts/kicad_route.py,
  scripts/hw_install.py, ~/.freerouting/freerouting-2.4.1.jar,
  ~/.hw_forge/KiCadRoutingTools @ ab8d0c3648209d6a2ac6c1c0fb71a0ddcb545aa6)
date: 2026-09-20
confidence: verified-in-cad
---

# hexpad through both autorouting backends: the real round trip, numbers and traps

The first real (not hand-built, not docs-only) exercise of
`scripts/kicad_route.py`'s Freerouting flow, and the first run of
KiCadRoutingTools against an hw_forge board, both against a copy of the
hexpad keyboard (`kb/projects/hexpad.md`). Generic conclusions are written
into `skills/hw-design/references/autorouting.md` §6a and
`skills/hw-design/references/kicad-api.md` §10; this card is the specific
numbers and per-command trail behind those.

## 1. Setup

Copied `~/1_projects/dev/keyboard/hexpad/kicad/{hexpad.kicad_pcb,
.kicad_pro, .kicad_sch, fp-lib-table, sym-lib-table, lib/,
hwforge-overrides.json}` into a scratch directory (`hw_forge/.tmp/autoroute/`,
never committed). Under KiCad's bundled python, loaded the board, removed
every `PCB_TRACE_T`/`PCB_ARC_T`/`PCB_VIA_T` (150 segments, 0 arcs, 45 vias),
kept both zones (VCC on F.Cu, GND on B.Cu) and all 41 footprints, saved as
the unrouted board. 59 nets were left to route.

**Trap, not previously written down: `hwforge-overrides.json` must travel
with the board.** The first attempt omitted it. `kicad_scaffold.repatch()`
(called by `kicad_zonefill.fill`, called by both `import-ses` and
`route-krt`) reapplies severities from that sidecar file to every
`.kicad_pro` in the directory; without it, a board whose project had
deliberately demoted `courtyards_overlap`/`npth_inside_courtyard`/
`pth_inside_courtyard` to `warning` (hexpad's own display-over-MCU courtyard
overlap, see `kb/projects/hexpad.md` §3.8) comes back with those at KiCad's
`error` default, and `kicad_gate.py` reports 29 phantom violations that have
nothing to do with the routing pass. Second trap, related: when copying a
board file under a new basename before running `import_ses`/`route_krt` with
a different `-o`, always pass the *original* board (with its own correct
sibling `.kicad_pro`) as the input and let the script's own `SaveBoard`
create the output's `.kicad_pro`; a bare `cp board.kicad_pcb
renamed.kicad_pcb` with no sibling `.kicad_pro` makes `pcbnew.LoadBoard`
silently fall back to KiCad's project defaults.

## 2. Freerouting v2.4.1

### Java discovery: two JREs, one silently wrong

`/usr/bin/java` (OpenJDK 21.0.2) loads the jar far enough to print
`UnsupportedClassVersionError: ... class file version 69.0 ... only
recognizes ... up to 65.0`, then **exits 0** with no `.ses` written, a
return-code check alone reports success. `/opt/homebrew/opt/openjdk/bin/java`
(OpenJDK 25.0.2, Homebrew) runs the jar cleanly. `kicad_route.py`'s
`find_java` now probes every candidate's own `java -version` and prefers the
highest major version found, rather than a fixed path order. Fixed in this
run; previously `find_java` checked only `/usr/bin/java`, which is exactly
the one that fails.

### The route

```
python3 scripts/kicad_route.py export-dsn hexpad_unrouted.kicad_pcb -o hexpad.dsn
  -> 0 wires, 0 fixed (board has no tracks yet)
python3 scripts/kicad_route.py route hexpad.dsn -o hexpad.ses --passes 40
  -> returncode 0, elapsed 7-9s (kicad_route.py's own wall time, JVM start included)
python3 scripts/kicad_route.py import-ses hexpad_unrouted.kicad_pcb hexpad.ses -o hexpad_routed.kicad_pcb
  -> tracks 0 -> 267, vias 0 -> 37, nets_emptied: []
python3 scripts/kicad_route.py adopt hexpad_routed.kicad_pcb -o routing_freerouting.py
  -> 267 segments, 0 arcs, 37 vias
```

Freerouting's own log (captured by invoking the jar directly, since
`kicad_route.py route` only prints the full log on failure): fanout stage
1.64s (83 of 85 SMD pins escaped, 97.6%), auto-routing stage 5 passes /
5.72s, final score 999.99/1000, **0 unrouted, 0 violations** by its own
reckoning. Total Freerouting job time 6.06s.

### What Freerouting's own "done" did not catch

`kicad_gate.py` on the imported, zone-refilled board (island-mode area, run
automatically inside `import_ses`):

```
DRC  FAIL  track_width x20, copper_edge_clearance x11
unconnected  FAIL  unconnected_items x3
```

- **`track_width` x20**, six nets (`LED_D0` x7, `L01`/`L02`/`L04` x3 each,
  `R1` x2, `c1_top` x2), every one delivered at **0.1874 mm** against the
  0.2 mm project floor, despite the DSN's declared `kicad_default` class
  width being 0.25 mm. Every other net came out at the declared width.
  Freerouting's fanout stage (escaping dense LED/matrix pads) chose a
  narrower width on these six nets specifically; root cause not chased
  further than that.
- **`copper_edge_clearance` x11**, all against `LED1`/`LED3`/`LED4`/`LED6`,
  each of which carries its own `Edge.Cuts` cutout for the light path.
  Freerouting has no notion of a footprint-owned interior board cutout and
  routed copper through the 0.5 mm clearance band around four of them. The
  original hand-routed board (DRC 0) avoided these by construction.
- **`unconnected_items` x3**, all the same GND zone corner (board coord
  approx. -13.225, -5.7): a real pinch below `SetMinThickness`, the trap
  `skills/hw-design/references/kicad-api.md` §4 already documents for
  scripted routing, reproduced here by an autorouter. Freerouting cannot see
  zones at all, which is why its own log reported this run as fully clean.

### Coordinate fidelity (settles the resolution-scaling question)

Read the imported, routed board back with `kicad_geom.py`: **107 of 534
track endpoints land exactly (0.0000 mm) on a pad centre.** The 10x
`(resolution um N)` scaling trap documented for a hand-built session
(`kicad-api.md` §10) does not reproduce against a real router's own session.
No fix to `import_ses` was needed; the existing code already handles a real
Freerouting session correctly.

### Lock survival

Built a second board: the unrouted board plus 2 tracks copied back from the
original (net `C0`, both on the same net, one per layer), `SetLocked(True)`
before saving. `export-dsn` reported 2 wires, 2 fixed, matching. After
`route` and `import-ses`, both tracks came back at identical net, endpoints
(to 0.0001 mm), width, and layer. **Lock is fully honoured end to end** for
a real router, not just at the export boundary (which the pre-existing
docstring already verified).

## 3. KiCadRoutingTools @ `ab8d0c3648209d6a2ac6c1c0fb71a0ddcb545aa6`

```
~/.hw_forge/venv/bin/python py_router/route.py hexpad_krt_unrouted.kicad_pcb \
    hexpad_krt_routed.kicad_pcb --power-nets GND VCC
```

Wall time 12-16s (includes venv python/numpy/scipy interpreter startup).
Tool's own reported routing time: **1.68s**, 2,933,542 A* iterations.
Single-ended 33/33 routed, multi-point 63/63 pads connected across 8 nets,
0 failed. Output: 262 segments, 0 arcs, 59 vias.

Its own checkers, both clean:

```
py_router/check_connected.py  -> ALL NETS FULLY CONNECTED!
py_router/check_drc.py        -> NO DRC VIOLATIONS FOUND! (0.2mm clearance grading)
```

### The trap: `route.py`'s own "clean" is not `kicad_gate.py`-ready

Running `kicad_gate.py` directly on `route.py`'s raw output (no refill):
**251 `clearance` violations and 76 `hole_clearance` violations, every one
at `actual 0.0000 mm`.** This is the exact "zones carry a cached
`filled_polygon`, stale the instant anything moves" trap `kicad-api.md` §4
already documents for scripted routing, hit by a second, independent tool.
KRT's "plane finalize" step taps nets into a plane; it does not recompute
the `filled_polygon` `kicad-cli`'s DRC reads.

Running `kicad_zonefill.py --island-mode area` on the output (the same call
`import_ses` already makes for the Freerouting flow) fixed all 327
violations in one pass:

```
DRC          ok
unconnected  ok
```

This is now automated: `kicad_route.py route-krt BOARD.kicad_pcb
--power-nets GND VCC` runs `route.py` then the zone refill in one step, so a
caller cannot skip it by accident the way this run's first pass did.

### The second trap: `route.py` rewrites the project's DRC floors

Its default (`--no-fix-drc-settings` turns it off) lowers the output
`.kicad_pro` Board Setup constraints to the values it routed. Measured here:
`min_hole_clearance` 0.25 mm became 0.20 mm. Gated under the original project
file, the routed board carried 70 `hole_clearance` violations (tracks at
0.244 mm from switch NPTH holes, the refilled VCC zone at 0.2005 mm from
mounting holes). `kicad_route.py route-krt` now passes `--no-fix-drc-settings
--escalation board --strict-sizes`, routes at the larger of the project's
copper and hole clearance (0.25 mm here), and copies the input's project files
beside the output before the refill. Re-run that way: 33 of 33 nets, 271
tracks, 58 vias, 9.9 s wall, `kicad_gate.py` clean with the rules unchanged.

## 4. Side by side

| Metric | Freerouting v2.4.1 | KiCadRoutingTools |
|---|---|---|
| Wall time (whole `kicad_route.py` call) | 7-9s | 12-16s |
| Tool's own routing time | 6.06s | 1.68s |
| Tool's own completion report | 0 unrouted, 0 violations, score 999.99 | 33/33 single-ended, 63/63 multi-point pads, 0 failed |
| Segments / vias | 267 / 37 | 262 / 59 |
| Total track length | 911.3 mm | 927.9 mm |
| `kicad_gate.py`, after the mandatory zone refill | FAIL: track_width x20, copper_edge_clearance x11, unconnected x3 | PASS, but first measured against a .kicad_pro the router had loosened (min_hole_clearance 0.25 to 0.20 mm); under the project's rules the same copper had 70 hole_clearance violations. Re-run with the rules preserved: PASS, 271 tracks, 58 vias, 9.9 s (autorouting.md §6b) |
| `kicad_gate.py`, before any zone refill | not applicable (`import_ses` always refills) | FAIL: clearance x251, hole_clearance x76 (stale zone fill; fixed by the refill row above) |
| Lock survival (2 tracks pre-locked) | PASS, byte-identical | not applicable (no export/import boundary) |

On this one board, KiCadRoutingTools produced a `kicad_gate.py`-clean board
outright (once its output went through the same mandatory zone refill both
backends need); Freerouting left three real DRC classes needing
investigation. Both backends are fast enough here that wall time is
dominated by process/interpreter startup, not routing. See
`skills/hw-design/references/autorouting.md` §6a for the recommendation this
supports and its stated scope (one small, two-layer board; not a claim about
dense BGAs or RF layouts).

## 5. What changed in the repository because of this run

- `scripts/kicad_route.py`: `find_java` now probes multiple JRE candidates
  (adds `/opt/homebrew/opt/openjdk/bin/java`, `/usr/local/opt/openjdk/bin/java`)
  and prefers the highest version found, instead of only checking
  `/usr/bin/java`. New `route-krt` subcommand and `route_krt` /
  `refill_krt_output` functions: a second autorouting backend, with the same
  `adopt` step as the Freerouting flow.
- `scripts/hw_install.py` (new): reproducible install for all three optional
  tools (Freerouting jar, Fabrication Toolkit plugin, KiCadRoutingTools +
  venv), sharing discovery with `kicad_route.py` rather than duplicating it.
- `scripts/preflight.py`: `check_router`'s hint now names
  `scripts/hw_install.py --router` as the fix.
