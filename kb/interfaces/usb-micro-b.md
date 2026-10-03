---
domain: interfaces/usb
tags: [usb, micro-b, receptacle, 5-pin, id-pin, molex-105017, amphenol-10118194, mating-direction]
source: [KiCad 10 Connector_USB.pretty (read), Micro-USB spec Rev 1.01 (located, not loaded)]
date: 2026-10-03
confidence: needs-verification
---

# USB 2.0 Micro-B receptacle: stock footprints and geometry

Rules: `skills/hw-design/references/interfaces.md` section 2. Pinout: 1 VBUS, 2 D-, 3 D+,
4 ID, 5 GND, shell to GND or chassis.

## Stock footprints (verified-in-cad)

| Footprint file (`Connector_USB.pretty`) | Signal pads | Outer pad span | Shield |
|---|---|---|---|
| `USB_Micro-B_Molex-105017-0001.kicad_mod` | 5 pads 0.40 x 1.35 mm at x = -1.3 to +1.3 mm, 0.65 mm pitch, y = -1.4625 | 8.20 x 4.375 mm | 2 through-hole oval, 2 through-hole round (1.45 mm, 0.85 mm drill), 4 SMD |
| `USB_Micro-B_Amphenol_10118194-0001LF_Horizontal.kicad_mod` | 5 pads 0.40 x 1.35 mm, 0.65 mm pitch, y = -1.4 | 7.89 x 4.15 mm | through-hole ovals and SMD pads |

No packages.json entry (not in the connector set requested); the check reports SKIP.

## mating_direction

`+y` for both. The Molex file has `PCB Edge` text on `Dwgs.User` at y = +2.6875 (fab
outline to y = +3.39). The Amphenol file draws a `Dwgs.User` line `PCB Edge` at y = +2.75.
verified-in-cad.

## Mated plug envelope and panel opening

| Item | Value | Status |
|---|---|---|
| Receptacle opening | about 6.85 x 1.80 mm | needs-verification (Micro-USB spec) |
| Plug overmold | about 10.6 x 8.5 mm maximum | needs-verification |
| Cycles | 10 000 | needs-verification |

Panel opening: until the overmold is confirmed, size a closed window for 10.6 x 8.5 mm
plus 0.5 mm per side (11.6 x 9.5 mm, derived from the unconfirmed overmold) or use an
open notch.

## Traps

- The shell has an asymmetric profile: the plug cannot be inserted upside down.
- Signal pads are 0.65 mm pitch and fail under side load. Solder every shield tab.
- A device-only product leaves ID unconnected.

## What a research pass must confirm

1. Opening and overmold dimensions, and cycle rating, from the Micro-USB spec Rev 1.01.
2. The Amphenol and Molex vendor drawings against the footprints.
