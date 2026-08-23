---
domain: keyboards/parts
tags: [sk6812, sk6812mini-e, ws2812, addressable-led, underglow, pin-order, reverse-mount, shine-through, serpentine]
source: z_board v0.4 (HISTORY.md, kicad/NOTES.md, kicad/POWER.md, kicad/lib/)
date: 2026-08-22
confidence: verified-in-cad
---

# SK6812MINI-E — pin-order trap, reverse mounting, chain rules

## The `-E` vs plain `MINI` pin-order trap

The two parts share a family name and **number their pins differently**:

| Pin | SK6812MINI-**E** | SK6812MINI (plain, top-mount) |
|---|---|---|
| 1 | **VDD** | DOUT |
| 2 | **DOUT** | VSS |
| 3 | **VSS** | DIN |
| 4 | **DIN** | VDD |

KiCad ships only the plain top-mount `SK6812MINI` symbol. **Pairing the stock symbol with
an `-E` footprint swaps power and data on every LED in the chain — silently, and DRC-clean
with full schematic parity**, because both files are internally consistent. This is the
canonical instance of the "one pin table, two emitters" doctrine
(`references/kicad-api.md` §8): make a project-local symbol *and* footprint from the
datasheet's `-E` order and never mix vendors' halves.

## Footprint geometry

Reverse-mount: the part sits on the **back** face and emits **up through a window cut in
the PCB** into the switch housing above.

| Feature | z_board project footprint | foostan `YS-SK6812MINI-E` |
|---|---|---|
| pads | ±2.70, ±0.70; 1.4 × 1.0 | ±2.80, ±0.70; 1.7 × 0.825 |
| light window | `Edge.Cuts` rect **2.8 × 3.1 mm** | 3.6 mm wide (ceoloide/ergogen lineage) |
| body height below PCB | 1.40 mm | same part |

**Window width is a clearance decision, not a light decision.** The 3.6 mm window left only
0.2 mm copper-to-edge and generated **168 `copper_edge_clearance` violations**; narrowing to
2.8 mm buys 0.6 mm and the violations vanish with no visible loss of light. Window is
centred on the cell's mirror line so a reversible cell maps it onto itself.

Placement in z_board: LED body at key centre **+ (0.0, 4.9)** in KiCad space (+y south);
100 nF cap at key **+ (5.3, 5.6)**; diode at key **+ (0.0, 8.2)** rotated 180°.

**Nothing emits downward.** A reverse-mounted chain shining through the board means a
diffusing enclosure floor does nothing — do not add one.

## Per-row rotation in a serpentine chain — mandatory

A row-major serpentine chain (run a row straight, snake to the next row in the board
margin) requires the LED to be **rotated 180° on reversed-direction rows** so DOUT always
faces the direction of travel.

- Without it, every westbound link has to cross its own cell and collides with that key's
  departure: **58 `shorting_items` on the first attempt.**
- It is not removable. This was re-proposed as a simplification and **rejected on
  evidence**.
- Consequences to document so they are not read as bugs: the pick-and-place file shows
  **0°/180° alternating by row** (intended); and **everything that serves an LED pad must
  be positioned relative to the LED's own local frame, not the cell** — cell-relative caps
  and vias stay put while the pads they serve move to the other end of the part, putting
  traces straight across the light windows.

## Electrical

- **DIN wants ≈0.7 × VDD.** Powering the chain from the MCU's own 3.3 V logic rail
  satisfies it by construction (2.31 V threshold vs ~3.3 V drive) — no level shifter. This
  is the whole argument for VCC over a 5 V rail; see `zmk-electrical.md` and
  `references/electronics.md` §2.
- **Series resistor at the driver: 470 Ω 0603** when the LED rail is gated. `(3.3−0.7)/470
  ≈ 5.5 mA` injection cap; `470 Ω × ~80 pF ≈ 38 ns` edge against the SK6812's **±150 ns**
  tolerance on a 300/600 ns bit → ~4× margin. Usable band 100–500 Ω; do not exceed ~1 kΩ.
  100 Ω limits to ~26 mA, above an nRF52840 pin's drive, so it limits nothing.
- Controllers switch at **~800 kHz**. Optional per-LED 100 nF at the VDD pad suppresses
  supply ringing whose symptom is flicker at the **far end** of a long chain. Note: corne
  v3, corne v4 (cherry + chocolate) and helix all ship **zero** per-LED caps and work, and
  ZMK's docs give no electrical guidance (`grep 100nF zmk/docs` → nothing). z_board
  populates them as a deliberate decision, plus 10 µF + 1 µF bulk at rail entry.

## Current budget (22 LEDs)

| Case | Per LED | 22 LEDs |
|---|---|---|
| gated off | 0 | **0** |
| lit rail, all pixels black | ~0.7–1 mA | ~20 mA (flattens 500 mAh in ~24 h) |
| full white | 18–60 mA (binning spread) | **0.4–1.3 A** |
| working target | ~14 mA | ~300 mA (0.6C on a 500 mAh cell) |

1.3 A worst case against an 800 mA LDO makes a **firmware brightness cap a hardware
requirement** — see `zmk-electrical.md`.

Trade accepted at 3.3 V: dimmer and slightly blue-shifted versus a 5 V chain.
