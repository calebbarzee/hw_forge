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

**The required form of this rule is three assertions, not the prose above.** Every project that carries a size code carries the dimensions too, so check that they agree:

```python
v.equals("size code thickness", float(code[0:2]) / 10.0, p.bat_thk)
v.equals("size code width",     float(code[2:4]),        p.bat_wid)
v.equals("size code length",    float(code[4:6]),        p.bat_len)
```

It is the cheapest possible check and it caught a real error on its first outing: a handoff described a **503035** as "50 × 30", reading the leading `50` as a length. It means **5.0 × 30 × 35 mm** — a 35 mm cell, not a 50 mm one, and the bay being recommended for it would have been **14.4 mm longer than the cell**. A cell part number that disagrees with its own dimensions is always a **spec error**, never a rounding one; fix the spec, do not widen a tolerance.

**Thickness is the number that drives enclosure height. Plan area is almost never the constraint** in a flat device — choose the cell on thickness, then check the footprint fits a boss-free band. **When it *is* the constraint, "find a thinner cell" does not help at all**: see §7 for the order of operations that separates the plan constraint from the vertical one.

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

Sanity check any figure you are told: for cells of this class, **capacity ≈ 0.08–0.12 mAh per mm³** of enclosed volume. The band is **two-tier**, and the tier is set by **plan footprint**, not by volume:

| Tier | Families | mAh/mm³ |
|---|---|---|
| Small plan footprint (≲1100 mm²) | 12×30, 20×30, 25×35, 30×35 | **0.08–0.105** |
| Large flat | 34×50 | **0.11–0.12** |

Every row above sits inside its own tier: 301230 0.102, 401230 0.104, 402030 0.083, 502030 0.083, 602030 0.083, 503035 0.095, 602535 0.095, 303450 0.118, 403450 0.118, 503450 0.118, 803450 0.114. Packaging overhead dominates a small footprint — the tiers are that effect, quantified.

**Apply the ~30 %-off marketing test against the relevant tier, not against the overall band.** The doctrine tells a project to code a plausibility sentence as an assertion, and the previous single band (0.10–0.12) failed **five of the eleven rows above** — exactly the small-footprint ones — so the first small cell considered produced a false failure. A band a catalogue row cannot pass is a bug in the band.

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

**Order of operations when plan area is the binding constraint.** "Only thickness varies" holds once the bay footprint fits; getting it to fit is a separate derivation, and a thinner cell buys nothing:

1. Derive the bay's **plan** constraint from the **full-height obstacles only** — fastener bosses, walls, ribs: things that reach from floor to board. Nothing else can touch it.
2. Derive the bay's **vertical** constraint separately, from the parts standing over the bay's own footprint (§3).
3. A single "guaranteed clear rectangle" handed over by a PCB phase **conflates the two and always comes out too small.** (hexpad: the handed-over band was 34.0 mm for a 34 mm-wide cell — zero room for the mandatory 0.6 mm of in-plane slop (§3, `mechanical.md` §5), before ribs or a 3.10 mm boss keepout. The cell's top plane sits 2.60 mm under the PCB and clears every part on the underside, so only the screw bosses actually constrained it in plan.)
4. **A bay handoff emits TWO things or neither** — the component-keepout rectangle **and** the full-height obstacle list (bosses, ribs, walls) with their own geometry. **The rectangle bounds components, not cavities; intersect it with the fastener geometry before placing a cell.** Getting every edge's derivation right does not fix this, because a rectangle is still a single rectangle: on any real board it overlaps the boss seats in its own corners, so a phase that consumes the rectangle and trusts it **places a cell through a fastener.** A prose caveat beside the numbers is not a fix — the rectangle is the machine-readable part and the caveat is not. (Measured: a corrected handoff emitted `x −11.000…51.125, y 19.280…62.075`, right derivation per edge, plus a note that two boss seats "intrude on the south corners" — and a real overlap with two Ø5.600 seats. The consumer asserted that overlap *deliberately*, with `case_verify.Suite.interferes()`, so nobody can later "fix" the rectangle back, and put the pocket in the bay's north half instead — which as a bonus made the retention fence free-standing for the first time.)

- The bay footprint is shared by a whole length/width family (e.g. everything `xx3450`), so only **thickness** varies.
- Make `cell_thk`, `cell_len`, `cell_wid` parameters; let cavity depth, case height and **screw length** derive from them. A thinner cell shortens the cavity, which shortens the screw — the generator must print the computed length rather than the doc asserting one.
- Publish the family as a table so a user can substitute without re-running CAD:

| Cell | Capacity | `cell_thk` | Case height | Screw |
|---|---|---|---|---|
| 303450 | ~600 mAh | 3.0 | 15.2 mm | M2 × 12 |
| 403450 | ~800 mAh | 4.0 | 16.2 mm | M2 × 12 |
| **503450** | **~1000 mAh** | **5.0** | **17.2 mm** | **M2 × 14** |

**"Bay" is two nouns; name which one every assertion is about.** The **pocket** is the volume the cell occupies; the **fence** is the pocket plus its 1.6 mm ribs. Assert in `verify()`, with the right noun on each, and report the nearest offender by name:

1. **Pocket** vs every fastener boss — the 0.30 mm keepout.
2. **Pocket** vs every part taller than the bay's own clearance budget.
3. **Fence** sits inside the cavity, with rib thickness to spare.
4. **Fence top z** below the underside bound.

**A fence may merge with a boss.** A rib and a boss are both plastic on the same printed part, so a merge is not an interference — it stiffens the fence. And `mechanical.md` §4's 0.30 mm keepout is explicitly "clearance to any **component**": a boss is not a component.

One ambiguous noun is worth a 2× capacity difference. (hexpad rev 1 read "bay" as the fence and got away with it because the board was long enough. Rev 2's board is 15.6 mm shorter: under the fence reading — fence held 3.10 mm off the H1/H2 bosses — a 34 mm-wide cell has **no legal placement at all**, and the handoff concluded the 503450 did not fit and recommended a ~500 mAh cell. Under the pocket reading, which is what the physical requirement is, the full four-sided fence fits, the two bosses simply **fuse into its southern corners**, and the pocket still stands 1.205 mm clear of both: 1000 mAh, not 500.)

- Record which spec the bay *superseded* and why. A cell chosen early against a guessed height budget is the most common stale number in a hardware spec: one project's 110 mAh cell became a 1000 mAh cell, and it cost +3.1 mm of case height — all of it in the bottom cavity.
