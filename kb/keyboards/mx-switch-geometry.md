---
domain: keyboards/geometry
tags: [mx, cherry-mx, keyswitch, kailh-hotswap, plate, cutout, pitch, npth, corridor, footprint-side, clearance-ledger, enclosure]
source: z_board v0.4 (kicad/NOTES.md, case/zboard_case.py, keyswitches.pretty); hexpad phase-4/6 (kicad/hexpad.kicad_pcb, case/hexpad_case.py, GAPS.md #25/#45)
date: 2026-08-23
confidence: verified-in-cad
---

# Cherry-MX key geometry and the Kailh hotswap cell

## Numbers

| Quantity | Value | Notes |
|---|---|---|
| Key pitch | 19.05 mm both axes | 0.75", the ortho/1u grid |
| Plate cutout | 14.00 mm square nominal | fused deposition modeling (FDM) press-fit: 14.15 (nominal + 0.15); tune in ±0.05 steps |
| Plate top surface → PCB top face | 5.00 mm | the MX spec dimension; treat as locked |
| Typical plate thickness | 1.50 mm | → plate underside at +3.50 mm above the PCB, which is all the room a deck has |
| MX body below the plate | 13.97 mm square | inter-switch gap = 19.05 − 13.97 = 5.08 mm |
| MX pin / locating-post protrusion below PCB | ≈2.20 mm | the tallest thing under a switch cell; sets cavity floor budget |
| Kailh MX hotswap socket height below PCB | 1.85 mm (1.85–1.90) | second tallest; use 1.85 for clearance math, 1.90 if quoting a range |
| SK6812MINI-E reverse-mount body below PCB | 1.40 mm | see `sk6812mini-e.md` |

Consequence for enclosures: 3.50 mm under the plate is the whole budget for anything on
the switch face. A socketed nice!nano needs 6.30 mm, so a deck physically cannot pass over
it; see `nice-nano-v2.md`.

### The footprint's `side` lies about where the hardware is

`Kailh_socket_MX` is a front-face footprint whose hardware lives entirely under the
board. Its pads are declared on B.Cu but the footprint sits on F.Cu, so
`kicad_geom.py --json` (and `pcbnew`, and the fab pos file) report it as a top-side
part. Meanwhile 1.85 mm of socket body and 2.20 mm of MX pin/locating post hang below
the PCB. Filtering for `side == "bottom"` to build an underside clearance ledger therefore
misses every switch cell on the board.

Measured on hexpad (6 keys, 2 rows): asking for back-side footprints reported a
full-width free band of 14.96 mm under the key field. Including the sockets, the real
figure is 5.52 mm. A battery bay sized against the first number interferes with all
six switches, and every clearance check passes, because the ledger never contained them.

The same trap, one step removed, applies to any through-hole socketed module on the
front face: `MCU_nice_nano_v2` and a nice!view header are front-face parts whose clipped
solder tails stand proud on the back. Their obstacle rectangles belong on the
back-face ledger too (budget ~1.5 mm unless measured).

Rule: build the underside ledger from **what protrudes, not from the footprint's declared
side**. `kicad_geom.py --json` now answers this directly: each footprint carries a
`protrudes` list of the faces its hardware stands proud of (plus `pad_side` and
`through_hole`), so the ledger is derivable rather than hand-enumerated. On hexpad rev 2 it
reports 29 parts protruding below a 33-footprint board, the six Kailh sockets and both
socketed modules among them, none of which are bottom-side footprints.

The check worth copying: assert that every ref the board says protrudes downward has a
height in your ledger. Then a part added to the board cannot silently miss it, which is
what the hand-enumerated rev-1 version could not promise
(`hexpad/case/hexpad_case.py`, `obstacles_bot()` / `height_below()`).

## Kailh_socket_MX footprint: the non-plated through-hole (NPTH) pattern

Footprint-local coordinates (KiCad frame, +y south), from
`keyswitches.pretty/Kailh_socket_MX.kicad_mod`:

| Feature | Position | Size |
|---|---|---|
| pad 1 (→ column net) | (+6.29, −5.08) | 2.55 × 2.50 surface-mount (SMD), B.Cu |
| pad 2 (→ col-row net) | (−7.56, −2.54) | 2.55 × 2.50 SMD, B.Cu |
| contact hole | (+2.54, −5.08) | Ø3.0 NPTH |
| contact hole | (−3.81, −2.54) | Ø3.0 NPTH |
| center stem | (0, 0) | Ø3.9878 NPTH |
| locating post | (+5.08, 0) | Ø1.7018 NPTH |
| locating post | (−5.08, 0) | Ø1.7018 NPTH |

Five NPTH per cell, and NPTH blocks every copper layer. Solving the clearance
inequalities against those five holes leaves exactly one full-height routing corridor
per column pitch, at key center +7.8 … +10.2 mm in the z_board resolution.

Every net that must cross the cell vertically contends for that one corridor, so lanes are
assigned by hand, not by an autorouter. There is likewise no north–south channel once
a light window and diode vias are added: perimeter feeds must come down a board margin.

z_board's resolved two-layer lane assignment (as a worked example, not a universal):
columns on B.Cu straight vertical at key +7.0, rows on F.Cu straight horizontal at key
+8.2 with one via per diode cathode, switch→diode inside the cell on B.Cu.

## The socket is not symmetric

`Kailh_socket_MX` has no mirror symmetry, so a key cell cannot be mirrored. Two
consequences that bite:
- A mirrored board keeps the same cell-relative bus offsets, so relative to a turned
  module those buses sit on the other side. Recheck every bus that falls inside a
  turned part's own span (`references/electronics.md` §8).
- `Kailh_socket_MX_reversible` in `keyswitches.pretty` mirrors in y, which turns the MX
  switch 180° between faces, and the switch's own light aperture turns with it, so a
  single light window shines into the contacts on one face. For an x-mirror reversible
  cell you must generate your own footprint; the x-mirrored contact holes then land
  2.84 mm apart (0.16 mm closer than two Ø3.0 drills may be), so the pair becomes one
  routed Ø3.0 slot.

## Fab hole census (per MX hotswap cell)

1 × Ø3.9878, 2 × Ø3.0, 2 × Ø1.7018, all NPTH. Assert these counts in the fab-check
profile (`22 keys → 22 × 3.9878, 44 × 3.0, 44 × 1.702`); a reversible cell reports its
Ø3.0 tool as routed slots rather than drilled circles.
