# KiCad automation — API surface, invocations, and known traps

Generic KiCad knowledge. Part-specific and project-specific facts live in `kb/`.
Verified against **KiCad 10.0.5** unless a version is named.

## 1. Pick the right interface

| Interface | Requires | Can write? | Use for |
|---|---|---|---|
| Files as text (s-expr) | nothing | yes, riskily | reading geometry, auditing pin maps, metadata edits |
| `kicad-cli` | 8+, best 10+ | no (outputs only) | **all verification and export**; headless, scriptable |
| SWIG `pcbnew` (bundled python) | ≤ 10 | yes | headless board generation *today* |
| IPC API (`kicad-python` / `kipy`) | 9+, **GUI running** | yes, transactionally | live edits, generative layout |

Rules:
- **Verification is always `kicad-cli`.** Never assert cleanliness from a generator's own bookkeeping.
- **Writing copper as text is forbidden.** Tracks carry UUIDs, zones carry cached fills, and nothing revalidates until KiCad parses the file. Text edits are for metadata and placement only.
- **SWIG `pcbnew` is deprecated in 9 and removed in 11.** Anything written now must be portable to IPC (`pip install kicad-python`). Plan the port; see §7.
- IPC cannot plot or export in 9/10. The durable split is **IPC (or SWIG) for edits, CLI for verification and export.**

## 2. The gate invocations

```bash
kicad-cli sch erc --severity-error --format json --exit-code-violations \
    -o erc.json board.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-error --format json \
    --exit-code-violations -o drc.json board.kicad_pcb
```

- `--exit-code-violations` returns **5** when violations exist → DRC/ERC become tests, usable directly in a Makefile.
- `--schematic-parity` is **not** the default and is the flag that catches the whole class of "board and schematic drifted": missing footprints, net mismatches, stale pad numbering. A DRC run without it is not a gate.
- `--severity-error` is the gate; run `--severity-all` separately to enumerate warnings and *document each surviving one*. A clean run only means something if the benign classes are written down.
- The JSON report has three independent buckets — `violations`, `unconnected_items`, `schematic_parity` — plus per-item `severity`. **Read all three**; a board can be DRC-clean and still have unconnected nets.
- Gate the *whole* set per project: `ERC 0 / DRC 0 at error severity with parity / unconnected 0`.
- Zones must be filled **before** the gate. Unfilled pours report their nets as unconnected.

## 3. Export invocations and their flag gotchas

```bash
# Gerbers — name every layer explicitly; the default set is not the fab's set.
kicad-cli pcb export gerbers -o fab/ \
  --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts \
  --no-protel-ext --subtract-soldermask board.kicad_pcb

# Drill — separate PTH/NPTH, absolute origin, mm, decimal. Every one matters.
kicad-cli pcb export drill -o fab/ --format excellon --drill-origin absolute \
  --excellon-units mm --excellon-separate-th --excellon-zeros-format decimal \
  --generate-map --map-format pdf --generate-report --report-path fab/drill.txt \
  board.kicad_pcb

# Placement — export all three; assemblers ask for different ones.
kicad-cli pcb export pos -o fab/pos-all.csv --side both   --format csv --units mm board.kicad_pcb
kicad-cli pcb export pos -o fab/pos-top.csv --side front  --format csv --units mm board.kicad_pcb

# BOM — export FLAT, then group in your own script (see below).
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
- **Inner layers must be added by hand** for a 4-layer board (`In1.Cu,In2.Cu`). Forgetting them produces a plausible-looking, unfabbable gerber set. Derive the layer list from the stackup, do not hardcode one.
- `--excellon-separate-th` splits PTH from NPTH — most fabs require it; a merged file silently plates your mechanical holes.
- `--drill-origin absolute` matches the gerbers' origin. Any other choice needs the same choice on the gerbers.
- **Do not pass `--check-zones` on the fab path.** Refilling during export means the plotted copper is not bit-for-bit the geometry the gate approved. Fill once, in generation; plot what was gated.
- `export pos --mirror` does not exist; use the per-side exports. `export svg --mirror` is for viewing the back layers as seen from the back.
- `kicad-cli sch export bom`'s grouping is weak; export flat with an explicit field list and regroup in a script that also emits a `Populate`/DNP column.
- Always follow the export with an **assertion script**: every artifact exists and is non-empty; drill tool table matches the expected hole census (count × diameter per tool); placement row count equals the expected footprint count. A fab export that "ran" is not a fab export that is right.
- Jobsets (`kicad-cli jobset run --file fab.kicad_jobset project.kicad_pro`, 9+) collapse the export set into one committed reviewable file. Worth adopting once the flag set stops changing.

## 4. Headless `pcbnew` (SWIG) — pattern and traps

Invoke under KiCad's *bundled* interpreter, never the system python:

```makefile
KICAD := /Applications/KiCad/KiCad.app/Contents          # macOS
CLI   := $(KICAD)/MacOS/kicad-cli
KPY   := $(KICAD)/Frameworks/Python.framework/Versions/Current/bin/python3
# Linux: /usr/bin/kicad-cli and system python3 with `import pcbnew` on the path.
```

Consequence for the design layer: the **logical design module must be pure python with no dependencies**, so that it imports identically under the system interpreter (schematic emitter, checks) and the bundled one (board emitter). One source of truth, two interpreters.

`pcbnew` prints `wxApp` warnings to stderr on every headless run; filter them (`2>&1 | grep -v wxApp || true`) rather than suppressing all output.

### Trap: `FLIP_DIRECTION` — the silent 180°
`BOARD_ITEM::Flip()`'s second argument was `bool aFlipLeftRight` through KiCad 8; in 10 it is a `FLIP_DIRECTION` enum whose `LEFT_RIGHT` member is **0**. So the KiCad-8 idiom `Flip(centre, False)` (= mirror top-to-bottom, i.e. "put this part on the back face") silently becomes a *left-right* mirror under 10. A left-right mirror equals a top-bottom mirror **plus 180°**, so every back-face footprint comes out end-for-end and every pad-relative track lands on the wrong terminal.

```python
FLIP_TB = getattr(pcbnew, "FLIP_DIRECTION_TOP_BOTTOM", False)   # 10 first, 8 fallback
fp.Flip(pt(x, y), FLIP_TB)
```
General rule: **never pass a bare bool to a KiCad API that may have grown an enum.** Prefer `getattr(pcbnew, "SOME_ENUM_MEMBER", <old-literal>)`.

### Trap: `SaveBoard()` overwrites the sibling `.kicad_pro`
`pcbnew.SaveBoard()` rewrites `<stem>.kicad_pro` from pcbnew's own defaults, wiping whatever the project scaffolder wrote (net classes, rule severities, min clearances). Therefore: **anything the DRC needs must be patched into the `.kicad_pro` *after* the save**, as an explicit post-step:

```python
pcbnew.SaveBoard(out, board)
patch_project(out)   # json-load .kicad_pro, merge board.design_settings.rule_severities, dump
```
Keep the patch table small and every entry commented with its justification — a demoted rule you cannot justify is a hidden defect.

### Zones
- `pcbnew.ZONE_FILLER(board).Fill(board.Zones())` **works headlessly in KiCad 10**; under 8 it aborted the interpreter (the filler wanted the app framework and `wx.App()` hangs with no display). Filling inside generation is what removes the last GUI step from the build.
- **Island removal must be by area, not connectivity, whenever a pour is fed by vias.** KiCad does not count a via when deciding whether a filled island is connected — only pads. A plane whose only *pad* is one pin will have every other island deleted under the default mode (observed: ~7900 mm² of fill reduced to 9.8 mm², 22 via-fed taps reported unconnected, with no clearance violation anywhere).
  ```python
  z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
  z.SetMinIslandArea(int(mm(3.0)) * int(mm(3.0)))
  ```
  Belt and braces: also route an explicit **stitch via** from the fed lane into the pour, so the connection is real copper rather than a fill coincidence. Never let *connectivity* depend on a fill.
- **Pad connection: solid (`ZONE_CONNECTION_FULL`), not thermal**, for generated boards. Thermal relief buys hand-soldering comfort and costs a `starved_thermal` error on any pad whose spokes land in a small island. Reflow and through-hole into a 1 oz pour do not need it.
- `SetMinThickness()` is a real failure mode: a pour pinched below its own minimum thickness by nearby copper silently splits into isolated islands, again **with no clearance violation** — nothing was too close to anything. When taps go unconnected and DRC is otherwise clean, suspect a pinch, not a clearance.

### Custom rules
Fab-justified relaxations go in a generated `<project>.kicad_dru` written by the same `patch_project()` step, one rule with its justification in a comment. Do not relax a global minimum to fix a local geometry problem.

Custom rules also run the other way: **fab capability floors**. KiCad's stock DRC is looser than real fabs in places (no absolute clearance floor at all, 0.10 mm via annular vs typical 0.15, 0.25 mm hole-to-copper and hole-to-hole vs typical 0.28/0.45 for plated holes), so a default-settings pass is not proof of manufacturability. Encode `max(design floor, fab floor)` per spec — never loosen your own floors to fab minimums. Unconditional floors go in the project `rules` dict via `patch_project()`; anything that differs by pad type goes in the `.kicad_dru`, because **the project `min_hole_clearance` knob is hole-blind** — it cannot distinguish plated from unplated holes, and fabs quote them differently (applying a PTH number globally cost z_board 148 false NPTH violations). Condition on `A.Pad_Type`; vias carry no `Pad_Type`, so PTH-conditioned rules correctly skip them. Current numbers per fab live in `kb/fabs/`.

### Trap: refs without a numeric suffix poison the CLI annotation check
Every reference a generator emits must end in a digit (`SW_PWR1`, not `SW_PWR`). A digitless ref makes every `kicad-cli sch` invocation print `schematic has annotation errors` forever — masking real annotation problems — and if anyone runs Annotate in the GUI, KiCad silently renames the part (`SW_PWR` → `SW23`), breaking every generator constant and BOM note keyed on the old ref.

## 5. Reading files as text (s-expressions)

Excellent for **reading**: parsing a footprint's pads out of `.kicad_pcb` is faster and more trustworthy than any GUI inspection, and it is how a pin-map audit should be done. Gotchas:

- **Footprint rotation in file coordinates is clockwise-positive**, and the file's y axis points *south*. A CAD frame that is right-handed with y north therefore needs **both** a `y → −y` and a rotation-sign flip. Getting one and not the other yields geometry that looks plausible and is wrong. Convert once, in one named helper, and assert the round-trip.
- Pad coordinates are **footprint-local**; the board position is `footprint.at` composed with the pad's `at` *rotated by the footprint angle*. Do not read a pad's `at` as a board coordinate.
- Zones carry a cached `filled_polygon`. It is stale the instant anything moves; never trust it without a refill.
- Everything carries a `uuid`/`tstamp`. Copying s-expr blocks duplicates UUIDs — KiCad tolerates it inconsistently. Generate fresh ones.
- NPTH (`np_thru_hole`) pads block **every** layer. When solving routing clearances, holes are not a copper-layer constraint, they are a whole-stackup constraint.
- KiCad counts an unplated hole wall as a **board edge** and applies the 0.5 mm outline clearance to it. That is a routed-outline number; a milled slot flank can legitimately be relaxed (fabs quote ~0.254 mm) — but only by a named custom rule, never globally.

## 6. Format upgrading

Vendored third-party footprints and symbols are usually an older format. Upgrade them into the project library once, in a scripted step:

```bash
kicad-cli fp  upgrade <lib>.pretty
kicad-cli sym upgrade <lib>.kicad_sym
kicad-cli pcb upgrade board.kicad_pcb      # one-way
kicad-cli sch upgrade board.kicad_sch      # one-way
```
Upgrades are **one-way** — branch or copy first. Custom-primitive pads are the usual casualty; diff a render before and after.

## 7. Migration note: SWIG → IPC (`kipy`)

`pip install kicad-python`; enable **Preferences → Plugins → API server**. `Board` exposes `get_footprints/tracks/vias/pads/nets/zones/selection`, `create_items/update_items/remove_items`, `begin_commit/push_commit/drop_commit` (grouped undo), `refill_zones()`, `save()`. Constraints: the GUI must be running, and plotting/export are not in the 9/10 API. Keep generators structured so the *geometry* layer is pure python and only a thin adapter touches `pcbnew` — that adapter is the whole port.

## 8. Doctrine: one pin table, two emitters

**Generate the symbol and the footprint for any module from a single pin table.** Hand-authoring both lets pin order drift between them, and the result is a board that is DRC-clean, parity-clean, and mis-wired on every instance of the part. The failure is silent because both files are internally consistent.

Corollary rules:
- The pin table is ordered by **physical pad position**; the pad *numbers* are whatever the vendor silkscreens. Never assume `index == pad number`. (Cost of assuming it once: a module footprint whose pad-1 marker sat at the wrong end of the column, needing a full renumber `k → N+1−k`.)
- Geometry helpers must be **index-based** off that table, so a renumbering changes no routing code.
- When a vendor ships two variants of a part with **different pin order under the same family name**, a project-local symbol paired with a project-local footprint from one table is the only safe construction. Pairing a stock symbol with a variant footprint swaps nets silently and DRC-clean. (See `kb/keyboards/sk6812mini-e.md` for the canonical instance.)
- Carry the electrical type per pin in the same table so ERC is meaningful (`power_in`, `power_out`, `input`, `bidirectional`).
