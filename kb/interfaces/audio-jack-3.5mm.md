---
domain: interfaces/audio
tags: [3.5mm, trs, trrs, headphone, ctia, omtp, cui-sj1-3535ng, pj320e, mating-direction, switch-contacts]
source: [KiCad 10 Connector_Audio.pretty (read)]
date: 2026-10-03
confidence: verified-in-cad
---

# 3.5 mm jacks: stock footprints, nose direction, and the unnamed pad

Rules: `skills/hw-design/references/interfaces.md` section 14.

## Stock footprints (verified-in-cad)

| Footprint (`Connector_Audio.pretty`) | Pads | Geometry | packages.json key |
|---|---|---|---|
| `Jack_3.5mm_CUI_SJ1-3535NG_Horizontal` | `S` (0, 0), `T` (2.0, 2.4), `TN` (0, 11.6), `RN` (0, 6.1), `R` (2.0, 7.9) | Oval pads 2.8 x 1.8 mm, drill 2 x 1 mm slot. Outer span 13.4 x 4.8 mm. Fab 8.2 x 18.0 mm | `Jack-3.5mm-CUI-SJ1-3535NG` |
| `Jack_3.5mm_PJ320E_Horizontal` | `T` (0, 0), `R1` (0, -4.0), `R2` (0, -7.0), `S` (4.5, 1.5), and one unnamed plated pad at (5.5, -7.0) | Oval pads 2.0 x 1.4 mm, 90 degree rotated, drill 1.2 x 0.6 mm slot; two 1.2 mm non-plated posts. Outer span 10.5 x 6.9 mm. Fab 7.1 x 14.0 mm | `Jack-3.5mm-PJ320E` |

## mating_direction

`-y` for both. The fab outline of each steps to a narrow nose at the negative-y end: SJ1
nose 6.0 mm wide, 4.0 mm deep (y -5.2 to -1.2); PJ320E nose 5.6 mm wide, 2.8 mm deep (y
-12.0 to -9.2). The nose is the part that passes through the panel. verified-in-cad.

## Mated plug envelope and panel opening

Plug barrel diameter 3.5 mm. A plug's overmold or strain relief is commonly 6 to 8 mm
(needs-verification). A flush panel opening for the nose is the nose width plus clearance
(SJ1: 6.0 + 0.4 = 6.4 mm, derived). A recessed jack needs the plug overmold to fit inside
the opening.

## Wiring

- CTIA: tip left, ring 1 right, ring 2 ground, sleeve microphone. OMTP: ring 2
  microphone, sleeve ground. They are not compatible (needs-verification: general
  knowledge). The SJ1 is a 3 conductor TRS with switch contacts, not a TRRS.
- The PJ320E lists `T`, `R1`, `R2`, `S` as a TRRS. The assignment of its rings to
  CTIA or OMTP must come from the part drawing (needs-verification).

## Traps

- The PJ320E stock footprint has one plated pad with an empty number at (5.5, -7.0). It
  carries no net. Name it per the drawing or document it as a no-connect.
- The `TN` and `RN` pads are the switch contacts that open on insertion. Floating them is
  fine. Using them needs the polarity from the drawing.
- Retention is the panel bushing, not the pins.

## What a research pass must confirm

1. CTIA or OMTP order for the PJ320E. 2. The unnamed pad's function. 3. Panel bushing size.
