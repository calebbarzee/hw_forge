---
domain: interfaces/jst
tags: [jst, xh, 2.5mm, b2b-xh-a, s2b-xh-a, xhp, mating-direction]
source: [JST eXH.pdf (read pages 1 to 6), KiCad 10 Connector_JST.pretty (read)]
date: 2026-10-03
confidence: researched
---

# JST XH (2.5 mm): stock footprints, mated size, mating direction

Rules: `skills/hw-design/references/interfaces.md` section 5.

## Stock footprints (verified-in-cad)

| n | Footprint (vertical) | Pads | Outer span | packages.json key |
|---|---|---|---|---|
| 2 | `JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical` | 2 | 4.2 x 2.0 mm | `JST-XH-2` |
| 3 | `JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical` | 3 | 6.7 x 1.95 mm | `JST-XH-3` |
| 4 | `JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` | 4 | 9.2 x 1.95 mm | `JST-XH-4` |
| 5 | `JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical` | 5 | 11.7 x 1.95 mm | `JST-XH-5` |
| 6 | `JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical` | 6 | 14.2 x 1.95 mm | `JST-XH-6` |

Side entry: `JST_XH_S<n>B-XH-A_1x0<n>_P2.50mm_Horizontal`, same pads. Pads 1.7 x 1.95 mm
(2.0 mm tall for n = 2), drill 0.95 mm (1.0 mm for n = 2), pitch 2.50 mm. `-AM` (boss),
`-A-1` (7.6 mm side entry) and `-SM4-TB` variants are different footprints.

## mating_direction

| Footprint | `mating_direction` | Status |
|---|---|---|
| `..._Vertical` | `+z` | researched: top-entry type |
| `..._Horizontal` | `+y` | needs-verification: pad row at y = 0, fab y -2.30 to +9.20 matches JST's C = 9.2 mm |

## Mated plug envelope

| Item | Value (JST eXH.pdf) |
|---|---|
| Header B<n>B-XH-A width | 2.5 x (n-1) + 4.9 mm, 5.75 mm deep, 7.0 mm above board |
| Assembled height, top entry | 9.8 mm |
| Side entry | 14.3 mm mated length, 6.1 mm tall (C = 9.2 mm type) |
| Housing XHP-n | 2.5 x (n-1) + 4.8 mm wide, 5.7 mm deep, 7.5 mm tall |
| Rating | 3 A with AWG 22, 250 V; wire AWG 30 to 22; PCB thickness 1.6 mm |

## Panel opening

Mostly internal. A plug leaving the case needs the 5.7 x 7.5 mm housing plus clearance,
and 9.8 mm of height above the board for top entry.

## Traps

- Confusion with PH (2.0 mm): see `jst-ph.md`.
- Four-pin XH conforms to JEMA home-automation terminal housings, which fixes the
  housing, not the signals.
- Whether XH has a mating latch is not stated on the pages read (needs-verification).

## What a research pass must confirm

1. `+y` for the side-entry footprints. 2. The mating latch.
