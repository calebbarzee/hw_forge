---
domain: keyboards/enclosure
tags: [live-geometry, kicad_geom, hand-transcribed, parse-and-compare, drift, case-verify, regression]
source: z_board combo case rebuild, 2026-09-20 (.tmp/analysis_case_thin_fit_2026-09-20.md "combo geometry vs case hardcode"; case/zboard_combo_case.py; case/README.md)
date: 2026-09-20
confidence: verified-in-cad
---

# A case generator must read board geometry live, with a parse-and-compare check

A case generator that hand-transcribes a board's component positions into
python constants (`MCU_C = (2.975, 59.5)`, and so on) is a copy that can go
stale the moment the board changes. Nothing about the case build fails when
it does: the numbers still compute, the shells still export as valid
solids, and every check written against those same stale constants still
passes, because the check and the constant share the same wrong source.

## Measured drift

z_board's older single-hand case (`case/zboard_case.py`) hardcoded
component positions transcribed from the halves' board. When the combo
board's own MCU corridor was re-spun, the two diverged silently:

| part | case hardcode | combo board (parsed) | dx | dy |
|---|---|---|---|---|
| MCU1 | (2.975, 59.5) | (2.34, 59.5) grid A / (2.34, 62.04) grid B | −0.635 | 0 / +2.54 |
| SW_PWR | (−10.725, 59.5) | (−10.8, 60.9) | −0.075 | +1.4 |
| SW_RST | (21.475, 59.5) | (20.5, 53.0) | −0.975 | −6.5 |
| J1 | (24.0, 52.5) | (22.0, 68.6) | −2.0 | **+16.1** |

The J1 drift alone was 16.1 mm in y, large enough that it silently broke a
downstream dependent calculation (the battery-bay notch logic and
bay-overlap checks, both written against the stale J1 position, were 16.1 mm
short of where the connector actually was). None of this showed up as a
failing check, because the check and the hardcode agreed with each other;
they were both wrong about the same thing in the same way.

## The fix: read from the board file, every generation

z_board's combo case (`case/zboard_combo_case.py`) reads every board-derived
number, outline, corner radius, the six M2 mounting holes, the MCU
header's two grids, `SW_PWR`/`SW_RST`/`J1` positions and rotations, out of
`kicad/combo/zboard_combo.kicad_pcb` at generation time, via
`scripts/kicad_geom.py` (plus lower-level s-expression primitives for the
module envelope and a from-scratch coordinate-frame proof). Nothing
board-shaped is a python constant copied by hand. Only component
*heights*, z, above or below the board plane, stay as documented python
constants, because a 2D `.kicad_pcb` file has no z-axis information to read.

## The check this needs is not "does it compute a number"

A live read still needs its own assertion, because a parsing bug or a
misidentified reference designator would silently produce a wrong number
the same way a stale hardcode does, the failure mode moves, it does not
disappear. The check that actually catches drift is a comparison against
the board's own reported geometry (`kicad_geom.py`'s own output, or a
`--json` field), with the expected value asserted by name (`SW_RST
poke-hole x == parsed SW_RST footprint x`), not merely "the case exported
without error." z_board's `case/checks_combo.py` (242 checks) asserts every
board-derived opening's position this way.

## Takeaway for a new case generator

Treat "read live from the board" as the default, not an optimization to add
once a mismatch is found. The failure this prevents does not announce
itself: every generation, every export, and every check that shares the
same stale source will keep passing, right up until someone measures the
printed part against the real board.
