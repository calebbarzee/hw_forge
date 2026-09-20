---
domain: fabs/jlcpcb
tags: [jlcpcb, drc, design-rules, capability, 4-layer, 2-layer, hole-to-hole, annular-ring,
       kicad-dru, npth, pth, clearance, assembly, bom, cpl, lcsc, pre-upload, fabrication-toolkit]
source: jlcpcb.com/capabilities/pcb-capabilities (read 2026-08-22) + z_board combo DRC alignment run
  + local read of the Fabrication Toolkit plugin source (2026-09-20)
  + kb/runs/a6mzero-fable5-rp2350.md (2026-09-20)
date: 2026-09-20
confidence: researched
---

# JLCPCB rigid-PCB capability floors, and how they map onto the KiCad design rule check (DRC)

Numbers read off JLCPCB's capability page on 2026-08-22. Re-read the page before a new
order; fabs revise these. Values are the capability minimum, not the no-extra-cost
tier. Very small vias (<0.3 mm drill) and tight geometry can carry a price adder even when
buildable.

## The numbers (1 oz outer copper)

| Spec | 2-layer | 4-layer (multilayer) | KiCad default | Who is stricter |
|---|---|---|---|---|
| Min track width / spacing | 0.10 / 0.10 mm | 0.09 / 0.09 mm | 0.2 track, **no clearance floor** | mixed; see below |
| Min via drill / diameter | 0.3 / 0.5 typical | 0.15 / 0.25 mm | 0.3 / 0.5 | KiCad |
| Via annular ring | 0.15 mm abs. min (0.2 recommended) | same | **0.10 mm** | **JLC** |
| Via-to-via hole spacing | 0.2 mm | 0.2 mm | 0.25 | KiCad |
| Plated-through-hole (PTH) pad hole-to-hole (drill web) | 0.45 mm | 0.45 mm | **0.25** | **JLC** |
| PTH drill to track | 0.28 mm | 0.28 mm | **0.25** | **JLC** |
| Non-plated-through-hole (NPTH) to track | 0.2 mm | 0.2 mm | 0.25 | KiCad |
| Copper to routed board edge | 0.2 mm | 0.2 mm | 0.5 | KiCad |
| Min NPTH hole | 0.5 mm | 0.5 mm | n/a | n/a |
| Min plated slot width | 0.5 mm | 0.35 mm | n/a | n/a |
| Min non-plated slot width | 1.0 mm | 1.0 mm | n/a | n/a |
| Silkscreen line / text height | 0.15 / 1.0 mm | same | 0.15 thick / 0.8 high text | mixed |
| Solder mask bridge | 0.10 mm | 0.10 mm | n/a | n/a |
| Outline tolerance | ±0.2 mm | ±0.2 mm | n/a | n/a |

The three bold rows are where KiCad's stock DRC is looser than what the fab can build. A
board can pass a default-settings DRC and still be rejected or mis-built at order time.
Those three are the whole point of the alignment pass.

## How to encode them (the z_board combo pattern)

Rule: DRC floor = max(your design floor, fab floor). Tighten where the fab is
stricter, never loosen your own floors down to fab minimums.

- Global, unconditional floors → project `board.design_settings.rules`
  (`min_clearance: 0.09`, `min_via_annular_width: 0.15`). Applied by the generator's
  `patch_project()` because `SaveBoard()` rewrites the `.kicad_pro`.
- Anything that differs by pad type → conditioned rules in the generated `.kicad_dru`,
  because the project `min_hole_clearance` knob is hole-blind: it cannot tell a
  plated hole (0.28 at JLC) from an unplated one (0.2 at JLC). Verified the hard way on
  z_board: setting the knob to 0.28 produced 148 false violations, every one an NPTH
  socket slot legitimately sitting at 0.2505 mm from zone fill.

```
(rule "jlc_pth_hole_to_hole"
    (constraint hole_to_hole (min 0.45mm))
    (condition "A.Pad_Type == 'Through-hole' && B.Pad_Type == 'Through-hole'"))

(rule "jlc_pth_hole_to_copper"
    (constraint hole_clearance (min 0.28mm))
    (condition "A.Pad_Type == 'Through-hole' || B.Pad_Type == 'Through-hole'"))
```

Vias carry no `Pad_Type` property, so these conditions exclude them. Via pairs stay on
the project's 0.25 knob, which already beats JLC's 0.2. That selectivity is what the
knob cannot do.

## Related JLC facts

- Overlapping drills are a fab reject; two holes closer than the drill web minimum must
  become one routed slot (z_board: two 3 mm contact holes 2.84 mm apart → one oval).
- NPTH-to-copper 0.2 mm is what makes z_board's 0.3 mm `npth_to_copper` edge-clearance
  relaxation safe (KiCad treats an unplated hole wall as board edge at 0.5 mm otherwise).
- Standard 4-layer stackup is JLC04161H-7628; inner copper 0.5 oz.

## Pre-upload checks

The JLCPCB assembly upload is itself a gate, not a formality after the real gates have
passed. It rejects parts it cannot source and flags a package mismatch between a
footprint's pads and the LCSC part's own package string. Both classes of failure pass
every DRC and ERC hw_forge runs today, because DRC checks a footprint against itself and
against other copper, never against the ordering code of the part assigned to it.

An outside run hit both failure modes at this exact point, after a clean DRC pass: a
flash chip picked in a SOIC-8 wide package with SOP-8 narrow pads drawn for it, a
boost-converter transistor whose package was too small for its pads, and separate part
availability problems, all caught only when JLCPCB processed the assembly order rather
than at any point during design. Full account in `kb/runs/a6mzero-fable5-rp2350.md`
§3-4. Running the same checks before upload, close to order time, moves each failure back
to where fixing it costs minutes instead of a re-order.

Verify, in this order, before every assembly upload:

1. **LCSC part number present in the BOM field for every placed, non-DNP part.** A blank
   field is not a warning to JLCPCB, it is a line item they cannot place at all. Confirm
   the field name a project's part table writes into is one the export step actually
   reads (see the Fabrication Toolkit's field list below); a field named something else
   produces a BOM that looks complete and uploads with silent blanks.
2. **Basic versus extended part class, and its cost.** JLCPCB's basic parts sit
   pre-loaded on assembly-line feeders at no extra charge; extended parts are pulled from
   stock per order and each *unique* extended part on a board carries a setup fee, reported
   elsewhere as on the order of $3 per unique extended part (needs-verification: not
   confirmed against JLCPCB's own current pricing page in this pass; re-read
   `jlcpcb.com/help/catalog/PCBA-Price-Details` before relying on the number). A board with
   many distinct extended parts can carry a meaningful, easy-to-miss fee stack; check the
   part class before locking a BOM, not after seeing the quote.
3. **Stock quantity at the time of upload**, not at the time the part was chosen. LCSC
   stock changes daily; a part that resolved cleanly during design can be gone by order
   time, and it is only a real check if it runs close to when the order is actually
   placed.
4. **Package string agreement with the footprint's family**, checked before the LCSC
   number is assigned, not after: does the chosen LCSC part's package field (for example
   `SOIC-8_150mil` vs `SOP-8_150mil`) match the footprint family and pitch actually drawn
   for that reference designator. This is the exact class of failure in
   `kb/runs/a6mzero-fable5-rp2350.md` §3, and it is what `scripts/kicad_fpcheck.py` (in
   progress in this repository as of 2026-09-20) is for: catching it before DRC ever sees
   the board, not at the upload.
5. **Rotation and origin conventions in the CPL (component placement) file.** JLCPCB
   expects rotation reported as viewed from above the board; a bottom-side part's rotation
   is not the same number KiCad reports for it, and getting this wrong uploads cleanly and
   places the part backwards or spun, which is not caught until assembly photos or a
   physically wrong board. See exactly how the locally available toolkit derives this,
   below.

### What the locally installed JLC fab toolkit plugin produces, and whether it runs headless

The plugin is "Fabrication Toolkit" (renamed from "JLC-Plugin-for-KiCad"), by Benny
Megidish, Apache-2.0 license. The 8.0 install (v5.2.0, via KiCad's Plugin and Content
Manager) is untouched and still lives at
`~/Documents/KiCad/8.0/3rdparty/plugins/com_github_bennymeg_JLC-Plugin-for-KiCad/`.

**As of 2026-09-20 it is also installed for KiCad 10.0**, at v5.3.1, not through the PCM
(the 3rdparty layout does not require it; KiCad loads plugins from that directory
regardless of how they got there, so it is not recorded in
`~/Library/Preferences/kicad/10.0/installed_packages.json`):
`~/Documents/KiCad/10.0/3rdparty/plugins/com_github_bennymeg_JLC-Plugin-for-KiCad/`
(`cli.py`, `plugin.py`, `process.py`, `thread.py`, `utils.py`, `options.py`, `config.py`,
`events.py`, `transformations.csv`, `metadata.json`, `icon.png`) plus
`.../3rdparty/resources/com_github_bennymeg_JLC-Plugin-for-KiCad/icon.png`. Installed from
the pinned v5.3.1 release zip (SHA-256
`80b05531c887cca4c7d801c6613e3fdbe17ae5ec8b802e87a6d16c3b9a0f4c45`,
github.com/bennymeg/Fabrication-Toolkit/releases/download/5.3.1/Fabrication-Toolkit-5.3.1.zip),
reproducibly via `python3 scripts/hw_install.py --jlc-plugin`.

**Running it headlessly needs `runpy`, not a plain script invocation.** `cli.py` uses
relative imports (`from .thread import ProcessThread`) and a `__main__` guard, so `python3
cli.py ...` fails with "attempted relative import with no known parent package"; it must run
as a module of its own package. Verified 2026-09-20, under KiCad's bundled interpreter, from
the `3rdparty/plugins` directory:

```python
import sys, runpy
sys.argv = ["cli.py", "--path", "board.kicad_pcb", "--nonInteractive", ...]
runpy.run_module("com_github_bennymeg_JLC-Plugin-for-KiCad.cli", run_name="__main__")
```

The module name's hyphens (`JLC-Plugin-for-KiCad`) are the directory's own name and are not
a problem for `runpy.run_module`: it resolves dotted segments against the filesystem, not
against python identifiers, and `--help` through this exact call printed the plugin's real
argument parser output, confirmed by running it. `cli.py` calls `sys.exit()` on completion,
so wrap the `runpy.run_module` call in `try/except SystemExit` to read its exit code rather
than letting it kill the caller.

Read directly from its source (`cli.py`, `plugin.py`, `process.py`, `thread.py`,
`config.py`), 2026-09-20, it exports, into a `production/` folder beside the board file:

- Gerbers, one file per active layer, X2 format available, via `pcbnew.PLOT_CONTROLLER`.
- A drill file (Excellon), via `pcbnew.EXCELLON_WRITER`.
- An IPC-356D netlist, `netlist.ipc`.
- `designators.csv`: per-reference-designator instance counts.
- `positions.csv`, the CPL: header `Designator, Mid X, Mid Y, Rotation, Layer`, position
  measured from the board's auxiliary origin. Rotation is reported as viewed from above
  the board, which is why a bottom-layer part's rotation is transformed as
  `180 − rotation` before any further offset is applied
  (`process.py::generate_tables`), not passed through as KiCad's own
  `GetOrientation()` value.
- `bom.csv`: header `Designator, Footprint, Quantity, Value, LCSC Part #`, with rows
  merged when footprint, value, and LCSC part number all match.
- A zipped gerber archive, plus a timestamped backup archive of the whole output set.

It reads the LCSC part number from the footprint's own symbol fields, trying, in order,
`LCSC Part #`, `JLCPCB Part #`, `Part #`, `Part`, `PN`, `P/N`, `Part No.`, `Part Number`,
then falling back to `LCSC`, `JLC`, `MPN`, `Mpn`, `mpn`
(`process.py::_get_mpn_from_footprint`). A project's part-table generator must write to
one of these field names, or the plugin silently emits a blank LCSC column for every part,
which is check 1 above failing invisibly.

**It runs headless.** `cli.py` accepts `--path board.kicad_pcb --nonInteractive`, plus
flags for extra layers, automatic zone fill, DNP exclusion, automatic position/rotation
translation, and backup control, and drives the same `ProcessManager` /
`ProcessThread` classes the GUI button does, with no `wx` GUI dependency on that code
path (confirmed by reading `cli.py` and `thread.py`; not run in this pass). Because it
imports `pcbnew` directly, it must run under KiCad's bundled Python interpreter, the same
constraint as every other SWIG-based script in this pipeline
(`skills/hw-design/references/kicad-api.md` §4).

It also carries its own rotation/position correction database
(`transformations.csv`, matched against footprint or library name by regex) and applies
it automatically when the `--autoTranslate` option is set. A project that also hand-applies
rotation offsets on top of this will compound the correction rather than replace it; pick
one source of truth for rotation corrections, not both.
