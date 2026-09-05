---
domain: keyboards/geometry
tags: [mx, cherry-mx, keyswitch, kailh-hotswap, plate, cutout, pitch, npth, corridor, footprint-side, clearance-ledger, enclosure]
source: z_board v0.4-v0.6 (kicad/NOTES.md, case/zboard_case.py, keyswitches.pretty); hexpad phase-4/6 (kicad/hexpad.kicad_pcb, case/hexpad_case.py, GAPS.md #25/#45); measured from kbd.3dshapes/CherryMX Switch.step; Cherry Keymodule MX drawing
date: 2026-08-30
confidence: verified-in-cad  # the FDM cutout and printed-PCB traps are verified-in-hardware (z_board v0.5 first print)
---

# Cherry-MX key geometry and the Kailh hotswap cell

## Numbers

| Quantity | Value | Notes |
|---|---|---|
| Key pitch | 19.05 mm both axes | 0.75", the ortho/1u grid |
| Plate cutout | 14.00 mm square nominal, ±0.05, corner radius R0.3 max | Cherry's spec hole. A fabbed FR4 plate uses it as-is: the foostan corne FR4 plate measures 14.00 sq at 1.64 mm thick. |
| Plate cutout, FDM | model **14.35** with a 0.25 mm lead-in chamfer | nominal + 0.15 clip fit + 0.20 hole shrink. **14.15 was tried and was too tight to clip a Holy Panda into.** Calibrate with a coupon; see "The plate cutout on FDM" below. |
| Plate top surface → PCB top face | 5.00 mm | the MX spec dimension; treat as locked |
| Typical plate thickness | 1.50 mm | → plate underside at +3.50 mm above the PCB, which is all the room a deck has |
| MX body below the plate | 13.98 mm square | inter-switch gap = 19.05 − 13.98 = 5.07 mm |
| MX pin protrusion below the PCB **top** face | 3.30 mm | i.e. 1.70 mm below a 1.6 mm board's underside. An earlier revision of this card said ≈2.20 mm below the underside; that was conservative, not measured. |
| Kailh MX hotswap socket height below PCB | 1.85 mm (1.85–1.90) | second tallest; use 1.85 for clearance math, 1.90 if quoting a range |
| SK6812MINI-E reverse-mount body below PCB | 1.40 mm | see `sk6812mini-e.md` |

### The full z profile, measured

Read by slicing `kbd/kicad-packages3D/kbd.3dshapes/CherryMX Switch.step` (the
foostan corne library) in build123d, cross-checked against Cherry's Keymodule
MX drawing. Both agree on every figure. z = 0 is the PCB top face, which is the
switch's seating plane.

| z (mm) | Cross-section | What it is |
|---|---|---|
| −3.30 | 1.20 × 0.30 blades | contact pin tips |
| −2.90 | — | posts begin to taper to their lead-in |
| −2.50 … 0 | Ø3.85 / Ø1.60 ×2 / 1.20 ×2 | centre post / locating posts / blades |
| 0 | 13.05 sq | bottom housing base, sitting on the PCB |
| 0.2 … 3.0 | 13.05 → 13.98 | moulding draft on the bottom housing |
| 3.00 … 5.00 | **13.98 sq** | the neck: what the plate cutout passes |
| **5.00** | **15.60 × 16.00** | top-housing flange, **sits on the plate top** |
| 11.60 | — | top of the housing shell |
| 15.20 | 4.00 sq | top of the stem, unpressed |

The 15.60 × 16.00 flange is the keep-out envelope for anything near the plate's
top plane — a wall, a rim, a countersink. Using the 14 mm cutout as the
reference there collides with the housing. At 19.05 pitch the flanges clear
each other by 3.05 mm.

Cherry's own documents disagree on total height (11.6 vs 15.2/15.6 mm). The
slice resolves it: **11.6 mm is the top of the housing shell, 15.2 mm the top
of the stem.**

### base-to-flange is exactly the plate-to-PCB spec, so the stack has no margin

Base-to-flange measures 5.00 mm and the plate top is specified at 5.00 mm above
the PCB. The switch is therefore stopped by its base on the PCB *and* by its
flange on the plate, at the same instant. There is nowhere to put a tolerance.

Assert the equality in `verify()` rather than letting it drift, and on FDM pick
a layer height that divides 5.00 mm: 0.20 mm is exactly 25 layers, 0.16 mm is
31.25 and lands the standoff seat 0.04–0.12 mm off.

### The plate cutout on FDM

FR4 gets away with a 14.00 hole on a 13.98 neck — 0.01 mm per side — because
the cut is accurate and the wall is smooth. FDM does not. On z_board v0.5 the
plate is printed **face down on the bed**, so the cutout's first layer is the
one that squashes out, and 14.15 modelled came out too tight to clip a Holy
Panda into. Two fixes, both needed:

1. Model the hole with an explicit shrink allowance on top of the fit
   allowance, and check the *predicted printed* hole against the 13.98 neck,
   not the modelled one.
2. Add a lead-in chamfer at the bed face. It guides the switch in and moves the
   squashed first layer off the critical dimension. Bound it by the flange
   seat: `(flange − (cutout + 2·chamfer)) / 2` must stay ≥ ~0.3 mm, which at
   15.60 in x is the binding axis.

Calibrate the shrink with a coupon rather than a full plate — five cutouts in
0.10 mm steps plus two standoffs at the real z = 0 seat plane tests both the
hole size and the 5.00 mm stack in one small print.
(`z_board/case/zboard_case.py`, `coupon()`.)

### Never dry-fit a switch against an FDM-printed stand-in PCB

The failure looks exactly like a case-design error, and it is not.

| Feature | Switch | Footprint hole | Clearance per side |
|---|---|---|---|
| Centre post | Ø3.85 | Ø3.9878 | 0.069 mm |
| Locating post ×2 | Ø1.60 | Ø1.7018 | 0.051 mm |
| Contact blade ×2 | 1.20 | Ø3.00 | 0.900 mm |

A fabbed board holds those tolerances. An FDM mock prints holes 0.1–0.3 mm
undersized, which exceeds the entire clearance on the centre and locating
posts. The posts cannot enter, the switch rests on the mock's surface with up
to 2.9 mm of post proud, and the plate-to-PCB gap reads several millimetres too
small. Observed on z_board v0.5: a printed-PCB dry fit reported the case ">1 mm
off" in z when the case geometry was correct.

To dry-fit anyway, open the mock's per-cell holes to Ø4.2 / Ø1.9 / Ø3.2.

Note also that Ø1.7018 on a Ø1.60 post is only 0.05 mm per side on the real
board too. It is standard MX practice and it works, but it leaves nothing for
NPTH drill tolerance.

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

## §7 (z_board MCU-flip work, 2026-09-03): the reversible cell's switch-to-socket mating

How one physical switch orientation can serve both the left-hand and the right-hand
build of a reversible (x-mirrored) hotswap cell, worked out from measurement rather than
asserted. Measured on the z_board combo board, cell `SW20` at (57.15, 57.15):

```
Ø1.702  (52.07, 57.15)   locating post, centre − 5.08 x
Ø3.988  (57.15, 57.15)   centre stem post
Ø1.702  (62.23, 57.15)   locating post, centre + 5.08 x
oval 5.8398 x 3.0 @ 243.435°  (53.975, 53.34)
oval 5.8398 x 3.0 @ 296.565°  (60.325, 53.34)
```

The two locating posts and the centre stem are the same three holes the non-reversible
`Kailh_socket_MX` census above already gives (§ "Kailh_socket_MX footprint"), just
re-centred on this cell's origin. The two ovals are new: on a plain cell those are two
separate Ø3.0 NPTH contact holes; on the reversible footprint they are routed into
stadium-shaped slots.

### Resolving a routed oval as a stadium: use (long − short), not the full length

A stadium (a rectangle capped by two semicircles) is fully described by an axis length
and a radius. KiCad's oval-pad dimensions give the **overall** long and short
dimensions, 5.8398 × 3.0 here, not the stadium's own parameters. The short dimension is
the diameter, so radius = 3.0 / 2 = 1.5. The axis length is the overall long dimension
**minus** the short one, not the long one on its own:

```
axis length = long − short = 5.8398 − 3.0 = 2.8398
half-axis   = 1.4199
radius      = 1.5
```

Getting this wrong is the trap worth stating explicitly: modelling the axis as the full
5.8398 mm treats the slot as 1.42 mm longer at **each** end than it is, which silently
eats into the surrounding copper web (next section).

At the first oval's rotation (243.435°) and the second's (296.565°, its mirror about
the cell's vertical axis), the stadium end-centres resolve to cell-relative offsets:

| Slot | End A | End B |
|---|---|---|
| oval 1 (243.435°) | (−3.81, −2.54) | (−2.54, −5.08) |
| oval 2 (296.565°, x-mirror of oval 1) | (+3.81, −2.54) | (+2.54, −5.08) |

Compare these to the standard (non-reversible) `Kailh_socket_MX` contact-pin positions
already in this card: (−3.81, −2.54) and (+2.54, −5.08). Both appear here, but split
across the two slots: oval 1's end A is the true left-hand contact hole, and oval 1's end
B is the **x-mirror** of the true right-hand contact hole (which is oval 2's end B, the
real one). Each routed slot therefore merges one genuine MX contact hole with the
x-mirror image of the other pin's hole.

**This is the mechanism that lets one switch orientation serve both hands.** A switch
seated at the cell's own origin puts its two contact pins into opposite ends of the two
slots (one pin near end A of oval 1, the other near end B of oval 2, the "true" pair). A
switch on the mirrored build's cell uses the *other* end of the same two slots (end B of
oval 1, end A of oval 2, the x-mirrored pair). No second footprint, no second switch
orientation: the slot shape already contains both valid pin positions, and whichever pair
the switch's own moulded pin spacing lands on is the one that gets used.

### The copper web this leaves, and why a wrong stadium formula reads as unfabbable

The number that decides whether this cell is fabbable is the **tightest web of copper**
between two adjacent NPTH features inside the cell. Measured (correctly, per the formula
above) on the z_board combo board:

```
tightest web = 0.4889 mm, between a Ø3.0 slot end and a Ø1.702 locating post
```

This figure is identical on the reversible combo board and on the plain (non-reversible)
left/right halves; the reversible slot's extra length runs away from the locating post,
not toward it, so reversibility itself costs nothing at this particular pinch point.

A first attempt at this measurement modelled the oval's axis as the full 5.8398 mm
overall length rather than (long − short). That inflates the slot by 1.4199 mm at **each**
end (2.8398 mm of extra reach total, only half of which points at the post in question)
and produces a bogus web of **0.0982 mm** — five times tighter than the real figure, and
in the range that reads as unfabbable at most fab houses. The correct stadium formula
(axis = long − short, radius = short / 2) is the fix; state it explicitly in any script
that resolves an oval pad to a routed-slot polygon, so this error is not reintroduced.
