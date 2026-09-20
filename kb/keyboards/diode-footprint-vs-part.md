---
domain: keyboards/parts
tags: [diode, sod-123, 1n4148w, footprint-vs-part, package-verification, assembly, z_board, hexpad, kicad_fpcheck]
source: z_board v0.4 (kicad/design.py, kicad/left/zboard_left.kicad_pcb, kicad/lib/zboard_kbd.pretty); hexpad (kicad/design.py, kicad/hexpad.kicad_pcb); user report of an assembly-time fit problem
date: 2026-09-20
confidence: needs-verification
---

# Per-key diode footprint vs. the part actually supplied

At assembly, a keyboard project's per-key diode footprint was reported as
slightly too large for the diode that was actually supplied. This card
records what the design files say, what was measured directly out of the
board files, and what is not known. Confidence is `needs-verification`
because the supplied part's identity and its actual dimensions were never
recorded; do not read the numbers below as a resolved incident.

## Scope

Both `z_board` (`kicad/design.py`, tested against
`kicad/left/zboard_left.kicad_pcb`) and `hexpad` (`kicad/design.py`,
`kicad/hexpad.kicad_pcb`) declare the same diode, by the same three
constants:

```python
SYM_DIODE = ("Device", "D")
FP_DIODE  = "Diode_SMD:D_SOD-123"                  # stock
DIODE_VALUE = "1N4148W"
```

`Diode_SMD:D_SOD-123` is KiCad's stock footprint (not project-vendored), and
`1N4148W` is, per every major manufacturer's datasheet (Nexperia, Vishay,
Diodes Inc.), nominally a SOD-123 part. The design files are internally
consistent: the declared part and the declared footprint name the same
package family. That consistency is exactly why no gate in the pipeline
flagged anything: ERC, DRC, and schematic parity all compare board to
schematic, and this was never a board-vs-schematic disagreement.

## Geometry, read out of the actual board file

Read with `python3 scripts/kicad_geom.py` and `python3
scripts/kicad_fpcheck.py` against `z_board/kicad/left/zboard_left.kicad_pcb`
(22 diode instances, D1–D22 minus gaps). Every instance measures identically,
confirming the footprint on the board is the unmodified KiCad stock
`D_SOD-123`, not a project-customized copy:

| Quantity | Value | Source |
|---|---|---|
| Pad outer span (lead-to-lead) | 4.20 mm | `pads_bbox` / `kicad_fpcheck.py` span_long |
| Pad height | 1.20 mm | `pads_bbox` / `kicad_fpcheck.py` span_short |
| Pad inner gap (facing edges) | 2.40 mm | `kicad_fpcheck.py` gap |
| Body (F.Fab outline) | 2.80 × 1.80 mm | `body_bbox` |
| Courtyard | 4.70 × 2.30 mm | `courtyard` |
| Rotation on board | 180° (varies by instance) | `rotation` |
| Side | bottom (`pad_side` = bottom, `protrudes` = [bottom]) | `pad_side`/`protrudes` |

`kicad_fpcheck.py Diode_SMD:D_SOD-123` against `packages.json`'s `SOD-123`
entry (nominal body 2.675 × 1.6 mm, Nexperia SOD123.pdf) reports every
instance **PASS**, because the footprint matches its own declared package
exactly: it IS the stock footprint, measured against the same stock
footprint's own geometry. That is a necessary check and it is not the one
this incident needed: **the gap (2.40 mm) leaves only 0.275 mm of the
nominal 2.675 mm body length as margin to bridge the pads (0.14 mm on each
side).** That is a tight tolerance by design, not a defect, since SOD-123's own
land pattern is drawn this way industry-wide, but it means a supplied part
even slightly under nominal body length will not comfortably span the pads.
See `kb/parts/package-family-traps.md` for the general form of this trap.

## What is not known

- **The exact part number actually supplied and soldered.** Neither
  project's files, notes, or provenance records name it. Do not infer one;
  if it becomes known, correct this card and raise its confidence.
- **The measured dimensions of the supplied part.** No caliper reading or
  datasheet for the actual unit is on record.
- **Whether the mismatch was the body being short, the leads being
  narrower, or a different SOD variant entirely** (SOD-123F is longer than
  plain SOD-123, not shorter, see `kb/parts/package-family-traps.md`,
  so a same-named substitute is not automatically the same size in either
  direction).
- **Whether this was a one-off supplier substitution or a class of part
  routinely undersized against nominal SOD-123.**

## What this does and does not mean for future boards

This is a receiving-inspection / supply-chain problem, not a design-file
problem: the design's own declared package and its footprint agree, and
`kicad_fpcheck.py --design design.py` reports a clean PASS on this exact
footprint because there is nothing in the design files for it to disagree
with. A design-time package check cannot see what a supplier ships instead
of what was ordered. See `docs/BACKLOG.md` B3 for the open half of this
problem and what would be needed to close it (hardware-in-the-loop component
measurement, out of scope for a design-time pipeline check).

What a design-time check DOES catch, a different, design-file-only failure
where the declared package and the laid-down footprint disagree with each
other, is `kicad_fpcheck.py`'s actual job; see
`kb/parts/package-family-traps.md` for the incident that motivates it. When
that check does fire, on this board or a future one, the fix is not a note
in a card: fork the stock footprint into the project library with
`scripts/kicad_fplib.py fork`, apply the correction (`set-pads` for a pad
size or position, `set-model` for a 3D model), and record the source with
`annotate`. This card's own 0.275 mm margin finding is exactly the kind of
number that would justify a `set-pads` change on a project that wants more
margin than SOD-123's own land pattern gives by default: enlarging the pads
(or moving them closer together) narrows the gap `kicad_fpcheck.py` measures
and gives a body even slightly under nominal length more copper to bridge.
See `kb/README.md`'s "where a fact lives" table for why the library, not the
card, is where that change belongs.
