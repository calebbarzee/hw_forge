---
domain: interfaces/card-edge
tags: [card-edge, pcie, m.2, nvme, key-m, key-b, key-e, gold-fingers, bevel, board-thickness, mating-direction]
source: [KiCad 10 Connector_PCBEdge.pretty (read); PCI-SIG PCIe CEM and M.2 specifications named by the footprints (not read)]
date: 2026-10-03
confidence: needs-verification
---

# Card edge: PCIe and M.2 finger footprints

Rules: `skills/hw-design/references/interfaces.md` section 19. The footprints are the
board's own edge, not a component: they carry `exclude_from_bom` and
`exclude_from_pos_files`.

## Stock footprints (verified-in-cad)

| Footprint (`Connector_PCBEdge.pretty`) | Geometry |
|---|---|
| `BUS_PCIexpress_x1` | 36 fingers: 2 short (0.7 x 3.2 mm) and 34 long (0.7 x 4.3 mm) at 1.0 mm pitch, x = 0 to 19. Courtyard 21.3 x 9.4 mm. Text note `PCB Thickness 1.57 mm`. `Edge.Cuts` outline at y = +3.45, key notch between x = 10.55 and x = 12.45 mm |
| `M.2_2280-xx-M` | 67 fingers 0.35 mm wide (34 x 1.5 mm and 33 x 2.0 mm tall), 0.5 mm pitch per side, y = 1.5 to 3.5 mm. Text notes `Chamfer 20 degree 0.3 mm` and `PCB thickness 0.8 mm`. `Edge.Cuts` at y = +4.0, module outline to y = -76. Key M notch x = -6.725 to -5.525 (1.2 mm wide) |

Other keys (`M.2_2230-xx-A`, `-B`, `-E`, `M.2_2280-xx-B`, others) and `BUS_PCIexpress_x4`,
`x8`, `x16` were not measured.

## mating_direction

`+y` for both: the fingers sit at the `+y` edge, with the `Edge.Cuts` edge at y = +3.45
(PCIe) and y = +4.0 (M.2). verified-in-cad (by the footprint's own outline). The
direction is the card's insertion direction.

## Keys and thickness (needs-verification: PCI-SIG documents not read)

M.2 key notch pins: A 8 to 15, B 12 to 19, E 24 to 31, M 59 to 66. Key M is PCIe x4 and
SATA, key B PCIe x2 and SATA, keys A and E PCIe x2 and USB 2.0 (wireless). Board
thickness: 1.57 mm (PCIe card), 0.8 mm (M.2).

## Fabrication notes (needs-verification)

Hard gold fingers, a leading-edge bevel (20 degrees on M.2 per the footprint note),
no copper or mask openings beyond the fingers in the insertion region.

## Traps

- Ordering at 1.6 mm for an M.2 module (0.8 mm) fails to mate.
- The footprint is excluded from the BOM: the finger finish must be in the fab notes.
- Differential pairs need controlled impedance (`domains.md` section 3).

## What a research pass must confirm

1. Key pin ranges and finger plating from the PCI-SIG documents.
2. The other key and width footprints.
