---
domain: parts/packages
tags: [package-family, soic, sop, sod-123, sod-123f, sod-323, footprint-selection, kicad_fpcheck, jedec, ipc-7351, fable-5]
source: a6mzero.com, "This PCB is brought to you by Fable 5" (blog post, agent-designed RP2350 board); scripts/packages.json (JEDEC/manufacturer citations, retrieved 2026-09-20); kb/keyboards/diode-footprint-vs-part.md
date: 2026-09-20
confidence: researched
---

# Package family traps: same name, different part; same silhouette, different family

Two ways a footprint can be the wrong physical size for its declared part
without any design rule check (DRC), electrical rule check (ERC), or
schematic parity check ever seeing it. Both are what
`scripts/kicad_fpcheck.py` exists to catch; see that script's module
docstring for the check itself.

## 1. SOIC-8 wide vs. SOP-8 (SOIC-8) narrow: a family mismatch, not a tolerance problem

An agent-designed RP2350 board (a6mzero.com, "This PCB is brought to you by
Fable 5") selected a `W25Q128JVS` SPI flash, which every major distributor
lists in SOIC-8 **wide** body (JEDEC MS-013, 7.5 mm body width), and laid
down an SOIC-8/SOP-8 **narrow** body footprint (JEDEC MS-012, 3.9 mm body
width) for it. A separate part on the same board, a boost-converter
transistor, had a real package smaller than the pads drawn for it. Every DRC
passed on both. Both were caught only after the files reached JLCPCB for
assembly, and the resolution was a part substitution (to `P25Q64SH`) after
back-and-forth with the fab.

This is not a tolerance problem, narrow and wide SOIC-8 do not overlap by
any reasonable margin:

| | Body width | Pad outer span (lead-to-lead) | Pitch |
|---|---|---|---|
| SOIC-8 narrow (MS-012) | 3.9 mm | 6.90 mm | 1.27 mm |
| SOIC-8 wide (MS-013) | 7.5 mm | 12.45 mm | 1.27 mm |

Source: JEDEC MS-012/MS-013 designators (per Wikipedia's SOIC summary and
multiple manufacturer datasheets), cross-checked against KiCad's own stock
footprints `Package_SO.pretty/SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod` and
`SOIC-8_7.5x5.85mm_P1.27mm.kicad_mod` (pad `(at)`/`(size)` fields, retrieved
2026-09-20; see `scripts/packages.json` entries `SOIC-8-N`/`SOIC-8-W`).

Pitch is identical between the two, which is exactly why this trap is easy
to miss on a quick visual check: a narrow and a wide SOIC-8 both look like
"an 8-pin gull-wing part at 1.27 mm pitch" at a glance, and only the pad
outer span, 5.55 mm apart, gives it away. `kicad_fpcheck.py
--declared-only` catches this from the family strings alone, with no
dimension table needed, provided the design declares which one was meant
(`design.py`'s `PACKAGES` table; see `templates/design.py`).

**Practical rule:** never resolve a part's footprint from "SOIC-8" or "SOP-8"
alone. Confirm narrow vs. wide (equivalently: 150 mil vs. 208/300 mil, 3.9 mm
vs. 7.5 mm body) from the part's own datasheet or distributor listing before
picking a footprint, and record which one in `design.py`'s `PACKAGES` table
so the check has something independent to verify against. Where the correct
family is a different stock KiCad footprint (as it is here, `SOIC-8-N` vs.
`SOIC-8-W`), re-point the design's `FP_` reference at it directly. Where no
stock footprint matches the real part at all, fork the nearest one into the
project library with `scripts/kicad_fplib.py fork` and correct it there;
either way, the fix is a change to what the design references or the library
itself, never a note that the mismatch was found (`kb/README.md`'s "where a
fact lives" table).

## 2. SOD-123 vs. SOD-123F vs. SOD-323: three diode families, not one with variants

A second, adjacent trap, relevant to `kb/keyboards/diode-footprint-vs-part.md`:
these three small-outline diode packages are routinely confused because
their names look like a size progression (123, 123F, 323) and their
silhouettes are all "a small two-terminal gull-wing part". The dimensions do
not follow the name:

| Package | Body (L × W) | Pad outer span | Pad inner gap |
|---|---|---|---|
| SOD-123 | 2.675 × 1.6 mm | 4.20 mm | 2.40 mm |
| SOD-123F (flat lead) | **3.5** × 1.6 mm | 3.90 mm | 1.70 mm |
| SOD-323 | 1.7 × 1.25 mm | 2.70 mm | 1.50 mm |

Sources: Nexperia SOD123.pdf and mbedded.ninja's SOD-123F component-package
page (body dimensions); KiCad stock footprints `Diode_SMD.pretty/D_SOD-123.
kicad_mod`, `D_SOD-123F.kicad_mod`, `D_SOD-323.kicad_mod` (pad geometry,
retrieved 2026-09-20; see `scripts/packages.json` entries `SOD-123`,
`SOD-123F`, `SOD-323`).

**SOD-123F's body (3.5 mm) is LONGER than plain SOD-123's (2.675 mm)**,
the "F" suffix means flat-lead, not smaller, which is the opposite of what
an unfamiliar reader expects from the name. Meanwhile SOD-323 is a real size
step down from both (body 1.7 mm), and is visually similar to SOD-123 on a
board render at typical zoom.

None of the three pad footprints will accept either of the other two
part bodies without one of `kicad_fpcheck.py`'s two failure signatures
firing: a body that cannot bridge a too-wide gap (SOD-123's 2.40 mm gap
against SOD-323's 1.7 mm body: 0.70 mm short), or a footprint whose pad
span badly exceeds a smaller part's lead span.

**Practical rule:** treat SOD-123, SOD-123F, and SOD-323 as three unrelated
footprints that happen to share a naming lineage, not as one footprint with
a size option. Confirm which one a diode's own datasheet specifies, every
time, the same as rule 1 above, and re-point the design at the correct stock
footprint. If the datasheet's own body length sits close enough to the
declared package's pad gap that `kicad_fpcheck.py` reports a thin-margin
WARN rather than a clean PASS (the failure mode
`kb/keyboards/diode-footprint-vs-part.md` records), a note in a card does not
change what gets fabbed: fork the footprint with `scripts/kicad_fplib.py
fork`, tighten the pad gap with `set-pads`, and record the source with
`annotate`, so the margin the datasheet actually supports is what the board
carries.

## Why no gate catches either trap on its own

ERC has no notion of a pad. DRC and schematic parity compare the board's
copper and netlist to the schematic's, never to a part's physical package,
a wrongly-sized footprint is fully connected and geometrically legal, so it
is invisible to every check hw_forge runs before `kicad_fpcheck.py`. Both
traps above are exactly the class of failure `docs/BACKLOG.md` B3 named as
open and `scripts/kicad_fpcheck.py` was built to close: see that script's
module docstring for the check, `agents/resource-scout.md` gate 7 for where
it runs in the pipeline, and `agents/fab-docs-engineer.md` for the pre-export
re-check.
