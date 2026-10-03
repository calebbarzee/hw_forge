---
domain: interfaces/power
tags: [barrel-jack, dc-jack, 2.1mm, 2.5mm, 5.5mm, center-positive, pj-102ah, wuerth-694108106102, reverse-polarity, mating-direction]
source: [CUI PJ-102AH drawing rev A 2005-11-17 (read), KiCad 10 Connector_BarrelJack.pretty (read)]
date: 2026-10-03
confidence: needs-verification
---

# DC barrel jacks: stock footprints, size mismatch, mating direction

Rules: `skills/hw-design/references/interfaces.md` section 15.

## Stock footprints (verified-in-cad)

| Footprint (`Connector_BarrelJack.pretty`) | Pads | packages.json key |
|---|---|---|
| `BarrelJack_CUI_PJ-102AH_Horizontal` | 3 through-hole 2.6 mm, drill 1.6 mm, at (0, 0) rect, (0, 6.0), (4.7, 3.0). Outer span 8.6 x 7.3 mm. Fab 9.0 x 14.4 mm | `BarrelJack-2.1-CUI-PJ-102AH` |
| `BarrelJack_Wuerth_694108106102_2.5x5.5mm` | 4 SMD 2.0 mm at (+-5.5, +-3.075), two non-plated holes 1.8 and 1.6 mm. Outer span 13.0 x 8.15 mm. Fab 9.7 x 14.7 mm | `BarrelJack-2.5-Wuerth-694108106102` |

`BarrelJack_Horizontal` (generic) and the CUI PJ-063AH (2.0 mm ID, 24 V, 8 A per its
`descr`) have no packages.json entry.

## PJ-102AH facts (CUI drawing, read)

Body 11.0 mm wide, 9.0 mm tall, 14.4 mm long. Centre pin 2.0 mm diameter. Bore 6.5 mm. 24 V
DC, 5 A. Contact resistance 50 mohm maximum. 5 000 cycles. -25 to +85 C. Terminal 1 is
the centre pin tail.

## mating_direction

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| PJ-102AH | `+y` | Fab outline y -0.7 to +13.7 mm with a step at y = +10.2 to a 3.5 mm front section that matches the drawing's 3.5 mm dimension. verified-in-cad |
| Wuerth 694108106102 | needs-verification | No nose or edge marker in the footprint |

## Mated plug envelope and panel opening

The common supply plug is 5.5 mm outer diameter. Plug barrels on molded supplies are
often 10 to 12 mm across (needs-verification). The bore is 6.5 mm. Size the opening to
the plug the user will have, not to the bore.

## Traps

- A 2.5 mm centre pin plug does not fit the 2.0 mm pin of a 2.1 mm jack. A 2.1 mm plug in
  a 2.5 mm jack fits loosely (needs-verification).
- Polarity is center-positive by convention only. Silkscreen it.
- No reverse-polarity protection is in the part. Add it.
- Hot-plugging onto ceramic input capacitors rings above the supply voltage
  (needs-verification, `domains.md` section 2).

## What a research pass must confirm

1. The Wuerth part's direction and size. 2. Plug overmold sizes of the intended supplies.
