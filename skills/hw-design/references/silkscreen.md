# Silkscreen readability: rules, placement algorithm, and the phase-4 gate

Design rule check (DRC) tells you a board is geometrically legal. It has
nothing to say about whether a human can read it. A board can pass
`silk_overlap`, `silk_edge_clearance` and `silk_over_copper` at zero and still
ship with every reference designator hidden and no board name anywhere.
Measured case, z_board's combo board, first iteration: 123 footprints, 9
visible reference designators (7.3%), zero board-level text, zero `silk_*`
DRC findings. See `kb/keyboards/silkscreen-readability.md` for the numbers
and the fix.

This is the missing check for that gap, and the rule set the PCB phase
(`agents/pcb-engineer.md`) applies to close it.

## 1. The rule set

Every number below is a named constant in the generator, not a literal
scattered through placement code (the same discipline `agents/pcb-engineer.md`
requires of every geometric constant).

- **Size and stroke floors.** 1.0mm text height, 0.15mm stroke width.
  JLCPCB's own published minimum (`kb/fabs/jlcpcb.md`: "Silkscreen line / text
  height 0.15 / 1.0mm"), stricter than KiCad's own default (0.15mm thick,
  0.8mm high). A fab that requires less never blocks a board built to this
  floor; a fab that requires more is a `--text-height-mm`/`--stroke-mm`
  override on the checker below, not a reason to loosen the generator's own
  default.
- **One reading orientation per face.** Declare it once (a board rotation in
  degrees, default 0 -- upright in the file's own `+x` east / `+y` south
  frame) and hold every silk text item to `{0, 90}` degrees relative to it.
  Not `{0, 90, 180, 270}`: 180 reads upside down and is not a second legal
  orientation, it is the first one's failure mode. A back-face label built
  at the same declared rotation and passed through `PCB_TEXT.SetMirrored()`
  reads correctly once the board is turned over and viewed from that face --
  KiCad does the glyph mirroring; the generator only has to pick the layer
  right.
- **Refdes placement.** Outside the part's courtyard (or, for a
  courtyard-free reversible footprint, outside its known pad/body extent),
  never over a pad, a via, or a hole.
- **Silk-to-copper clearance.** 0.25mm from any pad, via or hole's copper/mask
  boundary, above JLCPCB's own 0.2mm copper-to-edge floor
  (`kb/fabs/jlcpcb.md`) with margin: silk printed across a mask opening does
  not survive reflow, so "does not overlap" is not the same claim as "prints
  correctly".
- **No text under a module body or a hotswap socket.** Both hide silk
  entirely; a label placed there is invisible on the finished, populated
  board even though it passes every geometric check on the bare PCB.
- **Required labels, by part class** (present wherever the part exists on the
  board -- omit rows for parts the board does not have, never force a label
  where there is no matching hardware):

  | Part class | Required label(s) |
  |---|---|
  | Every board | Board name + version + date |
  | A reversible board (one PCB, populated on either face) | A hand mark ("LEFT"/"RIGHT" or equivalent) on **each** face, stating which hand that face's population serves |
  | An MCU header / castellated module | Pin names along the row(s) |
  | An addressable LED (DIN/DOUT chain) | DIN polarity (an arrow or a dot at the data-in pad) |
  | A diode | A cathode bar |
  | A battery/JST-style power connector | `+`/`-` at the correct pad, per populated face if the connector is reversible |
  | A power switch | An "ON" direction mark, **only if the datasheet gives a throw-to-position mapping the generator can verify** -- see §4's "what not to guess" |
  | A reset button | An "RST" label (its own revealed reference designator satisfies this if the refdes text itself reads "RST"-prefixed, e.g. `SW_RST`) |
  | Debug/programming test pads (SWD or equivalent) | Pad function labels, e.g. "SWDIO SWCLK GND 3V3" -- only if the pads exist; a locked decision to drop them (see the board's own `SPEC.md`) makes this row not-applicable, not unmet |
  | An internal-antenna RF module with its own copper keepout zone | The keepout outline reproduced on silk, plus a "NO COPPER" callout |

## 2. The placement algorithm

A small, rule-driven routine, not a hand-picked coordinate table:

1. For each label (a board-level string, or a footprint's own reference
   designator), build a list of **candidate positions**: north/south/east/west
   of the anchor point at increasing standoff radii for a part-anchored
   label, or a coarse grid along the four board margins for a board-level
   label with no single owning footprint.
2. For each candidate, in order, compute the label's estimated text bounding
   box (see §3 for the calibration) and test it against every real pad, via,
   hole and previously placed label bounding box, queried off the board that
   has actually been built so far -- never a spec table, never a courtyard
   number trusted without a fresh read.
3. Take the first candidate that clears every obstacle by the required
   clearance and the board edge by the edge margin. Place it there.
4. If no candidate clears, **report and skip.** Print which label, near
   which anchor, and move on. A silkscreen pass that crashes the generator
   because one label had nowhere to go is worse than a board with one label
   missing and a line in the log saying so.

Reference implementation: `kicad/gen_combo.py`'s `Builder.place_label()` /
`Builder.reveal_ref()` (z_board), mirrored in `kicad/dongle/gen_pcb.py` for a
single-face board. Both keep one obstacle set (`collect_geometry()`, called
once after every footprint/track/via exists, before any label) and reuse it
across every subsequent placement in that generation pass, so label N+1 never
lands on label N.

**Priority ordering matters when space is genuinely tight.** A real RF
keepout (§1's antenna row) is a fab/regulatory requirement; a board-id label
is not. Draw the keepout (and any other hard requirement) into the obstacle
set *first*, before any optional label is attempted, so a scarce few square
millimetres of clear silk go to the requirement that cannot be renegotiated,
not to whichever label's code happened to run first. Measured: the dongle
board's antenna keepout and its board-id text were both candidates for the
same narrow margin strip; drawing the board-id text first let it claim the
strip, and the keepout's own boundary line then came back `silk_overlap`
against a footprint tick it would otherwise have cleared. Reordering, not
adding more inset, was the fix -- the two problems were racing for the same
space, and only one of them is allowed to lose that race.

**Not every label fits, and that is a real result, not a bug to nudge away.**
On a board dense enough (z_board's dongle: 25 x 18mm, an antenna keepout, a
16-pin 0.5mm-pitch connector, and a castellated module edge in it), the
placement search can legitimately fail for every candidate of a label that
would fit comfortably on a roomier board. Report the actual numbers ("widest
contiguous clear run measured 8.38mm; the label needs 9.5mm") and either
shorten the label or drop it, rather than shrinking the size/stroke floor to
force a fit -- the floor exists for the fab and the hand holding a
soldering iron, not for this generation pass's convenience.

## 3. Glyph metrics: measured, not estimated

The overlap and floor checks need an axis-aligned estimate of a text item's
real footprint, and no font is loaded to compute one exactly. A first pass
estimated 0.65mm per character with no fixed overhead; measured against real
`pcbnew.PCB_TEXT.GetBoundingBox()` calls at 1.0mm text height, that
underestimated every string tried: `'A'` came out 1.107mm wide against a
modelled 0.65mm, `'SW_RST'` 5.821mm against 3.9mm. The gap is exactly what put
a revealed reference designator on top of its own footprint's silk tick
(`silk_overlap`, only visible once real DRC ran against the "successfully
placed" board).

Recalibrated, at 1.0mm text height:

```
width  = (0.5 + character_count) * 1.0mm     (scale linearly with text height)
height = 1.8 * text_height                    (measured constant: 1.696mm at 1.0mm height)
```

Both are conservative (they overestimate most real strings by 5-15%), so a
placement this model accepts is never tighter in KiCad's own render than what
was checked. `scripts/kicad_silkcheck.py`'s `--char-width-mm` /
`--char-base-mm` / `--height-factor` override them for a different font.

## 4. What not to guess

A power switch's silk "ON" arrow needs a throw-to-slide-direction mapping
from the part's own datasheet. Where that mapping is not available (or not
verified), do not draw an arrow -- a wrong arrow costs a returned or
miswired board; a missing one costs a datasheet lookup at assembly time. Same
principle as the footprint-provenance rule in `kb/README.md`: state the
limitation, do not fabricate the missing fact.

## 5. Diagnosing an existing board

Render the two silk layers and the two 3D views before touching anything:

```
kicad-cli pcb render --side top --output top.png board.kicad_pcb
kicad-cli pcb render --side bottom --output bottom.png board.kicad_pcb
kicad-cli pcb export svg --layers F.Silkscreen,Edge.Cuts -o f_silk.svg board.kicad_pcb
kicad-cli pcb export svg --layers B.Silkscreen,Edge.Cuts -o b_silk.svg board.kicad_pcb
kicad-cli pcb drc --severity-all --format json -o drc-all.json board.kicad_pcb
```

Then read the actual text items (size, thickness, position, rotation,
visibility) out of the `.kicad_pcb` -- `kicad_geom.py` does not parse text
items, so this is a direct s-expression read or (once this tool exists on the
board in question) `kicad_silkcheck.py --json`, which reports every text item
alongside the violation list. Cross-reference against §1's required-label
table by part class, and write the result as a table (see
`kb/keyboards/silkscreen-readability.md`'s source project for the pattern):
part/feature, current state, defect. Counts alone hide which finding is one
root cause repeated across every instance of a cell versus 19 independent
problems -- read the records, not the count (the same rule
`agents/pcb-engineer.md` states for DRC).

## 6. `kicad_silkcheck.py` as a phase-4 gate

`scripts/kicad_silkcheck.py board.kicad_pcb [flags]` -- pure Python, no
`pcbnew` dependency (it reuses `kicad_geom.py`'s s-expression parser and
rotation convention), so it runs in the same shell as the rest of the gate.
Six checks: `text_too_small`, `text_too_thin`, `text_over_pad`,
`text_over_text`, `text_rotation`, `refdes_far`, plus `label_missing` against
a `--require`/`--require-file` list. Exit 0 with zero violations, 1
otherwise -- the same contract as `kicad_gate.py`.

Run it after DRC, not instead of it: DRC still owns geometric legality
(`silk_overlap`, `silk_edge_clearance`, `silk_over_copper`), and this tool
owns readability, which is a distinct, non-overlapping question. A project's
`Makefile` wires it as its own target (e.g. `silk-combo`, `silk-dongle`),
kept **separate from** the existing `check-<variant>` target unless that
target's own exit-code contract already tolerates a second failing check
cleanly -- most existing z_board-style `_check` targets print `FAILED` but
never propagate a nonzero exit for ERC/DRC (unconnected nets are deliberately
non-fatal there), and chaining a script that `sys.exit(1)`s on any violation
as a hard prerequisite would abort that target before it printed anything,
changing established behaviour rather than adding to it.

Use it on a fresh board and its predecessor both: it found the exact defect
counts listed in `kb/keyboards/silkscreen-readability.md` on z_board combo's
first iteration, and reports 0 on the fixed board -- that pairing (defects
found on the "before", 0 on the "after") is the acceptance test for any
readability pass, the same way a DRC violation count before/after is the
acceptance test for a routing pass.
