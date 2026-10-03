---
domain: interfaces/rf
tags: [u.fl, ufl, hirose, ipex, rf, coax, mhf, mating-cycles, mating-direction]
source: [KiCad 10 Connector_Coaxial.pretty (read); Hirose drawing URL in the footprint returned HTTP 403]
date: 2026-10-03
confidence: needs-verification
---

# U.FL receptacle: footprint and mating

Rules: `skills/hw-design/references/interfaces.md` section 13.

## Stock footprint (verified-in-cad)

`Connector_Coaxial.pretty/U.FL_Hirose_U.FL-R-SMT-1_Vertical.kicad_mod`: centre pad 1.05 x
1.0 mm at x = -1.525 mm, two ground pads 2.2 x 1.05 mm at y = +-1.475 mm, outer span 3.15
x 4.0 mm, fab 2.85 x 3.0 mm, courtyard 4.35 x 5.0 mm. Another stock footprint,
`U.FL_Molex_MCRF_73412-0110_Vertical`, was not measured.

## mating_direction

`+z` (vertical receptacle, plug pushes straight down onto the component face).

## Mated plug envelope (needs-verification)

Mated height about 2.5 mm; 50 ohm; DC to 6 GHz; about 30 mating cycles; plug cable 0.81
or 1.13 mm coax. The cable's first bend leaves the plug sideways, so reserve a keepout of
several millimetres around the receptacle in the cable direction.

## Traps

- U.FL, W.FL, MHF4, and other IPEX sizes differ by fractions of a millimetre and do not
  mate. Put the plug series in the BOM.
- Pulling the cable lifts the receptacle's pads. Clip or glue the cable.
- 30 cycles: an assembly connector, not a user connector.
- Keep the 50 ohm line starting at the centre pad with ground under it.

## What a research pass must confirm

1. The Hirose drawing: mated height, cycles, frequency.
2. The Molex MCRF footprint.
