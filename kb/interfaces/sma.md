---
domain: interfaces/rf
tags: [sma, rf, coax, 50-ohm, edge-launch, edge-mount, amphenol-132134, amphenol-132289, molex-73251, mating-direction]
source: [KiCad 10 Connector_Coaxial.pretty (read)]
date: 2026-10-03
confidence: needs-verification
---

# SMA connectors: stock footprints and mating direction

Rules: `skills/hw-design/references/interfaces.md` section 12. SMA is 50 ohm, threaded
(1/4-36 UNS, needs-verification).

## Stock footprints (verified-in-cad)

`Connector_Coaxial.pretty/`.

| Footprint | Pads | Geometry |
|---|---|---|
| `SMA_Amphenol_132134_Vertical` | 1 centre + 4 ground legs | Centre pad 2.05 mm, drill 1.5 mm. Ground legs 2.25 mm, drill 1.7 mm, at (+-2.54, +-2.54) mm. Outer span 7.33 x 7.33 mm. Fab 7.0 x 7.0 mm |
| `SMA_Amphenol_132289_EdgeMount` | SMD centre pad 1.5 mm wide, 5.08 mm long; ground pads at y = +-4.25 mm | Fab x -1.91 to +13.97, y -5.08 to +5.08 |
| `SMA_Molex_73251-1153_EdgeMount_Horizontal` | SMD centre 5.08 x 2.29 mm at x = -1.72; ground 5.08 x 2.42 at y = +-4.38; vias at x = +1.72 | Fab x -13.79 to +2.50, y -4.76 to +4.76 |

None is in packages.json (not in the requested set).

## mating_direction

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| Amphenol 132134 vertical | `+z` | Vertical |
| Amphenol 132289 edge mount | `+x` | Body extends to x = +13.97 away from the launch pads. needs-verification (no edge marker) |
| Molex 73251-1153 edge mount | `-x` | Body extends to x = -13.79. needs-verification |

The two edge-mount parts face opposite ways in their own frames. Reusing one part's
rotation for the other mirrors the connector.

## Mated plug envelope and panel opening (needs-verification)

The plug nut is larger than the receptacle thread (about 8 mm across flats, common). A
bulkhead SMA jack needs a hole near 6.4 mm, with a flat on some. Read the part drawing.

## Layout traps

- The launch geometry depends on board thickness: use the vendor footprint for the
  stated stackup. Stitching vias around the launch under lambda/20 apart.
- The edge launch must sit on the board edge: a gap makes a stub.

## What a research pass must confirm

1. Edge-mount directions against the vendor drawings. 2. Thread, hole, and torque.
3. The stackup the launch was designed for.
