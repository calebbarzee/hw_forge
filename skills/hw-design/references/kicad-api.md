# KiCad automation: interfaces, invocations, and known traps

Generic KiCad knowledge. Part-specific and project-specific facts live in `kb/`.
Verified against KiCad 10.0.5 unless a version is named.

## Terms used here

| Term | Meaning |
|---|---|
| BOM | Bill of materials. |
| CLI | Command-line interface. Here, the `kicad-cli` binary. |
| DNP | Do not populate. A part on the board that the assembler should skip. |
| DRC | Design rule check. |
| ERC | Electrical rule check. |
| GUI | Graphical user interface. KiCad's windowed application. |
| IPC | KiCad's supported scripting interface, installed as `kicad-python` and imported as `kipy`. |
| KIID | KiCad's per-item unique identifier, written into the file as a `uuid` or `tstamp`. |
| NPTH | Non-plated through hole. A mechanical hole with no copper wall. |
| PTH | Plated through hole. |
| s-expression | The parenthesised text format KiCad uses for its `.kicad_pcb` and `.kicad_sch` files. |
| SWIG | The older generated Python binding for `pcbnew`. Deprecated in KiCad 9, removed in 11. |

## 1. Pick the right interface

| Interface | Requires | Can write? | Use for |
|---|---|---|---|
| Files as text (s-expression) | nothing | yes, riskily | reading geometry, auditing pin maps, metadata edits |
| `kicad-cli` | 8+, best 10+ | no (outputs only) | all verification and export; headless, scriptable |
| SWIG `pcbnew` (bundled python) | ≤ 10 | yes | headless board generation today |
| IPC API (`kicad-python` / `kipy`) | 9+, GUI running | yes, transactionally | live edits, generative layout |

Rules:

- **Verification is always `kicad-cli`.** Never assert cleanliness from a
  generator's own bookkeeping.
- **Writing copper as text is forbidden.** Tracks carry unique identifiers,
  zones carry cached fills, and nothing revalidates until KiCad parses the file.
  Text edits are for metadata and placement only.
- **SWIG `pcbnew` is deprecated in 9 and removed in 11.** Anything written now
  must be portable to IPC (`pip install kicad-python`). Plan the port; see §7.
- IPC cannot plot or export in 9 or 10. The durable split is IPC, or SWIG, for
  edits, and CLI for verification and export.

## 2. The gate invocations

```bash
kicad-cli sch erc --severity-error --format json --exit-code-violations \
    -o erc.json board.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-error --format json \
    --exit-code-violations -o drc.json board.kicad_pcb
```

- `--exit-code-violations` returns 5 when violations exist, which turns DRC and
  ERC into tests usable directly in a Makefile.
- `--schematic-parity` is not the default. It is the flag that catches the whole
  class of "board and schematic have drifted": missing footprints, net
  mismatches, and stale pad numbering. A DRC run without it is not a gate.

### The flag alone is not a gate either

KiCad ships all five parity checks at `warning` severity. A default
`.kicad_pro` carries `missing_footprint`, `extra_footprint`, `net_conflict`,
`footprint_symbol_mismatch`, and `lib_footprint_mismatch` all at `warning`.

So `--severity-error` filters every one of them out before they are counted, and
the run prints a `parity` section of length zero.

Measured, on a board with a revised schematic and a stale board file, where the
schematic had gained 7 diodes and a 6-terminal encoder, five general-purpose
input/output pins had been reallocated, and the old nets were gone:

```
kicad_gate.py kicad          ->  ERC ok   DRC ok   parity ok   unconnected ok   (exit 0)
same board, --severity-all   ->  31 schematic parity issues
                                 21 net_conflict, 8 missing_footprint,
                                 2 footprint_symbol_mismatch
```

That is a green gate on a board missing eight parts and mis-wiring twenty-one
nets. It was not a project misconfiguration. It was every project that had not
promoted the five checks by hand, and an audit of a second, older project found
the same blind spot hiding two genuinely missing components on its proto slice.

The fix has two halves:

1. **Promote all five to `error` in the project file.** `kicad_scaffold.py`
   writes them as defaults. They are the pipeline's contract with itself, not a
   fab capability limit.
2. **Have the gate assert the promotion before trusting a parity pass.**
   `kicad_gate.py` prints `parity UNENFORCED` and, with `--strict-parity`,
   fails.
3. **On the forked `kicad-cli`, the project file no longer decides.**
   `kicad_gate.py` passes `--severity-override KEY=LEVEL` for the five parity
   keys and the scaffolder's fab promotions, at the levels
   `hwforge-overrides.json` records, and prints `parity enforced (override)`.
   The `.kicad_pro` promotion is still needed for the GUI and for stock.

Demote one only as an explicit, justified decision, like any other severity
override.

The general rule: **a check whose severity is below the severity you filter on
is not a check.**

### The rest of the gate

- `--severity-error` is the gate. Run `--severity-all` separately to enumerate
  warnings and document each surviving one. A clean run only means something if
  the benign classes are written down.
- The JSON report has three independent buckets, `violations`,
  `unconnected_items`, and `schematic_parity`, plus a per-item `severity`. Read
  all three. A board can be DRC-clean and still have unconnected nets.
- Gate the whole set per project:
  `ERC 0 / DRC 0 at error severity with parity / unconnected 0`.
- Zones must be filled before the gate. Unfilled pours report their nets as
  unconnected.

## 3. Export invocations and their flag gotchas

```bash
# Gerbers: name every layer explicitly. The default set is not the fab's set.
kicad-cli pcb export gerbers -o fab/ \
  --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts \
  --no-protel-ext --subtract-soldermask board.kicad_pcb

# Drill: separate PTH/NPTH, absolute origin, mm, decimal. Every one matters.
kicad-cli pcb export drill -o fab/ --format excellon --drill-origin absolute \
  --excellon-units mm --excellon-separate-th --excellon-zeros-format decimal \
  --generate-map --map-format pdf --generate-report --report-path fab/drill.txt \
  board.kicad_pcb

# Placement: export all three. Assemblers ask for different ones.
kicad-cli pcb export pos -o fab/pos-all.csv --side both   --format csv --units mm board.kicad_pcb
kicad-cli pcb export pos -o fab/pos-top.csv --side front  --format csv --units mm board.kicad_pcb

# BOM: export flat with the full sourcing field list, then group in your own
# script (see below), or use scripts/kicad_bom.py, which audits completeness
# and the board-inherent exclusion rule before it exports.
kicad-cli sch export bom -o .bom-flat.csv \
  --fields "Reference,Value,Footprint,DNP,Description,Manufacturer,MPN,LCSC,Package,Datasheet" \
  --labels "Refs,Value,Footprint,DNP,Description,Manufacturer,MPN,LCSC,Package,Datasheet" \
  --group-by "" --sort-field Reference --ref-range-delimiter "" board.kicad_sch
# A symbol placed with (in_bom no) is dropped by this export, and the flag
# --include-excluded-from-bom is deprecated and has no effect on 10.0.5. That
# is the intended path for mounting holes, fiducials, test points, and logos.

kicad-cli pcb render -o top.png --side top -w 2000 --height 1450 --zoom 1.35 \
  --background opaque --quality high board.kicad_pcb
kicad-cli pcb export svg -o back.svg --mode-single --mirror \
  --layers B.Cu,B.Mask,B.Silkscreen,Edge.Cuts --exclude-drawing-sheet \
  --page-size-mode 2 board.kicad_pcb
```

Gotchas:

- **Inner layers must be added by hand** for a 4-layer board
  (`In1.Cu,In2.Cu`). Forgetting them produces a plausible-looking, unfabbable
  gerber set. Derive the layer list from the stackup rather than hardcoding one.
- `--excellon-separate-th` splits PTH from NPTH. Most fabs require it, and a
  merged file silently plates your mechanical holes.
- `--drill-origin absolute` matches the gerbers' origin. Any other choice needs
  the same choice on the gerbers.
- **Do not pass `--check-zones` on the fab path.** Refilling during export means
  the plotted copper is not bit-for-bit the geometry the gate approved. Fill
  once, in generation, and plot what was gated.
- `export pos --mirror` does not exist; use the per-side exports.
  `export svg --mirror` is for viewing the back layers as seen from the back.
- `kicad-cli sch export bom`'s grouping is weak. Export flat with an explicit
  field list, and regroup in a script that also emits a `Populate` or DNP column.
- **Always follow the export with an assertion script.** Check that every
  artifact exists and is non-empty, that the drill tool table matches the
  expected hole census (count and diameter per tool), and that the placement row
  count equals the expected footprint count. A fab export that ran is not a fab
  export that is right.
- Jobsets (`kicad-cli jobset run --file fab.kicad_jobset project.kicad_pro`, 9+)
  collapse the export set into one committed reviewable file. Worth adopting
  once the flag set stops changing.

## 4. Headless `pcbnew` (SWIG): pattern and traps

Invoke under KiCad's bundled interpreter, never the system python:

```makefile
KICAD := /Applications/KiCad/KiCad.app/Contents          # macOS
CLI   := $(KICAD)/MacOS/kicad-cli
KPY   := $(KICAD)/Frameworks/Python.framework/Versions/Current/bin/python3
# Linux: /usr/bin/kicad-cli and system python3 with `import pcbnew` on the path.
```

The consequence for the design layer: the logical design module must be pure
python with no dependencies, so that it imports identically under the system
interpreter, which runs the schematic emitter and the checks, and under the
bundled one, which runs the board emitter. One source of truth, two
interpreters.

`pcbnew` prints `wxApp` warnings to stderr on every headless run. Filter them
with `2>&1 | grep -v wxApp || true` rather than suppressing all output.

### Trap: `FLIP_DIRECTION`, the silent 180 degrees

`BOARD_ITEM::Flip()`'s second argument was `bool aFlipLeftRight` through
KiCad 8. In 10 it is a `FLIP_DIRECTION` enum whose `LEFT_RIGHT` member is 0.

So the KiCad 8 idiom `Flip(centre, False)`, meaning mirror top-to-bottom, or
"put this part on the back face", silently becomes a left-right mirror under 10.
A left-right mirror equals a top-bottom mirror plus 180°, so every back-face
footprint comes out end-for-end and every pad-relative track lands on the wrong
terminal.

```python
FLIP_TB = getattr(pcbnew, "FLIP_DIRECTION_TOP_BOTTOM", False)   # 10 first, 8 fallback
fp.Flip(pt(x, y), FLIP_TB)
```

General rule: **never pass a bare bool to a KiCad API that may have grown an
enum.** Prefer `getattr(pcbnew, "SOME_ENUM_MEMBER", <old-literal>)`.

### Trap: the composed rotate-then-flip transform

This transform is in no documentation.

The rule is: **never derive a pad side. Place the part, read `pad_xy()` back,
and route from what the footprint says.** The transform below is why you cannot
do it in your head.

The generator idiom is `SetOrientationDegrees(θ)` and then `Flip(pos, FLIP_TB)`,
which composes to:

```
local (lx, ly)  ->  ( lx·cosθ + ly·sinθ ,  +(lx·sinθ − ly·cosθ) )
```

That is the rotation first, then a mirror in y, not the other way round. It
decides which board direction a footprint's pad 1 ends up facing, and it is
nowhere in the KiCad documentation.

Cost of reasoning it out backwards: two parts placed on the belief that "rot 270
puts pad 1 north", when it puts it south. That was paid for with 2
`shorting_items` and 2 `solder_mask_bridge` violations, which the DRC caught
instantly.

The useful distinction is that the generator in question already obeyed "read it
back" for routing. The failure was applying human reasoning to a placement
decision, namely which rotation to pass. That is the same trap one level up from
routing, and DRC is the only thing that catches it. See `electronics.md` §8 for
the mirroring invariants this sits under.

### Trap: a generated board is not byte-stable, and cannot be

`pcbnew` mints a fresh random KIID for every item it creates, and `SaveBoard()`
writes footprints in its own internal order rather than insertion order.

So two runs of an unchanged generator differ in thousands of lines while
describing identical copper. One measured case differed in 5744 of 10488 lines.
`diff` and a plain checksum therefore report a false failure every time.

"Regeneration is deterministic", which is part of the phase-4 contract, has to
be checked on the canonical form instead: drop every `uuid` and `tstamp`, sort
the remaining lines, then hash. What survives is every coordinate, layer, net,
width, drill, property, and filled-zone outline, which is everything a fab, a
DRC, or an enclosure generator reads.

```bash
python3 scripts/kicad_digest.py BOARD.kicad_pcb
```

It is pure stdlib, so it runs under the system python and needs no `pcbnew`.
Equal digests across a wipe-and-rebuild is the strongest determinism claim this
toolchain supports. A real regression, such as a moved lane, a changed fill, or
a dropped footprint, changes the digest immediately.

### Trap: `SaveBoard()` overwrites the sibling `.kicad_pro`

`pcbnew.SaveBoard()` rewrites `<stem>.kicad_pro` from pcbnew's own defaults,
wiping whatever the project scaffolder wrote: net classes, rule severities, and
minimum clearances.

Therefore anything the DRC needs must be patched into the `.kicad_pro` after the
save, as an explicit post-step:

```python
pcbnew.SaveBoard(out, board)
patch_project(out)   # json-load .kicad_pro, merge board.design_settings.rule_severities, dump
```

Keep the patch table small, and comment every entry with its justification. A
demoted rule you cannot justify is a hidden defect.

### Zones

- `pcbnew.ZONE_FILLER(board).Fill(board.Zones())` works headlessly in KiCad 10.
  Under 8 it aborted the interpreter, because the filler wanted the application
  framework and `wx.App()` hangs with no display. Filling inside generation is
  what removes the last GUI step from the build.
- **Island removal must be by area, not connectivity, whenever a pour is fed by
  vias.** KiCad does not count a via when deciding whether a filled island is
  connected, only pads. A plane whose only pad is one pin will have every other
  island deleted under the default mode. Observed: about 7900 mm² of fill
  reduced to 9.8 mm², with 22 via-fed taps reported unconnected and no clearance
  violation anywhere.

  ```python
  z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
  z.SetMinIslandArea(int(mm(3.0)) * int(mm(3.0)))
  ```

  Also route an explicit stitch via from the fed lane into the pour, so the
  connection is real copper rather than a fill coincidence. Never let
  connectivity depend on a fill.
- **Pad connection should be solid (`ZONE_CONNECTION_FULL`), not thermal**, for
  generated boards. Thermal relief buys hand-soldering comfort and costs a
  `starved_thermal` error on any pad whose spokes land in a small island.
  Reflow, and through-hole into a 1 oz pour, do not need it.
- `SetMinThickness()` is a real failure mode. A pour pinched below its own
  minimum thickness by nearby copper silently splits into isolated islands,
  again with no clearance violation, because nothing was too close to anything.
  When taps go unconnected and DRC is otherwise clean, suspect a pinch rather
  than a clearance.

  **There is nothing upstream of DRC for this, and there should be.** The
  generator knows every track, via, and pad it emitted, plus the zone outline,
  so the check is available at generation time: flood the zone polygon minus
  copper expanded by clearance, on a `min_thickness`-sized grid, count
  components, and compare against the number of distinct pad groups.

  Measured, on a first fully-routed board: one `unconnected_items` finding, from
  a ground island of about 300 mm² fenced in by two band lanes and two column
  buses. Its escape route was a 1.10 mm window with a 0.6 mm via keepout in the
  middle of it, leaving 0.075 mm of pourable channel against a 0.20 mm minimum.

  The lane arithmetic that prevents it is in `electronics.md` §7:
  `2 × zone_clearance + min_thickness` between fencing lanes, and a via between
  them needs `via_r + zone_clearance` more than a track does.

  The island-count and narrowest-channel checker is on the backlog. Until it
  lands, gate `unconnected` on every regeneration, and treat any lane extension
  along an existing bus as a pour change (§7).

### Custom rules

Fab-justified relaxations go in a generated `<project>.kicad_dru` written by the
same `patch_project()` step, one rule with its justification in a comment. Do
not relax a global minimum to fix a local geometry problem.

Custom rules also run the other way, as **fab capability floors**. KiCad's stock
DRC is looser than real fabs in places: no absolute clearance floor at all,
0.10 mm via annular against a typical 0.15, and 0.25 mm hole-to-copper and
hole-to-hole against a typical 0.28 and 0.45 for plated holes. A
default-settings pass is therefore not proof of manufacturability.

Encode `max(design floor, fab floor)` per spec. Never loosen your own floors to
fab minimums.

Unconditional floors go in the project `rules` dict via `patch_project()`.
Anything that differs by pad type goes in the `.kicad_dru`, because the project
`min_hole_clearance` knob is hole-blind: it cannot distinguish plated from
unplated holes, and fabs quote them differently. Applying a PTH number globally
cost one project 148 false NPTH violations.

Condition on `A.Pad_Type`. Vias carry no `Pad_Type`, so PTH-conditioned rules
correctly skip them. Current numbers per fab live in `kb/fabs/`.

### Demoting a DRC rule: the enumeration discipline

Severity overrides are per rule, not per item pair, so demoting one disables it
board-wide.

Meanwhile a single locked geometry decision produces a whole finding class. One
measured case put a 36 × 14 mm display courtyard over the microcontroller and
produced 25 findings in two rule classes: one `courtyards_overlap` and 24
`pth_inside_courtyard`, one per through-hole pad of the overlapped footprint.
See `kb/projects/hexpad.md` §3.8.

These two rules come in pairs, and the pad-wise one scales with pad count, so a
front-face overlap multiplies.

A defensible demotion is four steps:

1. Run `--severity-all` and enumerate the whole finding set the override will
   silence.
2. Prove the set is exhaustively the sanctioned cause. In the case above, all 24
   findings name one footprint.
3. Record that proof next to the override, in the `patch_project()` table or the
   `.kicad_dru` comment, not in a commit message.
4. Prefer a scoped `.kicad_dru` rule over a global severity whenever the
   condition can be written.

A demotion whose finding set you have not enumerated is not a demoted rule. It
is a rule you have switched off.

### Trap: refs without a numeric suffix poison the CLI annotation check

Every reference designator a generator emits must end in a digit, so `SW_PWR1`
rather than `SW_PWR`.

A digitless reference makes every `kicad-cli sch` invocation print
`schematic has annotation errors` forever, which masks real annotation problems.
If anyone then runs Annotate in the GUI, KiCad silently renames the part, for
example `SW_PWR` to `SW23`, breaking every generator constant and BOM note keyed
on the old reference.

### Trap: `GetLayerName()` is the human-readable name, not the canonical one

`item.GetLayerName()` returns KiCad's *display* string for a layer, "F.Silkscreen",
not the canonical name the file format and every other API surface use,
"F.SilkS". Filtering an obstacle collector on
`item.GetLayerName() in ("F.SilkS", "B.SilkS")` is therefore always false, and
the failure is silent: the collector runs, returns an empty set, and nothing
raises.

Cost, measured: an obstacle collector built this way excluded every
footprint-owned silk graphic (corner ticks, cathode bars, a module's
polarity marker) from an entire generation pass. The silk-label placement
routine reported success on every call, because from its point of view no
footprint silk ever occupied the space it was searching. The DRC run
immediately after found real `silk_overlap` violations against exactly the
excluded items.

Compare `item.GetLayer()` (the integer layer ID, `pcbnew.F_SilkS` /
`pcbnew.B_SilkS`) instead of the string. General rule: **never filter a
`pcbnew` layer by its display-name string**; match the integer ID, or the
canonical name read from a `.kicad_pcb` file's own `(layer ...)` token, which
is `F.SilkS`, not `GetLayerName()`'s `F.Silkscreen`.

Source: the z_board silkscreen pass, 2026-09-20
(`kb/keyboards/silkscreen-readability.md`).

## 5. Reading files as text (s-expressions)

Reading is what this is good for. Parsing a footprint's pads out of
`.kicad_pcb` is faster and more trustworthy than any GUI inspection, and it is
how a pin-map audit should be done.

Gotchas:

- **Footprint rotation in file coordinates is clockwise-positive**, and the
  file's y axis points south. A CAD frame that is right-handed with y north
  therefore needs both a `y → −y` and a rotation-sign flip. Getting one and not
  the other yields geometry that looks plausible and is wrong. Convert once, in
  one named helper, and assert the round-trip.
- **Pad coordinates are footprint-local.** The board position is `footprint.at`
  composed with the pad's `at` rotated by the footprint angle. Do not read a
  pad's `at` as a board coordinate.
- Zones carry a cached `filled_polygon`. It is stale the instant anything moves.
  Never trust it without a refill.
- Everything carries a `uuid` or `tstamp`. Copying s-expression blocks
  duplicates them, and KiCad tolerates that inconsistently. Generate fresh ones.
- **NPTH (`np_thru_hole`) pads block every layer.** When solving routing
  clearances, holes are not a copper-layer constraint, they are a
  whole-stackup constraint.
- KiCad counts an unplated hole wall as a board edge and applies the 0.5 mm
  outline clearance to it. That is a routed-outline number, and a milled slot
  flank can legitimately be relaxed, since fabs quote about 0.254 mm. Relax it
  only by a named custom rule, never globally.

## 6. Format upgrading

Vendored third-party footprints and symbols are usually an older format. Upgrade
them into the project library once, in a scripted step:

```bash
kicad-cli fp  upgrade <lib>.pretty
kicad-cli sym upgrade <lib>.kicad_sym
kicad-cli pcb upgrade board.kicad_pcb      # one-way
kicad-cli sch upgrade board.kicad_sch      # one-way
```

Upgrades are one-way, so branch or copy first. Custom-primitive pads are the
usual casualty; diff a render before and after.

## 7. Migration note: SWIG to IPC (`kipy`)

Run `pip install kicad-python`, then enable Preferences, Plugins, API server.

`Board` exposes `get_footprints/tracks/vias/pads/nets/zones/selection`,
`create_items/update_items/remove_items`,
`begin_commit/push_commit/drop_commit` for grouped undo, `refill_zones()`, and
`save()`.

Constraints: the GUI must be running, and plotting and export are not in the 9
or 10 API.

Keep generators structured so that the geometry layer is pure python and only a
thin adapter touches `pcbnew`. That adapter is the whole port.

## 8. Doctrine: one pin table, two emitters

**Generate the symbol and the footprint for any module from a single pin
table.** Hand-authoring both lets pin order drift between them, and the result is
a board that is DRC-clean, parity-clean, and mis-wired on every instance of the
part. The failure is silent because both files are internally consistent.

Corollary rules:

- The pin table is ordered by physical pad position. The pad numbers are
  whatever the vendor silkscreens. Never assume `index == pad number`. Cost of
  assuming it once: a module footprint whose pad-1 marker sat at the wrong end
  of the column, needing a full renumber `k → N+1−k`.
- Geometry helpers must be index-based off that table, so a renumbering changes
  no routing code.
- When a vendor ships two variants of a part with different pin order under the
  same family name, a project-local symbol paired with a project-local footprint
  from one table is the only safe construction. Pairing a stock symbol with a
  variant footprint swaps nets silently and DRC-clean. See
  `kb/keyboards/sk6812mini-e.md` for the canonical instance.
- Carry the electrical type per pin in the same table so ERC is meaningful:
  `power_in`, `power_out`, `input`, `bidirectional`.

### When both halves are stock, assert the pairing instead

A stock symbol paired with a stock footprint generates nothing, so there is no
single table to generate from. The reasoning behind the rule, that a hand-paired
symbol and footprint will eventually disagree, still applies in full.

The answer is an assertion in the project's library builder:

- the footprint's pad set equals the symbol's pin set;
- every pad has a net in the design's own pin-net table;
- and, the one that catches the actual trap, **for any part whose labels are
  known to be non-portable, assert by physical position, never by letter.**

Worked case: a rotary encoder whose knowledge-base card states that the letter
on the common terminal is not portable between footprint authors, and that only
its physical position, the middle of the 3-pad row, is. So the assertion becomes
"the middle pad of the x=0 three-pad row is the one the design grounds". It
passes, and it would have caught a swap.

That is the same doctrine one sentence longer, and it covers the two families
where this keeps happening: connectors and encoders.

## 9. STEP export: the AP214 assembly, `(model ...)` conventions, and proving nothing moved

A KiCad STEP export is an **AP214 assembly**. Each unique 3D model's geometry is
written once, in its own local frame. Every footprint that uses it is an
instance, carried by:

```
NEXT_ASSEMBLY_USAGE_OCCURRENCE
  -> PRODUCT_DEFINITION_SHAPE
  -> CONTEXT_DEPENDENT_SHAPE_REPRESENTATION
  -> ITEM_DEFINED_TRANSFORMATION
  -> AXIS2_PLACEMENT_3D
```

That structure makes `grep CARTESIAN_POINT | min/max` two different tools
depending on what it is pointed at.

### Trap: `CARTESIAN_POINT` is a valid z-extent check for the board and copper, and an invalid one for components

The board slab and copper are baked into the file as absolute coordinates, so a
min/max sweep over their points is correct. A component's geometry sits at its
raw local coordinates and is placed only by the occurrence transform chain
above, so the same sweep over a component's points reports where its model was
authored, not where it sits on the board. One tool answers one question
correctly and the other confidently wrong, in the same file.

The failure signature: every component appears to sit at z 0 to h, on the wrong
face, intersecting the board. Read that way once, it was reported as a defect,
an agent was dispatched to fix a bug that did not exist, and the round trip was
wasted.

Verify correctly, cheapest check first:

1. `kicad-cli pcb render --side left` (or `--side bottom`). One command,
   transform-aware, and a side profile shows a back-face part hanging below the
   board or a front-face part standing above it immediately. Reach for this
   before writing any STEP parser.
2. Resolve the occurrence transform chain, which `scripts/kicad_3d.py verify`
   does:

   ```bash
   python3 scripts/kicad_3d.py verify OUT.step --board BOARD.kicad_pcb
   ```

   It reports every occurrence's placed origin, its Z-axis direction and hence
   its face, and with `--board` cross-checks that face against the footprint's
   own `IsFlipped()`, exiting nonzero on a mismatch. `--verbose` gives the
   per-occurrence table, `--json` makes it consumable.

   **It deliberately does not map each model's local geometry through the
   transform**, so it will not tell you a part is floating above the board at
   the right face. Only the render does that. The two are complementary and
   neither subsumes the other: `verify` catches a wrong face across 150
   occurrences nobody will eyeball, the render catches a right face at the
   wrong height.

   One semantic to know before reading its output: **one footprint may carry
   several models, and one of them may sit on the opposite face on purpose.** A
   keyswitch inserted from the far side into a socket soldered on this one is
   the standard case. So the failure condition is not "some model faces the
   other way", it is "no model for this footprint is on the face the board
   says". `verify` prints the former as an informational `opposite-face models`
   line and fails only on the latter. Written the naive way it turned 22
   correct switches into 22 red lines.

Measured datum, KiCad 10.0.5, 1.6 mm board: the board slab spans z −0.085 to
+1.595, the two offsets being soldermask overhang. A back-face occurrence's
origin lands at z exactly −0.085 with a mirrored Z axis; a front-face
occurrence's origin lands in [0, 1.595].

### Trap: `(model ...)` offset and rotation do not use the sign you would guess

The block is `(model PATH (offset (xyz ...)) (scale (xyz ...)) (rotate (xyz
...)))`, offsets in mm and rotations in degrees, attached per footprint.

The offset's Y component is inverted relative to the footprint's local +Y. Z
rotation is clockwise-positive, and a naive counter-clockwise rotation matrix
gives the wrong sign: a module whose model had USB at local +Y needed `rotate
(0,0,-90)` to put USB west, and `+90` put it east instead. Derive the sign for a
new part by rendering it, not by trusting the matrix.

### Trap: `scale` mirrors a part; it does not turn it over

`scale (xyz -1 1 1)` is honoured as a true geometric reflection, which is the
mechanism for serving the mirrored population of a reversible footprint.
Verified by rendering a mirrored and an unmirrored instance of an asymmetric
part side by side.

A part mounted from the opposite face needs `rotate (180,0,0)` plus a negative z
offset equal to the board thickness, not `scale (1,1,-1)`. The 180-degree X
rotation flips z and y together, which is what turning a part over actually
does. The scale mirrors the part in place and leaves it inside-out; the symptom
was a keyswitch stem poking up through the top of the board.

### Trap: a STEP file may declare its units as metres

KiCad honours the unit context on import, so a mis-scale is a factor of 1000. It
is invisible in a numeric check on the placed coordinates and unmissable in a
render. Verify units by picture, not by reading the declared scale back.

### Calibrate on one instance before applying to all

Attach the model to one footprint, render, look, and iterate on that one before
touching the rest. On the reference run this took two iterations each for the
switch and for the module and got the other five parts right on the first try.
The cost of skipping this step is paying for the same sign error N times instead
of once.

A reversible footprint serving two mirror-image populations can carry only one
model placement. Pick a build, state which, and expect the other build's render
to show those parts mirrored. That is inherent to a single-placement
attachment, not a bug to fix.

### Trap: a vendor model may include hardware your board does not carry

The nice!nano model ships with populated pin headers reaching 5.04 mm past the
board's back face. This design socket-mounts the module on 1.90 mm standoffs and
has no such pins. Left in, the headers dominate the assembly's z extent and make
an enclosure clearance look far worse than it is. Flag features like this rather
than trusting the model's own z extent.

### Trap: attaching models makes the raw diff enormous, and enormous does not mean wrong

Attaching models regenerates footprints, which churns UUIDs, so `git diff` on
the board file is enormous and useless for judging whether copper moved: the
reference change showed 18,613 deletions for an edit that moved nothing.
`kicad_digest.py --compare` also reports `DIFFERS`, correctly, because the model
lines are genuinely new lines.

The check that means something is a **geometry fingerprint**: compare the
multiset of pads, tracks, vias, zone outlines, and edge segments between the old
and new board, ignoring model attachment lines entirely. On the reference
project that count was identical before and after: combo 1503 primitives, left
793, right 811, proto 23. Either extend `kicad_digest.py`'s comparison to
separate "model lines added" from "geometry changed", or state the fingerprint
method by hand. Describe the principle here; do not invent a comparison flag for
a script you have not read.

## 10. Specctra DSN export and SES import: the autorouter bridge

`scripts/kicad_route.py` uses this for the autorouting flow decided in
`references/autorouting.md`. This section is the API-level detail: what
interface does it, and every trap found while exercising it. Verified against
KiCad 10.0.5 unless stated otherwise; every check below was run against a copy
of a real board, never a toy file.

### There is no `kicad-cli` path

Checked directly: `kicad-cli pcb export --help` lists 3dpdf, brep, drill, dxf,
gencad, gerbers, glb, hpgl, ipc2581, ipcd356, odb, pdf, ply, pos, ps, stats,
step, stl, stpz, svg, u3d, vrml, xao. No `dsn`. `kicad-cli pcb import --help`
imports a *different* CAD tool's PCB file into KiCad format (pads, altium,
eagle, cadstar, fabmaster, pcad, solidworks), it does not read a Specctra
session, and nothing in `kicad-cli` writes one either.

The KiCad 10 IPC API (`kicad-python` / `kipy`) does not fill this gap. Its
published documentation (docs.kicad.org/kicad-python-main) shows `Board`
exposing `get_footprints/tracks/vias/pads/nets/zones`, headless document
open/create, and generic graphic shapes, no DSN/SES import or export, and no
documented track/via creation call as of this writing. So a scripted router
integration in KiCad 10 has exactly one path: the same SWIG `pcbnew` module
`kicad_zonefill.py` already depends on.

```python
pcbnew.ExportSpecctraDSN(board, "board.dsn")   # -> bool
pcbnew.ImportSpecctraSES(board, "board.ses")   # -> bool
```

Both confirmed present by introspecting the bundled interpreter
(`hasattr(pcbnew, "ExportSpecctraDSN")` / `"ImportSpecctraSES"`), both
free functions (not `BOARD` methods) taking the board and a filename. Both run
under KiCad's bundled interpreter only, like every other `pcbnew` call in this
file, run either under the system python and you get an ImportError, not a
routing result.

### Trap: locking is the whole protection mechanism, and export is silent about it

`ExportSpecctraDSN` writes a wire's Specctra `type` field from the track's own
`Locked` state and nothing else. Measured: exporting a board with five tracks
marked `SetLocked(True)` and 190 left alone produced a DSN with exactly five
`(type fix)` wires; every unlocked wire carries no `(type ...)` field at all
(that omission is the Specctra "normal", meaning free to reroute).

So the entire hybrid-routing contract in `references/autorouting.md`, the
generator routes power, differential pairs, the crystal, USB by script, and
those runs are supposed to survive the autorouter, depends on one line the
generator must not forget: `track.SetLocked(True)` / `via.SetLocked(True)`
before `SaveBoard()`, for every item on a net the generator routed itself.
Nothing at export time enforces this; a generator that forgets it produces a
perfectly valid DSN, and the autorouter will happily reroute a "protected"
net with no error from any tool in the chain. `kicad_route.py export-dsn`
reports the locked-track count from the board against the fixed-wire count in
the DSN and warns on a mismatch, but that is a smoke check, not a substitute
for locking in the first place.

### Trap: an external router may rewrite the project's DRC floors

KiCadRoutingTools' `route.py` lowers the output `.kicad_pro` Board Setup
constraints to whatever it routed unless `--no-fix-drc-settings` is passed
(measured: `min_hole_clearance` 0.25 mm to 0.20 mm). A gate run beside that
file passes copper the project's own rules reject. Any wrapper around an
external tool copies the project's own `.kicad_pro` beside the output before
the refill and the gate; `kicad_route.py route-krt` does. The general form of
the rule: a tool's "DRC clean" is a claim about the rules it wrote, and the
gate measures against the rules the project wrote.

### Trap: `ImportSpecctraSES` replaces the routing, it does not patch it

Measured on a copy of a fully-routed 150-track / 45-via test board: importing
a hand-built session that named a single wire on a single net left the board
with **one track and zero vias**. Every other net's copper was gone, not
flagged as unrouted, just absent, because a session file is read as the
board's entire routing solution, not a diff against what was already there.
The two copper pours were untouched, because Specctra has no zone concept at
all; only tracks and vias are subject to replacement.

This is safe exactly once: when you import a real router's own output session
against the same DSN it just routed, because that router's session enumerates
every net it read, including the ones it left untouched because they were
locked. It is never safe to import a partial, hand-edited, or stale session
against a board whose nets have since changed. `kicad_route.py import-ses`
diffs per-net track/via counts before and after and warns on any net that had
copper and now has none, which is this trap made visible instead of silent.

### Trap: the session's `(resolution um N)` scales every coordinate on import

KiCad's DSN export declares `(resolution um 10)` and `(unit um)` in its header
and then writes coordinates in plain micrometres: on the test board, a switch
placed at the 19.05 mm key pitch appears as `(place SW2 19050 -31999.999
front)`, and a 0.25 mm track at x 7.0 mm as `(wire (path F.Cu 250 7000
-35000 7000 -38800))`. `ImportSpecctraSES`, however, divides every coordinate
and width in the session by the resolution the session's own `(routes
(resolution um N))` block declares.

Measured: a hand-built session that copied the DSN's numbers verbatim under a
`(resolution um 10)` header came back at 0.7, -3.5 to 0.7, -3.88 mm and
0.025 mm wide, every number exactly 10 times too small. The factor is the
declared resolution, not a rounding artefact.

A real router writes its session in resolution units (a 7.0 mm coordinate
under resolution 10 is written 70000), which is why the production
`ExportSpecctraDSN` to Freerouting to `ImportSpecctraSES` round trip does not
hit this (a third-party project using that exact pipeline,
github.com/bluzername/specs-to-pcb, applies no scaling correction anywhere).

**Verified locally, 2026-09-20**, against a real Freerouting v2.4.1 session
(`kb/runs/hexpad-autoroute-2026-09-20.md`): importing its output SES into the
same board it routed and reading tracks back with `kicad_geom.py`, 107 of 534
track endpoints land exactly (0.0000 mm) on a pad centre. The 10× scaling
trap does not reproduce against a real router's own session; it remains real
only for a hand-built or replayed one.

Two rules follow. A hand-built session is good only for proving the API call
is reachable and does not corrupt the board file; it is not evidence of
coordinate fidelity. And `kicad_route.py adopt` should only ever run against a
board produced by importing a real router's session, never a hand-built one.

### The generator/router boundary, and why `adopt` exists

An autorouter is not a pure function of `design.py`: run it twice and there is
no guarantee of the same tracks, or even the same topology. `gen_pcb.py`
calling into a router directly would break the determinism contract
`kicad_digest.py` exists to check, a wipe-and-rebuild is supposed to
reproduce the same canonical digest, and nothing about that claim survives an
autorouter in the hot path.

`kicad_route.py adopt` is the seam: it runs once, outside `gen_pcb.py`,
against a board whose routing has already been reviewed and gated by hand,
and freezes every track and via into a plain python data module, the same
kind of named-constant table `design.py` already carries for everything else.
`gen_pcb.py` imports that module and replays it; the router itself is never
called again during a normal build. A wipe-and-rebuild after adoption is
deterministic for the ordinary reason any constant-driven geometry is:
nothing nondeterministic runs during generation.

The corollary is the staleness rule: adopted copper is positioned against the
pad locations the board had when it was adopted, and a track endpoint carries
no memory of which pad it used to touch. Any placement change to any
footprint makes the whole adopted routing file suspect, because there is no
cheap way to prove which routes were unaffected short of cross-referencing
every moved footprint's pads against every route endpoint by hand, exactly
the kind of proof-instead-of-nudge this document's "nudge, do not prove" rule
elsewhere exists to avoid. Re-route in full on any placement change; do not
try to salvage part of an adopted file.

### Measured, 2026-09-20: the full round trip against a real Freerouting run

Everything above this point in §10 was verified against the DSN/SES
interfaces individually, or from Freerouting's own documentation. A complete
export-dsn / route / import-ses / gate / adopt round trip, against a real
Freerouting v2.4.1 process, on a copy of the hexpad board (see
`kb/runs/hexpad-autoroute-2026-09-20.md` for every command and number),
closes that gap. Two traps found doing it, neither previously documented:

**Two independent macOS JREs are not interchangeable for this jar, and the
wrong one fails silently rather than loudly.** `/usr/bin/java` (OpenJDK
21.0.2) loads freerouting-2.4.1.jar far enough to print `Error:
LinkageError... UnsupportedClassVersionError: ... has been compiled by a
more recent version of the Java Runtime (class file version 69.0), this
version of the Java Runtime only recognizes class file versions up to 65.0`
and then **exits 0**, with no `.ses` written. A caller checking only the
return code sees success. `/opt/homebrew/opt/openjdk/bin/java` (OpenJDK
25.0.2, Homebrew) runs the same jar cleanly. `kicad_route.py`'s `find_java`
now probes every candidate's own `java -version` and picks the highest major
version rather than a fixed path order, because which JRE is "correct" is a
property of the jar's own minimum, which climbs between Freerouting
releases, not of the machine.

**A router that completes 100% of what it can see is not the same as a
board `kicad_gate.py` will pass.** Freerouting's own log reported 0 unrouted
and 0 violations, final score 999.99/1000, for a run that `kicad_gate.py`
(after the mandatory post-import zone refill) failed on three grounds: 20
track segments delivered below the project's 0.2 mm floor on six specific
nets despite a 0.25 mm declared DSN class width, 11 `copper_edge_clearance`
violations from routing through four LED footprints' own interior
`Edge.Cuts` cutouts, and 3 `unconnected_items` from a single pinched GND
zone corner, the `SetMinThickness` trap in §4 above, reproduced by an
autorouter's copper instead of a scripted one. Freerouting has no notion of
either a footprint-owned board cutout or a zone's fill polygon, so none of
these three classes could have appeared in its own log. `references/
autorouting.md` §6a has the full comparison against KiCadRoutingTools, which
passed the same gate outright on the same board (after the zone refill its
own output also needs, a distinct, separately-measured instance of the same
stale-`filled_polygon` trap).

## 11. Footprint forking: the `(descr)`, `(tags)`, `(model)` fields, and why the copy lives in the project library

`scripts/kicad_fplib.py` is the write path for a footprint finding: fork a
stock footprint into the project library, edit the fork, record why. See
`kb/README.md`'s "where a fact lives" table for the doctrine this
mechanises, and `agents/resource-scout.md` gate 7 for where the finding that
triggers a fork comes from (`kicad_fpcheck.py`).

### Why the fork lives in `kicad/lib/`, not in KiCad's install directory

KiCad's own install (`/Applications/KiCad/KiCad.app/Contents/SharedSupport/
footprints/` on macOS; see `preflight.py`'s `model_roots()` for the
per-platform discovery this mirrors) is shared across every project on the
machine and is not this repository's to version. Editing a footprint there
changes it for every other project too, silently, and the edit disappears on
the next KiCad upgrade.

A project-local library under `kicad/lib/<project>.pretty/` is neither: it is
committed with the project, versioned with the project's own history, and
touches nothing outside it. This is the same reasoning `kb/keyboards/
local-libraries.md`'s "vendor into the project library, then upgrade"
doctrine already states for a whole library; a forked single footprint is the
same move at the grain of one part.

### `fp-lib-table` already resolves the fork, via `kicad_scaffold.py`

A project's `fp-lib-table` does not need to be told about a forked
footprint individually. `kicad_scaffold.py`'s `discover_libs()` globs every
`*.pretty` directory under the project's own `lib/` (or its parent's `lib/`,
the usual layout, one shared library serving several board variants) and
writes one `(lib ...)` row per directory, URI-anchored on `${KIPRJMOD}`:

```
(lib (name "myproj")(type "KiCad")(uri "${KIPRJMOD}/../lib/myproj.pretty")...)
```

So `kicad_fplib.py fork ... --into kicad/lib/<project>.pretty` followed by a
re-scaffold (or a scaffold that has not run yet) is enough for the project's
footprint library table to resolve every footprint in that directory,
forked ones included, by `LIB:NAME` exactly as any other project-local part.
No hand-edit of `fp-lib-table` is needed or wanted; see `references/
kicad-api.md` §1's rule that copper and library tables are both generated,
never hand-edited.

### The three fields a fork carries

A stock footprint already has `(descr ...)`, `(tags ...)`, and, where a 3D
model exists, `(model ...)`. A fork does not invent new fields, it rewrites
these three:

- **`(descr ...)`** is a single-line free-text string. `kicad_fplib.py
  annotate` appends a stamp to whatever was already there: `"<original> --
  hw_forge fork: <NOTE> (source: <URL>, <DATE>)"`. The original text
  survives, so a footprint forked twice keeps both stamps in order, readable
  in KiCad's own footprint properties dialog without opening the file.
- **`(tags ...)`** is a space-separated search-term string. `annotate` adds
  the literal word `hw_forge-fork`, once, so a project's whole library can be
  grepped or filtered for forked-and-modified footprints (`grep -l
  hw_forge-fork lib/*.pretty/*.kicad_mod`) without reading `lib/
  PROVENANCE.md` first.
- **`(model ...)`** is the 3D-model attachment block, covered in full in §9
  above (the AP214 assembly structure, the offset/rotate sign conventions,
  and why a render is the only reliable verification). `kicad_fplib.py
  set-model` writes or replaces this block using the `${KIPRJMOD}`-anchored
  path convention every project-local model already uses (`kb/README.md`'s
  "where a fact lives" table): `${KIPRJMOD}/3dmodels/NAME.step`, resolved by
  `preflight.py`'s `resolve_model()` against the LIBRARY directory (the
  `.pretty`'s own parent), not the board project directory. A shared
  library serving two board variants at different depths would otherwise
  resolve the same `${KIPRJMOD}` two different ways; anchoring it to the
  library, once, is what makes a forked footprint's model resolve
  identically regardless of which variant loads it.

None of the three is optional to get right: a `(descr)`/`(tags)` stamp with
no matching `lib/PROVENANCE.md` row is a footprint nobody can trace, and a
`(model ...)` block with the wrong anchor is a path that looks correct and
resolves to nothing (§9's "a footprint naming a model is not evidence that
the model exists" trap, one level up from the model file itself). Run
`preflight.py --project` after a `set-model` call, the same check gate 7
already requires before trusting a provenance row.
