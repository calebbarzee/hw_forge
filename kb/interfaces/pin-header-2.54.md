---
domain: interfaces/headers
tags: [pin-header, 2.54mm, 0.1in, swd, uart, i2c, ftdi, reversed-plug, mating-direction]
source: [KiCad 10 Connector_PinHeader_2.54mm.pretty (read with kicad_fpcheck.py)]
date: 2026-10-03
confidence: verified-in-cad
---

# 2.54 mm pin headers: stock footprints and conventions

Rules: `skills/hw-design/references/interfaces.md` section 9. The signal conventions
(SWD, UART, I2C) are not standards.

## Stock footprints (verified-in-cad)

`Connector_PinHeader_2.54mm.pretty/`. Pad 1 is a 1.7 mm square, the others 1.7 mm round,
drill 1.0 mm, pitch 2.54 mm, numbered along +y from the origin.

| Footprint | Pads | Outer span | packages.json key |
|---|---|---|---|
| `PinHeader_1x02_P2.54mm_Vertical` | 2 | 4.24 x 1.70 mm | `PinHeader-1x02-2.54` |
| `PinHeader_1x03_P2.54mm_Vertical` | 3 | 6.78 x 1.70 mm | `PinHeader-1x03-2.54` |
| `PinHeader_1x04_P2.54mm_Vertical` | 4 | 9.32 x 1.70 mm | `PinHeader-1x04-2.54` |
| `PinHeader_1x05_P2.54mm_Vertical` | 5 | 11.86 x 1.70 mm | `PinHeader-1x05-2.54` |
| `PinHeader_1x06_P2.54mm_Vertical` | 6 | 14.40 x 1.70 mm | `PinHeader-1x06-2.54` |

The `_Horizontal` footprints (6 mm pin length, per their `descr`) have the same pads and
share the key. The `_Vertical_SMD_Pin1Left` and `_Pin1Right` footprints have 2.51 x 1.0
mm SMD pads staggered each side (1x03: outer span 6.08 x 5.82 mm) and the keys
`PinHeader-SMD-1x0<n>-2.54`.

## mating_direction

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| `_Vertical` | `+z` | Straight pins out of the component face |
| `_Horizontal` | `+x` | Fab outline x -0.32 to +10.04 mm, pads at x = 0: the long pin runs to +x. verified-in-cad |
| `_Vertical_SMD_*` | `+z` | Straight pins |

## Mated plug envelope and panel opening

A female socket housing on a ribbon or jumper cable is about 2.54 mm wide per pin and 8
to 9 mm tall (needs-verification: no named drawing read). For a horizontal header the
plug lies along +x: reserve the pin length plus the housing. A panel opening is rarely
used; a debug header is usually reached with the case open.

## Conventions (needs-verification)

- SWD: 4 pin (3V3 or VTref, SWDIO, SWCLK, GND), 5 pin (adds nRESET). The order differs
  between programmers. Silkscreen the pin names.
- UART, 6 pin FTDI cable: GND, CTS, VCC, TXD, RXD, RTS or DTR. The cable's TXD goes to the
  target's RXD.
- I2C: GND, VCC, SDA, SCL, order varies. Prefer the Qwiic order (`qwiic-stemma-qt.md`).

## Traps

- Unkeyed: a plug can go on reversed or offset by one pin, driving a rail into a signal.
  Put GND on both ends or use a shrouded keyed header.
- Pad 1 is square. Silkscreen pin 1 even so, because the square is hard to see on a
  populated board.

## What a research pass must confirm

1. Pin size and rating from a named header datasheet. 2. Programmer pin orders.
