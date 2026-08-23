---
domain: projects/zboard
tags: [z_board, regression-fixture, split-keyboard, zmk, nice-nano, reversible-pcb, build123d, gates]
source: z_board v0.4 (README.md, HISTORY.md, kicad/NOTES.md, kicad/POWER.md, case/README.md, PIPELINE.md)
date: 2026-08-22
confidence: verified-in-cad
---

# z_board — the pipeline's origin project and regression fixture

`/Users/calebbarzee/1_projects/dev/keyboard/z_board`

A 42-key (44 with two optional thumb keys) wireless split ortholinear keyboard: nice!nano v2
per half, ZMK, BLE-only to a Prospector dongle, per-key reverse-mount SK6812MINI-E lighting,
3D-printed two-shell case. **Every artifact is code-generated and every phase has a
machine-checkable exit gate; no GUI step anywhere, no autorouter, copper is never
hand-edited.** hw_forge is the generalisation of this run.

**Role for hw_forge: the regression fixture.** The genericized scripts must reproduce
z_board's current gate numbers from the outside. If `kicad_gate.py` does not report
0/0/0/0 on all four projects, the script is wrong, not the board.

## Gate state (2026-08-22, KiCad 10.0.5)

| | proto (1 key) | left | right (mirrored) | combo (reversible) |
|---|---|---|---|---|
| ERC | 0 | 0 | 0 | 0 |
| DRC (error severity, `--schematic-parity`) | 0 | 0 | 0 | 0 |
| schematic parity | 0 | 0 | 0 | 0 |
| unconnected | 0 | 0 | 0 | 0 |

Halves: 101 footprints each; 421 tracks / 102 vias (left), 405 / 99 (right); zones filled
inside the generator. Combo is clean at **every** severity, no warnings, both inner planes
filling as a single island — and since 2026-08-22 its DRC also carries **JLCPCB capability
floors** (0.09 clearance and 0.15 via annular in project rules; 0.45 PTH hole-to-hole and
0.28 PTH hole-to-copper as pad-type-conditioned `.kicad_dru` rules — see `kb/fabs/jlcpcb.md`),
applied by `gen_combo.patch_project()`. The 2-layer halves do not carry them yet. Documented surviving warnings on the halves only: two
deliberate `npth_inside_courtyard` per board (power switch nested under the module) and one
`isolated_copper` sliver in the left VCC pour. Board outline **122.3 × 86.2 mm**, 2 layers
(VCC pour F.Cu, GND pour B.Cu). Fab exports and renders generated and assertion-gated.

## Where the knowledge lives

| File | Contents |
|---|---|
| `prompt.md` | the locked spec — arbiter for every decision |
| `HISTORY.md` | design evolution v0.1→v0.4, and what was rejected on evidence |
| `README.md` | as-built summary, the iterate/gate commands |
| `kicad/NOTES.md` | routing bands, the MCU corner, KiCad-10 traps, zones, the mirroring diagnosis, the whole combo rationale |
| `kicad/POWER.md` | rail topology, R1 reasoning, current budget, **11-row rejected-protection table** |
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

- **v0.1/v0.2** ergogen + freerouting, one reversible board. Killed by: regenerating
  destroys routing; reversible footprints bought 42 `hole_near_hole`, 24 spare jumper nets
  and a jumper that could put battery voltage on a matrix pin; the wide LED window gave 168
  `copper_edge_clearance`.
- **v0.3a** scripted trace stamping with `type fix` in the DSN + a netlist cross-check.
  **Validated the method** (generate, then verify headlessly) — that is what survived. The
  implementation ran on SWIG `pcbnew` and is archived.
- **v0.3b** the decisive simplification: **stop being reversible, build two separate
  boards** from one logical design. The `hole_near_hole` and jumper classes vanished with
  the reversibility.
- **v0.4** the mirrored half's bands re-derived in board coordinates; the MCU corner's
  three-band layout; fab exports; `POWER.md`. Plus the combo board as a stretch goal.
- **Rejected on evidence** (do not relitigate): removing per-row LED rotation (58
  `shorting_items`); dropping the LED light window (narrowed to 2.8 mm instead); the 110 mAh
  cell (superseded by 1000 mAh); M1.6 mounting hardware; wired TRRS split; MCU under the
  inner column; on-keyboard display.

## The reversible combo board — scheme summary

One PCB, fabbed twice, populated on the **back** face for the left half and the **front**
for the right. Flip about the **vertical** axis (x = 47.625) — the only flip that leaves row
order alone — under which the key grid maps onto itself with logical column indices intact,
so both halves share one netlist. **Four layers**: signals on the outer faces, `In1.Cu` =
GND plane + the four row buses, `In2.Cu` = VCC plane + twelve column buses (one per column
per face). Ten reversible footprints generated from the halves' own tables. nice!nano on
**two interleaved through-hole grids (48 holes) offset purely across by one full pitch** —
which puts each pad number's two holes on one x, lets one track in a pad gap reach both,
and lets both planes flow through the same gaps. One custom DRU rule: 0.3 mm copper to an
unplated hole wall (a mirrored contact slot passes 0.432 mm from the other face's socket
pad). 123 placements, 101 parts per build. Row nets move to D2–D5, **so this board's ZMK
devicetree is not the halves'**. Full rationale in `kicad/NOTES.md`; build steps in
`kicad/combo/ASSEMBLY.md`.

## Case — fastening summary

Four printed parts (`{left,right} × {top,bottom}`), build123d, 65 numeric checks on every
run. Top shell = integrated MX plate + full perimeter wall + six M2 standoffs; bottom shell
= a lid dropping into a 1.2 mm rabbet, carrying six bosses, the counterbores, the reset
poke-hole and the battery bay.

**Clamp scheme**: M2 × 14 from below → counterbore in the floor → up the boss → through the
board's own **Ø2.2 mm clearance hole** → into an **M2 heat-set insert (Ø3.2 OD × 4.0 long)**
in the top-shell standoff. No screw or plastic touches copper. Ø5.6 posts (1.2 mm wall
around the insert), 4.4 mm bore with a 0.6 mm deck cap.
Stack-up: `(floor 2.60 − counterbore 2.10) + cavity 8.00 + PCB 1.60 = 10.10 mm` of travel →
**3.90 mm engagement**. The spec's M2×8 was written for a 4.5 mm cavity and is 2.1 mm short
of even reaching the insert.
Case outer **127.9 × 91.8 × 17.2 mm** per half; plate top at z = +5.00 (z = 0 is the PCB top
face); cavity 8.00 mm sized by a **503450 ~1000 mAh** cell (5.0 + 0.4 swell) over a
2.60 mm parts clearance. Both shells print **support-free**, reference face down.

## Open items on z_board itself

- Case not yet updated for the combo board (USB cutout 2.54 mm taller, actuator slot moves,
  battery pocket and reset poke-hole move to the corner east of the module).
- Boards not yet ordered; no hardware exists — hence `verified-in-cad`, not
  `verified-in-hardware`, on every z_board-sourced card.
- SWIG `pcbnew` dependency must go before KiCad 11.
