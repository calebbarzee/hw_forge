---
description: Fill in a bill of materials (BOM) a buyer can act on, and keep board-inherent geometry off it. Audits a schematic's part fields, researches what is missing, writes it into design.py, regenerates, re-audits, and exports.
argument-hint: "<project-dir> [--assembly jlcpcb|none]"
---

# /hw-bom

BOM is the bill of materials, the part list an assembler orders from. This
command exists because a generated BOM is only as good as the fields the
schematic carries, and a generator that never wrote them produces a list of
bare values: "100n", "470", "1N4148W", with a mounting hole listed right
alongside them as if it were a part to buy. Neither failure is caught by
ERC, DRC, schematic parity, or `kicad_fpcheck.py`: none of those compares
the board to what a human needs to place an order.

## 1. Audit first

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kicad_bom.py" audit \
    <project-dir>/<name>.kicad_sch \
    [--board <project-dir>/<name>.kicad_pcb] \
    --design <project-dir>/design.py \
    [--assembly jlcpcb]
```

Read the report before touching anything. It sorts every symbol into one of
two rulebooks and names the rule that fired:

- **Board-inherent** (a mounting hole, fiducial, test point, logo, net tie,
  or edge connector formed by the board itself): must carry `in_bom no` on
  its schematic placement, and, when `--board` is given, `exclude_from_bom`
  in its footprint's `(attr ...)` tokens.
- **Sourced** (everything else): must carry a Description of at least four
  words that is not the value restated, a Manufacturer, an MPN, a Package,
  a Datasheet, and, when `--assembly jlcpcb`, an LCSC part number.

Expect many FAILs on a project whose schematic predates this doctrine. That
is the finding, not a bug in the check.

## 2. Research each failing sourced part

For every sourced part the audit flagged, research its fields with the
`resource-scout` discipline (`agents/resource-scout.md`, `commands/hw-research.md`):
the manufacturer's own datasheet first, then a distributor page, and record
which source gave which fact. Two independent sources are not required
here the way they are for a pin table, since a description and a part number are
lower-stakes than a pinout, but a manufacturer datasheet always outranks a
distributor's own paraphrase of it.

Local machine first, same as any other research task: another project on
this disk may already carry the same part's fields in its own `design.py`.

## 3. Write the fields into design.py, never into the schematic

The fields belong in `design.py`'s `PARTS` table (see
`templates/design.py`, "Part fields"), keyed by reference or value, the same
lookup order `PACKAGES` already uses:

```python
PARTS = {
    "C1": {
        "description": "100nF X7R ceramic decoupling capacitor, 0603",
        "manufacturer": "Samsung Electro-Mechanics",
        "mpn": "CL10B104KB8NNNC",
        "package": "0603",
        "datasheet": "https://www.samsungsem.com/...",
        "lcsc": "C1525",
    },
}
```

Never hand-edit the fields into the `.kicad_sch` directly. The schematic
emitter writes `PARTS` into the symbol properties; a next regeneration
overwrites a hand-edit and loses it silently, the same reason nothing else
in this pipeline is hand-edited. The one exception is a project with no
emitter at all; see §6.

### The description standard

A description is a sentence a buyer can act on: what the part does, its
key rating or ratings, and its package. Never the value restated, and never
so generic it fits any part in the same family.

Good:

- "100nF X7R ceramic decoupling capacitor, 0603": function (decoupling),
  rating (X7R, implies temperature stability), package.
- "1N4148W small-signal switching diode, SOD-123, 100V/200mA": function,
  key ratings, package.
- "SK6812MINI-E addressable RGB LED, integrated driver, 3.5x3.5mm PLCC4":
  function, what makes it different from a plain LED, package.

Bad:

- "100n": the value, not a description. This is exactly what the probe
  export produced for every capacitor on a real project.
- "Capacitor": true of every part in the table; carries no information a
  buyer could not get from the Value column already.
- "SMD component": worse than useless. It does not even say what the part
  does.

### The exclusion rule, with examples

A BOM lists what still has to be bought and soldered onto a bare board. A
hole is neither. Declare a part's kind in `design.py`'s `BOARD_INHERENT`
table (mounting_hole, cutout, fiducial, test_point, logo, net_tie,
edge_connector) when it is one of these, and nothing else:

- **Exclude**: four M2 mounting holes (H1-H4) that take a fastener and
  mount nothing themselves. `BOARD_INHERENT = {"H1": "mounting_hole", ...}`.
- **Exclude**: three fiducials used only for pick-and-place optical
  alignment.
- **Do not exclude**: a mounting hole that also carries a press-fit
  standoff or a heat-set insert someone has to source and install, that
  location holds a real part, so it belongs in `PARTS`, not
  `BOARD_INHERENT`, however much its footprint resembles a plain hole.
- **Do not exclude**: a test point that is actually a populated pogo-pin
  header. Same reasoning: something real gets placed there.

A plain board-edge cutout with no footprint at all (a USB notch cut as
board-outline geometry) needs no entry either way, since it was never a
schematic symbol, and `kicad-cli sch export bom` never sees it.

## 4. Regenerate and re-audit

Regenerate the project (`make` or the project's own generator invocation),
then re-run the audit from §1. Iterate: read the report, fix the named
field, regenerate, re-audit. This is the same nudge loop every other gate
in this pipeline uses.

## 5. Export

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kicad_bom.py" export \
    <project-dir>/<name>.kicad_sch -o <out>.csv [--assembly jlcpcb]
```

This runs the real `kicad-cli sch export bom` with the full field list,
grouped by Value plus Footprint plus MPN, `--exclude-dnp`, then re-checks
the CSV it wrote for empty required cells and fails on any. A board-inherent
part correctly marked `in_bom no` never reaches this CSV: kicad-cli drops it
at export time (verified against KiCad 10.0.5: the deprecated
`--include-excluded-from-bom` flag has no effect).

`scripts/kicad_fab.py`'s own BOM step runs the same field list and the same
completeness rule as part of a full fab export (`agents/fab-docs-engineer.md`);
running `/hw-bom` first means that step finds nothing left to fail on.

## 6. Exception: a schematic with no code generator

Some projects are a hand-drawn `.kicad_sch` with no `design.py` and no
emitter. `PARTS` and `BOARD_INHERENT` have nothing to write into. In that
case, and only in that case:

1. State plainly that this is the exception path, not the normal one, in
   your report.
2. Edit the symbol's `property` s-expressions directly in the `.kicad_sch`
   text file (Description, Manufacturer, MPN, Package, Datasheet, LCSC)
   matching the format KiCad itself writes:

   ```
   (property "Description" "100nF X7R ceramic capacitor, 0603"
       (at 444.5 368.3 0)
       (effects (font (size 1.27 1.27)) (hide yes)))
   ```

   Set `in_bom no` on a board-inherent symbol's placement the same way,
   as a bare boolean on the symbol instance, not a property.
3. Open the file in KiCad afterward and confirm it still parses (a save
   and an ERC run is the cheapest proof). This is a documented, narrow
   exception to "never hand-edit a `.kicad_sch`"; everywhere else in this
   pipeline, that edit would be silently lost at the next regeneration, but
   a hand-drawn project has no regeneration step to lose it to.
4. Re-run `kicad_bom.py audit` to confirm the edit actually took.

## Report

- The audit's before/after FAIL counts, and its final clean run, verbatim.
- Each part researched, with the source (datasheet URL or distributor
  page) for each fact.
- Any part where the schematic's own value made the description
  ambiguous, and how you resolved it.
- Whether `--assembly jlcpcb` applied, and if so, confirmation every
  sourced part carries an LCSC number.
- If the hand-edit exception (§6) applied: say so explicitly, and what you
  verified afterward.
