---
domain: parts/passives
tags: [electrolytic, radial, polarity, footprint, c_radial, cp_radial, rubycon, yxj, 25yxj, height, silkscreen, kicad-library]
source: [hypercardiod_mic lib/research/passives-active.md sections 3 and 8 (2026-10-03), Rubycon YXJ catalogue sheet p2 (https://www.rubycon.co.jp/wp-content/uploads/catalog-aluminum/YXJ.pdf), KiCad 10.0.5 stock footprints]
date: 2026-10-04
confidence: researched
---

# Radial electrolytic footprints: the non-polar sibling and the 11 mm height

Two traps for a 5 x 11 mm radial aluminium electrolytic on a 2.0 mm pitch. ERC and DRC
accept both. `kicad_fpcheck.py` catches trap 1 when it is given the schematic. No gate
catches trap 2.

## Trap 1: the name that fits is non-polar

| Footprint (KiCad 10.0.5) | Polarity | Can |
|---|---|---|
| `Capacitor_THT:C_Radial_D5.0mm_H11.0mm_P2.00mm` | its `descr` says "Non-Polar Electrolytic Capacitor"; both pads are circles; no plus mark on the silkscreen | 5 mm diameter, 11 mm tall |
| `Capacitor_THT:CP_Radial_D5.0mm_P2.00mm` | polarized: square pad 1, plus mark | drawn for a 7 mm can |

The mic run placed six 25YXJ electrolytics on the non-polar footprint with the symbol
`Device:C_Polarized`. Nothing on the board marked polarity. A reversed electrolytic on a
15 V rail is a hand-assembly failure.

`kicad_fpcheck.py --sch` now FAILs this footprint. For a polarized symbol it reads the
footprint `descr` and keywords for polarity hints. This `descr` says "Non-Polar". It also
requires a pad 1 mark: pad 1 shape or size differing from its pair, or a silk or fab item
in pad 1's half of the footprint.

Fix with a polarized footprint. Either:

- use a stock `CP_` footprint that fits the can, or
- fork the footprint with `kicad_fplib.py fork`, make pad 1 square, add a plus mark
  beside it, correct the `descr`, `annotate` the change, and add the
  `lib/PROVENANCE.md` row (`kb/README.md`, "Where a fact lives").

A board-level silk plus does not pass the check, because it is not part of the
footprint. The polarized sibling above is not a drop-in: its 3D model and courtyard are
for a 7 mm can, so check both against the 11 mm part (needs-verification: height and
courtyard of the sibling were not compared).

## Trap 2: seated height is 12.5 mm, not 11

No gate sees this trap.

Rubycon YXJ p2 lists, for phi D 5: phi d 0.5, F 2.0, L 11, and L + alpha 12.5 mm maximum
(alpha 1.5 mm for L up to 16 mm). The footprint name and its 3D model say 11.0 mm. Read
12.5 mm for the enclosure's height ledger: the part reaches 1.5 mm higher than the
footprint name states.

The model's own z band, from the `kicad_3d.py extent` sweep in the run, is minus 2.0 to
11.0 mm (2 mm of lead below the board). Its x and y values from that sweep were too
large to use (10.1 x 10.1 mm for a 5 mm can), so no bounding box is recorded here.

## Parts this was measured on

| Ref | MPN | LCSC |
|---|---|---|
| 100 uF 25 V | Rubycon 25YXJ100M5X11 | C108360 |
| 47 uF 25 V | Rubycon 25YXJ47MTA5X11 | C1498122 |

The `TA` packing suffix is read from LCSC's listing only and is not defined on the YXJ
sheet, so the equivalence of the taped and bulk parts rests on LCSC's own parameters.

## Related

`kb/parts/package-family-traps.md` (same silhouette, different family),
`skills/hw-design/references/kicad-api.md` section 9 (model checks).
