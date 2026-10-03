---
domain: interfaces/audio
tags: [xlr, trs, balanced-audio, neutrik, nc3fah, nc3mah, phantom-power, p48, pin-1, shield, mating-direction]
source: [KiCad 10 Connector_Audio.pretty (read), Neutrik NC3FAH product page (read, text only), P48 via Wikipedia and sound-au.com]
date: 2026-10-03
confidence: needs-verification
---

# XLR and balanced TRS: stock footprints, panel line, phantom power

Rules: `skills/hw-design/references/interfaces.md` section 17.

## Stock footprints (verified-in-cad)

| Footprint (`Connector_Audio.pretty`) | Pads | Evidence for mating direction |
|---|---|---|
| `Jack_XLR_Neutrik_NC3FAH_Horizontal` (female, no shell contact) | pins 1 and 2: 3.4 mm pads, drill 1.6 mm, at (0, 0) and (-0.635, 7.62); pin 3: 2.9 mm, drill 1.2 mm, at (-4.45, 3.81); two 1.6 mm non-plated holes. Outer span 7.6 x 11.0 mm | `+x`: `Dwgs.User` line at x = 12.7 mm, fab outline steps out to x = 15.4 mm beyond it |
| `Jack_XLR_Neutrik_NC3MAH_Horizontal` (male, separate ground contact `G` to the mating shell) | pins 1, 2 at x = 0 and 7.62, y = 0, pin 3 and `G` at x = 3.81 | `+y`: `Dwgs.User` line at y = 17.78 mm |
| `Jack_XLR_Neutrik_NC3FAV_Vertical` | pins 1 to 3 | `+z` (needs-verification: vertical by name) |
| `Jack_6.35mm_Neutrik_NRJ6HF_Horizontal` | `R`, `S`, `T` and switch pads, 3.0 mm round, 1.5 mm drill | needs-verification |

Neutrik NC3FAH (page text): 6 A per contact, below 50 V, insertion and withdrawal force
20 N maximum, 23 mm between centres at highest packing. The page links DXF and STEP
files for the panel cutout (not read).

## Pinout and phantom power

XLR3: pin 1 shield (ground), pin 2 hot, pin 3 cold. TRS balanced: tip hot, ring cold,
sleeve shield (needs-verification against IEC 60268-11 and -12, AES14). P48: 48 V +-4 V
through two matched 6.81 kohm resistors, return on pin 1, 10 mA maximum (secondary
sources, IEC 61938).

## Mated plug envelope and panel opening

Panel opening for the D series: about 24 mm hole with two M3 holes (needs-verification,
Neutrik drawing not read). The female latch has a release button on the shell: leave
finger access.

## Traps

- Pin 1: the male `NC3MAH` has a ground contact to the mating shell, the female
  `NC3FAH` has none. This decides whether shield reaches the chassis at the connector.
- Phantom resistors must match; blocking capacitors must be rated above 48 V.
- The panel plane is drawn on `Dwgs.User` in the footprint. Use it as the case wall
  datum.
- Keep both non-plated positioning holes.

## What a research pass must confirm

1. The D-series cutout. 2. IEC 60268 and AES14 pin assignments. 3. NC3FAV and NRJ6HF
directions.
