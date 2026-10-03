---
domain: interfaces/usb
tags: [usb, type-a, receptacle, host, molex-67643, plug-footprint-trap, mating-direction]
source: [KiCad 10 Connector_USB.pretty (read), USB 2.0 spec chapters 6 and 7 (not read)]
date: 2026-10-03
confidence: needs-verification
---

# USB Type-A receptacle: stock footprint and the plug-footprint trap

Rules: `skills/hw-design/references/interfaces.md` section 3. Pinout: 1 VBUS, 2 D-, 3 D+,
4 GND.

## Stock footprint (verified-in-cad)

`Connector_USB.pretty/USB_A_Molex_67643_Horizontal.kicad_mod`: pad 1 roundrect 1.6 x 1.5
mm, pads 2 to 4 round 1.6 mm, all with 0.95 mm drill, at x = 0, 2.5, 4.5, 7.0 mm, y = 0.
Two shield pads 3.0 mm round, 2.3 mm drill, at x = -3.07 and +10.07, y = +2.71. Outer span
16.14 x 5.01 mm. Fab outline x -3.70 to 10.70, y -2.27 to 12.99 (14.4 x 15.26 mm).

## mating_direction

`+y` (the opening is at the +12.99 mm end). needs-verification: no `PCB Edge` marker in the
file, inferred from the body lying on the +y side of the pad row.

## Trap: a "USB_A" footprint that is a plug

`Connector_USB.pretty/USB_A_CNCTech_1001-011-01101_Horizontal.kicad_mod` has the
description "USB type A Plug". It is the male end of a PCB-edge USB stick: pads at x =
-9.65, a `PCB Edge` line at x = -3.8, fab outline 21.3 mm long. Use it only to make a
board that plugs into a host. For a host port use a receptacle such as the Molex.

## Mated plug envelope and panel opening (needs-verification)

Standard-A plug shell about 12.0 x 4.5 mm; receptacle opening about 12.5 x 5.0 mm; plug
overmolds on common cables are commonly 15 to 17 mm wide. Source needed: USB 2.0
specification chapter 6.

## Host requirements (needs-verification, USB 2.0 sections 7.1.5 and 7.2.4.1)

15 kohm +-5 % pulldown on each of D+ and D-; a switched, current-limited VBUS; at least
120 uF on a downstream port.

## What a research pass must confirm

1. The mechanical figures and host electrical figures above.
2. `mating_direction` from the Molex 67643 drawing.
