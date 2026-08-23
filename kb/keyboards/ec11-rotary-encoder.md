---
domain: keyboards/mcu
tags: [ec11, ec11e, alps, pec11r, rotary-encoder, encoder, push-switch, kicad-stock, 3d-model, hexpad, quadrature, knob, deck-opening, enclosure]
source: hexpad resource-scout run, 2026-08-23 — KiCad 10 stock library (Rotary_Encoder.pretty), tech.alpsalpine.com official product pages, DigiKey/Mouser distributor listings, ceoloide/ergogen-footprints rotary_encoder_ec11_ec12.js, KiCad/kicad-packages3D PR #549 (horfee); hexpad rev-3.1 phase-6 case run, 2026-08-23 (case/hexpad_case.py, 416-check verify() pass) — see 5a
date: 2026-08-23
confidence: researched
---

# EC11-class rotary encoder (with push switch)

Researched for **hexpad L10** (rotary encoder in the north strip, ~aligned to
the col-1 key column). Covers part selection, the two-source pin table, a
real KiCad-library trap this run caught, dimensions, detent/pulse spec, and
the 3D model situation.

## 1. Part decision

**Alps Alpine EC11E15244B2** — 15 pulses/revolution, 30 detents/revolution,
φ6mm metal shaft (knurled/flat/slotted variants exist), "H20mm" shaft-length
class, **with** an integrated SPST push-on switch, 5 electrical terminals +
2 mechanical mounting bosses, through-hole. In stock at DigiKey and Mouser.
Two-source verified: [tech.alpsalpine.com product page](https://tech.alpsalpine.com/e/products/detail/EC11E15244B2/)
(official manufacturer) + DigiKey/Mouser distributor listings (independent
lineage, cross-referencing the same manufacturer datasheet but confirming
stock/part-active status and the switch feature independently).

### The trap this run caught: KiCad's own stock footprint cites the wrong sibling part

KiCad 10 ships `Rotary_Encoder.pretty/RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm.kicad_mod`
— note the name says **-Switch-**, and it has `S1`/`S2` pads. But its own
`descr` field links to `EC11E15204A3` — a **real, in-stock, currently-produced**
Alps part (confirmed via [DigiKey](https://www.digikey.com/en/products/detail/alps-alpine/EC11E15204A3/21721644)
and [Alps Alpine's own page](https://tech.alpsalpine.com/e/products/detail/EC11E15204A3/)),
whose own "Built-in Switch" field is explicitly **No**. The footprint's
citation and the footprint's own pads disagree about whether this is a
switch part. This is the same "silkscreen/citation is not the real part"
trap `resource-scout.md` warns about, just in a datasheet-URL instead of a
silkscreen label. Resolution used here: trust the **pads**, not the citation
— pick a real, in-stock, *with-switch* sibling that matches the pad count and
mechanical class (EC11E15244B2, confirmed 5-pin + switch, H20mm, φ6mm, per
§1 above), and use the KiCad stock footprint's geometry as-is (Alps'
switch and non-switch H20mm variants in this sub-family share one common PCB
footprint — the pad positions are not in question, only the citation is).
**Do not trust a footprint's own `descr`/`Datasheet` field to name the right
part without checking the pads agree with what that part actually is.**

### Alternative not chosen

`ceoloide/ergogen-footprints` `rotary_encoder_ec11_ec12.js` (MIT licensed)
generates a compact, reversible EC11/EC12 footprint aimed at co-locating an
encoder in a keyswitch position on an ultra-compact split — its reference
part, Alps EC12E2440301, is a **short through-shaft encoder with no
switch**. Not chosen for hexpad: the SPEC calls for a knob the user can grip
outside the case, which wants the tall H20mm shaft class, not a flush
through-shaft one. Its file was still useful — see §2's trap note.

## 2. Two-source pin table (and a labeling trap)

| KiCad pad | Physical position (H20mm footprint) | Function |
|---|---|---|
| `A` | (0, 0) — rect, pin-1 marker | Quadrature output A |
| `C` | (0, 2.5) — **physical middle** of the 3-pad row | **Common** (ground reference for A/B) |
| `B` | (0, 5) | Quadrature output B |
| `MP` ×2 | (7.5, −3.1) and (7.5, 8.1) | Mounting bosses, mechanical only, not netted |
| `S1` | (14.5, 5) | Switch terminal 1 |
| `S2` | (14.5, 0) | Switch terminal 2 (SPST push-on, no polarity) |

Two-source agreement on **function** (which role each terminal plays, not
raw coordinates): the official Alps Alpine product pages (which describe "two
output signals A and B plus a push-on switch" with the third encoder terminal
as the ground/common reference) and an independent web aggregation of
multiple EC11-family datasheets (Cirkit Designer's EC11 pinout guide: "the
other two (A and B) provide rotation signal relative to the third pin (C),
which is normally connected to ground"). Pad **coordinates** are taken
directly from the KiCad stock footprint file, which is the actual artifact
this project uses — not independently re-measured against a physical part.

**Labeling trap, caught by comparing to a second footprint family**: the
*letter* assigned to the common/ground terminal is **not consistent across
footprint authors**, only its *physical position* (middle of the 3-pad row)
is. KiCad's stock EC11E footprint calls the middle pad `C`. The independent
`ceoloide/ergogen-footprints` `rotary_encoder_ec11_ec12.js` generator puts
its middle pad's default net at `GND` but names that pad **`B`** (its `A`
and `C` are the two quadrature signals, one on each side). **Never trust a
pin letter alone across two encoder footprints/datasheets — confirm by
physical position (the common terminal is always the one in the middle of
the 3-pad row) before wiring firmware or a schematic net.**

## 3. Dimensions, shaft/knob, and case implications

- Body: "11mm size" class (Alps' own sizing name — footprint's own F.Fab
  outline is ~11 × 11.6mm), courtyard extends to ~17.5 × 14.2mm once the
  switch pads and silkscreen clearance are included (read directly from the
  stock `.kicad_mod`).
- Shaft: **φ6mm**, metal, "H20mm" class = 20mm actuator length (confirmed
  matching the footprint's own name suffix against the Alps Alpine product
  page's "flat actuator... measuring 20mm in length" for both EC11E15204A3
  and EC11E15244B2 — the H20mm figure is the **shaft length above the
  encoder's own mounting face**, not above the PCB; add the encoder body's
  own seated height between the PCB and its mounting face when computing
  deck-hole clearance, which was **not found in either source
  (needs-verification)** — typical Alps EC11E THT bodies seat close to the
  PCB (no socket/standoff, soldered flush), so as a working assumption the
  20mm figure is close to "shaft length above the PCB" but this has not been
  measured or confirmed against a mechanical drawing.
- Knob assumption: a 20mm-long φ6mm flatted shaft is the common "arcade knob"
  class used across hobbyist keyboard builds (matches, e.g., the shaft class
  Sofle/other community boards use per the general encoder-mounting
  references found during this run) — assume a generic press-fit knob
  (~10–15mm OD cap) sized for a flatted 6mm shaft, and give the case's deck
  hole clearance for that knob OD, not just the bare shaft. **Not
  confirmed against a specific knob part** — flagged for whoever picks the
  physical knob to buy.
- Recommend the case's deck hole be sized off the shaft, not the body: the
  body sits below the deck (inside the case), only the shaft/knob protrudes
  through it.

## 4. Detent/pulse spec for ZMK

EC11E15244B2: **15 pulses per revolution, 30 detents per revolution** (i.e.
2 detents per electrical pulse — a common EC11-family ratio, not 1:1). ZMK's
`ec11` sensor driver (`&<name> { steps = <N>; };` or the newer
`resolution`/`sensor-binding` config depending on ZMK release) needs the
**pulse** count, not the detent count, for one-detent-per-step behavior —
using the detent count instead would make the encoder feel like it fires
every-other-detent, or double-fires, depending on which number is fed in.
**This project's exact ZMK config keys were not re-verified against the
current ZMK release in this pass** (firmware is out of scope per SPEC.md
L9) — flagged for whoever wires the ZMK devicetree: confirm which of the
two counts the specific `ec11` binding config field wants before trusting
"15" or "30" blindly.

## 5. 3D model

**No 3D model for any `Rotary_Encoder.pretty` footprint ships in KiCad 10**
(confirmed by direct filesystem check — the local `3dmodels/` directory has
no `Rotary_Encoder.3dshapes` entry among its 107 category directories — and
confirmed a second way: `KiCad/kicad-packages3D`'s upstream GitHub mirror
returns 404 for that path). This is a long-standing, **tracked, still-open**
upstream gap: [Issue #547](https://github.com/KiCad/kicad-packages3D/issues/547)
(opened 2019) and [PR #549](https://github.com/KiCad/kicad-packages3D/pull/549)
(a real STEP+WRL pair for exactly `RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm`,
built with FreeCAD/KiCad StepUp by contributor `horfee`) have sat **unmerged**
since 2019–2020, when the repo was archived and migrated to GitLab. **Vendored
into `hexpad/lib/3dmodels/` from the PR's fork** (`horfee/kicad-packages3D`
commit `7a1d016fbda6eb6f7ae842b31ead5cd162b98a05`), under the target repo's
CC-BY-SA 4.0 terms (a PR submitted to a CC-BY-SA-4.0 repo is offered under
that license by GitHub contribution norms; not independently re-licensed by
the contributor). This is the exact filename the stock footprint's own
`(model ...)` reference expects, so linking it back to
`${KICAD10_3DMODEL_DIR}/Rotary_Encoder.3dshapes/...` or a project-local
equivalent path should work without editing the footprint.

## 5a. Case answers, closed by hexpad rev 3.1 (`verify()`-passing, 416 checks)

§3 left two questions for the case phase and recommended sizing the deck hole
off the shaft rather than the body. Both are answered now, and one of them
turned out not to matter.

- **The body height never reaches the case.** Whatever it is, it exceeds the
  3.50 mm of clearance under a 1.5 mm MX plate, so the deck has to be an open
  window over the encoder and the case is **insensitive** to the figure. hexpad
  asserts that at *both* cited values — 7 mm and 11 mm — instead of picking one.
  So `needs-verification` on the body height no longer blocks an enclosure; it
  only blocks an accurate rendered assembly.
- **Size the deck opening as a bay rect plus a separate DISC at the shaft, not
  one rectangle.** §3's "size it off the shaft" is right, and the reason to keep
  the knob's extra reach *local* is that a rectangle grown to swallow a 10–15 mm
  knob reaches ~7.8 mm in every direction from the shaft, and will eat whatever
  the strip's other fasteners are. Numbers that worked:
  `disc_r = knob_od/2 + 0.300` (6.800 for a 13 mm knob), merged into the west end
  of the module/display bay rect, reaching 0.700 mm west of it and staying inside
  it in y. On hexpad rev 3 that disc was the difference between clearing a
  mounting boss by 9 mm and missing it by 0.020 mm.
- **Shaft proud of the deck**, on the H20mm class seated flush (§3's working
  assumption): 20.00 − 5.00 (plate top above the PCB) = **15.00 mm**, which is
  ~5.5 mm above a 1u keycap's top plane — so the knob is gripable and stands
  clear of the caps. Budget a knob whose bore is ≤ 15 mm deep.
- **The disc is sized by the knob, never by the shaft**: `disc_r − shaft_r` is
  3.800 mm on the numbers above. Make the knob OD a parameter — on hexpad nothing
  but the disc depends on it, and even the 15 mm end of the band cleared the
  nearest fastener seat by 5.942 mm.

Worked: `hexpad/case/hexpad_case.py` (`knob_od`, `knob_band`, `enc_shaft_len`,
`enc_body_h` / `enc_body_h_alt`).

## 6. Open items

- Encoder body height above the PCB — still not found, `needs-verification`.
  **No longer blocks a case** (see §5a); it does block an accurate 3D assembly,
  and hexpad's own two inputs disagree (7 mm vs 11 mm).
- Exact knob part — not chosen, flagged for the case/BOM phase.
- ZMK `ec11` binding's exact config field semantics (pulses vs. detents) —
  not re-verified against current ZMK, flagged for the firmware-facing phase.
- The vendored PR #549 model has never been merged upstream or used in a
  shipped design as far as this run found — treat its geometry as
  `researched`, not `verified-in-cad`, until a hexpad board actually renders
  it without a 3D-viewer error.
