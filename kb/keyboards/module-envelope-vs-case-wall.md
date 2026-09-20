---
domain: keyboards/enclosure
tags: [module-envelope, header-pins, fab-layer, kicad_geom, case-verify, nice-nano-v2, collision, usb-shell, obstacle-rect]
source: z_board combo re-spin, 2026-09-20 (.tmp/analysis_case_thin_fit_2026-09-20.md "collision"; kicad/design_combo.py MCU_ENVELOPE; kicad/combo/ASSEMBLY.md "MCU envelope, for the case tool")
date: 2026-09-20
confidence: verified-in-cad
---

# A case-vs-module fit check must use the full module outline, not the header pins

A socketed, through-hole module (nice!nano v2 or similar) is easy to model
in a case generator as "the pin grid it plugs into", the header pins are
what the case's standoffs and hole grid actually engage. That model is
wrong for a wall-clearance check: the module's own PCB body and its USB-C
shell both extend well past the header pins in plan, and a check scoped to
the pins alone cannot see either.

## The measured miss

z_board's combo board re-spin (2026-09-20) traced a real collision to
exactly this gap: the case's inner-wall model had only ever verified the
module's header-pin positions, never its full 33.0 × 17.78 mm PCB body or
the USB-C shell overhanging past it. The module's own PCB envelope
intersected the case's modelled inner wall by **0.335 mm**, a real
mechanical interference, invisible to every check that only looked at pins.

## What to check instead

Build one obstacle rectangle that unions:

1. the module's PCB body (its full outline, not the pad span), and
2. its USB-C shell overhang (the receptacle typically extends past the PCB
   edge to sit flush with, or overhang, the board's own edge).

Source it from a **Fab-layer rectangle in the footprint**, not from pad
positions or a courtyard (courtyards on a socketed module are frequently
smaller than the body, see `nice-nano-v2.md`, "The courtyard is smaller
than the module, by 2.02 mm", and header pins smaller still). z_board's
`design_combo.MCU_ENVELOPE` constant defines this union (33.0 × 17.78 mm
body, 0.60 mm/7.35 mm deep/8.94 mm wide USB-C overhang), written onto the
footprint as an explicit `F.Fab`/`B.Fab` rectangle per hole grid by
`mklib_rev.py`, so `kicad_geom.py --json`'s `fab_items`, and therefore
`body_bbox`, which unions every Fab-layer graphic on the footprint, report
it without any script change on the geometry-reading side. On the combo
board this reads back as `MCU_ENVELOPE_UNION = [-13.49, 50.61, 20.11,
70.93]` (both grids' envelopes combined).

A case generator's own wall-clearance check should assert against this
union rectangle, not against `pads_bbox` (the header pins) and not against
`courtyard` alone.

## Why this needs its own rectangle, not the courtyard

`nice-nano-v2.md` already documents that a nice!nano's courtyard and body
disagree in both directions (body wins along the module's length by
1.010 mm per end, courtyard wins across its width by 0.250 mm per side),
so "size on the courtyard" is already wrong for a deck opening. For a
*wall*-clearance check specifically, the dimension that matters is the
along-edge one (does the module's west edge clear the wall?), which is
exactly the axis where the body, not the courtyard, is larger. A check
written against the courtyard alone would have reported clearance on a
board that was actually 0.335 mm short of it.

## Consequence for a case generator's own regression coverage

A case check that passes because it never modeled the offending geometry is
worse than one that fails: it reports a clean bill of health right up until
the case is printed. Assert the check *exists* and covers the full
envelope, z_board's combo case (`case/zboard_combo_case.py`,
`case/checks_combo.py`) now checks `module envelope clears the inner wall`
per side, per grid, against `MCU_ENVELOPE_UNION`, and the assertion's own
name states what it is checking so a reviewer does not have to trust that
the right rectangle was used.
