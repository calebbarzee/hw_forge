# Electronics: rails, protection, routing topology, mirroring

Generic rules. Part numbers, firmware symbols, and project geometry live in
`kb/`.

## Terms used here

| Term | Meaning |
|---|---|
| CMOS | Complementary metal-oxide-semiconductor. The logic family most digital parts use. |
| ESD | Electrostatic discharge. |
| FET | Field-effect transistor. A P-FET is the p-channel type, used here as a high-side switch. |
| GPIO | General-purpose input/output pin. |
| LDO | Low-dropout regulator. |
| MCU | Microcontroller unit. |
| PCM | Protection circuit module. The small board bonded to a lithium cell. |
| PTC | Positive temperature coefficient device. A resettable fuse. |
| SMD | Surface-mount device. |
| TVS | Transient voltage suppressor. A clamping diode for ESD. |
| VDD | A part's positive supply voltage. |
| VIH | The minimum input voltage a receiver reads as a logic high. |

## 1. Power-rail topology: decision tree

Start from what the module already contains, not from a blank schematic.

```
Is the MCU a MODULE (carrier board) or a bare chip?
├─ MODULE → enumerate what it already provides before adding anything:
│           charger, protection IC, LDO/regulator + its enable pin, USB ESD/TVS,
│           reset pull-up, input capacitance, decoupling.
│           Adding a second instance of any of these is cost, mass, and a new
│           failure mode for zero function. Write the enumeration down.
└─ BARE CHIP → you owe all of it. Budget board area for it up front.

Which rail does each load hang off?
├─ Load must be switchable in firmware, or has non-zero quiescent draw
│  → the GATED regulated rail (regulator output whose enable the firmware owns).
│     Gating comes free; no external load switch, no extra FET.
├─ Load must survive with the regulator off (charger, always-on sense)
│  → the raw/battery rail. Accept that it cannot be switched without a P-FET.
└─ Load is a peripheral the MCU talks to
   → the SAME rail as the MCU logic. See §2. This satisfies level shifting
     by construction and is almost always the right answer.
```

**Quiescent-current test for gating.** A part with even about 1 mA of idle draw,
multiplied by the number of instances and measured against the cell capacity,
decides this:

```
idle_hours = capacity_mAh / (N × I_idle_mA)
```

22 parts at about 1 mA each is about 20 mA, which flattens a 500 mAh cell in
roughly 24 h. Anything that flattens the cell in under a week must be on a gated
rail.

**Regulator enable pins are free gating.** If the module's regulator enable is
wired to an MCU GPIO that the firmware already drives, hang the switchable load
on that regulator's output rather than adding an external load switch. That
gives fewer parts and one control point, and the regulator's own current limit
becomes a hard ceiling on how much current the load can draw.

## 2. Level shifting: the 0.7 × VDD rule

Most single-ended CMOS logic inputs specify `VIH ≥ 0.7 × VDD`, where VDD is the
receiver's supply.

- **Powering the peripheral from the driver's own logic rail satisfies this by
  construction**, with no shifter: `0.7 × 3.3 = 2.31 V` against a drive of about
  3.3 V. There is nothing to check.
- **Raising the peripheral's rail is what breaks it.** A peripheral at 5 V wants
  `0.7 × 5 = 3.5 V`, which a 3.3 V driver cannot reach.

  The field workarounds are all poor. One is a series diode dropping the
  peripheral rail to about 4.3 V, so that `0.7 × 4.3 = 3.0 V` clears; this is
  common on 5 V addressable-LED boards. The other is a real level shifter.
- **Choose the peripheral rail so that no shifter is needed**, and only then
  evaluate what the higher rail buys. The typical cost of the low rail is
  reduced output, meaning dimmer, quieter, or slower, and sometimes a colour or
  gain shift. That is usually acceptable. Write the trade-off down.

## 3. Series resistor into a gated rail

**Any data line driven from an always-powered domain into a peripheral on a
gated rail needs a series resistor at the driver.** Ungated designs do not need
one, and their precedent does not transfer, because that is the one topological
difference that matters.

The failure mode without it: when firmware drops the rail, the peripheral's VDD
is 0 V while the driver pin may still be driven or parked high. The input then
forward-biases the receiver's input ESD clamp into a dead rail.

That produces a phantom drain, a partially powered peripheral (the familiar
case of the first device in a chain still faintly glowing with the power off),
the driver propping the dead rail up, and at worst a latched input.

### When a gated reference design omits it

The counter-evidence that matters is a reference design with the same topology,
meaning a gated rail and an always-powered driver, not an ungated one. When you
find one, the rule above does not settle the question by itself.

Decide instead on the receiver class. Injection matters for addressable-LED
chains and other parts that can partially light or partially operate off clamp
current, since that is the visible symptom. It also matters for parts whose
datasheet forbids signals present before VDD, and for anything where the driver
can end up propping a dead rail.

It matters much less for a receiver whose datasheet is silent and whose failure
mode is invisible.

The resistor is inexpensive, and the decision must be recorded either way in the
power decision record, with the receiver class, the counter-evidence, and which
way it went. Measured case: `kb/projects/hexpad.md` §3.10.

### Sizing

```
I_inject = (V_drive − V_clamp) / R          # V_clamp ≈ 0.7 V for a diode clamp
choose R so I_inject is comfortably below the driver's per-pin current limit
t_edge  ≈ R × (C_in + C_trace)              # must be ≪ the protocol's edge tolerance
```

Worked example, from a gated addressable-LED chain: `R = 470 Ω` gives
`I = (3.3−0.7)/470 ≈ 5.5 mA`, and `470 Ω × 80 pF ≈ 38 ns` against a ±150 ns
timing tolerance on a 300/600 ns bit. That is about 4× margin.

- Too small is pointless. `100 Ω → 26 mA` is above the MCU's per-pin drive
  anyway, so it limits nothing and only does the damping job.
- Too large softens the edge. Keep `t_edge` under about 25 % of the protocol's
  tolerance. For most serial protocols that puts the usable band at 100 to
  500 Ω. Do not exceed about 1 kΩ.
- **Source-series damping** is a secondary benefit, always present, on the one
  long singly-terminated stub. In a daisy chain every link after the first is
  reshaped by its own receiver, so the run from the driver to the first device
  is the only unterminated one, and the only one that needs damping.

## 4. Decoupling policy

- **Per-part local capacitor**, typically 100 nF in an 0402 or 0603 package,
  placed hard against the part's own supply pad, one per instance. Its job is
  the part's own switching transient. Loop area is what matters, so placement
  matters more than value.
- **Bulk at rail entry.** A low-frequency reservoir where the rail enters the
  load group, typically `10 µF + 1 µF` in parallel, giving bulk and
  mid-frequency reserves with different self-resonances. This is not optional
  when the rail is gated, because the turn-on is a current step.
- Sum the added capacitance and check the regulator is stable into it. A few
  tens of µF is fine for a small LDO, and inrush is bounded by the regulator's
  own current limit.
- **Per-part capacitors on a long chain are a judgement call, not a datasheet
  mandate.** Reference designs frequently ship none and work.

  What they buy is suppression of supply ringing from many controllers switching
  at once. The symptom of that ringing is misbehaviour at the far end of a long
  chain, not a dead board. If you populate them, record it as a decision with
  that reasoning rather than citing a datasheet that does not say it.

## 5. Current budget arithmetic

Build this table before routing. It decides rail choice, trace width, and
connector.

| Case | Per part | × N | Compare against |
|---|---|---|---|
| gated off | 0 | 0 | not applicable |
| idle or quiescent | measured, or from the datasheet | | cell capacity ÷ target standby days |
| worst-case full load | datasheet maximum, including binning spread | | regulator rating, and cell C-rate |
| intended working ceiling | design target | | pick this, then enforce it |

Rules:

- **Use the worst bin, not the typical figure.** A 3× spread between typical and
  maximum is normal for LEDs and radio-frequency parts.
- If the worst case exceeds the regulator rating, **a firmware cap is a hardware
  requirement, not a preference.** Record the specific configuration key and
  value in the power document, and say what must be measured before raising it.
- **Check dropout as well as current:** `Vin ≥ Vout + Vdropout(at I)`. Near
  end-of-discharge the high-current rail sags long before a low-power MCU, which
  may run down to 1.7 V, notices. This is another argument for the firmware cap.
- Charge rate is `C_charge = I_charger / capacity`. A module's fixed 100 mA
  charger is 0.2C into a 500 mAh cell, which is safe and takes about 6 h from
  empty, but 0.9C into a 110 mAh one. **The charger sets a minimum cell size.**
- For discharge, state the working ceiling as a C-rate, as in
  `300 mA from 500 mAh = 0.6C`, so it can be checked against the cell rather
  than only against the regulator.

## 6. Protection: what to add, and what not to

The default posture on a carrier board under a protected MCU module is to **add
nothing**. For each candidate part, name the hazard it addresses and the path
that hazard takes on this board. If the path does not exist, the part does not
go on.

Commonly rejected, and why:

| Candidate | Why it is rejected |
|---|---|
| Reverse-polarity element on a cell | With a polarised connector the hazard is a pigtail-wiring error, not a system state. A series element in that path also breaks charging through it. Use a keyed connector plus a documented polarity check. |
| Fuse or PTC on a cell | The cell's own PCM covers short circuit and overcurrent. Add one only if there is a second high-current path. |
| Protection IC, charger, regulator, or USB TVS | Already on the module. Enumerate these, do not duplicate them. |
| External load switch | Redundant for a load already on a firmware-gated rail. |
| Level shifter | Unnecessary where the peripheral shares the logic rail. See §2. |
| Series resistors on scanned matrix lines | GPIOs are drive-limited, per-key diodes block reverse paths, and the firmware uses internal pull-ups. |
| RC debounce or pull-up on reset | Usually on-module. A bare momentary switch to ground is the expected circuit. |
| TVS on a net entirely internal to the board | No ESD path exists. |
| Bulk capacitor on the raw input | The module has its own input capacitance, and a cell's series resistance is low. |

Write these down as a rejection table with reasons. It is the artifact that
stops the next reviewer re-adding them.

## 7. Matrix and chain routing patterns

- **Layer split by net family.** Give each orthogonal family its own face: one
  axis of the matrix on the front, the other on the back, with one via per
  crossing at the part that needs it. The two families then meet only at
  through-hole pads and cannot collide. This is what lets many nets share one
  congested corner without an autorouter.
- **Corridor analysis before placement.** Mechanical holes block every layer.
  Solve the clearance inequalities per repeated cell to find how many
  full-height corridors exist per pitch, and route to that number. Per side,
  `needed = hole_r + hole_clearance + track_w/2`. If the answer is exactly one
  corridor, every net contending for it must be assigned by hand.
- **Serpentine chains: run a row straight, and turn around outside the outermost
  cell.** In-row links then become short neighbour hops, which is what makes a
  long chain routable on two layers. Running each row straight beats reversing
  direction within each cell.
- **Rotation against return trace.** For a directional part, with data in one
  end and out the other, a chain that reverses direction each row has two
  options. Rotate the part 180° on reversed rows so the output always faces the
  direction of travel, or keep one orientation and pay a return trace that
  crosses its own cell.

  Rotation usually wins, because the return trace collides with the next link's
  departure. Rotation costs two things: the pick-and-place file shows
  alternating 0° and 180°, which should be documented as intended, and
  everything positioned relative to that part must be positioned relative to the
  part rather than the cell (see §8).
- **Bus detours around mechanical holes** are cheaper than moving the bus. Step
  the run aside over a short window at each hole, generated from the hole table,
  so that moving a hole moves its detour.
- **Ordering rules keep a fan-out planar without an autorouter.** Two that
  generalise: a feed that crosses a barrier further along takes a lane further
  out, so its run never meets a crossing already placed; and the mirror of that
  rule applies on the far side. Assign lanes by that ordering, not by
  convenience.

### Nest or interleave

Two nets that run along an axis and turn off it are planar on one layer if and
only if their lane order across the axis follows their turn order along it. That
reads as a recipe: sort by turn order, assign lanes, done.

It is incomplete, and the missing half costs a full build cycle. Each net
occupies the span `[rise, turn]`:

- Spans that **nest** (`rise_i < rise_j < turn_j < turn_i`) have a lane order.
  The inner net takes the near lane.
- Spans that **interleave** (`rise_i < rise_j < turn_i < turn_j`) have **no lane
  order that works.** Whichever is put nearer, one of the two verticals must
  cross the other's horizontal. One layer change is required. Count it in the
  via budget rather than trying the other lane order, which cannot succeed.

**A two-terminal SMD's rotation is a topology decision for every net that leaves
it.** This is what puts a board in one case or the other.

Measured: three north-band nets turning south at fixed x, which the MCU pinout
owns, rose at +2.500, −2.500, and −2.000. The first two nested and the last two
interleaved, because an SOD-123 diode at `rot 180` put its cathode 0.500 mm east
of the neighbouring pad instead of 2.800 mm west of it. One part rotation turned
a via-free band into a two-via band.

### Pours, lanes, and islands

- **Two parallel lanes that fence a region need
  `2 × zone_clearance + min_thickness` of separation, and a via between them
  needs `via_r + zone_clearance` more than a track does.** This is the
  arithmetic behind a pour that closes: 0.625 mm against 0.425 mm on one board
  was an entire bug.

  A pour pinched below its own `SetMinThickness` splits into isolated islands
  with no clearance violation anywhere, so nothing upstream of DRC objects. See
  §10.3 and `kicad-api.md` §4.

  Measured: a 1.10 mm window between two lanes, with a 0.6 mm via keepout in the
  middle of it, left 0.075 mm of pourable channel against a 0.20 mm minimum, and
  fenced a ground island of about 300 mm² off the net.
- **A pour vent can be a lane that is not there**, and no artifact shows which
  absence is load-bearing. This is the inverse of the pinch above. A pocket
  drains through a stretch of a lane's own y that simply has no copper on it,
  because the bus starts further east.

  Nothing marks that. The board file shows copper, not the gaps that matter. In
  one case a generator's comment documented the other vent at length, because in
  that revision nothing threatened this one.

  So: **when a net's bus already exists on a lane, extending that lane east or
  west to reach a new terminal is a pour change, not just a routing change.**
  Re-check island count, not just DRC. Measured cost of not doing so: 198 mm² of
  unconnected ground, from a routing choice that looks, in every view a person
  has, like joining a net to itself along an existing line.
- **Deliberate nesting under a tall part** is legitimate, such as a low part in
  the standoff shadow of a socketed module. It produces findings of the
  `npth_inside_courtyard` class. Demote that specific rule in the project file
  with the justification; do not move the part.

## 8. The two mirroring traps

State these as invariants.

**Trap 1: a footprint cannot mirror in one axis without changing layers.**
Mirroring a part in x while keeping it on the same face is not a rigid motion.
So the mirrored variant of an asymmetric part is actually a 180° rotation, an
end-for-end turn, which:

- keeps edge-relative features on the variant's own outer edge, which is usually
  why you did it, but
- **swaps the functional roles of the two pad groups.** The group that faced one
  direction now faces the other.

**Trap 2: one sign cannot carry both axes.** If the part turns end-for-end but
the surrounding grid does not mirror in the other axis, then any constant
expressed as a part-local offset, such as "2 mm on the pad-column side", lands
on the wrong physical side of the board.

The symptom is a whole routing block's worth of violations from a single
inherited sign: lanes on top of pad rows, parts pushed off an edge, and
clearances to holes that were never intended.

Four invariants prevent both:

1. **Express routing lanes in board coordinates**, never as part-local offsets,
   on any board that has a mirrored sibling.
2. **Derive functional roles from the rotation** at generation time, from the
   actual pad table. Never inherit them.
3. **One sign describes where the parts are, and nothing about the lanes may be
   inherited through it.** Keep a `place()` helper carrying the mirror sign,
   which correctly describes physical position, and a separate per-variant
   corner router. Two-terminal parts whose pad order must keep pointing at a pad
   group whose role swapped get an explicit opt-out of the turn.
4. When a repeated cell contains an asymmetric part, **the cell does not mirror
   either**, so cell-relative bus offsets sit on the opposite side of the
   mirrored part. Recheck every bus that falls inside the mirrored part's own
   span.

**These traps govern pad sides too, not just tracks.** On a part that is both
rotated and flipped, the same reasoning error decides which board direction pad
1 faces. That is a placement decision rather than a routing one, so no lane
convention protects against it.

The composed rotate-then-flip transform, and the rule that follows from it,
**never derive a pad side; place the part and read `pad_xy()` back**, are in
`kicad-api.md` §4.

The payoff when this is done right is that the mirrored corner often comes out
simpler than the original, with fewer tracks and vias, because nets that had to
thread a gap can now run straight.

## 9. Reversible-board schemes

One PCB, fabricated twice, populated on the front for one variant and on the
back for the other.

**Flip-axis selection criterion: choose the axis that preserves the ordering of
the functional groups.** For a row and column grid, flipping about the axis
perpendicular to the row direction maps the grid onto itself with logical
indices intact, so both variants share one netlist. Any other axis reorders the
groups, and there is no shared netlist.

The prerequisites are all checkable numerically. The outline, the mounting
holes, and the two variants' module positions must each be symmetric about the
chosen mirror line.

Two governing rules:

- **No via may land on a one-sided part's pad.** If the part must keep its data
  direction in board coordinates on both faces, the two faces' pad sets are
  mirrors of each other, so each pad position carries a power pad on one face
  and a data pad on the other. A via there shorts a rail into the signal.
- **Every net with copper on both faces needs at least one tie**, or
  connectivity reports it as two islands. It is almost always a via that had to
  exist anyway. Pick it deliberately rather than discovering it from the DRC.

### Interleaved through-hole grids for a flipped module

Turning a module over swaps its pad columns, mapping hole `i` onto pad `N+1−i`.
That pairs supply with signal and is a dead short, so the two variants cannot
share one hole grid. Use two interleaved grids, giving 2N holes.

**Offset them purely across by one full pitch, not diagonally.** Diagonal
offsets, which are the common published choice, stagger the pad rows so nothing
threads them, seal the corridor off from the margins, and turn every net into
two feeds arriving from opposite sides.

A pure one-pitch cross-offset gives all of:

- both holes of a pad number on the same coordinate along the module, so one
  track plus a short stub reaches both;
- all rows sharing one set of gap positions, so a single track threads the whole
  corner;
- planes flowing through those same gaps;
- a full pitch of drill web between the grids, instead of a fraction;
- both variants' connector ends on the same coordinate, so one enclosure cutout
  serves both.

### When four layers earn their cost

Reversibility doubles the pad count on every net while the board area is
unchanged, because each per-cell part exists twice. If the two-layer version
already uses both faces to capacity, two layers cannot do it, and no amount of
effort changes that.

What the inner layers buy:

- The two bus families move inward, one plane per rail carrying the buses, which
  frees both outer faces for local per-cell copper.
- With the buses inward, the chain has nothing to cross. There is one straight
  run per face, and the two faces' runs cross at the middle of every link, which
  is exactly where the tie via goes.
- Every part reaches its rail through one via to a plane, instead of a pour
  island on a crowded face. That retires the pour-island trap entirely, because
  planes then fill as a single island.
- Planes flow through the module's hole wall while signals thread the same gaps
  on the outer faces.

Six layers add nothing that this class of board needs.

### Why "0 unconnected" is a sufficient proof for a reversible board

Every piece of copper is present in both builds, and only the parts differ. An
unsoldered pad is still copper that a trace can enter and leave. So a net that
DRC reports as fully connected is connected for either populate face.

The only way to get it wrong is to rely on a component to bridge two pads. Audit
for that explicitly, and route both terminals independently.

### Two things that look like bugs and are not

- The second hole of an unused pin should be an unnumbered pad. Numbering it
  puts a no-connect net on two pads a pitch apart, and connectivity then demands
  copper between them.
- A fully blocked axis through a repeated cell is normal. Feeds come down a
  margin and re-enter through a pad gap.

## 10. Verification doctrine

1. **Schematic first.** Reach ERC 0 before any board work. The board inherits
   the netlist, and a power-design change is a netlist change. Power review
   belongs in the schematic phase, not the layout phase.
2. **The PCB gate is DRC 0 at error severity with schematic parity, and 0
   unconnected.** All four numbers, per board variant, per build.

   **Parity is only a gate once its severities are promoted. Passing the flag is
   not enough.** KiCad ships all five parity checks at warning severity, so
   `--severity-error` filters every one of them out before anything is counted,
   and the run prints `parity ok` having checked nothing.

   `kicad_scaffold.py` writes the five promotions into every new project, and
   `kicad_gate.py` prints `parity UNENFORCED`, or fails with `--strict-parity`,
   when a project's `.kicad_pro` does not carry them. The mechanism, the five
   rule names, and the measurement are in `kicad-api.md` §2.

   The rule to hold onto is the one that generalises: **a check whose severity
   is below the severity you filter on is not a check.**
3. **No net may reach its own pads only through a fill it does not own.** The
   trap is a net whose pads lie outside its own pour and connect to it only
   because the fill closes over them, which is the via-fed-plane trap. Route
   rail entries and bulk decoupling as explicit copper plus a stitch via.

   A plane's own net legitimately depends on its fill for the pads that sit
   inside the pour. That is what a plane is for, and a back-face SMD pad with an
   Ø3.0 contact hole, or a light window on every side, has nowhere to put a
   stub. Measured case: `kb/projects/hexpad.md` §3.11.

   Three things make that safe, and all three are required. State in the report
   that the plane net depends on the fill. Fill zones inside generation. Gate
   `unconnected` on every regeneration, so a fill regression fails the build
   instead of shipping.

   See `kicad-api.md` §4: island removal and `SetMinThickness()` are the two
   ways a fill silently stops connecting with no clearance violation anywhere.

   **A part's face is also its plane-net access, so a face change orphans its
   plane pads.** On a two-layer board the two pours are two different nets, for
   example ground on B.Cu and VCC on F.Cu. A footprint's pads on a plane net are
   free only while the part is on that plane's face, so a face change costs one
   stitch via per plane net.

   Measured: a connector with two ground pads and two grounded mounting bosses,
   plus two instances of a switch with one ground pad each, moved to the front
   face, and every one of those pads stopped being in a pour. The board still
   generated and still filled, and reported the problem only as
   `unconnected_items` after DRC, with the offending pads named by zone position
   rather than by pad, so the message points at a zone corner instead of at the
   part that moved.

   This is checkable statically, before any fill, from the netlist and the pad
   layer sets alone. For every pad whose net has a zone, assert that the pad's
   layer set intersects that zone's layer. Otherwise require an explicit via on
   that net within `via_pitch`, and report it by reference designator and pad
   number.
4. **Do not prove clearances on paper.** Generate, read the DRC JSON, nudge one
   named constant, regenerate. Every lane, offset, and gap is a named constant
   precisely so that the loop is cheap.

   Observed: one corner took most of a session proving inequalities by hand,
   while the mirrored corner was laid out from the pad table and passed on the
   first regeneration. Another board went from 374 violations to 0 in eleven
   passes.
5. **Proto slice first.** Build a one-cell version of anything repeated, such as
   one key, one LED, or one fastener, and gate it before instantiating N.

   A slice that omits the MCU has no driver for its rails and no consumer for
   its signal nets, so it needs deliberate `PWR_FLAG`s, and on a fuller slice
   `no_connect`s, purely to satisfy ERC. An "input power pin not driven" finding
   on a proto slice means the slice is partial, not that it is wrong.
6. **Diagnostic pattern: known-good artifact against fresh regeneration.** When
   a previously clean design suddenly fails, regenerate and compare against the
   committed artifact under the same checker.

   If the committed file still passes and the regeneration does not, the fault
   is in the toolchain, not the design and not the rules. Same rules, different
   geometry. This isolates an API or version regression in minutes. One
   295-violation storm was traced this way to a single changed enum; see
   `kicad-api.md` §4.

   Run this smoke test before starting design work after any toolchain change.
