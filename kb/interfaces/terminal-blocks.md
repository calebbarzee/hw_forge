---
domain: interfaces/terminals
tags: [terminal-block, screw-terminal, pluggable, phoenix, mstb, mc, mkds, 5.08mm, 3.5mm, creepage, ipc-2221, mating-direction]
source: [KiCad 10 Connector_Phoenix_MSTB.pretty, Connector_Phoenix_MC.pretty, TerminalBlock_Phoenix.pretty (read), RS Components listing of Phoenix 1757268 (search result)]
date: 2026-10-03
confidence: needs-verification
---

# Terminal blocks: stock footprints, ratings, pad gap

Rules: `skills/hw-design/references/interfaces.md` section 18.

## Stock footprints (verified-in-cad)

| Footprint | Pads | Body (fab) | Rating (footprint `descr`) |
|---|---|---|---|
| `Connector_Phoenix_MSTB.pretty/PhoenixContact_MSTBA_2,5_4-G-5,08_1x04_P5.08mm_Horizontal` | 4 x 2.08 x 3.6 mm, drill 1.4 mm, 5.08 mm pitch, outer span 17.32 x 3.6 mm | 22.32 x 12.0 mm (x -3.54 to 18.78, y -2.0 to 10.0) | 12 A (order 1757268), 16 A HC variant; 320 V per the RS listing |
| `..PhoenixContact_MSTBVA_2,5_4-G-5,08_1x04_P5.08mm_Vertical` | same pads | 22.32 x 8.6 mm | 12 A (order 1755752) |
| `Connector_Phoenix_MC.pretty/PhoenixContact_MC_1,5_4-G-3.5_1x04_P3.50mm_Horizontal` | 4 x 1.8 x 3.6 mm, drill 1.2 mm, 3.5 mm pitch, outer span 12.3 x 3.6 mm | 15.4 x 9.2 mm | 8 A, 160 V (order 1844236) |
| `TerminalBlock_Phoenix.pretty/TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal` | 2 x 2.6 mm, drill 1.3 mm, 5.0 mm pitch | 10.0 x 9.8 mm | not in the footprint |

None is in packages.json (not in the requested set).

## mating_direction

| Footprint | `mating_direction` | Status |
|---|---|---|
| MSTBA angled | `+y` | needs-verification: pad row at y = 0, body to y = +10.0 |
| MC 1,5 angled | `+y` | needs-verification: body y -1.2 to +8.0 |
| MSTBVA vertical | `+z` | by name |
| MKDS 1,5 screw terminal | needs-verification | wire opening is along y, the footprint shows no marker for which end |

## Mated plug envelope

Plug dimensions were not read (needs-verification). Reserve the header body plus the plug
height: MSTB 5.08 mm plugs stand well above the header. Pluggable headers with the `GF`
suffix have a threaded flange for the plug screws.

## Pad gap against working voltage

Gap = pitch minus pad width: 5.08 - 2.08 = 3.00 mm (MSTBA), 3.5 - 1.8 = 1.70 mm (MC
3.5). IPC-2221B Table 6-1 spacing for external uncoated conductors (needs-verification,
recalled): 0.6 mm to 100 and to 150 V, 1.25 mm to 250 V, 2.5 mm to 500 V. 3.00 mm covers
the MSTBA's 320 V, and 1.7 mm covers the MC's 160 V.

## Traps

- 5.00, 5.08, 3.81, 3.50 mm pitches are all common and not interchangeable.
- Wire strain: a screw terminal relies on the clamp; add a cable tie point.

## What a research pass must confirm

1. Directions. 2. IPC-2221B values. 3. Plug dimensions and MKDS rating.
