# The quality process

What hw_forge proves about a board before it is ordered, and which check
proves each property. The process is the same for any electrical design: a
keyboard, a microphone preamp, a motor driver, a sensor breakout. What changes
between domains is the list of domain rules in section 4, not the sequence.

For how to run the pipeline, see [`../README.md`](../README.md). For the phase
contracts, see [`ARCHITECTURE.md`](ARCHITECTURE.md) section 3.

## 1. Three ways a board fails

Every check below exists to prevent one of three outcomes after an order.

| Class | What happens | Measured example |
|---|---|---|
| **Does not fit** | The board or a part collides with its enclosure, a wall is too thin to print, or a screw is too short. | A case wall thinned to 0.35 mm passed every numeric check (`BACKLOG.md` B9). |
| **Does not connect** | A plug cannot reach its socket, or a cable carries the wrong signal to the wrong pin. | A USB-C receptacle placed with its mating face inboard passed DRC, courtyard and case checks, and could not be plugged in (`BACKLOG.md` B8). A USB-C device port with no CC pulldowns passes ERC and draws no power from a USB-C charger (`references/interfaces.md` §1.4). |
| **Does not work** | The circuit is wired as drawn and the drawing is wrong: a part outside its bias window, a missing decoupling capacitor, the wrong package for the ordered part. | A SOIC-8 wide flash on SOP-8 narrow pads passed every DRC and was caught at assembly (`kb/parts/package-family-traps.md`). |

ERC, DRC and schematic parity prove one thing: the board matches its own
schematic. None of the three examples above is visible to them. The rest of
the sequence exists for that reason.

## 2. The properties, in order

Each row is a property the pipeline proves, the check that proves it, and the
class of failure it prevents. A check proves its property only when it exits 0
**and** its input declarations exist. A check that ran on nothing reports
SKIP, and a SKIP is a property nobody proved.

| # | Property | Check | Prevents | Declarations it needs |
|---|---|---|---|---|
| 0 | The board and the schematic were generated from the current `design.py` | `hw_review.py` row `fresh` (`hw_stamp.py`) | all three, by not gating a stale board | the template Makefile's generation rule (`hw_stamp.py --write --also gen_sch.py --also gen_pcb.py`), or generators that call `hw_stamp.stamp_file` (`templates/design.py`, "Generated-file stamp"); a `design.py` the review can find (`--design`, or `PROJECT_DIR` and three directories up) |
| 1 | The toolchain runs; every library URI resolves on disk, KiCad path variables included; every 3D model link resolves, the project's own footprints and every footprint placed on the board; `design.py` imports under the system python and KiCad's; the project Makefile is the current template version; and no rule file names one of the ten known fork keywords while this `kicad-cli` is stock | `preflight.py --project` | all three, by not trusting a broken tool | rule files written from the shipped templates |
| 2 | The schematic is electrically consistent | `kicad_gate.py` ERC | does not work | none |
| 3 | The board matches the schematic, at error severity, with parity enforced, and obeys the fab's floors | `kicad_gate.py --require-board --strict-parity`; severities and `NAME.kicad_dru` from `kicad_scaffold.py`; on a forked `kicad-cli`, `--severity-override` and `--strict-rules` | does not connect, does not work | a scaffolded project |
| 4 | Every footprint is the package the part is, and every polarized part sits on a footprint that marks its polarity | `kicad_fpcheck.py --design` | does not work | `design.py` `PACKAGES`; a family not in `scripts/packages.json` in `packages-project.json`; `FPCHECK_WAIVERS` with a reason for a padded part no table can describe; the schematic, for polarity |
| 5 | Every sourced part can be bought, every board-inherent item is off the BOM, and every off-board part (a panel connector on a pigtail, a capsule on leads) is on it while its pads stay out of the placement file | `kicad_bom.py audit` | does not work | `design.py` `PARTS` sourcing fields; `BOARD_INHERENT` or `PARTS[ref].offboard` for off-board parts |
| 6 | No supply pin lacks a decoupling capacitor, every rail carries bulk capacitance, the first addressable LED has a data resistor, and I2C and reset nets have a pull-up inside their class's window; DNP parts count for nothing | `kicad_schrules.py` | does not work | `sch-rules.json` only to change a default or waive a finding with a reason |
| 7 | A human can read the silkscreen | `kicad_silkcheck.py` | assembly errors | the fab's floors |
| 8 | Every standardized connector is wired to its standard | `kicad_ifcheck.py --board` | does not connect | `PARTS[ref].interface`; a definition shipped, in a knowledge base, or in the project (`PROJECT/interfaces/*.json`, `PROJECT/kb/interfaces/*.md`) |
| 9 | Every connector declares a mating direction, and its mating face points out through a board edge within a stated distance | `kicad_geom.py --contract` | does not connect | `PARTS[ref].mating_direction` for every connector |
| 10 | The board and every part body fit the enclosure with margin, every external mating face has a clear opening on the right wall, every off-board panel part's opening clears its body and its mated plug and its pigtail reaches, no wall is thinner than the print floor, and the screws engage | `case_verify.py --contract` with `board_in_cavity`, `cavity_clearance`, `connector_openings`, `min_wall`, `fastener_stackup` | does not fit, does not connect | the fit contract, part heights (`height_mm` or STEP models), `PARTS[ref].offboard` for a part on the enclosure |
| 11 | The fab export is complete and matches the board: hole tallies, placement counts, empty layers, no empty BOM cell | `kicad_fab.py --profile` | does not work | `fab-profile.json` |
| 12 | The populated 3D assembly exports, with every body placed | `kicad_3d.py export` + `verify` | does not fit | 3D model links |
| 13 | All of the above, at once, on the board about to be ordered | `hw_review.py` exit 0 | all three | all of the above |

Row 0 is the first row of the pre-order review: a board older than its
`design.py` makes every other row a statement about a design that no longer
exists (measured, hypercardiod_mic: `design.py` edited 28 minutes after the
board was saved, and every gate ran on the old board).

Rows 0 to 12 run inside their own phases (`SKILL.md`, "The phases"). Row 0's
stamp is written in two phases: phase 3 `gen_sch.py` stamps the schematic, and
phase 4 `gen_pcb.py` stamps the board. The Makefile's generation rule then
restamps both with one hash that also covers `gen_sch.py` and `gen_pcb.py`. The phase 4 gate is row 3 (DRC with parity, and the unconnected count), row 7
(silk), row 8 (interfaces) and row 9 (the fit contract); `make check` is its
DRC half, and `make review` runs all of it. Row 13 is phase 5a, the pre-order
review, and it is the one gate whose exit code means "ready to order". Its
entry contract is a gated board plus its fab profile. It runs after phase 4
and before the fab export (it exports into a scratch directory of its own),
and again after phase 6 when there is an enclosure, so the case row is real.
`make fab` depends on it.  `hw_review.py PROJECT_DIR` accepts a project
root: it uses PROJECT_DIR, else PROJECT_DIR/kicad, else the one board
variant under PROJECT_DIR/kicad, and prints which.

Stock `kicad-cli` 10.0.5 drops a whole rule file that names any keyword it
does not compile, silently and with exit 0, which would disable every rule in
the file. Two checks close that:

- Row 1 detects the ten known fork keywords (`preflight.py`'s
  `FORK_KEYWORDS`, checked against the probe's verdict on this `kicad-cli`).
- Row 3 covers every other keyword. On a binary without `--strict-rules`,
  `kicad_gate.py` checks each constraint keyword in `NAME.kicad_dru` against
  `preflight.STOCK_CONSTRAINTS` (read from the 10.0.5 parser) and fails
  `DRC rules DROPPED`. On the forked `kicad-cli` it passes `--strict-rules`,
  and a rule file that does not compile fails with exit 8, reported as
  `rule file invalid`.

Rule files are still written from the shipped templates
(`templates/drc-baseline.kicad_dru`, and `templates/drc-fork.kicad_dru` as the
block `kicad_scaffold.py --fork-rules` manages), never with hand-typed
keywords.

### The fit contract

Properties 9 and 10 rest on one file. `kicad_geom.py BOARD --contract FIT.json
--design design.py` writes the board-to-enclosure interface: outline polygon
and cutouts, mounting holes, and per part its plan envelope, one body box per
STEP model, its z band, and for a connector or user-facing part its mating
direction in board axes, the wall it points through, and the opening the case
must provide. The schema is in `kicad_geom.py`'s docstring.

The case reads that file. It never retypes a number from it, because a
retyped number is the one that drifts (`references/mechanical.md` §7 item 3).

A part that lives on the enclosure rather than the board (a GX16 panel
connector wired by a pigtail to solder pads) has no board coordinates to
read.  Its `PARTS[ref].offboard` block places it in the case frame, or
relative to a named case datum, as coaxial body pieces plus the mated plug
envelope, and the contract carries it under `offboard[]`.  Without it the
contract-driven opening check is vacuous for a product whose only external
connector is off the board (hypercardiod_mic GAPS.md gap 13).

The forked `kicad-cli`'s `connector_edge` DRC reads the same source: the
footprint property `mating_direction` (+x -x +y -y +z -z in footprint axes,
rotated by the footprint, y mirrored on the back face, +z and -z skipped).
Its message carries `body_to_edge_mm` and the angle to the nearest edge
normal. Without the property it falls back to the shortest body to edge
distance. Since 2026-10-03 the old board-frame field `Mating_Direction`
(N/S/E/W) is no longer read.

### Declarations are part of the check

Two of the three classes are invisible in the board file. The file carries a
footprint's position and rotation, not which way it mates, how tall it is, or
which standard it follows. So `design.py`'s `PARTS` table carries
`mating_direction`, `height_mm` (or `z_band`) and `interface` for every
connector and user-facing part (`templates/design.py`). A missing declaration
never reads as a pass:

- A connector is any part `PARTS` gives a role, an interface or a mating
  direction, any part whose reference prefix is J, P, USB, CN or X, and any
  part whose footprint library starts with `Connector`. One with no
  `mating_direction` fails the fit contract ("undeclared mating_direction"),
  and `connector_openings` fails it too.
- A board with no connector gets SKIP "no connector on this board" in the
  fit row, never PASS.
- A part with copper pads that `kicad_fpcheck.py` skipped (no declared
  package, no name it recognises) makes the fpcheck row FAIL, naming it.
  A `design.py` `FPCHECK_WAIVERS` entry with a reason makes it a WARN that
  prints the reason. PASS means every padded part was checked
  (hypercardiod_mic GAPS.md gap 2: a row read PASS with 28 of 29 parts
  skipped).
- No `design.py` found is a FAIL in the fresh row: the board cannot be
  proven fresh.
- A board or schematic with no `design.py` stamp is a FAIL in the fresh
  row, not a pass.
- A library URI whose path variable cannot be resolved is a preflight
  warning naming the variable, never an ok.
- A part with no height is a WARN, counted in the fit row's text.
- A declared interface with no definition is a WARN in `hw_review.py`
  (`--strict-interfaces` makes it a FAIL), and an ifcheck with nothing to
  check prints SKIP.

## 3. What the pipeline does not prove

Stated so a green table is not read as more than it is.

- **Part geometry is boxes.** `cavity_clearance` tests one box per STEP model
  (plan bbox times z band). A part whose plan changes with height, such as an
  encoder shaft through a deck, is coarser than a box. Such parts are exempted
  by name, with the reason printed as a recorded line.
- **`min_wall` samples.** Rays are cast inward from a grid on each face,
  about `spacing` mm apart (default 2 mm) on each face axis, capped at 64
  samples per axis. A thin region narrower than the spacing can be missed,
  and so can one on a face longer than 64 x `spacing` (128 mm at the
  default), where the cap stretches the grid. Lower `spacing` near a feature
  that must be proven. Deliberate thin features (an insert cap over a blind
  bore, 0.6 mm by `mechanical.md` §1) are exempted by region, with the reason
  printed (`BACKLOG.md` B9).
- **Numeric `cavity_clearance` is one-sided when told to be.** Without
  shells, a `floor_z` or `ceiling_z` left as None means infinite clearance on
  that side, printed as "not checked"; with both None the z test does not
  run. The numbers are the case's own, so this mode is weaker than the solid
  mode.
- **`kicad_schrules.py` pull-up windows are fixed ranges** per net class
  (i2c 1 k to 10 k, reset 4.7 k to 100 k by default), not the UM10204
  rise-time window, which needs the bus capacitance (`domains.md` 3.8).
- **Rules marked MANUAL or `manual`** in `references/interfaces.md` and
  `references/domains.md` have no script. `kicad_ifcheck.py` prints them as
  MANUAL, never PASS.
- **The physical part.** `kicad_fpcheck.py` checks the design file, not the
  unit a supplier ships (`BACKLOG.md` B3).
- **Placement-class interface rules**, such as a TVS within 5 mm of its
  connector (`X-ESD-02`), are not yet checked by a script.
- **Polarity marks are read from pads, silk and fab drawing only.**
  `kicad_fpcheck.py` accepts a pad 1 whose shape or size differs from the
  pad it pairs with, or a silk or fab item lying wholly in pad 1's half
  along the axis between the two pads.  A mark only in copper reads as no
  mark.  The check does not read what the mark means: a band or a "+" in
  pad 1's half passes whichever terminal pad 1 is, so a footprint whose
  pad 1 is the anode on a part whose pad 1 should be the cathode still
  passes.
- **Off-board bodies are cylinders and boxes along one axis**, and the
  pigtail check is a straight line from the pad centre to the panel tail
  plus the stated slack, not a routed length.
- **The fresh stamp hashes `design.py`, plus the files the stamp names.**
  The Makefile's stamp step folds in `gen_sch.py` and `gen_pcb.py`; a stamp
  a generator writes for itself covers `design.py` alone.  A change to a
  routing file or a footprint library does not make the stamp stale.

## 4. Domain-specific checks

The sequence above is generic. What a specific kind of circuit must also
satisfy, such as an analog front end's bias window, a buck converter's loop
layout, an RF trace's impedance, or a battery charger's protection, is listed
per domain in [`../skills/hw-design/references/domains.md`](../skills/hw-design/references/domains.md),
with the check or review step that establishes each property and its section
10, "What runs automatically today". Per-connector requirements, with rule ids
`kicad_ifcheck.py` reports, are in
[`../skills/hw-design/references/interfaces.md`](../skills/hw-design/references/interfaces.md).

At phase 0 the orchestrator names the domains a design touches in `SPEC.md`.
Each named domain's rules then enter the phase-3 and phase-4 agent prompts the
same way the locked decisions do (`SKILL.md`, "When to load which
reference").

## Appendix: terms

| Term | Meaning |
|---|---|
| BOM | Bill of materials. |
| DRC, ERC | KiCad's design rule check on a board and electrical rule check on a schematic. |
| fit contract | The JSON file `kicad_geom.py --contract` writes: the board as the enclosure must receive it. |
| off-board part | A part that lives on the enclosure and is wired to board pads: a panel connector on a pigtail, a capsule on leads. Its BOM row is on the board's BOM; its pads are not machine-placed. |
| stamp | The `hw_forge design-sha1:` title-block comment a generator writes, read by the fresh row. |
| mating direction | The outward normal of a connector's mating face, in footprint-local axes. Defined in `references/interfaces.md` §0.1. |
| SKIP | A row whose property was not proven, with the reason. Not a pass. |
| STEP | The 3D exchange format KiCad exports and code-CAD reads. |
| z band | The vertical extent of a part, in the board frame: z = 0 on the top face. |
