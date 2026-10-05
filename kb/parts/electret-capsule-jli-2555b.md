---
domain: parts/electret
tags: [electret, microphone-capsule, jli-2555bxz3-gp, tsb-2555bxz3-gp, transound, 26mm, vent-holes, rear-clamp, off-board, case-geometry]
source: [hypercardiod_mic lib/research/offboard-connectors.md (conflict C1 and the capsule table, 2026-10-03), JLI TSB-2555BXZ3-GP datasheet p2 (https://www.jlielectronics.com/content/TSB-2555BXZ3-GP.pdf, read as a 400 dpi page image)]
date: 2026-10-03
confidence: researched
---

# JLI-2555BXZ3-GP electret capsule: flat front, 11.0 mm overall, rear stays open

One manufacturer drawing (JLI datasheet p2; the JLI-2555BXZ3-GP PDF carries the same
drawing). Printed values are "dimensioned". Values measured off the page image are
"scaled" and carry plus or minus 0.15 to 0.2 mm at 400 dpi, calibrated against the
dimensioned 26 mm outside diameter.

## Names

| Name | Meaning |
|---|---|
| JLI-2555BXZ3-GP | JLI's sales number. Datasheet title is TSB-2555BXZ3-GP |
| TSB-2555B | prefix used in a design brief: the same family. Full Transound suffix is BXZ3-GP |
| TSB-2555A | different part, no FET. Do not substitute |

Capsule made by Transound, sold by JLI Electronics. It ships without leads. 1.0 to 10 V,
0.5 mA, 2.2 kohm output (JLI product page and datasheet). JLI listed it in stock at
12.95 USD on 2026-10-03. No LCSC listing was found (scope: JLCPCB parts search and
LCSC detail by model, 2026-10-03).

## Conflict C1: the card a project may have copied is wrong in two places

An earlier project reading said the capsule is "11.0 mm tall including its domed mesh
cap" with "a ring of holes on the rear face outer annulus". The drawing says:

| Claim | Drawing |
|---|---|
| Domed mesh cap | Flat front face with a mesh-filled round opening about 16.5 mm across (band 16 to 17, scaled). No dome |
| 11.0 mm overall | 11.0 plus or minus 0.2, dimensioned. Measured from the flat front face to the top of the rear centre stud and lug. Can height is 7.0 plus or minus 0.2 |
| Vent holes in an outer annulus | 16 holes in rings from radius 4.9 to 12.1 mm. Only 4 sit in the outer annulus |

Both readings are of one tier-1 drawing, so this is a mechanical conflict banded rather
than decided. The rear stud and lug stand 4.0 mm above the can's rear face (11.0 minus
7.0, band 3.6 to 4.4, derived). A case that reads 11.0 mm as the can height leaves no
room for them.

## Dimensions

| Item | Value | Basis |
|---|---|---|
| OD | 26 with minus 0.05 (25.95 to 26.00) mm | dimensioned |
| Can height | 7.0 plus or minus 0.2 mm | dimensioned |
| Overall height | 11.0 plus or minus 0.2 mm | dimensioned |
| Term.1 (+) | centre stud, hex about 4.8 mm across corners (4.6 to 5.0) | scaled |
| Term.2 (-) | the can, through 3 rim solder pins at radius about 12.5 mm (12.3 to 12.7), at about 128, 28 and minus 119 degrees (rear view, +x right, +y up) | scaled |
| Rim pin height | about 9 mm above the front face (8.8 to 9.4) | scaled |
| Rear rim step | circle at radius 10.3 mm (10.1 to 10.5) | scaled |

## Vent geometry (rear face)

| Item | Value | Basis |
|---|---|---|
| Holes | 16: 4 at radius 5.5 to 5.8, 2 at 6.6, 6 at 9.1, 4 at 11.45 | scaled, each radius plus or minus 0.15 mm |
| Hole diameter | 1.1 mm (outer four 1.25) | scaled, band 1.0 to 1.3 |
| Vent field, inner edge | radius 4.9 mm (4.8 to 5.0) | scaled: 5.5 minus half a hole |
| Vent field, outer edge | radius 12.1 mm (12.0 to 12.3) | scaled: 11.45 plus half a hole |
| Solid rim beyond the field | radius 12.1 to 13.0 mm, 0.9 mm wide | scaled |

12 of the 16 holes sit inside radius 9.2 mm. The vent field is not an outer annulus.

## Consequences for a case

- Keep the rear face open from radius 4.8 to 12.2 mm. A rear pad, clamp ring, or foam disc
  covering that band blocks the vents.
- Retain the capsule by its OD, its front rim, or a shock ring around the OD. Do not clamp
  the rear: the only solid rim is 0.9 mm wide, and whether the can accepts a clamp at all
  is untested (needs-verification on a physical unit).
- Reserve about 4 mm behind the can's rear face for the stud and lug, plus wire bend room.
- Take the mesh opening (about 16.5 mm across) as the acoustic window in the front wall.

## 3D model

None vendored. Scope of the negative: `find` under `~/1_projects/dev` (maxdepth 6) and
the KiCad 10.0.5 `SharedSupport` tree for `*2555*`, `*electret*`, `*capsule*`; the JLI
product page and datasheet link; web searches "TSB-2555B capsule STEP 3D model",
"TSB-2555BXZ3 3D model", "JLI-2555BXZ3-GP"; GitHub code search "TSB-2555". Hits were
hobbyist holder meshes, not the capsule. No Transound manufacturer site was found, and
the search engine was rate-limited, so this negative is weaker than the others. Build
the capsule from the tables above.

## What a research pass must confirm

1. The rear stud height and lug position on a physical unit.
2. Whether the can accepts a clamp.
3. A Transound drawing, to cross-check the scaled values against a second source.
