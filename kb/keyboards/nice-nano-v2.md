---
domain: keyboards/mcu
tags: [nice-nano, nrf52840, pro-micro, pinout, nrf-port, ext-power, me6217, ldo, charger, usb-overhang, socket-stack]
source: z_board v0.4 (kicad/design.py MCU_HEADER + NRF_PORT, kicad/POWER.md, case/zboard_case.py)
date: 2026-08-22
confidence: verified-in-cad
---

# nice!nano v2 — pin map, rails, and mounting

nRF52840 pro-micro-footprint wireless module. 24 castellated/through-hole pins,
**33.0 × 17.78 mm** outline, module PCB **1.20 mm** thick, pin pitch **2.54 mm** down each
column and **15.24 mm (0.6")** between columns.

## Verified 24-pin map

Viewed from the **component side with USB at the top**. Pad numbers are the module's own
pro-micro numbering; pad 1 is D1 at the USB end of the left column (that is where the
footprint's square pad-1 marker belongs).

```
pads  1..12   left  column, top → bottom:  D1  D0  GND GND D2  D3  D4  D5  D6  D7  D8  D9
pads 24..13   right column, top → bottom:  B+  GND RST 3V3 D21 D20 D19 D18 D15 D14 D16 D10
```

**Index order ≠ pad number.** A pin table ordered by physical position (right column
top→bottom, then left column bottom→top) has pad numbers running 24…13, 12…1. Deriving
geometry from list *index* is correct; assuming `index+1 == pad number` puts pad 1 at the
wrong end and needs a full `k → 25−k` renumber later. Keep the geometry helpers index-based
so a renumber changes no routing code.

ERC pin types: `RAW` = power_in, `GND` = power_in, **`VCC` = power_out** (it is the module's
LDO output, not an input), `RST` = input, everything else bidirectional.

## D-label → nRF port (the trap)

**The `D` labels are pro-micro compatibility names, NOT nRF port numbers. D21 is P0.31, not
P0.21.** Keep this table in the design module so the confusion cannot recur; the ZMK
devicetree needs the right-hand column.

| Label | Port | | Label | Port |
|---|---|---|---|---|
| D0 | P0.08 | | D9 | P1.06 |
| D1 | P0.06 | | D10 | P0.09 |
| D2 | P0.17 | | D14 | P1.11 |
| D3 | P0.20 | | D15 | P1.13 |
| D4 | P0.22 | | D16 | P0.10 |
| D5 | P0.24 | | D18 | P1.15 |
| D6 | **P1.00** | | D19 | P0.02 |
| D7 | P0.11 | | D20 | P0.29 |
| D8 | P1.04 | | D21 | **P0.31** |

D9/D10 are on the same castellations as NFC (P0.09/P0.10) — leave free unless you accept
disabling NFC in devicetree.

## Rails — what the module already provides

```
cell ─ B+ (pad 24, "RAW") ─┬─ Li-Po charger, USB-C sourced, ~100 mA
                           └─ LDO ME6217C33M5G, 3.3 V, 800 mA
                                └─ enable = P0.13  ──▶  VCC (pad 21)
```

- **VCC (pad 21) is a gated 3.3 V rail**: the ME6217's enable is **P0.13**, which is exactly
  the pin ZMK drives as `EXT_POWER`. Hanging switchable loads on VCC gets gating for free —
  no external P-FET load switch. See `zmk-electrical.md`.
- **800 mA is a hard ceiling** on how much load mistake the cell can be asked to absorb.
- **Dropout**: the ME6217 needs roughly **Vin ≥ 3.45 V** to hold 3.3 V at 300 mA, so near
  end-of-charge a high-current rail on VCC sags before the nRF (which runs to 1.7 V) cares.
- Charger is ~100 mA = 0.2C into 500 mAh (safe, ~6 h from empty) but ~0.9C into a 110 mAh
  cell → **the charger sets a minimum cell size** of roughly ≥250 mAh.
- Also on-module and therefore **not to be duplicated** on a carrier: Li-Po protection,
  USB ESD/TVS, reset pull-up, input capacitance. A carrier with no USB net has no USB ESD
  path at all.
- Reset: pad 22 to a bare momentary to GND. No RC, no pull-up needed.

## Mounting

- **On 2x12 sockets, module component-side up on the switch (front) face** is the
  serviceable arrangement. Stack heights above the PCB top face:

  | Layer | mm |
  |---|---|
  | Mill-Max low-profile socket, seated | 1.90 |
  | nice!nano PCB | 1.20 |
  | USB-C receptacle shell above that | 3.20 |
  | **total** | **6.30** |
  | USB port centreline | 1.90 + 1.20 + 1.60 = **4.70** |

  Soldering the module down instead drops the whole stack by 1.90 mm.
- MX geometry only leaves **3.50 mm** under a 1.5 mm plate (`mx-switch-geometry.md`), so a
  **deck cannot roof a socketed module** — the module stands ~1.30 mm proud of the plate's
  top surface. The printable answer is an open window in the deck, not a raised bay.
- **USB overhang convention**: place the module with its own PCB edge flush to the board's
  outer edge, so the **USB-C shell overhangs by ~0.6 mm**. Benefits: no board material
  wasted, connector fully accessible. Costs: under 1 mm of board west of the pad columns,
  so **nothing can route around the USB end** — every crossing net must thread a gap
  between two pads (2.54 pitch − two 1.7 mm pads = 0.84 mm clear; enough for a 0.25 mm
  track at 0.2 mm clearance). The enclosure opening must go **clean through** the wall
  (0.6 mm overhang = 0.30 mm into a 2.5 mm wall).
- Through-hole socket strips put **solder joints proud on the back face** — a front-face
  module still occupies an obstacle rectangle on the back-face clearance ledger.
- The module stands off on 2.54 mm headers, so a low part (e.g. a slide switch) may be
  deliberately nested under it between the two pad columns, across the 15.24 mm corridor.
  Expect `npth_inside_courtyard` findings; demote that specific rule with a justification.

## Flipping it to the other face

Turning the module over maps hole *i* onto pad *25−i*, pairing RAW↔D1, RST↔GND and
VCC↔GND — **two dead shorts**, so two faces cannot share one 24-hole grid. Use two
interleaved grids (48 holes) offset **purely across by one full pitch**; see
`references/electronics.md` §9 for why the diagonal offset is the wrong choice.
