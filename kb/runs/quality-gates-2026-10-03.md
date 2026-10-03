---
domain: runs/quality-gates-2026-10-03
tags: [fit-contract, mating-direction, connector, case-verify, min-wall,
       connector-openings, kicad-geom, kicad-scaffold, kicad-dru, fork-rules,
       hexpad, mic-buffer, synthetic]
source: local runs, this machine, 2026-10-03 (scripts/kicad_geom.py --contract,
  scripts/case_verify.py, scripts/kicad_scaffold.py, scripts/hw_review.py;
  build123d from a project case venv; stock kicad-cli 10.0.5 and the forked
  kicad-cli built 2026-10-03)
date: 2026-10-03
confidence: verified-in-cad
---

# Quality-gate runs, 2026-10-03

The evidence `docs/BACKLOG.md` B8 and B9 and `docs/QUALITY.md` cite. Every run
used scratch copies of the projects, never the projects themselves. A synthetic
board is a 40 x 30 mm outline with one USB-C-shaped footprint, `J1`, placed and
declared per case.

## Fit contract: connector mating faces (B8)

`kicad_geom.py BOARD --contract FIT.json --design design.py`.

| Board, declaration | Verdict | Reason printed |
|---|---|---|
| hexpad, `MCU1` (nice!nano) `-y` | PASS | out through the east edge, overhanging 0.600 mm: the 0.60 mm hexpad's case constants state |
| hexpad, `MCU1` declared `+y` | FAIL | points west, but the part sits at the east edge: the plug would enter from inboard |
| mic_buffer, `J1` and `J2`, nothing declared | FAIL x2 | undeclared mating_direction: a connector (prefix J) |
| synthetic, east edge, `-y` | PASS | overhanging 1.200 mm |
| synthetic, same part declared the other way | FAIL | sits at the east edge, plug would enter from inboard |
| synthetic, mid-board, default edge_max_mm 1.0 | FAIL | points east from 16.100 mm inboard: no board edge within 1.000 mm |
| synthetic, mid-board, edge_max_mm 100 | PASS | out through the east edge, inboard 16.100 mm |
| synthetic, `+z` and `-z` | INFO | mates through the top or bottom face |
| synthetic, `"up"` | FAIL | not one of +x, +y, +z, -x, -y, -z |

Recorded earlier the same day, before the outboard test was reworked to judge
the edge the direction crosses, and not re-run since: z_board combo's nice!nano,
declared from its footprint's description, sits 0.625 mm inboard of the west
edge; the contract passes it at 1.0 mm and `kicad_ifcheck.py` fails it against
USB-C's 0.5 mm (`UC-ALL-05`). The rework does not change either verdict, since
both depend only on the crossed edge and the inset.

## Case suite: openings and wall floor (B8 case side, B9)

`case_verify.py checks.py --contract FIT.json` on the synthetic two-piece box,
2.0 mm walls, three variants:

| Variant | Result |
|---|---|
| good: opening in the east wall | 9 of 9 pass; thinnest walls 1.010 mm (top), 2.000 mm (bottom) |
| west: opening cut in the west wall | `J1 east opening ... meets top (43.309 mm^3)`, 1 FAIL |
| thin: one wall section at 0.35 mm | `thinnest wall = 0.350mm`, 2 FAIL (both shells) |

`min_wall` on a 100 x 20 x 10 mm box with a 1 mm slot leaving a 0.2 mm floor
reported 0.200 mm at `spacing=0.5` (11332 samples, 5.2 s) and at the default
2.0 mm (2006 samples, 0.8 s).

## Rule file regeneration (kicad_scaffold.py)

On a scratch project: a PARAM edited from 0.45 to 0.50 mm and an appended user
line survived two regenerations.  `--fork-rules` under the forked kicad-cli
inserted the block between `# hw_forge fork rules begin` and `# hw_forge fork
rules end`; a second run left the file byte-identical.  A regeneration under
stock kicad-cli removed the block with a WARNING and kept both user lines and
the edited PARAM.  `--reinstall-rules` restored the baseline.
