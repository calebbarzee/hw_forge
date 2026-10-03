---
domain: interfaces/jst
tags: [jst, ph, 2.0mm, b2b-ph-k, s2b-ph-k, phr, lipo, battery-connector, mating-direction, polarity]
source: [JST ePH.pdf (read pages 1 to 3), KiCad 10 Connector_JST.pretty (read with kicad_fpcheck.py)]
date: 2026-10-03
confidence: researched
---

# JST PH (2.0 mm): stock footprints, mated size, mating direction

Rules: `skills/hw-design/references/interfaces.md` section 4. The most common hobby
Li-Po connector (`skills/hw-design/references/batteries.md` section 5). Polarity of a
pigtail is set by the cable maker, not by the connector.

## Stock footprints (verified-in-cad)

`Connector_JST.pretty/`, read with `python3 scripts/kicad_fpcheck.py <file> -v`. The
through-hole top-entry (`B`) and side-entry (`S`) footprints share one pad pattern.

| n | Footprint (vertical; replace `B` with `S` and `Vertical` with `Horizontal` for side entry) | Pads | Outer span | packages.json key |
|---|---|---|---|---|
| 2 | `JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical` | 2 | 3.2 x 1.75 mm | `JST-PH-2` |
| 3 | `JST_PH_B3B-PH-K_1x03_P2.00mm_Vertical` | 3 | 5.2 x 1.75 mm | `JST-PH-3` |
| 4 | `JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical` | 4 | 7.2 x 1.75 mm | `JST-PH-4` |
| 5 | `JST_PH_B5B-PH-K_1x05_P2.00mm_Vertical` | 5 | 9.2 x 1.75 mm | `JST-PH-5` |
| 6 | `JST_PH_B6B-PH-K_1x06_P2.00mm_Vertical` | 6 | 11.2 x 1.75 mm | `JST-PH-6` |

Pads 1.20 x 1.75 mm (pad 1 roundrect, others oval), drill 0.75 mm, pitch 2.00 mm. JST's
recommended hole is 0.7 +0.1/0 mm.

## mating_direction

| Footprint | `mating_direction` | Status |
|---|---|---|
| `..._Vertical` (top entry) | `+z` | researched: JST catalogue top-entry type |
| `..._Horizontal` (side entry) | `+y` | needs-verification: body (fab y -1.35 to +6.25) lies on the +y side of the pad row; confirm with a mated view |

## Mated plug envelope

| Item | Value (JST ePH.pdf) |
|---|---|
| Header B2B-PH-K-S width | 2.0 x (n-1) + 3.9 mm, 4.5 mm deep, 6.0 mm above board |
| Mated height above board, top entry | 8 mm |
| Side entry | header 4.8 mm tall, 7.6 mm long; mated length 9.6 mm |
| Housing PHR-n | 2.0 x (n-1) + 3.8 mm wide, 4.5 mm deep, 6.85 mm tall |
| Rating | 2 A with AWG 24, 100 V; wire AWG 32 to 24 |

## Panel opening

Internal connector in most designs. If a pigtail leaves the case, the opening is the
housing's 4.5 x 6.85 mm plus clearance, and strain relief is the cable clamp. A
pre-molded cable assembly from a vendor can be larger than a bare crimp housing.

## Traps

- PH (2.0 mm) and XH (2.5 mm) look alike. `kicad_fpcheck.py` with `PACKAGES = {...:
  "JST-PH-4"}` on an XH footprint fails on family, pitch, and span.
- The `-SM4-TB` SMT headers are a different footprint and not in packages.json.
- Pin 1 marking: JST "No. 1 circuit". Silkscreen polarity.
- No mating latch is stated on the catalogue pages read (needs-verification).

## What a research pass must confirm

1. `+y` for the side-entry footprints.
2. Whether PH has any retention feature.
