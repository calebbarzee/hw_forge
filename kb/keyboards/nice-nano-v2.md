---
domain: keyboards/mcu
tags: [nice-nano, nrf52840, pro-micro, pinout, nrf-port, ext-power, me6217, ldo, charger, usb-overhang, socket-stack, courtyard, enclosure, usb-notch, pinctrl, pinmux, uart0, i2c0, spi1, nfc, p0-29]
source: z_board v0.4 (kicad/design.py MCU_HEADER + NRF_PORT, kicad/POWER.md, case/zboard_case.py); hexpad phase-6 (case/hexpad_case.py, 239-check verify() pass (board rev 2)); hexpad phase-7 harvest (nice_nano-pinctrl.dtsi, nice_nano.dts)
date: 2026-08-23
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

**The NFC pads are P0.09 and P0.10**, which on this module are the pins labelled **D10** and
**D16** (read them out of the table above, do not recall them). Leave those two free unless
you accept disabling NFC in devicetree. **D9 is P1.06 and is unaffected.**

> *Correction, 2026-08-22 (hexpad phase 3, which went to the ZMK source rather than trusting
> this prose):* this line previously read "D9/D10 are on the same castellations as NFC
> (P0.09/P0.10)" — wrong in both directions against the card's own table. A pin map trusting
> it would have skipped a free pin (D9) and used an NFC pin (D16). State pin roles in port
> terms and derive the label; see `kb/README.md`, "Pin-role facts — port first".

## Default peripheral pinmux — the enumeration, done once

`zmk-electrical.md` states the rule: before locking a pin map, list every default peripheral
pinmux on the target board and check it against the matrix and the chain — free GPIOs are not
the constraint, peripheral defaults are. This is the **answer** for nice!nano v2, so no
project re-derives it from the firmware tree. Source:
`zmk/app/module/boards/nicekeyboards/nice_nano/nice_nano-pinctrl.dtsi` and `nice_nano.dts`.

| Instance | Signal | Port | Label |
|---|---|---|---|
| `uart0` | RX | P0.08 | D0 |
| `uart0` | TX | P0.06 | D1 |
| `i2c0` | SDA | P0.17 | D2 |
| `i2c0` | SCL | P0.20 | D3 |
| `spi1` | SCK | P1.13 | D15 |
| `spi1` | MOSI | P0.10 | D16 |
| `spi1` | MISO | P1.11 | D14 |
| blue LED | — | P0.15 | none — not on a castellation |
| ext-power | LDO enable | P0.13 | none — ZMK `EXT_POWER` |

`spi0`, `spi2` and `spi3` have **nothing** until a shield or board overlay defines them —
which is exactly why an addressable-LED chain gets its own `&spi3` and a nice!view claims
`spi0` (`zmk-electrical.md`, `nice-view-display.md`).

**Trap: P0.29 (D20) has no default peripheral role at all.** A claim in one project's
resource doc that D20 was "`spi1`'s default SCK" was wrong — `spi1`'s SCK is P1.13 (D15).
hexpad used P0.29 for a key GPIO after checking the firmware. This is a fixed property of a
very common module, not a per-project fact: enumerate once here, cite it, do not re-derive.

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

### The courtyard is SMALLER than the module — 2.02 mm smaller

A 2×12 footprint's courtyard is normally drawn around the **pad grid**, not the module
body. Measured on hexpad's `MCU_nice_nano_v2`: courtyard **18.28 × 30.98 mm** against a
module outline of **17.78 × 33.00 mm**. The body overhangs its own courtyard by ~1.0 mm at
each end (pads run 2.53 … 30.47 in the part's local frame, i.e. 2.53 mm inside each edge).

This inverts the usual enclosure rule. `references/mechanical.md` §4 says to check
openings against the courtyard *rather than* the nominal body — correct when the courtyard
is the larger of the two, which is the normal case. For a socketed module it is the
smaller one, and a deck window sized on courtyards alone leaves a ~1.0 mm lip of plastic
reaching over a module that stands 1.30 mm **proud** of the plate. Every clearance check
passes: the courtyard said nothing was there.

Use `courtyard ∪ datasheet body` for the obstacle rect, and **assert the relation** so a
later footprint edit that "fixes" the courtyard cannot silently move the window. hexpad
does exactly this (`MCU1 body south edge 33.00 exceeds its courtyard 31.99`).

**Sharper, from hexpad rev 2: NEITHER rect alone bounds the module — the union is not
belt-and-braces, it is required.** Same footprint, rotated −90°, measured off the board:

| | courtyard | body | who overhangs |
|---|---|---|---|
| along the module's LENGTH | 19.635 … 50.615 | **18.625 … 51.625** | body, by **1.010 mm at each end** |
| across its WIDTH | **0.500 … 18.780** | 0.750 … 18.530 | courtyard, by **0.250 mm per side** |

The body wins on the long axis (the pad grid stops 2.53 mm inside each short edge); the
courtyard wins on the short axis (silk/fab margin). Sizing on the body alone loses 0.25 mm
per side; sizing on the courtyard alone lays 1.01 mm of deck over a module that stands
proud of the plate. Assert **both** relations in **both** directions, or a future footprint
edit "correcting" either one moves your opening.

`kicad_geom.py --json` still exports no body rectangle (only `courtyard` and `pads_bbox`),
so the body comes from this card and must be asserted against the footprint's own origin
and rotation. Compute it through the part's rotated frame, never by hand: the footprint is
drawn long-axis-along-**local y**, so its local half-extents are `(WID/2, LEN/2)` and it is
a **−90°** placement that lays the 33 mm axis along board x.

### USB out a side edge, module rotated

Rotating the module 90° so USB exits a side edge works and changes three numbers. From
hexpad rev 2 (module at rot −90, USB east):

- the **USB-C shell** is `local x ±USB_W/2` by `local y −LEN/2−0.60 … −LEN/2+7.35` — i.e.
  **8.94 mm across × 7.35 mm deep including the 0.60 mm overhang**. Placed: a 7.35 mm-deep
  shell reaching 0.60 mm past the board edge.
- a **nice!view laid over the module along its long axis** then sits *beside* the
  receptacle rather than on top of it: set the display back 7.00 mm from that edge and its
  envelope stops **0.25 mm short** of the shell, which removes the display-vs-shell z
  clearance from the design entirely (see `nice-view-display.md` §2a).
- the case's wall on that edge now carries **both** the USB notch (above the board plane)
  and whatever is under the module on the back face (hexpad: the slide switch, below it).
  Assert the **web** between them, not just each opening: hexpad's is
  `usb_floor(+1.20) − slot_ceiling(−1.60) = 2.80 mm` of full-thickness wall.

### Enclosure treatment that works, with numbers (hexpad, `verify()`-passing)

For a socketed module with USB out a wall, deck at +3.50 and a 6.30 mm stack:

| Feature | Resolution |
|---|---|
| deck over the module | **open window**, `courtyard ∪ body` + 0.30 keepout. Not a raised bay: a bay stands proud of the print's plate-down reference face. |
| USB-C opening | an open **notch** in the wall, floor at z = **+1.20** (port axis 4.70 − 7.0/2), cut clean through the wall and open above its top. No bridge — the notch reaches the first layer. |
| opening width | **12.0 mm** for an 8.94 mm receptacle shell: ≈1.5 mm each side, and it admits a chunky plug overmold. |
| why "clean through" | the shell overhangs the board edge by 0.60 mm and a typical cavity inset is 0.30 mm, so the shell reaches **0.30 mm into the wall**. A recess fouls it. |

## Flipping it to the other face

Turning the module over maps hole *i* onto pad *25−i*, pairing RAW↔D1, RST↔GND and
VCC↔GND — **two dead shorts**, so two faces cannot share one 24-hole grid. Use two
interleaved grids (48 holes) offset **purely across by one full pitch**; see
`references/electronics.md` §9 for why the diagonal offset is the wrong choice.
