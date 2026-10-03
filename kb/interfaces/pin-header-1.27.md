---
domain: interfaces/headers
tags: [pin-header, 1.27mm, 0.05in, cortex-debug, swd, 2x05, 10-pin, nreset, vtref, mating-direction]
source: [KiCad 10 Connector_PinHeader_1.27mm.pretty (read), Microchip Cortex Debug Connector (10-pin) page, myelin.nz Serial Wire Debug article (read)]
date: 2026-10-03
confidence: verified-in-cad
---

# 1.27 mm headers and the Cortex debug connector

Rules: `skills/hw-design/references/interfaces.md` section 10.

## Stock footprints (verified-in-cad)

`Connector_PinHeader_1.27mm.pretty/`. Pad 1 square 1.0 mm, others round 1.0 mm, drill 0.65
mm, pitch 1.27 mm.

| Footprint | Pads | Outer span | packages.json key |
|---|---|---|---|
| `PinHeader_1x04_P1.27mm_Vertical` (and `_Horizontal`, 4.0 mm pin) | 4 | 4.81 x 1.0 mm | `PinHeader-1x04-1.27` |
| `PinHeader_1x05_P1.27mm_Vertical` | 5 | 6.08 x 1.0 mm | `PinHeader-1x05-1.27` |
| `PinHeader_1x06_P1.27mm_Vertical` | 6 | 7.35 x 1.0 mm | `PinHeader-1x06-1.27` |
| `PinHeader_2x05_P1.27mm_Vertical` | 10 | 6.08 x 2.27 mm | `PinHeader-2x05-1.27` |
| `PinHeader_2x05_P1.27mm_Vertical_SMD` | 10 | 6.30 x 5.82 mm (2.4 x 0.74 mm pads) | `PinHeader-2x05-1.27-SMD` |

Numbering of the 2 x 5 footprint runs across the rows: pad 2 is 1.27 mm from pad 1 in
x, pad 3 is 1.27 mm from pad 1 in y, pad 10 at (1.27, 5.08) mm. That is the IDC convention
the Arm connector uses.

## mating_direction

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| `_Vertical` and `_Vertical_SMD` | `+z` | Straight pins |
| `1x0n ..._Horizontal` | `+x` | Fab outline x -0.20 to +5.50 mm with pads at x = 0. verified-in-cad |

## Cortex debug 10-pin pinout (secondary sources agree)

1 VTref, 2 SWDIO/TMS, 3 GND, 4 SWCLK/TCK, 5 GND, 6 SWO/TDO, 7 KEY (no pin), 8 NC/TDI, 9
GNDDetect, 10 nRESET. nRESET needs a 10 to 100 kohm pullup to VDD. The myelin.nz article
recommends a 10 to 100 kohm pulldown on SWCLK and no resistor on SWDIO (one author's
advice, needs-verification against the Arm specification).

## Mated plug envelope and panel opening

A shrouded 2 x 5 box header with a keyed notch is about 6.35 x 5.5 mm in the SMD
footprint's fab outline (3.41 x 6.35 mm through hole). The ribbon plug adds height and
a cable bend. Debug headers are normally reached with the case open or via a Tag-Connect
pad set (`Connector.pretty/Tag-Connect_TC2050-IDC-*`, no header part). (Plug envelope:
needs-verification, no named drawing read.)

## Traps

- Footprint pin 1 and the keyed shroud's notch must agree. Check the part's drawing.
- `PinHeader_2x05_P1.27mm_Vertical` is a prefix of the `_Vertical_SMD` name. Declare the
  package in `design.py` `PACKAGES`; the longer alias in packages.json wins otherwise.
- VTref senses the target rail. Wiring it to a different rail makes the probe drive the
  wrong level.

## What a research pass must confirm

1. The pin assignment and pulls in the Arm Debug Interface Architecture Specification.
2. The mating plug envelope of a named shrouded header.
