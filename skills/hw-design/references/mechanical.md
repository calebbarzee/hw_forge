# Mechanical: fastening, stack-ups, clearances, and printability

Generic rules and formulas. Specific parts, cells, and project geometry live in
`kb/`.

## Terms used here

| Term | Meaning |
|---|---|
| boss | A raised cylinder on a shell that a screw threads into or passes through. |
| courtyard | The keep-clear rectangle a footprint declares around itself. |
| deck | A horizontal internal shelf, usually carrying openings for parts below it. |
| FDM | Fused deposition modelling. Filament 3D printing. |
| ledger | The enumerated table of component heights and obstacle rectangles per board face. |
| ligament | The material left standing between two nearby features of one printed part. |
| OD | Outside diameter. |
| PCB | Printed circuit board. |
| rabbet | A stepped lip cut into a wall so a lid seats into it rather than butting against it. |
| reference face | The face a shell is printed against, flat on the bed. |
| seat | A flat face that a board rests on, setting its z position. |
| SMD | Surface-mount device. |

## 1. Heat-set inserts

| Quantity | Rule |
|---|---|
| Bore diameter | The insert's spec OD, not the thread size. Do not add clearance; the insert melts its own interference fit. (M2 inserts are typically Ø3.2 OD × 4.0 long.) |
| Bore depth | Insert length + 0.3…0.4 mm of slack, so the insert cannot bottom out and the screw cannot jack it out. |
| Wall around the bore | ≥ 1.2 mm of solid material. `wall = (post_OD − bore_D) / 2`, so an Ø3.2 bore needs an Ø5.6 post. |
| Deck cap over a blind bore | ≥ 0.5 mm, target 0.6 mm: `cap = reference_face_z − bore_depth`. |
| Install direction | From the cavity side, part resting on its reference face, before any other assembly step. |
| Temperature | About 220 to 240 °C for PETG, lower for PLA. |

A blind bore with a thin cap prints well, because the cap is a first-layer
feature in the plate-down orientation. If the printer cannot hold the cap, make
the bore a through-hole and press inserts from the outside instead. Expose that
choice as a parameter (`insert_bore_depth = reference_face_z`) rather than a
code edit.

`verify()` must assert all four of: wall thickness, depth against insert length,
cap thickness, and that the bore footprint stays under solid material rather
than inside an adjacent cutout or window.

## 2. Screw-length stack-up: worked formula

```
available_thread = screw_len
                 − (floor_thk − counterbore_depth)     # shoulder left under the head
                 − cavity_depth                        # the air gap the screw crosses
                 − pcb_thk                             # anything clamped on the way
```

That is, `travel_before_thread = (floor − counterbore) + cavity + PCB`, and
`engagement = screw_len − travel_before_thread`.

Worked: `(2.60 − 2.10) + 8.00 + 1.60 = 10.10 mm` of travel. An M2×14 then gives
3.90 mm of engagement into a 4.0 mm insert in a 4.4 mm bore. An M2×8 falls
2.1 mm short of even reaching the insert.

Acceptance:

- `engagement ≥ 2 × thread pitch` is the absolute floor (M2 pitch 0.4, so
  0.8 mm). It is not a design target.
- Into a heat-set insert, target an engagement close to the insert length, and
  require `engagement ≤ bore_depth` so it cannot bottom out. A machine-checkable
  band for M2-class fasteners: `2.5 mm ≤ engagement ≤ bore_depth`.
- Pick from the stocked length ladder rather than a continuous value:
  `screw = min(L for L in LADDER if L ≥ travel + engagement_target)`.
- Counterbore: `cbore_D = head_D + ~0.5 mm` fit, and
  `cbore_depth ≥ head_height`. Leave ≥ 0.45 mm of shoulder
  (`floor_thk − cbore_depth`) under the head, or the head pulls through. The
  clearance hole is about `thread + 0.4 mm`.

Any change to a cavity depth changes the screw length. The generator must
compute and print the required length on every run rather than carrying it in
prose. Any parameter that changes the cavity, such as a thicker battery or a
taller component, has to re-derive it.

Measured case: a locked spec called for M2×8 because it was written against a
4.5 mm cavity. The real cavity was 8.0 mm and the screw had to become M2×14.

## 3. Fastening schemes

**Clamp.** Preferred when the board has plain clearance holes. The board is
clamped between a seat face on one shell and a boss face on the other. The screw
passes through the board's own standard clearance hole and threads into an
insert in the opposite shell.

Its properties: no fastener or plastic touches copper; the board's z position is
set by two solid faces rather than by screw torque; and the board needs only a
standard clearance hole, so the case does not constrain its layout beyond that
hole.

**Pass-through, or standoff-through-board.** A standoff passes through an
oversized board hole. This costs real board area, needing an Ø5.4 hole where an
Ø2.2 would do. It constrains routing around every position and makes the case a
hard constraint on the layout. Use it only when the board must be captured from
one side.

Either way:

- Hole positions are owned by the board and read from its file. The case
  follows.
- Target: every seat and boss lands fully on the board, so
  `min(dist to each board edge) ≥ post_OD / 2`.

A board can make that target unsatisfiable, which is not a design failure. One
measured case has a mounting hole 2.275 mm from the east board edge that cannot
move without re-gating the PCB, against the 2.800 mm an Ø5.60 seat needs. See
`kb/projects/hexpad.md` §3.3.

When `edge_dist < post_OD / 2`, work this decision tree. Note that §1 outranks
§3: the insert wall is a strength requirement, and the landing inequality is a
clearance one.

1. **Never shrink the post below §1's insert-wall minimum.** The obvious fix is
   the silent violation. An Ø4.55 post, the largest round post that fits in one
   measured case, leaves `(4.55 − 3.20)/2 = 0.675 mm` of wall around an M2
   insert against §1's 1.20 mm, and the insert bursts out sideways on
   installation.
2. On the shell that owns the wall, keep the full OD and merge the seat into the
   wall with an explicit gusset. The material goes outward, so the bore then has
   3.475 mm to the wall's outer face. The constraint that was short becomes the
   one with the most margin.
3. On the shell that does not own that wall, the mating wall descends past the
   boss and there is nothing to merge into. Intersect every boss with the cavity
   inset by the lid gap, and let the one that needs it come out D-shaped.
4. Assert the resulting flat on the solid, by slicing the lid above its floor
   and reading the extent, not from the parameters. Reading the parameters
   asserts your intent rather than your geometry. Assert the bearing annulus
   (`edge_dist − screw_clear/2`) in place of the "fully lands" inequality.

Three further rules apply to every boss:

- **Every boss on a lid must be clipped to the mating shell's cavity**, even
  when no seat is near an edge. Unclipped, an Ø5.60 boss can interfere with the
  other part by 0.375 mm, and no per-feature check notices: every such check is
  about components, and a boss is not a component.
- **Where the clip removes nothing, assert on the solid that it removes
  nothing.** This case is both more common and more dangerous than the clipping
  case. A boss that was never clipped and a boss whose clip removes nothing
  produce the same solid, so item 4's "assert the flat" has nothing to assert
  and passes vacuously.

  Invert the assertion instead: slice the lid and require
  `max.X == boss_cx + boss_od/2`, the cylinder's own extent, rather than the
  clip plane. One line turns an untestable no-op into a check.

  Measured case: a revision constrained every mounting hole to a board corner,
  so every seat landed wholly on the board and the mandatory clip stopped
  cutting. Deleting the `& zbox(...)` line left the whole suite passing. A later
  revision moving a hole 0.7 mm outward would then have let the boss foul the
  other shell by the 0.375 mm above.
- Assert that every seat and boss clears every component (§4).

A self-mirroring hole-x set, symmetric about the board centre, lets one
parametric model serve both mirrored variants. Check that numerically rather
than assuming it.

## 4. The air-gap ledger

Enumerate every component height above and below the board, then assert every
clearance numerically in code. Never check a clearance by eye in a 3D view.

Build two tables per board face:

```python
H_BELOW = {"socket": 1.85, "led": 1.40, "connector_mated": 1.65,
           "reset_sw": 1.60, "switch_pin_protrusion": 2.20, ...}
OBSTACLES_TOP = [(name, (x0, y0, x1, y1)), ...]   # board coords, from the PCB file
OBSTACLES_BOT = [(name, (x0, y0, x1, y1)), ...]   # courtyards, not guesses
```

**Match reference designators on the parsed prefix, never with `startswith`.** A
reference designator is a prefix plus digits, and the prefixes are not a
prefix-free code: `D` against `DISP`, `R` against `RN`, `C` against `CN`, `J`
against `JP`.

`kicad_geom.py` reports a parsed `designator: {prefix, index}` per footprint.
Switch on `designator["prefix"] == "D"`.

Measured case: a ledger dispatching on `ref.startswith("D")` gave a display
(`DISP1`) an SOD-123 diode's 1.35 mm height instead of its 1.50 mm through-hole
tail. Its derived "every diode is in the ledger" count came out at 8 for a
7-diode board. A count disagreeing with itself caught it, not anything
geometric.

Then, in `verify()`:

- **Vertical:** `gap_below ≥ max(H_BELOW over the footprint of the gap) + keepout`.
  Compute the maximum over the parts actually above that region, not over the
  tallest part on the board.
- **Lateral:** for every post, boss, and rib,
  `rect_dist(post_xy, obstacle_rect) ≥ post_OD/2 + keepout`, over every
  obstacle. Report the nearest obstacle by name in the assertion message, since
  that name is what makes a failure actionable.
- **Through-hole solder joints stand proud on the opposite face.** A front-face
  socketed module still puts an obstacle rectangle on the back-face ledger. This
  is the most commonly missed entry.
- **Openings are checked against the part's courtyard, not its nominal body**,
  in both axes plus z: `slot spans the whole courtyard` and
  `slot z spans the body z`. Otherwise a wall lands on the part. This is the
  right rule only when the courtyard is the larger of the two.
- Default `keepout = 0.30 mm`. Raise it where a print tolerance stacks against
  it.

### Sizing an obstacle rect: three cases

Picking the wrong case costs either a part or a fastener.

| The part | Obstacle rect | Why |
|---|---|---|
| Hardware can exceed its own courtyard (a socketed module, an SMD part) | `courtyard ∪ body` | The default. The courtyard is drawn round the pad grid and can be the smaller rectangle. |
| Drawn as a keepout on purpose | `courtyard` | The courtyard is the declaration. |
| Through-hole, courtyard inflated by its own pad row | `body ∪ any protruding feature` | The excess is flat copper and silkscreen. A deck cannot hit it. |

The third case is the one that surprises.

Measured case: a rotary encoder's courtyard spans
`1.200…15.400 × −1.500…16.000`, while everything standing above the board is
inside `2.500…14.100 × 1.500…13.500`. The extra 3.0 mm on the north side is its
pad row. Sizing a deck window on the union pushed the window's north edge to
y −1.800, which is 0.020 mm from a mounting boss's seat. That forced a choice
between relocating a corner hole, forbidden by spec, and a bigger board. Sized
on the body, the window's north edge is y 0.200 and the boss has 0.480 mm.

**Read the decision, do not make it.** `kicad_geom.py` emits `obstacle_above`
and `obstacle_below` per footprint, as `{bbox, basis, courtyard_dropped}`,
applying exactly this table from `courtyard`, `body_bbox`, `pads_bbox`,
`through_hole`, and `protrudes`.

Consume that output, and assert the `basis` you expected. A generator that
silently switches from `body` to `courtyard ∪ body` because a footprint gained a
Fab line is a window that has moved.

### A keepout is invalidated by a component leaving, not only by it moving

Re-derive on both. A one-directional assertion, of the form "every reference the
board says protrudes has a height in the ledger", cannot see a departure,
because every remaining reference still has its height.

A stale ledger that is merely conservative is the case that goes unlooked-for:
the case still fits, and only wastes cavity. On a battery bay, that waste is
capacity.

`kicad_geom.py --diff OLD NEW` reports changes to the `protrudes` set (`+ref`,
`-ref`, `ref: bottom -> top`) beside the per-reference position deltas, which is
the check.

Measured case: a revision moved two parts to the other face, taking the
protrude-below set from 37 references to 35. Those two were the tallest parts on
the underside and the two that bounded a battery bay. The bay's north edge moved
5.820 mm and its east edge 6.775 mm, about 68 % more plan area, and nothing
reported it.

### A courtyard can be smaller than the part it holds

Footprint courtyards are routinely drawn around the pad grid rather than the
body. A socketed module's courtyard can be about 1.0 mm shorter than its body at
each end.

Sizing a deck window on courtyards alone then leaves a 1.0 mm lip of plastic
reaching over a module that stands proud of the plate. That is a hard
interference which every clearance check passes, because the courtyard reported
nothing there.

So obstacle rects are `courtyard ∪ datasheet body`, and the relation between the
two gets asserted, so a later footprint edit that "fixes" the courtyard cannot
silently move the window.

The trap is silent in both directions. A courtyard bigger than the part costs
margin; a courtyard smaller than the part costs the part.

Measured case with the numbers, and body dimensions per module:
`kb/projects/hexpad.md` §3.2 and `kb/keyboards/nice-nano-v2.md`.

### Openings and walls

- A protruding actuator or connector shell needs its own assertion:
  `tip_coordinate` against the wall's inner face, and the shell overhang against
  wall thickness. An overhang means the opening must go clean through the wall
  rather than into a recess.
- Two openings in one wall must not merge. Assert that the remaining rib
  satisfies `(z_lower_edge_of_upper − z_upper_edge_of_lower) ≥ rib_min`.
- **Take a per-wall opening census.** Per-feature checks are per feature, so two
  openings can each pass every check of their own while nothing stands between
  them. For each wall, enumerate its openings with both their z bands and their
  in-plane spans, and assert either disjoint in-plane spans or an intact web
  between them. Never neither.
  - The web may legitimately be the PCB itself, where the two openings sit on
    opposite faces of a board clamped across the whole overlap: one z band
    strictly above the top face, the other strictly below the bottom face. State
    that reading in the assertion message, because what carries the wall there
    is 1.6 mm of PCB plus two rabbets, not plastic.
  - The web must be plastic, per the rib rule above, wherever both openings are
    on the same side of the board, or wherever the in-plane overlap runs past
    the board outline and there is no PCB under it to carry the wall.
  - Measured case: `kb/projects/hexpad.md` §3.4.
- This is a class of interference the board creates and only the case suffers,
  and the board phase is where two features end up on the same edge. So it also
  belongs in the PCB phase's handoff: per board edge, which features open
  through it.

## 4a. Same-part clearances are not keepouts

`keepout` in §4 means clearance to a component, throughout. A distance between
two features of the same printed part, such as a boss and a deck edge, a rib and
a wall, or a standoff and an opening, is not a keepout. Reading it as one
asserts the wrong inequality.

It is one of three other things:

| Rule | Question | Default |
|---|---|---|
| Cover | Does A's material fully overlie B? | `deck_covers_seat_min = 0.10 mm` of overlap |
| Ligament | Is the material left between them thicker than the minimum printable wall? | ≥ 2 extrusion widths, about 0.80 mm |
| Merge | Do they simply join? | Free. A merge is not an interference. |

Worked, in both directions, from one session. A deck opening's north edge sits
0.130 mm from where a standoff tangents it, and both are plastic on the top
shell. A keepout reading says fail. In fact 0.130 mm is the margin by which the
deck fully covers the standoff's top face, and covering it is the requirement,
because the insert bore needs material all round. No thin section exists
anywhere.

The other direction is a retention fence overlapping a boss, which is legal for
the same reason, stated for a different pair.

This makes `batteries.md` §7's carve-out, that a boss is not a component, an
instance of a stated rule rather than a one-off. When two features of one
printed part are close, name which of the three rules applies before writing the
assertion. The first attempt at both cases above asserted the wrong inequality
and had to be rewritten.

## 5. Printability under fused deposition modelling

Choose the print orientation first, then forbid geometry that violates it. The
orientation is a design constraint, not a post-processing decision.

For a shell with an integrated reference face, such as a plate, deck, or fascia:

- **Reference face down on the bed.** All features then grow away from the bed,
  and the cavity opens at the top of the print.
- **Nothing may stand proud of the reference face.** This is a hard rule. Any
  raised boss, roof, or plateau above it breaks the orientation in both
  directions and forces supports over the whole face. If a tall part cannot fit
  under the deck, the answer is an open window in the deck, not a raised bay.

  Measured case: a roofed variant of a module bay modelled cleanly and passed
  every clearance check, and was still unprintable without support. It is
  retained as a resin-only option behind a flag.
- Put features you want on the first layer there deliberately, because that is
  where dimensional accuracy lives: precision cutouts, insert-bore caps, and
  counterbore pockets.
- For the mating lid, print outer face down. Counterbores become first-layer
  pockets, and bosses and ribs grow up.
- Acceptable remaining overhangs are a shallow lid rabbet at the very top of the
  print, and short bridges over slots: about 10 mm at any width, up to about
  15 mm where the bridged section is ≤ 3 mm wide.

  The limit needs the width term. A 12 mm bridge 2.5 mm wide, which is a wall's
  own thickness laid flat in PETG at 0.20 mm layers, is routine. A 10 mm bridge
  40 mm wide is not. A single scalar cannot express that, so a correct design
  either fails the rule or quietly raises it.
- **Take a per-shell bridge census**, in the same terms as §4's per-wall opening
  census: every unsupported span enumerated with both its length and its width,
  in the stated print orientation. Anything not on that list is a defect.

  One assertion is not a census, and a single assertion's name can hide the gap.
  Measured case: a suite asserted
  `at_most("longest bridge in the top shell (the slide slot)", 7.00, 10.0)`
  while a USB-C notch floor spanned 12.00 mm in the same shell. The docstring
  had called that opening "no bridge at all" because it is open at the top of
  the wall. That is true in the wall's frame and backwards in the print's, where
  the top of the wall is the first layer and the notch floor resumes in mid-air
  12 mm across. A check named "longest bridge" was asserting the shorter one.
- **Support-free is a machine-checked assertion, not an intention.** For each
  solid, assert that no feature's z extends beyond the reference plane in the
  forbidden direction.

Geometry rules:

- **Interior fillet radius ≤ what the mating part's corner allows.** A cavity
  fillet larger than the mating part's own corner radius fouls it. For a
  square-cornered PCB in a filleted cavity the cap is small, about 1.0 mm for a
  0.3 mm clearance. Compute it and assert it.
- **Rabbet the lid into the wall** rather than butting it: depth about 1.2 mm,
  air gap about 0.15 mm per side. It is self-locating and it hides the seam.
- Ribs and fences for retention: 1.6 mm thick, 3 to 4 mm tall, with a wire-exit
  notch where a lead has to leave.
- Wall 2.0 to 2.5 mm for a hand-held enclosure. Thin a wall locally with a
  recessed panel when a control must be reachable (see §6), keeping ≥ 0.8 mm.
- **The local wall floor is a check, not a reading.** `case_verify.py`'s
  `v.min_wall(shell)` casts rays inward from every face and asserts the
  thinnest wall against `MIN_WALL_MM`, 0.80 mm: two extrusion widths at a
  0.4 mm nozzle, the same figure as the ligament rule in §4a. Raise it with
  the nozzle; never lower it to pass. A deliberate thin feature, such as the
  0.5 to 0.6 mm cap over a blind insert bore (§1), is an exempt region with
  its reason. Measured case: a wall section thinned to 0.35 mm passed every
  clearance check on one run (`docs/BACKLOG.md` B9).

Tolerance defaults. Start here, then adjust one dimension at a time.

| Fit | Default |
|---|---|
| Press or clip fit for a moulded part, such as a switch into a plate cutout | nominal + 0.15 mm, **plus a hole-shrink allowance if the part is FDM** (see below) |
| Board-to-cavity clearance per side | 0.30 mm |
| Lid to rabbet air gap per side | 0.15 mm |
| General slip-fit gap | 0.2 to 0.3 mm |
| Clearance to any component (keepout) | 0.30 mm |
| In-plane slop inside a retention fence | 0.6 mm |
| Consumable swell or ageing allowance (cells) | + 0.4 mm, or vendor spec |
| Flying-lead outside diameter (`lead_od`) | 1.80 mm for a 28 AWG twisted pair, 1.60 mm for 30 AWG |

- Material: PETG, ABS, or ASA for anything under screw preload. PLA creeps under
  preload and softens in a warm car.
- 0.16 to 0.20 mm layers, 4 perimeters, and ≥ 25 % infill for a screwed
  enclosure.
- **Print a test coupon before a full part:** one cutout and one post or insert.
  Name the single parameter to tune first, usually the press-fit cutout, and the
  step size, usually ±0.05 mm. Better, put a *range* on one coupon (five sizes
  in 0.10 mm steps, engraved), so one small print settles the number instead of
  a bisection over several prints.

### An FDM hole is not the hole you modelled

The fit allowance in the table above is the clearance the *part* needs. It is
not a print allowance, and adding only the fit allowance is how a press fit
reaches a print too tight to assemble.

An FDM hole comes out roughly 0.1 to 0.3 mm undersized, from extrusion width and
thermal shrink, and more still when the hole is a **first-layer feature on the
bed**, where squash-out closes it further. So:

- Carry an explicit `fdm_hole_shrink` parameter next to the fit allowance, and
  assert against the **predicted printed** size, not the modelled one. A check
  on the modelled number cannot fail for the reason you care about.
- Put a lead-in chamfer on the entry face. It guides the part in and moves the
  squashed first layer off the critical dimension. Bound it against whatever
  flat seat the mating part lands on.
- `fdm_hole_shrink` is a property of the printer, not the design. Get it from a
  coupon; do not inherit a number from another project's parameter block.

Incident: a keyboard plate modelled its 14.0 mm switch cutout at nominal + 0.15,
printed face-down, and came out too tight to clip a switch into
(`kb/keyboards/mx-switch-geometry.md`).

### Never dry-fit against an FDM stand-in for a fabbed part

A printed mock of a PCB, a sheet-metal bracket, or a moulded part does not hold
the tolerances the real one does, and the mismatch shows up as an apparent error
in *your* geometry. The tell is a discrepancy far larger than any dimension in
your stack-up.

Before believing a physical measurement, check that every mating feature's
clearance exceeds the mock's own process tolerance. If it does not, the mock
cannot test that fit: open its features up, or wait for the real part.

Incident: a switch's Ø3.85 and Ø1.60 locating posts have 0.069 and 0.051 mm of
clearance in a fabbed board. An FDM mock of that board could not accept them at
all, leaving the switch 2.9 mm proud and the enclosure looking ">1 mm off" in a
dimension that was in fact exact.

### Spec-equal mating dimensions have zero margin

When a part's own dimension equals the spec gap your enclosure provides (a
switch whose base-to-flange height equals the specified plate-to-board distance,
say), the part is stopped by two faces at the same instant and there is nowhere
to put a tolerance.

Two obligations. Assert the equality numerically, so it cannot drift silently
into a revision. And on FDM, choose a **layer height that divides the
dimension**: 5.00 mm is exactly 25 layers at 0.20 mm and 31.25 at 0.16 mm, and
the second quantizes the seat face 0.04 to 0.12 mm away from spec.
- Give each mirrored half its own parameter instance, so fits can be adjusted
  per side.

## 6. Reachability and openings

- A control's usable travel is `proud_of_edge − wall_thickness`. If the actuator
  stands only a few tenths proud, a full-thickness wall makes it unreachable.
  Thin the wall with a recessed port panel, one recess carrying several
  openings, so a fingernail can reach it, and keep ≥ 0.8 mm of wall.
- **Third option: a bounded recess.** When
  `proud_of_edge < wall_min + cavity_inset`, no wall thin enough to leave the
  actuator proud is printable, so the two halves of the rule above cannot both
  be satisfied. That is not a design failure.

  The target becomes a recessed actuator inside a slot big enough to admit a
  fingernail. The assertions move off the travel figure, which cannot be made
  positive, onto three others: recess depth ≤ a stated bound, panel wall
  ≥ 0.8 mm, and slot opening tall enough to reach into.

  Measured case: `kb/projects/hexpad.md` §3.5.
- A poke-hole for a recessed button: Ø3.0 with an outside countersink of Ø4.6 ×
  0.8. Note in the documentation how deep the button sits, so the user brings
  the right tool.
- Cut openings from a single recessed panel rather than as independent pockets.
  That gives one datum, one z reference, and fewer interacting assertions.
- Emissive parts: check the light path before adding a diffuser. A
  reverse-mounted emitter shining through the board emits nothing on the other
  side, so a diffusing floor does nothing.

## 6a. Crossing the board plane

§6 covers things that go out through a wall. This section covers the other case:
a conductor that has to get from one face of a clamped PCB to the other, inside
a sealed enclosure. An example is a cell in an underside bay whose connector
ended up on the front face.

It arises from a single upstream fact, which is the direction the cable leaves
its connector (§7's census below). It has no default geometry, so it needs a
pattern. A pinched lithium-polymer lead is a fire risk rather than a cosmetic
problem.

Four constraints have to hold at once:

1. The only clear route is the board-edge-to-wall gap, which is `pcb_clear`,
   0.300 mm by default. That is flat enough to pinch a twisted pair.
2. Widening it needs `channel_w ≥ lead_od + keepout` of clear width, and a
   minimum wall outboard of it: `channel_w + wall_min ≤ pcb_clear + wall`.

   Worked: `0.300 + 2.500 = 2.800` does not cover `1.80 + 0.30` of channel plus
   `0.80` of wall. When it does not close, the wall thickens outward. The lead
   does not get thinner. The outer envelope then stops being a rectangle, which
   is the correct outcome rather than a failure.
3. The channel must not reach down to the rabbet, or the lid loses its seat
   across that whole span. This was found by nearly cutting it that way.
4. The run has to be computed and printed, in the same spirit as §2's computed
   screw length, because a pigtail is a purchased length. One measured case came
   to three legs and 40.7 mm.

The alternatives are worse, and worth stating so they are not re-proposed. A
slot through the PCB cuts whatever routes across it, which was five band lanes
on the board this came from. Moving the cell re-opens the bay derivation in
`batteries.md` §7.

## 7. Code-CAD doctrine

**Open with a census, and for every connector state where its cable goes**, in
board coordinates, after the placement transform. A connector's keepout is its
cable, not its body. The census is the fit contract (`kicad_geom.py --contract`):
it carries each connector's mating wall, span and z band, read from
`design.py`'s `mating_direction` and rotated by the placement, and
`case_verify.py`'s `connector_openings` checks the case against it.

The mating direction is in no machine-readable place. It is not in the
footprint, where a name containing `Vertical` is a convention rather than data,
and where a footprint's own metadata can cite the wrong part outright (see
`agents/resource-scout.md`). It is not in `pads_bbox` or `fab_items` either, and
`kicad_geom` will report `protrudes: ["top"]` for a connector whose cable is the
tall thing.

So it comes from the part's knowledge-base card, where `mating_direction` is a
required field of the connector section (`kb/README.md`), and is written once
into `design.py`'s `PARTS` table in footprint-local axes. `kicad_geom.py`
applies the placement transform that turns a footprint-local `+z` into "up,
out of the front face"; do not restate it by hand.

Measured case: one vertical top-entry receptacle changing faces between
revisions turned a one-line handoff note, that the lead points down into the bay
6 to 8 mm from the cell, into a routed channel of about 40 mm, a locally
thickened wall, and all of §6a.

Then, the doctrine proper:

1. **A parametric generator plus a numeric `verify()` that runs on every
   invocation, before export.** Non-zero failures raise, and no geometry ships.
   Print the derived summary on every run: heights, cavity, outer envelope, and
   computed screw length. These are the numbers that otherwise go into a
   document and rot.
2. **Every dimension is a named field on a params object.** Nothing is a literal
   inside geometry code. Left and right variants are separate instances of the
   same params class.
3. **Read mating geometry out of the actual CAD and PCB files, never from a spec
   table alone.** Footprint positions, courtyards, the outline, and hole
   positions all come from the as-built, gate-passing board. A spec table is
   provenance, not an input; it drifts the moment a hole moves.
4. **Coordinate-frame conversion happens once, in one named helper, and is
   asserted.** PCB files are y-south and rotation-clockwise. A right-handed CAD
   frame is y-north and counter-clockwise. Converting one and not the other
   yields geometry that looks plausible and is wrong.

   Anything that serves a rotated part's pad must be positioned through that
   part's own local frame. Measured case: components positioned relative to a
   cell instead of relative to the rotated part stayed put while the pads they
   served moved to the other end, and traces then crossed features they had to
   avoid.

   **Assert it against this:** put a known asymmetric feature through your own
   frame helper, and assert that it reproduces `kicad_geom`'s reported
   `pads_bbox` for that part. One assertion proves the whole coordinate
   pipeline. It must be an asymmetric part, because a y-symmetric body
   reproduces itself under a sign error. In the style this file asks for:
   `local_rect()'s frame agrees with kicad_geom on SW7's pads (y 5.615..13.665)`.

   Measured case: a case-handoff table gave a slide-switch knob at y 8.14…9.54
   where the board says y 9.790…11.090. The handoff number was mirrored about
   the part centre at 9.640, which is a rotation-sign error on a −90° part. It
   was invisible on the switch's y-symmetric body, which the handoff got right
   to ±0.05, and visible only on the asymmetric slider lobe. Centring the slot
   on the handoff figure would have put 2.0 mm of wall on top of the actuator,
   giving a part that passes every clearance check and cannot be switched on.

   Corollary: **a case suite must assert every handoff number it consumes**, so
   a stale table fails a check instead of steering a cut. `kicad_geom.py`'s
   docstring already warns that a rotation-sign error "is invisible on 0 and 180
   degree parts and silently wrong on every 90/270 part", and it still nearly
   cost a part, because the warning lived in a script's docstring and the error
   lived in a human table.
5. **Assert the mirror relationship rather than assuming it:**
   `mirror(left_feature) == right_feature` for every hole, part centre, and
   thumb or edge position, read from the right-hand board's own file. That
   assertion is what licenses one model to serve both halves.
6. **Assertion messages carry numbers and the offending name**, as in
   `"boss @(9.53,47.10) OD5.60: 0.42mm to cap 76.2,43.6 (need 3.10)"`. A boolean
   failure has to be debugged; a numbered failure is a one-line fix.
7. **Export STEP and STL**, plus cheap projected-view renders for inspection.
   Wrap the renders so a render failure never fails the build.

   Keep every render eye slightly off-axis. A true elevation view, with the eye
   exactly on an axis, puts every cylindrical standoff exactly edge-on.
   build123d's SVG exporter then hands a degenerate arc to svgpathtools, which
   raises `AssertionError: assert start != end` in `svgpathtools/path.py`,
   `Line.__init__`. The informative views of an enclosure are its elevations,
   which is where a USB notch and a switch slot are legible, so this is hit
   immediately. A few degrees off axis fixes it.
8. **Report volume and bounding box per part on every run.** It is the fastest
   signal that geometry has silently changed.
9. **A footprint's 3D model transform puts the model's origin at the
   footprint's own origin, on its mounting face.** So a reverse-mounted part,
   with its body on the far face working through a window in the PCB, needs an
   explicit offset or rotation. Which of the two, or both, or neither, is not
   derivable from anything in the file.

   A model that straddles the board plane is the tell: one measured LED model
   runs z −0.84…+0.79, and on a reverse-mount cell its body must sit entirely on
   one side. Resolve it by rendering once, then record the resolved offset in
   the part's knowledge-base card, so the next project inherits a number instead
   of a render loop. A model link is the one geometry input this doctrine cannot
   assert from the board file.
10. **A stand-in model must be STEP, must be named as a placeholder, and must
    take its dimensions from the design module.** All three, and the first is the
    one that bites.

    A hand-written `.wrl` box is text, needs no CAD dependency, and renders
    correctly in KiCad's 3D viewer. It also disappears silently from
    `kicad-cli pcb export step`, which consumes only STEP and IGES. A project
    that took that route passes an "every footprint links a model" review, looks
    right on screen, and hands the enclosure phase an assembly STEP with no
    module and no display in it. Those are exactly the parts most likely to
    collide with a shell.

    Name every one `*_PLACEHOLDER`, so it reads as a stand-in in the model list,
    the BOM audit, and the 3D view. Generate it from the design module's own
    dimensions rather than drawing it by hand. `preflight.py --project` resolves
    every `(model ...)` link and stats it, because a footprint naming a model is
    not evidence that the model exists.
