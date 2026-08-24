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

# BOM: export flat, then group in your own script (see below).
kicad-cli sch export bom -o .bom-flat.csv --fields "Reference,Value,Footprint,DNP" \
  --labels "Refs,Value,Footprint,DNP" --group-by "" --sort-field Reference \
  --ref-range-delimiter "" board.kicad_sch

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
