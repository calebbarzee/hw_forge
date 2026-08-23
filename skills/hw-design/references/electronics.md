# Electronics — rails, protection, routing topology, mirroring

Generic rules. Part numbers, firmware symbols and project geometry live in `kb/`.

## 1. Power-rail topology — decision tree

Start from *what the module already contains*, not from a blank schematic.

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
   → the SAME rail as the MCU logic. See §2 — this satisfies level shifting
     by construction and is almost always the right answer.
```

**Quiescent-current test for gating.** A part with even ~1 mA of idle draw, times N instances, against the cell capacity, decides this:
`idle_hours = capacity_mAh / (N × I_idle_mA)`. N=22 parts at ~1 mA each = ~20 mA = a 500 mAh cell flat in ~24 h. Anything that flattens the cell in under a week **must** be on a gated rail.

**Regulator enable pins are free gating.** If the module's regulator enable is wired to an MCU GPIO the firmware already drives, hanging the switchable load on that regulator's output is strictly better than an external load switch: fewer parts, one control point, and the regulator's own current limit becomes a hard ceiling on how much mistake the load can make.

## 2. Level shifting — the 0.7×VDD rule

Most single-ended CMOS/logic inputs specify `VIH ≥ 0.7 × VDD` (of the *receiver*).

- **Powering the peripheral from the driver's own logic rail satisfies this by construction**, with no shifter: `0.7 × 3.3 = 2.31 V` against a ~3.3 V drive. There is nothing to check.
- **Raising the peripheral's rail is what breaks it.** A peripheral at 5 V wants `0.7 × 5 = 3.5 V`, which a 3.3 V driver cannot reach. The field workarounds are all ugly: a series diode dropping the peripheral rail to ~4.3 V so `0.7 × 4.3 = 3.0 V` clears (common on 5 V addressable-LED boards), or a real shifter.
- Therefore: **choose the peripheral rail so no shifter is needed**, and only then evaluate what the higher rail buys. Typical cost of the low rail: reduced output (dimmer/quieter/slower), sometimes a colour or gain shift. Usually acceptable; write the trade down.

## 3. Series resistor into a gated rail

**Rule: any data line driven from an always-powered domain into a peripheral on a gated rail needs a series resistor at the driver.** Ungated designs do not need it, and their precedent does not transfer — this is the one topological difference that matters.

Failure mode without it: when firmware drops the rail, the peripheral's VDD is 0 V while the driver pin may still be driven or parked high. The input forward-biases the receiver's **input ESD clamp into a dead rail** — a phantom drain, a partially-powered peripheral (the classic "first device still faintly glows with the power off"), the driver propping the dead rail up, and at worst a latched input.

**When a gated reference design omits it.** The counter-evidence that matters is a reference design with the **same topology** — gated rail, always-powered driver — not an ungated one; when you find one, the rule above does not settle the question by itself. Decide on the **receiver class**. Injection actually matters for: addressable-LED chains and other parts that can partially light or partially operate off clamp current (that is the visible symptom); parts whose datasheet forbids signals present before VDD; anything where the driver can end up propping a dead rail. It matters much less for a receiver whose datasheet is silent and whose failure mode is invisible. The resistor is cheap and the decision must be **recorded either way** in the power decision record, with the receiver class, the counter-evidence, and which way it went. (hexpad: a nice!view on the module's gated VCC driven from always-powered GPIOs, and every shipping nice!view keyboard is topologically identical — also gated — and ships no series resistors. Fitted 470 Ω on the Sharp memory LCD's SPI lines whose datasheet could not be read, and wrote the disagreement with shipping designs into `POWER.md` rather than letting the reference silently indict a shelf full of working keyboards.)

Sizing:
```
I_inject = (V_drive − V_clamp) / R          # V_clamp ≈ 0.7 V for a diode clamp
choose R so I_inject is comfortably below the driver's per-pin current limit
t_edge  ≈ R × (C_in + C_trace)              # must be ≪ the protocol's edge tolerance
```
Worked example (from a gated addressable-LED chain): `R = 470 Ω` → `I = (3.3−0.7)/470 ≈ 5.5 mA`, and `470 Ω × 80 pF ≈ 38 ns` against a ±150 ns timing tolerance on a 300/600 ns bit — ~4× margin, so the resistor is free.
- Too small is pointless: `100 Ω → 26 mA`, which is above the MCU's per-pin drive anyway, so it limits nothing and only does the damping job.
- Too large softens the edge: keep `t_edge` under ~25 % of the protocol's tolerance. For most serial protocols this puts the usable band at **100–500 Ω; do not exceed ~1 kΩ.**
- Secondary benefit, always present: **source-series damping** of the one long singly-terminated stub. In a daisy chain, every link after the first is reshaped by its own receiver — only the driver→first-device run is unterminated, so that is the only run that needs damping.

## 4. Decoupling policy

- **Per-part local cap** (typ. 100 nF, 0402/0603) hard against the part's own supply pad, one per instance. Its job is the part's own switching transient; the loop area is the whole point, so *placement matters more than value*.
- **Bulk at rail entry**: a low-frequency reservoir where the rail enters the load group — typ. `10 µF + 1 µF` in parallel (bulk + mid-frequency, different self-resonances). Non-optional when the rail is *gated*, because the turn-on is a current step.
- Sum the added capacitance and check the regulator is stable into it. A few tens of µF is fine for a small LDO; inrush is bounded by the regulator's own current limit.
- **Per-part caps on a long chain are a judgement call, not a datasheet mandate.** Reference designs frequently ship zero of them and work. What they buy is suppression of supply ringing from N controllers switching simultaneously, whose symptom is *misbehaviour at the far end of a long chain*, not a dead board. If you populate them, record it as a decision with that reasoning — do not cite a datasheet that does not say it.

## 5. Current budget arithmetic

Build the table before routing; it decides rail choice, trace width, and connector.

| Case | Per part | × N | Compare against |
|---|---|---|---|
| gated off | 0 | 0 | — |
| idle / quiescent | measured or datasheet | | cell capacity ÷ target standby days |
| worst-case full load | datasheet **max**, incl. binning spread | | **regulator rating** and cell C-rate |
| intended working ceiling | design target | | pick this, then enforce it |

Rules:
- Use the **worst bin**, not the typical figure. A 3× spread between typ and max is normal for LEDs and RF.
- If worst-case exceeds the regulator rating, a **firmware cap is a hardware requirement, not a preference**. Record the specific config key and value in the power doc, and say what must be measured before raising it.
- Check **dropout too**, not just current: `Vin ≥ Vout + Vdropout(at I)`. Near end-of-discharge the *high-current* rail sags long before a low-power MCU (which may run to 1.7 V) notices. Another argument for the cap.
- Charge rate: `C_charge = I_charger / capacity`. A module's fixed ~100 mA charger is 0.2C into a 500 mAh cell (safe, ~6 h from empty) but 0.9C into a 110 mAh one. **The charger sets a minimum cell size.**
- Discharge: state the working ceiling as a C-rate (`300 mA from 500 mAh = 0.6C`) so it can be checked against the cell, not just the regulator.

## 6. Protection: what to add, and what not to

Default posture on a carrier board under a protected MCU module: **add nothing.** For each candidate, name the hazard it addresses and the path that hazard takes on *this* board. If the path does not exist, the part does not go on.

Commonly rejected, and why:
- **Reverse-polarity element on a cell** — if the connector is polarised the hazard is a pigtail-wiring error, not a system state; and a series element in that path also breaks charging through it. Fix it with a keyed connector plus a documented polarity check.
- **Fuse/PTC on a cell** — the cell's own protection PCM covers short and overcurrent; add one only if there is a second high-current path.
- **Protection IC / charger / regulator / USB TVS** — already on the module. Enumerate, don't duplicate.
- **External load switch** for a load already on a firmware-gated rail — redundant.
- **Level shifter** where the peripheral shares the logic rail — see §2.
- **Series resistors on scanned matrix lines** — GPIOs are drive-limited, per-key diodes block reverse paths, and the firmware uses internal pulls.
- **RC debounce / pull-up on reset** — usually on-module; a bare momentary to GND is the expected circuit.
- **TVS on a net that is entirely internal to the board** — no ESD path exists.
- **Bulk cap on the raw input** — the module has its own input capacitance and a cell's ESR is low.
Write these down *as a rejection table with reasons*. It is the artifact that stops the next reviewer re-adding them.

## 7. Matrix / chain routing patterns

- **Layer split by net family.** Give each orthogonal family its own face: one axis of the matrix on the front, the other on the back, one via per crossing at the part that needs it. The two families then meet only at through-hole pads and cannot collide. This is what lets many nets share one congested corner without an autorouter.
- **Corridor analysis before placement.** Mechanical holes block *every* layer. Solve the clearance inequalities per repeated cell to find how many full-height corridors exist per pitch, and route to that number. `needed = hole_r + hole_clearance + track_w/2` per side. If the answer is "exactly one corridor", every net contending for it must be assigned by hand.
- **Serpentine chains: run a row straight, turn around outside the outermost cell.** In-row links then become short neighbour hops, which is what makes a long chain routable on two layers. Row-major beats boustrophedon-within-cell every time.
- **Rotation vs return trace.** For a directional part (data in one end, out the other), a chain that reverses direction each row has two options: rotate the part 180° on reversed rows so the output always faces the direction of travel, or keep one orientation and pay a return trace that crosses its own cell. **Rotation usually wins** — the return trace collides with the next link's departure. Cost of rotation: the pick-and-place file shows alternating 0°/180° (document it as intended), and *everything positioned relative to that part must be positioned relative to the part, not the cell* (see §8).
- **Bus detours around mechanical holes** are cheaper than moving the bus: step the run aside over a short window at each hole, generated from the hole table so moving a hole moves its detour.
- **Ordering rules keep a fan-out planar without an autorouter.** Two that generalise: *a feed that crosses a barrier further along takes a lane further out*, so its run never meets a crossing already placed; and the mirror rule on the far side. Assign lanes by that ordering, not by convenience.
- **Nest or interleave — and for interleaved spans NO lane order exists.** The rule above ("two nets that run along an axis and turn off it are planar on one layer iff lane order across the axis follows turn order along it") reads as a recipe: sort by turn order, assign lanes, done. It is incomplete, and the missing half costs a full build cycle. Each net occupies the span `[rise, turn]`:
  - spans that **nest** (`rise_i < rise_j < turn_j < turn_i`) → a lane order exists; the inner net takes the near lane;
  - spans that **interleave** (`rise_i < rise_j < turn_i < turn_j`) → **no lane order works.** Whichever is put nearer, one of the two verticals must cross the other's horizontal. **One layer change is required — count it** in the via budget rather than trying the other lane order, which cannot succeed.

  Corollary, and it is the whole reason a board lands in one case or the other: **a two-terminal SMD's rotation is a topology decision for every net that leaves it.** Measured: three north-band nets turning south at fixed x (the MCU pinout owns those) rose at +2.500 / −2.500 / −2.000; the first two nested, the last two interleaved *because* a SOD-123 at `rot 180` put its cathode 0.500 mm **east** of the neighbouring pad instead of 2.800 mm west of it. One part rotation, and a via-free band becomes a two-via band.
- **Two parallel lanes that fence a region need `2 × zone_clearance + min_thickness` of separation, and a via between them needs `via_r + zone_clearance` more than a track does.** This is the arithmetic behind a pour that closes: 0.625 mm vs 0.425 mm on one board, which was the entire bug. See §10.3 and `kicad-api.md` §4 — a pour pinched below its own `SetMinThickness` splits into isolated islands with **no clearance violation anywhere**, so nothing upstream of DRC objects. Measured: a 1.10 mm window between two lanes, with a 0.6 mm via keepout in the middle of it, left **0.075 mm** of pourable channel against a 0.20 mm minimum, and fenced a ~300 mm² GND island off the net.
- **A pour vent can be a lane that ISN'T THERE**, and no artefact shows which absence is load-bearing. The inverse of the pinch above and nastier: a pocket drains through a stretch of a lane's own y that simply has no copper on it, because the bus starts further east. Nothing marks that. The board file shows copper, not the gaps that matter, and a generator's comment documented the *other* vent at length because in that revision nothing threatened this one. So: **when a net's bus already exists on a lane, extending that lane east or west to reach a new terminal is a POUR change, not just a routing change — re-check island count, not just DRC.** Measured cost of not doing so: 198 mm² of unconnected GND from a routing choice that looks, in every view a person has, like joining a net to itself along an existing line.
- **Deliberate nesting under a tall part** is legitimate (a low part in the standoff shadow of a socketed module). It produces `npth_inside_courtyard`-class findings; demote the specific rule in the project file with the justification, do not move the part.

## 8. The two mirroring traps

These cost more time than any other class of geometry bug. State them as invariants.

**Trap 1 — a footprint cannot mirror in one axis without changing layers.** Mirroring a part in x while keeping it on the same face is not a rigid motion. So "the mirrored variant" of an asymmetric part is actually a **180° rotation** (end-for-end turn), which:
- keeps edge-relative features on the variant's own outer edge (good — that is usually why you did it), but
- **swaps the functional roles of the two pad groups.** The group that faced one direction now faces the other.

**Trap 2 — one sign cannot carry both axes.** If the part turns end-for-end but the surrounding grid does *not* mirror in the other axis, then any constant expressed as a **part-local offset** ("2 mm on the pad-column side") lands on the wrong physical side of the board. Symptom: a whole routing block's worth of violations from a single inherited sign — lanes on top of pad rows, parts pushed off an edge, clearances to holes that were never intended.

Invariants that prevent both:
1. **Express routing lanes in BOARD coordinates**, never as part-local offsets, on any board that has a mirrored sibling.
2. **Derive functional roles from the rotation**, at generation time, from the actual pad table — never inherit them.
3. **One sign describes where the parts are; nothing about the lanes may be inherited through it.** Keep a `place()` helper carrying the mirror sign (correct — it describes physical position) and a *separate* per-variant corner router. Two-terminal parts whose pad *order* must keep pointing at a pad group whose role swapped get an explicit **opt-out of the turn**.
4. When a repeated cell contains an asymmetric part, **the cell does not mirror either** — so cell-relative bus offsets sit on the opposite side of the mirrored part. Recheck every bus that falls inside the mirrored part's own span.

**These traps govern pad sides too, not just tracks.** On a part that is rotated *and* flipped, the same reasoning error decides which board direction pad 1 faces — a placement decision, not a routing one, so no lane convention protects you. The composed rotate-then-flip transform and the rule that follows from it (**never derive a pad side; place the part, read `pad_xy()` back**) are in `kicad-api.md` §4.

Payoff when done right: the mirrored corner often comes out **simpler** than the original (fewer tracks and vias), because nets that had to thread a gap can now run straight.

## 9. Reversible-board schemes

One PCB, fabbed twice, populated on the front for one variant and the back for the other.

**Flip-axis selection criterion: choose the axis that preserves the ordering of the functional groups.** For a row/column grid, flipping about the axis *perpendicular* to the row direction maps the grid onto itself with logical indices intact — so both variants share one netlist. Any other axis reorders the groups and there is no shared netlist. Prerequisites, all checkable numerically: the outline, the mounting holes, and the two variants' module positions must each be symmetric about the chosen mirror line.

Two governing rules:
- **No via may land on a one-sided part's pad.** If the part must keep its data direction in *board* coordinates on both faces, the two faces' pad sets are mirrors of each other, so each pad *position* carries a power pad on one face and a data pad on the other. A via there shorts a rail into the signal.
- **Every net with copper on both faces needs at least one tie**, or connectivity reports it as two islands. Almost always a via that had to exist anyway — pick it deliberately rather than discovering it from the DRC.

**Interleaved through-hole grids for a flipped module.** Turning a module over swaps its pad columns, mapping hole *i* onto pad *N+1−i*. That pairs supply with signal and is a dead short, so the two variants cannot share one hole grid — use two interleaved grids (2N holes). **Offset them purely across by one full pitch, not diagonally.** Diagonal offsets (the common published choice) stagger the pad rows so nothing threads them, seal the corridor off from the margins, and turn every net into two feeds arriving from opposite sides. A pure one-pitch cross-offset gives: both holes of a pad number on the **same** coordinate along the module (one track plus a short stub reaches both); all rows sharing one set of gap positions (a single track threads the whole corner); **planes flowing through those same gaps**; a full pitch of drill web between the grids instead of a fraction; and both variants' connector ends on the same coordinate, so one enclosure cutout serves both.

**When four layers earn their cost.** Reversibility **doubles the pad count on every net** while the board area is unchanged — each per-cell part exists twice. If the two-layer version already uses both faces to capacity, two layers cannot do it, and this is not a matter of effort. What the inner layers buy:
- the two bus families move inward (one plane per rail, carrying the buses), freeing both outer faces for local per-cell copper;
- with the buses inward, the chain has nothing to cross — one straight run per face, and the two faces' runs cross at the middle of every link, which is exactly where the tie via goes;
- every part reaches its rail through **one via to a plane** instead of a pour island on a crowded face, which **retires the pour-island trap entirely** (planes then fill as a single island);
- planes flow through the module's hole wall while signals thread the same gaps on the outer faces.
Six layers buy nothing this class of board needs. Four is the answer.

**Why "0 unconnected" is a sufficient proof for a reversible board.** Every piece of copper is present in both builds — only the *parts* differ — and an unsoldered pad is still copper a trace can enter and leave. So a net DRC reports as fully connected is connected for either populate face. The only way to get it wrong is to **rely on a component to bridge two pads**; audit for that explicitly and route both terminals independently.

**Two things that look like bugs and are not:** (a) the *second* hole of an unused pin should be an **unnumbered** pad — numbering it puts a no-connect net on two pads a pitch apart and connectivity then demands copper between them; (b) a fully blocked axis through a repeated cell is normal, so feeds come down a margin and re-enter through a pad gap.

## 10. Verification doctrine

1. **Schematic first.** ERC 0 before any board work — the board inherits the netlist, and a power-design change *is* a netlist change. Power review belongs in the schematic phase, not the layout phase.
2. **PCB gate = DRC 0 at error severity WITH schematic parity, AND 0 unconnected.** All four numbers, per board variant, per build.

   **Parity is only a gate once its severities are promoted — the flag is not enough.** KiCad ships all five parity checks (`missing_footprint`, `extra_footprint`, `net_conflict`, `footprint_symbol_mismatch`, `lib_footprint_mismatch`) at *warning*, so `--severity-error` filters every one of them out before anything is counted and the run prints `parity ok` having checked nothing. Measured: a board missing eight parts and mis-wiring twenty-one nets gated green; `--severity-all` on the same board reported **31** parity issues. A second project's proto slice had been hiding two genuinely missing components behind a green gate for its whole life. `kicad_scaffold.py` now writes the five promotions into every new project and `kicad_gate.py` prints `parity UNENFORCED` (or fails, with `--strict-parity`) when a project's `.kicad_pro` does not carry them — but the rule to hold onto is the one that generalises: **a check whose severity is below the severity you filter on is not a check.**
3. **No net may reach its own pads only through a fill it does not own.** The trap is a net whose pads lie **outside** its own pour and connect to it only because the fill closes over them — the via-fed-plane trap. That must never happen: route rail entries and bulk decoupling as explicit copper plus a stitch via. A plane's own net *legitimately* depends on its fill for the pads that sit **inside** the pour; that is what a plane is for, and a back-face SMD pad with a Ø3.0 contact hole or a light window on every side has nowhere to put a stub. (hexpad's GND pour serves 27 such pads, among them a Kailh hotswap pad and every LED's VSS; z_board takes GND the same way.) What makes it safe, all three: state in the report that the plane net depends on the fill; fill zones **inside generation**; and gate `unconnected` on **every** regeneration, so a fill regression fails the build instead of shipping. See `kicad-api.md` §4 — island removal and `SetMinThickness()` are the two ways a fill silently stops connecting with no clearance violation anywhere.

   **A part's FACE is also its plane-net access, so a face change orphans its plane pads.** On a two-layer board the two pours are two *different* nets (GND on B.Cu, VCC on F.Cu): a footprint's pads on a plane net are only free while the part is on that plane's face, and **a face change costs one stitch via per plane net.** Measured: a connector (2 GND pads + 2 grounded mounting bosses) and a switch (1 GND pad, two instances) moved to the front face, and every one of those pads stopped being in a pour. The board still generated, still filled, and reported it only as `unconnected_items` *after* DRC — with the offending pads named by **zone position** rather than by pad, so the message points at a zone corner and not at the part that moved. Checkable statically, before any fill, from the netlist and the pad layer sets alone: for every pad whose net has a zone, assert the pad's layer set intersects that zone's layer, else require an explicit via on that net within `via_pitch` — and report it **by ref and pad number**. The fix (a stitch via just outside the part's body) is obvious once stated and invisible until then.
4. **Don't prove clearances on paper.** Generate → read the DRC JSON → nudge one *named constant* → regenerate. Every lane, offset and gap is a named constant precisely so the loop is cheap. Observed: one corner took most of a session proving inequalities by hand; the mirrored corner was laid out from the pad table and passed on the first regeneration. Another went 374 violations → 0 in eleven passes.
5. **Proto slice first.** Build a one-cell version of anything repeated (one key, one LED, one fastener) and gate it before instantiating N. A slice that omits the MCU has no driver for its rails and no consumer for its signal nets, so it needs deliberate `PWR_FLAG`s (and on a fuller slice, `no_connect`s) purely to satisfy ERC — "input power pin not driven" on a proto slice is the slice being partial, not the slice being wrong.
6. **Diagnostic pattern — known-good artifact vs fresh regeneration.** When a previously clean design suddenly fails, regenerate and compare against the committed artifact under the *same* checker. If the committed file still passes and the regeneration does not, it is **the toolchain, not the design, and not the rules** — same rules, different geometry. This isolates an API/version regression in minutes instead of burning a design session. (This is how a 295-violation storm was traced to one changed enum; see `kicad-api.md` §4.) Run this smoke test *before* starting design work after any toolchain change.
