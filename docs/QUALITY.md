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
| 1 | The toolchain runs, libraries resolve, every 3D model link resolves, and no rule file names one of the ten known fork keywords while this `kicad-cli` is stock | `preflight.py --project` | all three, by not trusting a broken tool | rule files written from the shipped templates |
| 2 | The schematic is electrically consistent | `kicad_gate.py` ERC | does not work | none |
| 3 | The board matches the schematic, at error severity, with parity enforced, and obeys the fab's floors | `kicad_gate.py --require-board --strict-parity`; severities and `NAME.kicad_dru` from `kicad_scaffold.py` | does not connect, does not work | a scaffolded project |
| 4 | Every footprint is the package the part is | `kicad_fpcheck.py --design` | does not work | `design.py` `PACKAGES` |
| 5 | Every sourced part can be bought and every board-inherent item is off the BOM | `kicad_bom.py audit` | does not work | `design.py` `PARTS` sourcing fields |
| 6 | No supply pin lacks a decoupling capacitor, every rail carries bulk capacitance, the first addressable LED has a data resistor, and I2C and reset nets have a pull-up inside their class's window; DNP parts count for nothing | `kicad_schrules.py` | does not work | `sch-rules.json` only to change a default or waive a finding with a reason |
| 7 | A human can read the silkscreen | `kicad_silkcheck.py` | assembly errors | the fab's floors |
| 8 | Every standardized connector is wired to its standard | `kicad_ifcheck.py --board` | does not connect | `PARTS[ref].interface` |
| 9 | Every connector declares a mating direction, and its mating face points out through a board edge within a stated distance | `kicad_geom.py --contract` | does not connect | `PARTS[ref].mating_direction` for every connector |
| 10 | The board and every part body fit the enclosure with margin, every external mating face has a clear opening on the right wall, no wall is thinner than the print floor, and the screws engage | `case_verify.py --contract` with `board_in_cavity`, `cavity_clearance`, `connector_openings`, `min_wall`, `fastener_stackup` | does not fit, does not connect | the fit contract, part heights (`height_mm` or STEP models) |
| 11 | The fab export is complete and matches the board: hole tallies, placement counts, empty layers, no empty BOM cell | `kicad_fab.py --profile` | does not work | `fab-profile.json` |
| 12 | The populated 3D assembly exports, with every body placed | `kicad_3d.py export` + `verify` | does not fit | 3D model links |
| 13 | All of the above, at once, on the board about to be ordered | `hw_review.py` exit 0 | all three | all of the above |

Rows 1 to 12 run inside their own phases (`SKILL.md`, "The phases"). The
phase 4 gate is row 3 (DRC with parity, and the unconnected count), row 7
(silk), row 8 (interfaces) and row 9 (the fit contract); `make check` is its
DRC half, and `make review` runs all of it. Row 13 is phase 5a, the pre-order
review, and it is the one gate whose exit code means "ready to order". Its
entry contract is a gated board plus its fab profile. It runs after phase 4
and before the fab export (it exports into a scratch directory of its own),
and again after phase 6 when there is an enclosure, so the case row is real.
`make fab` depends on it.

Row 1 detects only the ten known fork keywords (`preflight.py`'s
`FORK_KEYWORDS`, checked against the probe's verdict on this `kicad-cli`).
Stock `kicad-cli`
10.0.5 drops a whole rule file that names any keyword it does not compile,
silently and with exit 0, so any other unknown keyword still disables every
rule in the file. Rule files are therefore written from the shipped templates
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

The forked `kicad-cli`'s `connector_edge` DRC does not read the same source
yet. Its current baseline binary reads a board-frame field `Mating_Direction`
with values N, S, E, W. The fork's owner is changing it to read the footprint
property `mating_direction` with +x -x +y -y +z -z in footprint axes (their
workstream C, not yet landed). Once that lands, one footprint field serves
both checks. Until then the fit contract is the check that sees the mating
end.

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
| mating direction | The outward normal of a connector's mating face, in footprint-local axes. Defined in `references/interfaces.md` §0.1. |
| SKIP | A row whose property was not proven, with the reason. Not a pass. |
| STEP | The 3D exchange format KiCad exports and code-CAD reads. |
| z band | The vertical extent of a part, in the board frame: z = 0 on the top face. |
