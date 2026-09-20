---
domain: keyboards/silkscreen
tags: [silkscreen, drc, readability, z_board, combo, dongle, kicad_silkcheck, jlcpcb]
source: z_board combo v2 + dongle v1 silkscreen readability pass, 2026-09-20
date: 2026-09-20
confidence: verified-in-cad
---

# z_board's silkscreen readability pass: what v1 shipped with, what closed it

Generic rule set, placement algorithm and glyph-metric calibration live in
`skills/hw-design/references/silkscreen.md`. This card is the source
measurement that reference was written from, and the two project-specific
numbers (the dongle's margin budget, the combo board's per-key refdes count)
that do not generalize to every board.

## The v1 combo board, measured

`git show HEAD:kicad/combo/zboard_combo.kicad_pcb` at commit `599f1e11`, 123
footprints. 9 reference designators visible (`H1`-`H6`, `C23`, `C24`,
`SW_PWR`) -- 7.3%. Zero board-level `gr_text` items of any kind: no board
name, no version, no hand mark, no connector polarity, no MCU pin names.
`kicad-cli pcb drc --severity-all`: 117 `lib_footprint_issues` (unrelated
library metadata drift) and **zero** `silk_*` findings -- DRC has nothing to
say about any of the above. `scripts/kicad_silkcheck.py`, the tool this
project's silkscreen pass added:

```
combo_v1.kicad_pcb: 504 silk text item(s), 15 visible
  silkcheck   FAIL  text_over_pad x13, label_missing x4, text_rotation x1
```

13 `text_over_pad`: 4 from `C23`/`C24`'s own default ref position sitting
across their own pads, 7 from `SW_PWR`'s (five of its own pads plus two
GND-plane vias), 2 from mounting-hole refdes within 0.25mm of a nearby
stitching via. 1 `text_rotation`: `SW_PWR`'s refdes inherited the part's own
270-degree placement rotation (KiCad rotates a footprint's child text angle
with the footprint unless something resets it), unreadable against a
0-degree reading orientation. Full table: `kicad/combo/SILK.md` in the
z_board repo.

## The fix, and the one real bug it found along the way

Every fix went through the generator (`kicad/gen_combo.py`,
`kicad/design_combo.py`, `kicad/mklib_rev.py` for z_board; mirrored in
`kicad/dongle/gen_pcb.py`), never a hand edit to the `.kicad_pcb`. A generic
`Builder.place_label()`/`Builder.reveal_ref()` candidate search (see the
reference for the algorithm) that only takes a position clearing every real
pad/via/hole/other-label bounding box, queried off the board built so far.

**The bug**: the first version of `collect_geometry()`'s obstacle collector
filtered footprint silk graphics by `item.GetLayerName() in ("F.SilkS",
"B.SilkS")`. `GetLayerName()` returns KiCad's *human-readable* layer name
("F.Silkscreen"), not the canonical one ("F.SilkS") -- the string comparison
was silently always false, so no footprint-owned silk graphic (corner ticks,
cathode bars, a module's USB-end marker) was ever in the obstacle set for an
entire first generation pass. `place_label()`/`reveal_ref()` reported success
on every call; the DRC run immediately after found 3 real `silk_overlap`
findings against exactly the excluded items. Fix: compare `item.GetLayer()`
(the integer layer ID, `pcbnew.F_SilkS`/`pcbnew.B_SilkS`) instead of the
string. Measured lesson for any future obstacle-collection code against
`pcbnew`: never filter a layer by its display-name string.

**The other bug** (glyph metrics): a first pass estimated text width at
0.65mm/character with no fixed overhead. Measured against real
`pcbnew.PCB_TEXT.GetBoundingBox()`, every string came out wider than modelled
(`'SW_RST'`: 5.821mm real against 3.9mm modelled) -- recalibrated to
`width = (0.5 + chars) * 1.0mm`, `height = 1.8 * text_height` at 1.0mm text
height. See the reference doc for the full measurement table.

## Fixed board, measured

```
zboard_combo.kicad_pcb: 509 silk text item(s), 21 visible
  silkcheck   ok
```

`kicad-cli pcb drc --severity-all`: 2 `isolated_copper` (pre-existing,
unrelated to silk -- present in a silk-free regeneration of the same
pre-pass generator too, confirmed by reverting the silk-only edits and
rebuilding), zero `silk_*`. `kicad_digest.py --compare` between the pre-pass
and post-pass boards: every differing canonical line is a silk-layer
property (`gr_text`, `(justify mirror)`, a revealed refdes's `(at ...)`,
the LED footprint's new DIN-polarity notch line) -- no pad, track, via or
net line differs. Copper is unchanged; this was a silk-only pass.

## The dongle board's margin budget: real numbers, not every label fits

25.0 x 18.0mm outline, an internal-antenna module whose own stock footprint
carries a real copper keepout zone (12.4 x 3.75mm, `RF_Module.pretty/
Raytac_MDBT50Q.kicad_mod`), a 16-pin 0.5mm-pitch USB-C connector, and a
castellated module edge running the full south margin (pins 18-31, x
14.4-20.4, no gap wider than a pad pitch). Measured, not estimated: the
widest contiguous silk-clear run on either the north or south margin, after
the antenna keepout's own outline claims its share, is 8.38mm.

Consequences, all in `kicad/dongle/gen_pcb.py`'s own `add_silk_labels()`
comments:

- "dongle v1 2026-09-20" (~21.5mm estimated) and even "dongle v1" alone
  (~9.5mm) never clear any margin anchor. "DONGLE" (~6.5mm) and "V1"
  (~2.5mm) were tried as two separate labels; only "DONGLE" fits, and only
  once the antenna keepout is drawn *first* in the obstacle set (see the
  reference doc's priority-ordering note -- the first draft drew the board-id
  text first, which let it claim the exact strip the keepout needed, and the
  keepout came back `silk_overlap` when drawn second).
- D+/D-/VBUS/GND labels at the USB-C connector's own signal pads: attempted
  at all four pads, none clear (0.5mm pad pitch on a connector with a
  0603/0805 corridor 2.1mm wide on one side and a castellated module edge on
  the other leaves no candidate radius that does not land on a neighbouring
  pad).
- Every stock footprint's own default refdes position overlapped a
  neighbour's pad or via (`kicad_silkcheck.py`, first pass: 94 `text_over_pad`
  findings across 13 footprints). Hiding every refdes by default and
  revealing through the same candidate search fixed `U1` and `J1`; `D1`,
  `SW1`, `LED1`, `R1`-`R3`, `C1`-`C5` found no clear candidate at any radius
  tried (0.9-2.8mm) and stay hidden.

What did fit: the antenna keepout outline (inset 0.5mm inside the true
keepout rectangle -- never outside it, so "no copper here" stays a true
statement everywhere the drawn line encloses) plus a "NO COPPER" callout,
and the "DONGLE" board-id text. `kicad_silkcheck.py --require "NO COPPER"`
is the project's actual `silk-dongle` gate requirement; the rest are left as
live probes in the generator (their `SILK:`-prefixed stdout lines are the
record), not force-fit by shrinking the text floor below JLCPCB's own
minimum.

## Cross-references

- `skills/hw-design/references/silkscreen.md` -- the generic rule set,
  placement algorithm, and the two bugs generalized as lessons.
- `kicad/combo/SILK.md` (z_board repo) -- the full v1 defect table.
- `kb/fabs/jlcpcb.md` -- the 0.15mm/1.0mm silk floor this pass cites.
