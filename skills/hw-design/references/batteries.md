# Li-Po cells — sizing, naming, connectors, and the bay

Generic. Which cell a given project actually uses belongs in `kb/`.

## 1. The size code

Pouch-cell part numbers are **six digits encoding dimensions in units of 0.1 mm for the first pair and 1 mm for the rest**:

```
  T T   W W   L L
  └─ thickness ×0.1mm    └─ width mm    └─ length mm

503450  →  5.0 × 34 × 50 mm
301230  →  3.0 × 12 × 30 mm
803450  →  8.0 × 34 × 50 mm
```
Read it as **thickness × width × length**, thickness first and in tenths. Five- and seven-digit variants exist (a leading digit for ≥10 mm thickness, or 4-digit sub-mm codes); when a number does not parse cleanly, get the dimensions from the datasheet rather than guessing.

**Thickness is the number that drives enclosure height. Plan area is almost never the constraint** in a flat device — choose the cell on thickness, then check the footprint fits a boss-free band.

## 2. Common cells

Typical vendor ratings. Treat as a **shortlist for a first pass and verify against the specific vendor's datasheet** — the same size code ships with ±20 % capacity between suppliers, and protected cells are 1–2 mm longer than the code implies (§4).

| Code | Dimensions (mm) | Typical capacity |
|---|---|---|
| 301230 | 3.0 × 12 × 30 | ~110 mAh |
| 401230 | 4.0 × 12 × 30 | ~150 mAh |
| 402030 | 4.0 × 20 × 30 | ~200 mAh |
| 502030 | 5.0 × 20 × 30 | ~250 mAh |
| 602030 | 6.0 × 20 × 30 | ~300 mAh |
| 503035 | 5.0 × 30 × 35 | ~500 mAh |
| 602535 | 6.0 × 25 × 35 | ~500 mAh |
| 303450 | 3.0 × 34 × 50 | ~600 mAh |
| 403450 | 4.0 × 34 × 50 | ~800 mAh |
| **503450** | 5.0 × 34 × 50 | **~1000 mAh** — the reference "1 Ah" cell |
| 803450 | 8.0 × 34 × 50 | ~1500–1600 mAh |

Sanity check any figure you are told: for cells of this class, **capacity ≈ 0.10–0.12 mAh per mm³** of enclosed volume. Small cells sit at the low end (packaging overhead dominates); large flat cells at the high end. A quoted capacity more than ~30 % off that band is a marketing number.

## 3. Swell and the thickness budget

Pouch cells grow. Budget **+0.4 mm on thickness**, or the vendor's specified maximum-after-cycling figure if the datasheet gives one (often stated as thickness after 300–500 cycles, typically +5–10 %).

```
cavity_depth = parts_clear + cell_thk + swell
  where parts_clear = max(height of every part standing over the bay) + keepout
```
Worked (board-mounted cell bay under a PCB): tallest parts over the bay are a hotswap socket at 1.85 mm and a switch pin protrusion at 2.20 mm → `parts_clear = 2.20 + 0.40 = 2.60`; `cavity = 2.60 + 5.00 + 0.40 = 8.00 mm`. That single number then sets the case height **and the screw length** (see `mechanical.md` §2).

Never let a cell bear on a component or on the shell floor under compression. Retain it laterally with a rib fence (1.6 mm thick, 3–4 mm tall, 0.6 mm in-plane slop) and a square of double-sided foam tape, with a **wire-exit notch** (≈6 mm) in the rib on the connector side.

## 4. Protection circuit expectations

- Assume a bare pouch is **unprotected**. A "protected" cell carries a small PCM board under tape at the tab end: over-charge cutoff (~4.25–4.35 V), over-discharge cutoff (~2.4–3.0 V), over-current and short-circuit protection.
- The PCM **adds 1–2 mm to the stated length** and a small local thickness bump. Size the bay from the *assembled* cell, not the size code.
- **Use protected cells** unless the host board provides equivalent protection. A protected cell's own PCM is normally sufficient reason to omit a board-level fuse/PTC and reverse-polarity element — see `electronics.md` §6.
- Protection is not a charger. It cuts off at a fault threshold; it does not do CC/CV.
- Never series- or parallel-connect cells without a matched-pair/BMS discussion; out of scope for single-cell designs.

## 5. Connectors

| System | Pitch | Notes |
|---|---|---|
| **JST-PH 2.0** | 2.00 mm | The hobby-LiPo default; what most cells ship with. Robust, easy to crimp by hand, several amps. Tall — ~6 mm mated body — so it drives enclosure height on thin devices. |
| **Molex Pico-EZmate** | 1.20 mm | **1.65 mm mated height.** Polarised, positive-latch, low profile; the right choice when height matters. Vertical PCB header e.g. `78171-0002` (1×02, with mounting pin); mating pigtail e.g. `78172-0002`. |
| JST-SH 1.0 | 1.00 mm | Signal connector. Usable at low current but the contacts are small; avoid for a rail that will carry hundreds of mA. |
| Solder pads / wires | — | Lowest height and least failure-prone, at the cost of serviceability. Legitimate for a sealed build. |

**Polarity warning — vendor pigtails vary.** A cell shipped with one connector and a pigtail bought for another do not agree on which contact is positive by convention. Wiring a pigtail by colour or by connector orientation has reversed cells. Rules:
1. **Meter the cell's leads before crimping, every time**, and meter the assembled pigtail before first mate.
2. Document the intended polarity **relative to the board's own connector pin 1**, in the assembly instructions, with the pigtail part number.
3. Prefer a polarised, latching connector so the *mate* cannot be reversed once the pigtail is right.
4. Cells rarely ship with the connector you designed for: expect to need a `PH → target` adapter or a crimp/solder step, and put that step in the BOM.

## 6. Charge and discharge rates

```
C_charge    = I_charger / capacity_Ah          # 0.2C gentle, 0.5C typical max, 1C only if rated
minimum_cell = I_charger / C_charge_max_rated  # a fixed charger sets a MINIMUM cell size
C_discharge = I_load / capacity_Ah
runtime_h   = capacity_mAh / I_load_mA         # times ~0.8 for usable capacity
```
- A module with a **fixed** charge current makes cell choice a safety question, not a preference: a 100 mA charger is 0.2C into a 500 mAh cell (safe, ~6 h from empty) but ~0.9C into a 110 mAh one.
- State the working load as a C-rate so it can be checked against the cell as well as against the regulator: `300 mA from 500 mAh = 0.6C`, fine for any normal Li-Po.
- **Runtime is usually set by the duty cycle of one optional subsystem, not by the cell.** Quote it as a range with the assumption named: e.g. subsystem gated off → weeks; subsystem at its working ceiling → ~1.6 h. That table is what tells the user whether a bigger cell or a lower cap is the fix.
- End-of-discharge check: the *high-current* rail hits regulator dropout well before a low-power MCU browns out. See `electronics.md` §5.

## 7. The drop-in-family documentation pattern

**Design the bay for the largest cell you would ever fit; document the smaller compatibles as a table with every downstream dimension adjusted.**

- The bay footprint is shared by a whole length/width family (e.g. everything `xx3450`), so only **thickness** varies.
- Make `cell_thk`, `cell_len`, `cell_wid` parameters; let cavity depth, case height and **screw length** derive from them. A thinner cell shortens the cavity, which shortens the screw — the generator must print the computed length rather than the doc asserting one.
- Publish the family as a table so a user can substitute without re-running CAD:

| Cell | Capacity | `cell_thk` | Case height | Screw |
|---|---|---|---|---|
| 303450 | ~600 mAh | 3.0 | 15.2 mm | M2 × 12 |
| 403450 | ~800 mAh | 4.0 | 16.2 mm | M2 × 12 |
| **503450** | **~1000 mAh** | **5.0** | **17.2 mm** | **M2 × 14** |

- Assert in `verify()` that the bay rectangle: sits inside the cavity with rib thickness to spare; is clear of every fastener boss; and does **not** overlap any part taller than the bay's own clearance budget. Report the nearest offender by name.
- Record which spec the bay *superseded* and why. A cell chosen early against a guessed height budget is the most common stale number in a hardware spec: one project's 110 mAh cell became a 1000 mAh cell, and it cost +3.1 mm of case height — all of it in the bottom cavity.
