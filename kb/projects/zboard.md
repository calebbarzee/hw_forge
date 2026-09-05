---
domain: projects/zboard
tags: [z_board, regression-fixture, split-keyboard, zmk, nice-nano, reversible-pcb, build123d, gates, mcu-flip, schematic-parity, kicad-dru, zone-min-island, 3d-models]
source: z_board v0.4 (README.md, HISTORY.md, kicad/NOTES.md, kicad/POWER.md, case/README.md, PIPELINE.md); z_board MCU-flip and 3D-export work, 2026-09-03/04 (kicad/MCU-FLIP.md, kicad/3D-EXPORT.md)
date: 2026-09-03
confidence: verified-in-cad
---

# z_board: the pipeline's origin project and regression fixture

`/Users/calebbarzee/1_projects/dev/keyboard/z_board`

A 42-key (44 with two optional thumb keys) wireless split ortholinear keyboard: nice!nano v2
per half, ZMK, Bluetooth Low Energy (BLE) only to a Prospector dongle, per-key
reverse-mount SK6812MINI-E lighting, 3D-printed two-shell case.

Every artifact is code-generated and every phase has a machine-checkable exit gate: no GUI
step anywhere, no autorouter, and copper is never hand-edited. hw_forge is the
generalization of this run.

Role for hw_forge: the regression fixture. The genericized scripts must reproduce
z_board's current gate numbers from the outside. If `kicad_gate.py` does not report
0/0/0/0 on all four projects, the regression is in the genericized script; z_board's own
gate numbers are the reference.

## Gate state (2026-09-03, KiCad 10.0.5)

All four boards gate clean at **every severity**, not just error: violations 0,
unconnected 0, schematic parity 0, parity enforced 5/5 (`extra_footprint`,
`footprint_symbol_mismatch`, `lib_footprint_mismatch`, `missing_footprint`,
`net_conflict`, all promoted from `warning` to `error`; before that promotion "parity ok"
was never actually a gate).

| | proto (1 key) | left | right (mirrored) | combo (reversible) |
|---|---|---|---|---|
| ERC | 0 | 0 | 0 | 0 |
| DRC, all severities | 0 | 0 | 0 | 0 |
| schematic parity | 0 | 0 | 0 | 0 |
| unconnected | 0 | 0 | 0 | 0 |
| parity enforced | 5/5 | 5/5 | 5/5 | 5/5 |

This supersedes the card's previously recorded "documented surviving warnings" (two
`npth_inside_courtyard` and one `isolated_copper` on the halves). The MCU-flip work
(2026-09-03) retired both:
- `npth_inside_courtyard` was a dead demotion — reverting it to error and rebuilding fired
  nothing on any of the four boards. Removed from all three generators, with one
  footprint-scoped `.kicad_dru` rule (`courtyard_clearance (min -8mm)` conditioned on
  `MCU1`) taking its place for the five real MCU-courtyard overlaps.
- `isolated_copper` was fixed by raising `ZONE_MIN_ISLAND` 3.0 → 5.0, which removes only
  disconnected pour islands and leaves connected pour (e.g. the right half's 13.12 mm²
  VCC pocket, which has two taps) untouched.

Halves: 101 footprints each; 421 tracks / 102 vias (left), 405 / 99 (right); zones filled
inside the generator.

Combo carries JLCPCB capability floors on its DRC: 0.09 clearance and 0.15 via annular in
project rules, plus 0.45 plated-through-hole (PTH) hole-to-hole and 0.28 PTH hole-to-copper
as pad-type-conditioned `.kicad_dru` rules (see `kb/fabs/jlcpcb.md`), applied by
`gen_combo.patch_project()`. The 2-layer halves do not carry them yet.

Board outline 122.3 × 86.2 mm, 2 layers (VCC pour F.Cu, GND pour B.Cu). Fab exports and
renders generated and assertion-gated.

## The MCU is now on the back face, on all three boards

- Halves: a real `Flip()`. The module's pad columns land on the opposite pad-row y from
  before, which sounds like a free swap but is not: the Kailh socket's own footprint does
  not mirror, so every cell-relative offset (column bus, row via, socket pads) negates in
  along-axis space. Eight of nine corner-routing defects the flip surfaced trace back to
  this one fact; see `kicad/MCU-FLIP.md` for the routing detail (out of scope for this
  card).
- Combo: not a `Flip()` at all. The module sits on one of two interleaved 24-hole grids,
  offset from each other purely in y by one full pitch (`MCU_GRID_DX = 0`,
  `MCU_GRID_DY = 2.54`). Which grid a build uses is set by which face the module body is
  on, not by which half it is, so moving the module to the back face is a re-assignment
  between the two grids with **zero copper change** — `kicad_digest.py --compare` against
  the pre-flip board reports exactly one differing line, a corrected footprint `descr`
  string, no geometry.

## Where the knowledge lives

| File | Contents |
|---|---|
| `prompt.md` | the locked spec; arbiter for every decision |
| `HISTORY.md` | design evolution v0.1→v0.4, and what was rejected on evidence |
| `README.md` | as-built summary, the iterate/gate commands |
| `kicad/NOTES.md` | routing bands, the MCU corner, KiCad-10 traps, zones, the mirroring diagnosis, the whole combo rationale |
| `kicad/POWER.md` | rail topology, R1 reasoning, current budget, the 11-row rejected-protection table |
| `kicad/design.py` | the one logical design: nets, chain order, pin tables, `NRF_PORT` |
| `kicad/Makefile` | the gate contract (`make`, `make check`, `make fab`, `make renders`) |
| `case/README.md`, `case/zboard_case.py` | build123d generator + 65 numeric geometry checks |
| `CLEANUP.md` | repo-hygiene manifest (manifest-then-execute pattern) |
| `kicad-agent-workflow.md` | the interface survey that chose kicad-cli as the gate |
| `PIPELINE.md` | the plan hw_forge implements |

Pipeline shape: `design.py` (pure python, imports under both system and KiCad python) →
`gen_sch.py` / `gen_pcb.py` / `gen_combo.py` emitters → `mkproject.py` scaffolding →
`mklib.py` / `mklib_rev.py` symbol+footprint generation from pin tables → `make check`
(ERC/DRC/parity/connectivity) → `make fab` + `fabcheck.py` assertions → `case/` from
geometry read out of the as-built boards.

## Design evolution, compressed

- v0.1/v0.2: ergogen + freerouting, one reversible board. Killed by three things:
  regenerating destroys routing; reversible footprints bought 42 `hole_near_hole`, 24
  spare jumper nets and a jumper that could put battery voltage on a matrix pin; and the
  wide LED window gave 168 `copper_edge_clearance`.
- v0.3a: scripted trace stamping with `type fix` in the DSN + a netlist cross-check.
  It validated the method (generate, then verify headlessly), and that is what survived.
  The implementation ran on SWIG `pcbnew` and is archived.
- v0.3b: the decisive simplification, which was to stop being reversible and build two
  separate boards from one logical design. The `hole_near_hole` and jumper classes
  vanished with the reversibility.
- v0.4: the mirrored half's bands re-derived in board coordinates; the MCU corner's
  three-band layout; fab exports; `POWER.md`. Plus the combo board as a stretch goal.
- Rejected on evidence (do not relitigate): removing per-row LED rotation (58
  `shorting_items`); dropping the LED light window (narrowed to 2.8 mm instead); the 110 mAh
  cell (superseded by 1000 mAh); M1.6 mounting hardware; a wired tip-ring-ring-sleeve
  (TRRS) split; MCU under the inner column; on-keyboard display.

## The reversible combo board: scheme summary

One PCB, fabbed twice, populated on the back face for the left half and the front
for the right. It flips about the vertical axis (x = 47.625), which is the only flip that
leaves row order alone. Under that flip the key grid maps onto itself with logical column
indices intact, so both halves share one netlist.

Four layers: signals on the outer faces, `In1.Cu` = GND plane + the four row buses,
`In2.Cu` = VCC plane + twelve column buses (one per column per face). Ten reversible
footprints generated from the halves' own tables.

nice!nano sits on two interleaved through-hole grids (48 holes) offset purely across by
one full pitch. That puts each pad number's two holes on one x, lets one track in a pad
gap reach both, and lets both planes flow through the same gaps.

One custom `.kicad_dru` rule: 0.3 mm copper to an unplated hole wall (a mirrored contact
slot passes 0.432 mm from the other face's socket pad). 123 placements, 101 parts per
build. Row nets move to D2–D5, so this board's ZMK devicetree is not the halves'. Full
rationale in `kicad/NOTES.md`; build steps in `kicad/combo/ASSEMBLY.md`.

## Case: fastening summary

Four printed parts (`{left,right} × {top,bottom}`), build123d, 65 numeric checks on every
run. Top shell = integrated MX plate + full perimeter wall + six M2 standoffs; bottom shell
= a lid dropping into a 1.2 mm rabbet, carrying six bosses, the counterbores, the reset
poke-hole and the battery bay.

Clamp scheme: M2 × 14 from below → counterbore in the floor → up the boss → through the
board's own Ø2.2 mm clearance hole → into an M2 heat-set insert (Ø3.2 outer diameter ×
4.0 long) in the top-shell standoff. No screw or plastic touches copper. Ø5.6 posts
(1.2 mm wall around the insert), 4.4 mm bore with a 0.6 mm deck cap.

Stack-up: `(floor 2.60 − counterbore 2.10) + cavity 8.00 + PCB 1.60 = 10.10 mm` of travel →
3.90 mm engagement. The spec's M2×8 was written for a 4.5 mm cavity and is 2.1 mm short
of even reaching the insert.

Case outer 127.9 × 91.8 × 17.2 mm per half; plate top at z = +5.00 (z = 0 is the PCB top
face); cavity 8.00 mm sized by a 503450 ~1000 mAh cell (5.0 + 0.4 swell) over a
2.60 mm parts clearance. Both shells print support-free, reference face down.

## The combo now exports a populated assembly

Every footprint on the combo board carries a real, sourced 3D model. The combo exports a
populated assembly STEP for mechanical review, not a bare board. Provenance, licenses and
the calibration table are in `kicad/3D-EXPORT.md`; where each model came from is in
`kb/keyboards/local-libraries.md` §6.

**This is also the fixture's record of getting it wrong first.** The initial attempt wrote
`kicad/mk3d.py`, a pure-python STEP AP214 writer, and authored mock box solids for the
Kailh socket, the SK6812MINI-E and the nice!nano. Real, correctly-licensed models for the
first two were already on the same disk, in a sibling project, and a real MX switch and
nice!nano were one directory further. Phase 1's "zero hand-authored geometry" exit gate
already forbade this; it was being read as covering footprints and symbols only. `mk3d.py`
and its four outputs are retained, unreferenced, so the anecdote has something to point at.

## Open items on z_board itself

- The combo's reversible footprints carry **no courtyard** at all (`mklib_rev.py` never
  emits an `F.CrtYd`/`B.CrtYd` rectangle, unlike `mklib.py`'s non-reversible footprints).
  So `courtyards_overlap` on the combo board can only ever compare its 6 stock mounting
  holes; it is effectively unenforced across the other 117 placements. Zero violations
  there is silence, not a clean bill of health.
- Case not yet updated for the combo board. It is still built for the halves' MCU position
  (2.975, 59.5) and does not fit the combo's grid geometry (grid A at (2.34, 59.5), grid B
  2.54 mm south of it). Also: USB cutout 2.54 mm taller, actuator slot moves, battery
  pocket and reset poke-hole move to the corner east of the module.
- Boards not yet ordered; no hardware exists, hence `verified-in-cad`, not
  `verified-in-hardware`, on every z_board-sourced card.
- SWIG `pcbnew` dependency must go before KiCad 11.
