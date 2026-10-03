---
domain: interfaces/jst
tags: [jst, sh, 1.0mm, bm04b-srss-tb, sm04b-srss-tb, shr, qwiic, mounting-tab, mating-direction]
source: [JST eSH.pdf (read pages 1 to 4), KiCad 10 Connector_JST.pretty (read)]
date: 2026-10-03
confidence: researched
---

# JST SH (1.0 mm): stock footprints, mated size, mating direction

Rules: `skills/hw-design/references/interfaces.md` section 6. This is the Qwiic and STEMMA
QT connector (`qwiic-stemma-qt.md`).

## Stock footprints (verified-in-cad)

Pad counts include the two mounting-tab pads `MP`.

| n | Top entry | Side entry | Pads | Outer span | packages.json key |
|---|---|---|---|---|---|
| 2 | `JST_SH_BM02B-SRSS-TB_1x02-1MP_P1.00mm_Vertical` | `JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal` | 4 | 4.8 x 4.2 (BM), 5.55 x 4.8 (SM) | `JST-SH-2`, `JST-SH-2-SM` |
| 3 | `..BM03B..Vertical` | `..SM03B..Horizontal` | 5 | 5.8 x 4.2 (BM), 5.8 x 5.55 (SM) | `JST-SH-3` |
| 4 | `..BM04B..Vertical` | `..SM04B..Horizontal` | 6 | 6.8 x 4.2 (BM), 6.8 x 5.55 (SM) | `JST-SH-4` |
| 5 | `..BM05B..` | `..SM05B..` | 7 | 7.8 x 4.2 / 5.55 | `JST-SH-5` |
| 6 | `..BM06B..` | `..SM06B..` | 8 | 8.8 x 4.2 / 5.55 | `JST-SH-6` |

Signal pads 0.60 x 1.55 mm at 1.00 mm pitch. `MP` pads 1.2 x 1.8 mm at x = +-((n-1)/2 + 1.3) mm
from the centre (x = +-2.8 mm for n = 4). BM04B: signal pads at y = +1.325, `MP` at y =
-1.2. SM04B: signal pads at y = -2.0, `MP` at y = +1.875.

## mating_direction

| Footprint | `mating_direction` | Status |
|---|---|---|
| `..BM..Vertical` | `+z` | researched: top-entry type |
| `..SM..Horizontal` | `+y` | needs-verification: signal pads at y = -2.0, body to y = +2.58 |

## Mated plug envelope

| Item | Value (JST eSH.pdf) |
|---|---|
| Header width | 1.0 x (n-1) + 3.0 mm, 2.9 mm deep (top entry), 4.25 mm above board |
| Mated height above board, top entry | 6.3 mm |
| Side entry | 6.25 mm mated length, 2.95 mm tall |
| Housing SHR-nnV-S | 1.0 x (n-1) + 2.0 mm wide (+4.0 mm with protrusions), 2.8 mm deep, 5 mm tall |
| Rating | 1.0 A with AWG 28, 50 V; wire AWG 32 to 28 |

## Panel opening

Internal in most designs. A cable leaving the case: housing 2.8 x 5 mm plus clearance.

## Traps

- The mounting tabs `MP` carry the retention. Tie them to a net (`X-SHD-01`).
- 1 A at AWG 28 rules this out for a rail carrying hundreds of milliamps from a cell.
- A 2-position SH has a different pad envelope on the long axis for BM and SM, so it
  has two packages.json keys.
- No mating latch is stated on the pages read (needs-verification).

## What a research pass must confirm

1. `+y` for SM. 2. Retention features of the housing.
