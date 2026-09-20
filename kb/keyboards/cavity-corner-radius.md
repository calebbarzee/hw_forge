---
domain: keyboards/enclosure
tags: [cavity-corner-radius, pcb-clear, fillet, tangency, rounded-pcb, square-pcb, build123d, case-verify, locked-formula]
source: z_board combo case rebuild, 2026-09-20 (case/zboard_combo_case.py cavity_corner_radius(), checks_combo.py, 242/242 pass; .tmp/analysis_case_thin_fit_2026-09-20.md); z_board legacy case/zboard_case.py (square-PCB case, near-zero margin at r=1.02)
date: 2026-09-20
confidence: verified-in-cad
---

# Cavity interior corner radius: two locked formulas, by PCB corner shape

The inside corner of a printed case's PCB cavity can be rounded for print
strength, but only up to a radius the PCB's own corner and the air gap
around it can support. Which formula applies depends on whether the PCB
itself has square or rounded corners.

## Square-PCB corners: a tangency ceiling exists

A rounded cavity corner and a square PCB corner are tangent to a circle of
radius `r` only up to a maximum radius set by the air gap `g` (`pcb_clear`):

```
r_max = g * (2 + sqrt(2)) = 3.414 * g
```

Past `r_max` the rounded cavity wall would have to clip the PCB's own square
corner to stay tangent, the corner physically cannot fit. Numbers:

| g (mm) | r_max (mm) |
|---|---|
| 0.30 | 1.024 |
| 0.40 | 1.366 |
| 0.50 | 1.707 |
| 0.60 | 2.049 |
| 0.80 | 2.731 |

z_board's older single-hand case (`case/zboard_case.py`, square-Edge.Cuts
board) runs at `g = 0.30`, `r_max = 1.024`, and locks the interior corner
radius at **1.02 mm**, inside the ceiling by 0.004 mm, effectively zero
margin. `verify()` (now `checks()`) asserts this every run so a future
`pcb_clear` change cannot silently push it over. In practice, size for
margin, not the ceiling: a `pcb_clear` bumped to 0.40–0.50 mm buys real
headroom (1.37–1.71 mm radius) for the same print-strength benefit.

## Rounded-PCB corners: no ceiling, just add the gap

When the PCB's own Edge.Cuts corners are already rounded (radius `pcb_r`),
tangency is automatic for any `pcb_r`: the cavity corner radius is simply

```
cavity_r = pcb_r + g   (no ceiling)
```

z_board's combo board (`kicad/combo/zboard_combo.kicad_pcb`, re-spun
2026-09-20 with `EDGE_CORNER_R = 3.0`) uses this rule:
`pcb_r = 3.00`, `pcb_clear = 0.60` → `cavity_r = 3.60`, asserted in
`case/checks_combo.py` (`corner radius == locked formula = 3.6000`,
`rounded-PCB formula: cavity r = PCB r + pcb_clear = 3.6000`).

## Both formulas live in one function

`case/zboard_combo_case.py`'s `cavity_corner_radius(pcb_corner_r, pcb_clear)`
implements both branches (`if pcb_corner_r > 0: return pcb_corner_r +
pcb_clear; else: return pcb_clear * (2 + sqrt(2)) - 0.2`, the square-PCB
branch subtracts a 0.2 mm margin rather than using the bare ceiling, unlike
the legacy `zboard_case.py`'s hand-picked 1.02 mm). `pcb_corner_r` is read
live from the board's own Edge.Cuts arcs via `kicad_geom.py`, not assumed,
so the same function correctly serves a square-cornered sibling board and a
rounded one without a parameter flag.

**Takeaway for a new case generator:** round a PCB's own corners before
rounding the cavity around it. The rounded-PCB rule has no ceiling and no
near-zero-margin trap; the square-PCB rule always does, and the trap gets
worse as `pcb_clear` shrinks, exactly the direction a thinner case pushes.
