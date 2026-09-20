---
domain: keyboards/enclosure
tags: [usb-c, port-opening, overmold, plug-recess, bottom-open-notch, closed-window, build123d, case-verify]
source: z_board combo case rebuild, 2026-09-20 (case/zboard_combo_case.py USB notch code, case/README.md "Openings"; runs 3 and 4 of the combo case report, .tmp/report_combo_case_2026-09-20.md)
date: 2026-09-20
confidence: verified-in-cad
---

# USB-C port openings in a printed case: recess past ~0.5 mm forces an open notch

A USB-C receptacle's own shell is not the only thing a case opening has to
clear. A mated plug carries a molded **overmold** around its own shell,
the plastic housing the user's hand grips, and that overmold is
significantly wider and taller than the bare connector shell it wraps. A
closed window sized to the shell alone works only if the wall in front of
it is thin enough for the overmold to simply butt against the case's outer
face; past a small recess, the overmold cannot enter the opening at all and
the plug cannot mate.

## The overmold spec, and the sizing rule that follows

USB Type-C's own plug-mechanical spec gives a maximum overmold envelope of
**12.35 × 6.50 mm**. Any captured opening, a window with real wall
thickness in front of the receptacle, not flush with it, has to admit
this envelope, not just the bare shell (typically ~8.9 mm across for a
receptacle body). z_board rounds the spec max up to 12.50 mm and adds
0.50 mm clearance per side for the width formula:

```
opening width = (housing-axis span between grids, if more than one) + 12.50 + 2*0.50
```

On the combo board (two MCU hole grids 2.54 mm apart, both landing USB-C
at the same board x) this is `2.54 + 12.50 + 1.00 = 16.04 mm`.

## Measured: a closed window with a 2.625 mm recess is already too much

z_board's combo case went through this the hard way. Run 3 of the case
build tried a **closed, full-thickness window** through the wall, the
receptacle shell was clear, but the check that actually mattered (does the
overmold, not the shell, fit through the opening) failed: at a 2.625 mm
recess from the wall's outer face to the receptacle shell, the plug's own
overmold could not physically reach the shell to mate. The run passed
230/230 numeric geometry checks and was still rejected on this basis, the
checks that existed were the wrong checks until this one was added.

**Rule of thumb from this case:** past roughly 0.5 mm of true recess (wall
material between the case's outer face and the plug's mating point), a
closed window sized to the overmold envelope stops being sufficient on its
own merits, because the overmold (not the shell) is what has to travel
through the opening, and it is generally shorter than the shell's own
insertion depth.

## The fix: an opening that is open, not just wide

The adopted shape (combo case run 4, 242/242 checks) is a **U-shaped notch
open through the bottom face** of the shell, not a captured window:

- width 16.04 mm (formula above), vertical edges filleted r = 1.2 mm for
  print strength;
- full wall thickness kept on the three *closed* sides (top and both
  verticals), no local thinning;
- open straight down through the floor, so a plug's overmold slides in from
  below rather than needing to pass through a bounded hole;
- top edge set by the receptacle shell's own axis plus half the overmold
  height plus clearance: `shell_axis_z + 3.25 + 0.50`, which landed at
  z −1.65 on this board, only 0.05 mm below the PCB's own underside
  (z −1.60), asserted and reported as a tight, worth-a-look figure, not
  silently accepted.

With the opening bottom-open, "recess" no longer has a captured value to
bound (the overmold occupies the opening on its way in, rather than passing
through a fixed hole first). z_board reports the equivalent distance,
outer wall face to the mated shell, as **informational only**
(`case/README.md`, "Plug recess to the shell face: 2.625 mm"), explicitly
not gated, and documents why the earlier gate no longer applies.

## When to reach for this shape

A bottom-open notch is the right answer specifically when the receptacle
sits close enough to the shell's structural floor that a captured window
cannot also give the overmold room, on z_board this followed from putting
the MCU module on the back face at a low standoff, which drops the USB
port close to the case's own floor plane. A receptacle mounted higher in
the wall, with real material below it, may still take a closed window; use
the ≥0.5 mm-recess figure above as the trigger to check, not a hard rule
that a closed window never works.
