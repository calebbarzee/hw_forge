---
domain: interfaces/jst
tags: [jst, gh, 1.25mm, bm04b-ghs-tbt, sm04b-ghs-tb, ghr, latch, keying, mating-direction]
source: [JST eGH.pdf (read pages 1 to 4), KiCad 10 Connector_JST.pretty (read)]
date: 2026-10-03
confidence: researched
---

# JST GH (1.25 mm, latching): stock footprints, mated size, mating direction

Rules: `skills/hw-design/references/interfaces.md` section 7.

## Stock footprints (verified-in-cad)

| n | Top entry | Side entry | Pads | Outer span | packages.json key |
|---|---|---|---|---|---|
| 2 | `JST_GH_BM02B-GHS-TBT_1x02-1MP_P1.25mm_Vertical` | `JST_GH_SM02B-GHS-TB_1x02-1MP_P1.25mm_Horizontal` | 4 | 5.95 x 5.6 (BM), 5.95 x 5.4 (SM) | `JST-GH-2` |
| 3 | `..BM03B..` | `..SM03B..` | 5 | 7.2 x 5.6 | `JST-GH-3` |
| 4 | `..BM04B..` | `..SM04B..` | 6 | 8.45 x 5.6 | `JST-GH-4` |
| 5 | `..BM05B..` | `..SM05B..` | 7 | 9.7 x 5.6 | `JST-GH-5` |
| 6 | `..BM06B..` | `..SM06B..` | 8 | 10.95 x 5.6 | `JST-GH-6` |

Signal pads 0.6 x 1.7 mm at 1.25 mm pitch, `MP` pads 1.0 x 2.8 mm (BM) or 1.0 x 2.7 mm
(SM). BM04B: signal pads y = +1.95, `MP` y = -1.4, x = +-3.725. SM04B: signal pads y =
-1.85, `MP` y = +1.35.

## mating_direction

| Footprint | `mating_direction` | Status |
|---|---|---|
| `..BM..Vertical` | `+z` | researched: top-entry type |
| `..SM..Horizontal` | `+y` | needs-verification |

## Mated plug envelope

| Item | Value (JST eGH.pdf) |
|---|---|
| Header width | 1.25 x (n-1) + 4.5 mm, 4.25 mm deep, 4.05 mm above board (top entry) |
| Mated height above board, top entry | 7.3 mm |
| Side entry | 7.15 mm mated length, 4.35 mm tall |
| Housing GHR-nnV-S | 1.25 x (n-1) + 2.5 mm wide, 4.15 mm deep, 5.7 mm tall |
| Rating | 1.0 A with AWG 26, 50 V; wire AWG 30 to 26 |
| Lock | Positive latch ("secure lock mechanism", "large outer latch") |
| Keying | Keying pattern A (GHR-02V-2P, 04V-2P, 05V-2P and headers) prevents mating with standard GH |

## Panel opening

Internal in most designs. The latch needs finger or tool access: reserve the 7.3 mm
mated height and a path to release the latch, and do not seal the connector behind a
wall without a service opening.

## Traps

- Latched connector: a plug that cannot be released in place gets pulled by its cable,
  which tears the header off the board. Leave room.
- `MP` pads must be soldered and tied to a net.

## What a research pass must confirm

1. `+y` for SM. 2. Keying pattern A parts, which are not in the stock set read.
