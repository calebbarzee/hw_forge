---
domain: projects/hexpad
tags: [hexpad, macro-pad, dry-run, validation-fixture, nice-nano, nice-view, sk6812mini-e, msk12c02, ec11, lipo, pico-ezmate, build123d, case-verify, gates, parity, revision, hand-edit-adoption]
source:
  - hexpad rev 1 build, 2026-08-22 (first end-to-end run from this repo alone)
  - hexpad rev 2 revision, 2026-08-23 (module and display rotated 90 degrees, board shrunk)
  - hexpad rev 3 / 3.1 re-spec, 2026-08-23 (diode matrix, rotary encoder, 3D model per footprint, four parts hand-dragged in pcbnew)
  - docs/DRYRUN-HEXPAD.md (the verdict), hexpad/GAPS.md (per-gap disposition, in the hexpad project repo)
date: 2026-08-23
confidence: verified-in-cad
---

# hexpad, the forward-validation fixture

A 6-key wireless macro pad, designed end to end using only this repository. It
is the counterpart to `zboard.md`: z_board is where the pipeline came from, and
hexpad is the evidence that it transfers to a board it was not written from.

Deliberately trivial as hardware. Nothing about the device is difficult, so
anything a session had to ask about or rediscover is a gap in the skill, a
missing knowledge card, or a script bug rather than a design problem.

## 1. What it is

A nice!nano v2 on sockets, a nice!view display, per-key SK6812MINI-E addressable
RGB, a lithium-polymer cell on a Pico-EZmate connector, an MSK12C02 slide switch,
and a printed two-shell enclosure with M2 heat-set inserts. Revision 3 added a
diode matrix in place of direct-pin scanning, and an EC11 rotary encoder.

It exercises the whole pipeline once: direct-wire keys, a Serial Peripheral
Interface (SPI) peripheral, a socketed module, a battery, and an enclosure with
a plate and inserts.

## 2. Gate state by revision

| Revision | What changed | Board gates | Enclosure checks |
|---|---|---|---|
| rev 1 | first build | ERC 0, DRC 0 with schematic parity, 0 unconnected, on both the board and its one-key proto slice | 215 |
| rev 2 | module and display rotated 90 degrees, board shrunk, case rebuilt | same, re-verified | 239 |
| rev 3 / 3.1 | diode matrix, rotary encoder, a 3D model required per footprint, four parts hand-dragged in pcbnew (two onto the other face) | same, re-verified | 416 |

Revision 1 also produced a 21-file fab package whose hole census, placement
split, and layer set are asserted rather than inspected by eye.

Across the three rounds the runs logged 94 gaps. 89 are fixed, 4 are deferred
with reasons in `docs/BACKLOG.md`, and 1 is works-as-intended. None was a design
failure.

## 3. Incidents the reference documents cite

Each entry below is the measured case behind a rule stated generically in
`skills/hw-design/references/`. The rule lives there; the numbers live here.

### 3.1 The schematic-parity gate could not fail

Supports the parity-severity rule in `references/kicad-api.md` §2.

Revision 3 gated green while its board was one revision stale. The board was
missing eight parts and had twenty-one net conflicts. Re-running the same board
with `--severity-all` instead of `--severity-error` reported 31 parity issues.

KiCad ships all five schematic-parity checks at `warning` severity, and the gate
filters on `--severity-error`, so passing `--schematic-parity` could not fail a
build. Auditing z_board afterwards found the same blind spot on all four of its
boards, and two genuinely missing components on its proto slice.

### 3.2 A courtyard can be smaller than the part it holds

Supports the obstacle-rect rule in `references/mechanical.md` §4.

The `MCU_nice_nano_v2` footprint's courtyard measures 18.28 by 30.98 mm, against
a nice!nano v2 module body of 17.78 by 33.00 mm. The courtyard is 2.02 mm
shorter than the module, about 1.0 mm at each end.

A deck window sized on the courtyard alone leaves a 1.0 mm lip of plastic
reaching over a module that stands 1.30 mm proud of the plate. Every clearance
check passes, because the courtyard reported nothing there.

The fix is an obstacle rect of `courtyard ∪ datasheet body`, plus an assertion
on the relation between the two so a later footprint edit cannot silently move
the window. hexpad asserts
`"MCU1 body south edge 33.00 exceeds its courtyard 31.99"`.

Module body dimensions are in `kb/keyboards/nice-nano-v2.md`.

### 3.3 A boss can be unable to land fully on the board

Supports the fastening decision tree in `references/mechanical.md` §3.

Revision 2's H4 mounting hole sits 2.275 mm from the east board edge. A Ø5.60
seat needs 2.800 mm, and H4 cannot move without re-gating the PCB. The seat
therefore cannot fully land, which is a board constraint rather than a design
failure.

### 3.4 A rotation put two openings on one wall

Supports the board-plane crossing rules in `references/mechanical.md` §6a.

Rotating the module in revision 2 placed the USB-C notch and the slide-switch
slot on the same east wall, overlapping in the y axis and separated only by the
board. The notch floor is 1.20 mm above the board's top face; the switch knob
sits below its bottom face. The result is legal, and nothing in the process
prompted anyone to check for it.

### 3.5 A proud actuator that no printable wall can clear

Supports the bounded-recess option in `references/mechanical.md` §6.

The MSK12C02 slider stands 0.825 mm proud of the board edge, which is 0.525 mm
past the wall's inner face after the 0.30 mm cavity inset. Leaving it proud of
the outer face would need a 0.53 mm wall.

Resolved as a 0.275 mm recess inside a 7.0 by 4.0 mm slot, asserted as
`recess ≤ 0.60 AND panel wall ≥ 0.80 AND slot ≥ 3 mm tall`, and operable with a
fingernail.

### 3.6 A battery bay handoff needs two artifacts, not one

Supports the bay handoff pattern in `references/batteries.md` §7.

The first handoff gave a single guaranteed-clear rectangle: a band of 34.0 mm
for a 34 mm wide cell. That leaves no room for the mandatory 0.6 mm of in-plane
slop, before ribs or a 3.10 mm boss keepout. The cell's top plane sits 2.60 mm
under the board and clears every part on the underside, so only the screw bosses
actually constrained it in plan.

A rectangle bounds components, not cavities. On any real board it overlaps the
boss seats in its own corners, so a phase that trusts the rectangle places a
cell through a fastener. A prose caveat beside the numbers does not fix this,
because the rectangle is the machine-readable part and the caveat is not.

The corrected handoff emitted `x −11.000…51.125, y 19.280…62.075`, derived
per edge, plus the full-height obstacle list. Two Ø5.600 boss seats intrude on
the south corners. The consumer asserted that overlap deliberately with
`case_verify.Suite.interferes()`, so nobody can later "correct" the rectangle
back, and placed the pocket in the bay's north half instead.

### 3.7 One ambiguous noun cost half the battery capacity

Supports the vocabulary requirement in `references/batteries.md` §7.

Revision 1 read "bay" as the retention fence and was not penalised, because the
board was long enough. Revision 2's board is 15.6 mm shorter.

Under the fence reading, with the fence held 3.10 mm off the H1 and H2 bosses, a
34 mm wide cell has no legal placement at all. That handoff concluded the 503450
cell did not fit and recommended a cell of about 500 mAh.

Under the pocket reading, which is what the physical requirement actually is,
the full four-sided fence fits, the two bosses fuse into its southern corners,
and the pocket still stands 1.205 mm clear of both. That is 1000 mAh rather than
500.

### 3.8 One locked decision produces a whole finding class

Supports the rule-demotion discipline in `references/kicad-api.md` §4.

The locked decision "the display mounts above the module" put a 36 by 14 mm
display courtyard over the microcontroller unit. That produced 25 findings in
two rule classes: one `courtyards_overlap` and 24 `pth_inside_courtyard`, one
per through-hole pad of the overlapped footprint.

The two rules come in pairs, and the pad-wise one scales with pad count, so a
front-face overlap multiplies. All 24 findings name `Footprint DISP1`, which is
what makes the demotion provably exhaustive.

### 3.9 A regenerated board is not byte-stable

Supports the canonical-digest requirement in `references/kicad-api.md` §4.

Two runs of an unchanged generator differed in 5744 of 10488 lines while
describing identical copper. `pcbnew` mints a fresh KIID for every item it
creates, and `SaveBoard()` writes footprints in its own internal order.
Determinism has to be checked on the canonical form rather than by `diff` or a
plain checksum.

### 3.10 A series resistor decided against shipping precedent

Supports the gated-rail reasoning in `references/electronics.md` §3.

The nice!view display sits on the module's gated VCC rail and is driven from
always-powered general-purpose input/output pins. Every shipping nice!view
keyboard is topologically identical, also gated, and ships no series resistors.

hexpad fitted 470 Ω on the Sharp memory LCD's SPI lines, whose datasheet could
not be read, and recorded the disagreement with shipping designs in `POWER.md`
rather than letting the reference silently condemn a shelf of working keyboards.

### 3.11 A plane net reached its pads only through the fill

Supports the fill-dependency rule in `references/electronics.md` §10.

The ground pour serves 27 pads that connect to it only because the fill closes
over them, among them a Kailh hotswap pad and every addressable LED's VSS.
z_board takes ground the same way.

## 4. Where the rest of the knowledge lives

| Subject | Card |
|---|---|
| Module pinout, courtyard, socket stack | `kb/keyboards/nice-nano-v2.md` |
| Display pinout, mounting, stack height | `kb/keyboards/nice-view-display.md` |
| Addressable LED pin order and rotation | `kb/keyboards/sk6812mini-e.md` |
| Slide-switch geometry and reachability | `kb/keyboards/msk12c02-slide-switch.md` |
| Rotary encoder pads, shaft, knob | `kb/keyboards/ec11-rotary-encoder.md` |
| Key-cell geometry and hole census | `kb/keyboards/mx-switch-geometry.md` |
| Deck opening for a socketed strip | `kb/keyboards/socketed-strip-deck-opening.md` |
| Firmware facts that change the netlist | `kb/keyboards/zmk-electrical.md` |
| Fab capability floors | `kb/fabs/jlcpcb.md` |
| The originating project | `kb/projects/zboard.md` |

The full verdict, gap statistics, and round-by-round findings are in
`docs/DRYRUN-HEXPAD.md`.
