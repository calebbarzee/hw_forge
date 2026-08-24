---
domain: keyboards/parts
tags: [msk12c02, msk-12c02, shouhan, slide-switch, spdt, power-switch, actuator, edge-mount, enclosure, port-panel, reachability, lipo, rotation-sign, coordinate-frame]
source: hexpad phase-6 case runs, rev 1 and rev 2 (kicad/hexpad.kicad_pcb footprint geometry, case/hexpad_case.py 239-check verify() pass, GAPS.md #55); z_board v0.4 (case/zboard_case.py SW_PWR ledger)
date: 2026-08-23
confidence: verified-in-cad
---

# MSK-12C02 slide switch: geometry, and why it always ends up recessed

The default battery-disconnect switch on nRF52840 keyboards: a tiny surface-mount (SMD),
single-pole double-throw (SPDT) slide switch. It mounts on the board's underside at an
edge, with its slider protruding past that edge so a fingernail can reach it. KiCad
footprint: `Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02`.

## Numbers

| Quantity | Value | Source |
|---|---|---|
| Body (Fab rect; B.Fab here, the part is bottom-side) | 6.70 × 2.80 mm | the footprint's own Fab outline |
| Body height above its mounting face | 1.40 mm (assumed) | matches the "6.7 × 2.8 × 1.4" datasheet triple this family is sold under; not measured |
| Slider lobe, footprint-local | x 0.15 … 1.45, y −1.40 … −2.85 | footprint B.Fab lines |
| Slider lobe courtyard, local | x −1.70 … 1.70, y −1.70 … −3.10 | footprint B.CrtYd |
| Slider protrusion past the body | 1.45 mm | −2.85 − (−1.40) |
| Full courtyard | 8.90 mm (along the body) × 5.95 mm | with both lobes |
| Pad rows | 3 signal pads at local y = +1.95 (x −2.25 / +0.75 / +2.25); 4 mechanical pads at x ±3.675, y ±1.10 | |

**The slider is not centered on the body.** Its lobe spans local x 0.15 … 1.45, so its
center is at local x = +0.80, that is, 0.80 mm off the part's own origin.

Slot geometry must be positioned through the part's own rotated frame, not from the
footprint center. On hexpad (rot −90, both revisions) that difference puts the actuator
center 0.80 mm off the part's own y: rev 1 has the part at y 24.00 and the actuator at
24.80, rev 2 has the part at y 9.640 and the actuator at 10.440. The lobe courtyard
center stays on the part's y. A slot centered on the footprint origin is 0.80 mm off the
thing you actually push.

### This asymmetry is a rotation-sign canary: use it deliberately

That same off-center lobe makes this part the best available check on a coordinate
pipeline, and hexpad rev 2 proved it the hard way. At `(49.60, 9.640)` rot −90:

```
body (y-symmetric)        board y  6.290 … 12.990     <- a sign error is INVISIBLE here
slider lobe (asymmetric)  board y  9.790 … 11.090     <- and 1.65 mm wrong here
```

A written case-handoff table gave the lobe as y 8.14 … 9.54, the correct value mirrored
about the part center (9.640), that is, the rotation applied with the wrong sign. The
table's body numbers were right to ±0.05, so nothing looked wrong.

Cutting the wall slot on the handoff figure would have put 2.0 mm of solid wall on top of
the actuator: a case that passes every clearance check and cannot be switched on.

Two habits follow, and they cost one line each:

1. Validate your frame helper against `kicad_geom`'s own `pads_bbox` for this part
   before trusting it on anything. The MSK12C02's pads are asymmetric in the same axis, so
   reproducing `pads_bbox` proves the sign:
   `local_rect()'s frame agrees with kicad_geom on SW7's pads (y 5.615..13.665)`.
2. Assert the lobe's absolute board rect, not just the slot's relation to it, so a
   stale table cannot be "corrected" back into the generator later.

`kicad_geom.py`'s docstring already warns that a rotation-sign error "is invisible on 0 and
180 degree parts and silently wrong on every 90/270 part". This is the part to test that
warning against.

## The reachability trap: this switch cannot be made proud of a printed wall

Placed conventionally, with the body wholly on the board and the slider overhanging the
edge, the slider tip stands only 0.825 mm proud of the board edge. That figure is hexpad's,
measured off the board file; z_board's placement put it at 0.30 mm. Set it against the minimum wall
a fused deposition modeling (FDM) printer can lay down:

```
tip past the cavity's inner face = 0.825 − pcb_clear(0.30) = 0.525 mm
wall that would leave it proud   = < 0.53 mm
FDM minimum wall                 =   0.80 mm
```

So the slider is unavoidably recessed behind any printable wall, even a locally-thinned
recessed port panel. `references/mechanical.md` §6's formula
(`usable travel = proud_of_edge − wall_thickness`) goes negative, and its own advice
("thin the wall … keep ≥0.8 mm") cannot rescue it. This is not a design error; it is a
property of the part.

What to do instead: target a bounded recess inside a slot big enough to admit a
fingernail, and assert that instead of a travel figure.

| Assertion | hexpad value |
|---|---|
| recessed port panel leaves ≥0.80 mm of wall | 0.80 mm (from a 2.50 mm wall, 1.70 mm recess) |
| slider recess below the panel face ≤0.60 mm | 0.275 mm |
| slot spans the lobe courtyard, not just the slider | 7.0 mm slot over a 3.4 mm lobe courtyard |
| slot spans the body in z for any plausible height | z −1.60 … −5.60, i.e. any body ≤4.0 mm |
| slot cut clean through the wall | the tip passes the inner face, so a recess would foul it |

Making the slot's z span 4.0 mm rather than "body height + keepout" is the cheap trick
worth copying: it removes the unmeasured 1.40 mm body height from the geometry entirely,
so the assumption can only ever cost margin, never a collision.

## Placement notes

- On a nice!nano board this is the cell → B+ disconnect. It carries the whole system
  current, so it is a real (if small) series element, not a signal switch.
- Nesting it under a socketed nice!nano works and is the tidiest use of the space: the
  module stands off 2.54 mm headers, the switch body is 1.40 mm, and the two share a plan
  footprint with the slider still overhanging the board edge. hexpad rev 2 does this, with
  SW7 at (49.600, 9.640) sitting directly under MCU1 at (35.125, 9.640), both rot −90.
  Expect `npth_inside_courtyard` design rule check (DRC) findings, and demote that rule
  with a justification (`nice-nano-v2.md`).
- The case cost of nesting it under the module is that one wall then carries two
  openings: the module's USB notch above the board plane and this slot below it, overlapping
  in the along-wall axis. Assert the web between them, not each opening alone. hexpad's
  is `usb_floor(+1.20) − slot_ceiling(−1.60) = 2.80 mm` of full-thickness wall.
- All known placements put the switch on the board's bottom face at an edge, with the
  slider overhanging. Its obstacle rect on the underside ledger is the full courtyard, and
  the protruding lobe gets its own rect for the wall-opening check. They are different
  rectangles and both are needed.

## What a physical unit must confirm

- Body height above the mounting face. 1.40 mm is inferred from the part family's
  sales dimensions and the footprint's 6.70 × 2.80 B.Fab outline agreeing with it. Measure
  it; if it exceeds ~2.30 mm it eats into a typical `parts_clear` budget.
- Slider actuation force, and whether 0.275 mm of recess is comfortable in practice, or
  whether the slot wants a lead-in chamfer.
