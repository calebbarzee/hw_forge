---
domain: interfaces/usb
tags: [usb-c, type-c, receptacle, cc, rd, rp, usb4105, 16-pin, 24-pin, mating-direction, overmold, panel-opening]
source: [GCT usb4105.pdf rev B4 2019-10-04 (read), USB Type-C spec R1.0 chapter 4 excerpt (read), KiCad 10 Connector_USB.pretty (read with kicad_fpcheck.py), kb/keyboards/usb-c-port-opening.md]
date: 2026-10-03
confidence: needs-verification
---

# USB-C receptacle: stock footprints, mating direction, and the plug envelope

Rules and pinout: `skills/hw-design/references/interfaces.md` section 1. This card holds
the numbers for the named stock footprints. Where the case opening was measured on a
real build, see `kb/keyboards/usb-c-port-opening.md`.

## Stock footprints (verified-in-cad)

All in `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Connector_USB.pretty/`,
read with `python3 scripts/kicad_fpcheck.py <file> -v`.

| Footprint file | Pads counted | Outer pad span (long x short) | Signal pad | packages.json key |
|---|---|---|---|---|
| `USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal.kicad_mod` | 20 (16 contact, 4 shield) | 9.64 x 6.23 mm | 0.30 x 1.15 mm, 0.50 mm pitch; power pads 0.60 x 1.15 mm | `USB-C-16P-GCT-USB4105` |
| `USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod` | 20 | 9.64 x 6.62 mm | 0.30 x 1.45 mm; power pads 0.60 x 1.45 mm | `USB-C-16P-HRO-TYPE-C-31-M-12` |
| `USB_C_Receptacle_Amphenol_12401610E4-2A.kicad_mod` | 28 (24 contact, 4 shield) | 9.78 x 8.91 mm | 0.30 x 0.70 mm | `USB-C-24P-Amphenol-12401610E4` |

GCT USB4105 pad coordinates (footprint-local, mm): row at y = -3.68. Power and ground:
A1 and B12 at x = -3.2, A4 and B9 at -2.4, A9 and B4 at +2.4, A12 and B1 at +3.2.
Signal: B8 -1.75, A5 -1.25, B7 -0.75, A6 -0.25, A7 +0.25, B6 +0.75, A8 +1.25, B5 +1.75.
Shield: four oval through-hole pads at x = +-4.32, y = -3.105 (1.0 x 2.1 mm) and y = +1.075
(1.0 x 1.8 mm). Two 0.65 mm non-plated locating holes at x = +-2.89, y = -2.605.
Courtyard x -5.32 to 5.32, y -4.76 to 4.18. Fab outline 8.94 x 7.35 mm.

Do not treat one vendor's footprint as another's. The HRO and GCT 16-pin parts differ by
0.30 mm in pad length. The GCT USB4110 footprint (a different shield layout, large SMD
shield pads, span 12.4 x 6.08 mm) has no packages.json entry and reports SKIP.

## mating_direction

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| GCT USB4105 | `+y` | The file's `Dwgs.User` line at y = +3.675 is labelled `PCB Edge`. Fab outline spans y -3.675 to +3.675 with contact tails at y = -3.68. The shell front is flush with the edge line. verified-in-cad |
| HRO TYPE-C-31-M-12 | `+y` | Same body and tail layout, no edge marker. needs-verification |
| Amphenol 12401610E4-2A | `+y` | Contact pads at y = -5.02 and -3.32, fab y -5.22 to +5.23, no edge marker. needs-verification |

For a board edge on the `+y` side, a part placed at rotation 0 with its front flush is
correct. The courtyard extends 0.5 mm past the edge line (y = +4.18 against +3.675).

## Mated plug envelope

| Item | Value | Source |
|---|---|---|
| Plug overmold maximum | 12.35 x 6.50 mm | `kb/keyboards/usb-c-port-opening.md`, citing the Type-C plug limit. 6.5 mm height also on the GCT drawing |
| Receptacle opening | 8.34 +0.06/-0.02 x 2.56 +-0.04 mm | GCT drawing (read) |
| Receptacle shell length | 6.20 +-0.02 mm, reference only | Type-C ECN receptacle shell length (read) |
| Receptacle body | 8.94 x 7.35 x 3.31 mm | GCT drawing (read) |
| Mating force | 5 to 20 N; unmating 6 to 20 N after test; 20 000 cycles | GCT drawing (read) |

## Panel opening

- Flush front, wall thickness at most about 0.5 mm: shell opening 8.34 x 2.56 mm plus
  0.2 mm per side is 8.74 x 2.96 mm (derived). The overmold butts against the wall.
- Captured window deeper than about 0.5 mm: 12.35 x 6.50 mm plus 0.5 mm per side is
  13.35 x 7.50 mm (derived), and past that recess consider a notch open to a board
  face (`kb/keyboards/usb-c-port-opening.md` measured a 2.625 mm recess that blocked
  mating).

## Traps

- CC1 and CC2 each need their own 5.1 kohm pulldown on a device. A Type-A to Type-C cable
  has Rp built into its plug, so it powers a device with no Rd. A Type-C to Type-C
  charger will not. Bench-testing only with the A-to-C cable hides the defect.
- A 16-pin part has two D+ pads and two D- pads (A6 and B6, A7 and B7). Join them.
- The shield pads carry the plug's lateral load. Solder all four.

## Open items (what a research pass must confirm)

1. `mating_direction` for the HRO and Amphenol footprints, from a vendor mated view.
2. Plug shell 8.25 x 2.40 mm and the overmold limit against Type-C chapter 3 (the
   excerpt read contained chapter 4 only).
3. SuperSpeed pin numbers on the 24-pin part.
