# Mechanical — fastening, stack-ups, clearances, FDM printability

Generic rules and formulas. Specific parts, cells and project geometry live in `kb/`.

## 1. Heat-set inserts

| Quantity | Rule |
|---|---|
| Bore diameter | **= the insert's spec OD**, not the thread size. Do not add clearance; the insert melts its own interference fit. (M2 inserts are typically Ø3.2 OD × 4.0 long.) |
| Bore depth | insert length **+ 0.3…0.4 mm** of slack, so the insert cannot bottom out and the screw cannot jack it out. |
| Wall around the bore | **≥ 1.2 mm** of solid material. `wall = (post_OD − bore_D) / 2` → an Ø3.2 bore needs an **Ø5.6 post**. |
| Deck cap over a blind bore | **≥ 0.5 mm**, target 0.6 mm: `cap = reference_face_z − bore_depth`. |
| Install direction | from the cavity side, part resting on its reference face, **before any other assembly step**. |
| Temperature | ~220–240 °C for PETG; lower for PLA. |

- A blind bore with a thin cap is the printability-friendly choice: the cap is a **first-layer feature** in the plate-down orientation. If the printer cannot hold the cap, make the bore a through-hole and press inserts from the outside instead — expose that as a parameter (`insert_bore_depth = reference_face_z`), not a code edit.
- `verify()` must assert all four: wall, depth-vs-insert-length, cap thickness, and that the bore footprint stays **under solid material** (not inside an adjacent cutout or window).

## 2. Screw-length stack-up — worked formula

```
available_thread = screw_len
                 − (floor_thk − counterbore_depth)     # shoulder left under the head
                 − cavity_depth                        # the air gap the screw crosses
                 − pcb_thk                             # anything clamped on the way
```
i.e. `travel_before_thread = (floor − counterbore) + cavity + PCB`, and
`engagement = screw_len − travel_before_thread`.

Worked: `(2.60 − 2.10) + 8.00 + 1.60 = 10.10 mm` of travel → an M2×14 gives **3.90 mm** engagement into a 4.0 mm insert in a 4.4 mm bore. An M2×8 falls 2.1 mm short of even reaching the insert.

Acceptance:
- `engagement ≥ 2 × thread pitch` is the absolute floor (M2 pitch 0.4 → 0.8 mm). It is not a *design* target.
- Into a heat-set insert, target **engagement ≈ most of the insert length**, and require `engagement ≤ bore_depth` so it cannot bottom out. A practical machine-checkable band: `2.5 mm ≤ engagement ≤ bore_depth` for M2-class fasteners.
- Pick from the stocked length ladder, not a continuous value: `screw = min(L for L in LADDER if L ≥ travel + engagement_target)`.
- Counterbore: `cbore_D = head_D + ~0.5 mm` fit; `cbore_depth ≥ head_height`; and leave **≥ 0.45 mm of shoulder** (`floor_thk − cbore_depth`) under the head or the head pulls through. Clearance hole `≈ thread + 0.4 mm`.

**Cite:** a locked spec called for M2×8 because it was written against a 4.5 mm cavity; the real cavity was 8.0 mm and the screw had to become M2×14. **Any change to a cavity depth changes the screw length** — so the generator must *compute and print* the required length on every run rather than carrying it in prose. Any parameter that changes the cavity (a thicker battery, a taller component) must re-derive it.

## 3. Fastening schemes

**Clamp (preferred when the board has plain clearance holes).**
Board is clamped between a seat face on one shell and a boss face on the other; the screw passes through the board's own standard clearance hole and threads into an insert in the opposite shell. Properties: no fastener or plastic touches copper; the board's z position is set by two solid faces, not by screw torque; the board needs only a standard clearance hole, so its layout is unconstrained by the case beyond that hole.

**Pass-through / standoff-through-board.**
A standoff passes *through* an oversized board hole. Costs real board area (a Ø5.4 hole where a Ø2.2 would do), constrains routing around every position, and makes the case a hard constraint on the layout. Use only when the board must be captured from one side only.

Either way:
- Hole positions are **owned by the board** and read from its file. The case follows.
- Target: every seat/boss **fully lands on the board**, `min(dist to each board edge) ≥ post_OD / 2`. **A board can make that unsatisfiable**, and it is not a design failure. (hexpad rev 2's H4 sits **2.275 mm** from the east edge and cannot move without a PCB re-gate; a Ø5.60 seat needs 2.800.) When `edge_dist < post_OD / 2`, work the decision tree — and note that **§1 outranks §3**: the insert wall is a strength requirement, the landing inequality is a clearance one.
  1. **Never shrink the post below §1's insert-wall minimum.** The obvious fix is the silent violation: Ø4.55 (the largest round post that fits at H4) leaves `(4.55 − 3.20)/2 = 0.675 mm` of wall around an M2 insert against §1's 1.20 mm, and the insert bursts out sideways on installation.
  2. On the shell that **owns the wall**: keep full OD and **merge the seat into the wall** with an explicit gusset. The material goes *outward*, so H4's bore then has **3.475 mm** to the wall's outer face — the constraint that was short becomes the one with the most margin.
  3. On the shell that does **not** own that wall (the mating wall descends past the boss, so there is nothing to merge into): **intersect every boss with the cavity inset by the lid gap**, and let the one that needs it come out **D-shaped**.
  4. Assert the resulting flat **on the solid** — slice the lid above its floor and read the extent — not from the parameters, or you have asserted your intent rather than your geometry. Assert the **bearing annulus** (`edge_dist − screw_clear/2`) in place of the "fully lands" inequality.
- **Every boss on a lid must be clipped to the mating shell's cavity**, and this holds even when no seat is near an edge. Unclipped, a Ø5.60 boss at H4 interferes with the other part by **0.375 mm** and nothing else in a suite notices: every per-feature check is about *components*, and a boss is not a component.
- **Where the clip is a no-op, assert on the solid THAT it is a no-op** — that the boss reaches its own OD and not the clip plane. This is the more common case and the more dangerous one: a boss that was never clipped and a boss whose clip removes nothing produce **the same solid**, so §3.4's "assert the flat" has nothing to assert and passes vacuously. (Cite: a revision constrained every mounting hole to a board corner, so every seat landed wholly on the board and the mandatory clip stopped cutting. Deleting the `& zbox(...)` line left all 416 checks passing — until a later revision moves a hole 0.7 mm outward and the boss silently fouls the other shell by exactly the 0.375 mm above.) Invert the assertion: slice the lid and require `max.X == boss_cx + boss_od/2`, the cylinder's own extent, **not** the clip plane. One sentence, and an untestable no-op becomes a check.
- Assert every seat/boss clears every component (§4).
- A self-mirroring hole-x set (symmetric about the board centre) lets one parametric model serve both mirrored variants — check it numerically rather than assuming it.

## 4. The air-gap ledger

**Enumerate every component height above and below the board, then assert every clearance numerically in code. Never eyeball a 3D view.**

Build two tables per board face:

```python
H_BELOW = {"socket": 1.85, "led": 1.40, "connector_mated": 1.65,
           "reset_sw": 1.60, "switch_pin_protrusion": 2.20, ...}
OBSTACLES_TOP = [(name, (x0, y0, x1, y1)), ...]   # board coords, from the PCB file
OBSTACLES_BOT = [(name, (x0, y0, x1, y1)), ...]   # courtyards, not guesses
```

**Match designators on the parsed prefix, never with `startswith`.** A reference designator is `PREFIX + digits` and the prefixes are **not a prefix-free code**: `D`/`DISP`, `R`/`RN`, `C`/`CN`, `J`/`JP`. A ledger that dispatched on `ref.startswith("D")` gave a nice!view (`DISP1`) an SOD-123 diode's 1.35 mm height instead of its 1.50 mm through-hole tail, and its derived "every diode is in the ledger" count came out 8 for a 7-diode board — caught by a count disagreeing with itself, not by anything geometric. `kicad_geom.py` reports a parsed `designator: {prefix, index}` per footprint; switch on `designator["prefix"] == "D"`.

Then, in `verify()`:
- **Vertical**: `gap_below ≥ max(H_BELOW over the footprint of the gap) + keepout`. Compute `max()` over the *actual* parts above that region, not the tallest part on the board.
- **Lateral**: for every post/boss/rib, `rect_dist(post_xy, obstacle_rect) ≥ post_OD/2 + keepout`, over **every** obstacle, and report the *nearest* one by name in the assertion message. That name is what makes a failure actionable.
- **Through-hole solder joints stand proud on the opposite face.** A front-face socketed module still puts an obstacle rectangle on the back-face ledger. This is the most commonly missed entry.
- Openings must be checked **against the part's courtyard, not its nominal body**, and in both axes plus z: `slot spans the whole courtyard` and `slot z spans the body z`, else a wall lands on the part. That is only the right rule when the courtyard is the larger of the two.
- **Sizing an obstacle rect is three cases, not one**, and picking the wrong one costs either a part or a fastener:

  | The part | Obstacle rect | Why |
  |---|---|---|
  | Hardware can exceed its own courtyard (a socketed module, an SMD part) | `courtyard ∪ body` | the default; the courtyard is drawn round the pad grid and can be the smaller rect |
  | Drawn as a keepout on purpose | `courtyard` | the courtyard *is* the declaration |
  | **Through-hole, courtyard inflated by its own pad row** | `body ∪ any protruding feature` | the excess is flat copper and silk — nothing a deck can hit |

  The third case is the one that surprises. Measured: a rotary encoder's courtyard is `1.200…15.400 × −1.500…16.000` while everything standing above the board is inside `2.500…14.100 × 1.500…13.500` — the extra 3.0 mm on the north side is its pad row. Sizing a deck window on the union anyway pushed the window's north edge to y −1.800, **0.020 mm** from a mounting boss's seat, forcing either a relocated corner hole (forbidden by spec) or a bigger board. On the body, the window's north edge is y 0.200 and the boss has 0.480 mm. One part's flat pad row, and the whole difference.

  **Read the decision, do not make it.** `kicad_geom.py` emits `obstacle_above` / `obstacle_below` per footprint — `{bbox, basis, courtyard_dropped}` — applying exactly this table from `courtyard`, `body_bbox`, `pads_bbox`, `through_hole` and `protrudes`. Consume that, and assert the `basis` you expected: a generator that silently switched from `body` to `courtyard∪body` because a footprint gained a Fab line is a window that moved.
- **A keepout derived from a component bound is invalidated by that component LEAVING, not only by it moving.** Re-derive on both. A revision that moved two parts to the other face took the protrude-below set from 37 refs to 35 — and those two were the tallest parts on the underside and the two that bounded a battery bay. The bay's north edge moved 5.820 mm and its east edge 6.775 mm, ~68 % more plan area, and nothing noticed, because every *remaining* ref still had a height in the ledger. A one-directional assertion ("every ref the board says protrudes has a height") cannot see this. A stale ledger that is merely **conservative** is the failure mode nobody looks for: the case still fits, it just wastes a third of its cavity — or, on a battery bay, a third of the capacity. `kicad_geom.py --diff OLD NEW` reports `protrudes` **set** changes (`+ref`, `-ref`, `ref: bottom -> top`) beside the per-ref position deltas, which is the check.
- **A courtyard can be smaller than the part it holds.** Footprint courtyards are routinely drawn around the **pad grid**, not the body: `MCU_nice_nano_v2`'s courtyard is 18.28 × 30.98 mm against a nice!nano v2 body of 17.78 × 33.00 mm — 2.02 mm shorter than the module, ~1.0 mm at each end. Sizing a deck window on courtyards alone leaves a 1.0 mm lip of plastic reaching over a module standing 1.30 mm proud of the plate: a hard interference that **every clearance check passes**, because the courtyard said nothing was there. So obstacle rects are `courtyard ∪ datasheet body`, and **assert the relation between them** (hexpad asserts `"MCU1 body south edge 33.00 exceeds its courtyard 31.99"`) so a later footprint edit that "fixes" the courtyard cannot silently move the window. The trap is silent in both directions: a courtyard bigger than the part costs margin, a courtyard smaller than the part costs the part. Body dimensions per module live in `kb/keyboards/nice-nano-v2.md`.
- A protruding actuator or connector shell needs its own assertion: `tip_coordinate` vs the wall's *inner face*, and shell overhang vs wall thickness. An overhang means the opening must go **clean through** the wall, not into a recess.
- Two openings in one wall must not merge: assert the remaining rib `(z_lower_edge_of_upper − z_upper_edge_of_lower) ≥ rib_min`.
- **Take a per-wall opening census.** Per-feature checks are per *feature*: two openings can each pass every check of their own while nothing stands between them. So for **each wall**, enumerate its openings with **both their z bands and their in-plane spans**, and assert either **disjoint in-plane spans** or an **intact web** between them — never neither.
  - The web may legitimately be the **PCB itself** where the two openings sit on opposite faces of a board that is clamped across the whole overlap: one z band strictly above the top face, the other strictly below the bottom face. State that reading explicitly in the assertion message, because what carries the wall there is 1.6 mm of PCB plus two rabbets, not plastic.
  - The web **must be plastic** — the rib rule above — wherever both openings are on the same side of the board, or the in-plane overlap runs past the board outline, so there is no PCB under it to carry the wall.
  - (hexpad rev 2: rotating the module put the USB-C notch and the slide-switch slot on the **same east wall**, overlapping in y, separated only by the board — notch floor +1.20 mm above the board's top face, switch knob below its bottom face. Fine, and nothing told anyone to look for it.)
  - This is a class of interference **the board creates and only the case suffers**, and the board phase is where two features end up on the same edge. So it belongs in the **PCB phase's handoff** as well: per board edge, which features open through it.
- Default `keepout = 0.30 mm`. Raise it where a print tolerance stacks against it.

## 4a. Same-part clearances are not keepouts

**`keepout` in §4 means clearance to a COMPONENT, throughout.** A distance between two features of the *same printed part* — a boss and a deck edge, a rib and a wall, a standoff and an opening — is not a keepout, and reading it as one asserts the wrong inequality. It is one of three other things:

| Rule | Question | Default |
|---|---|---|
| **Cover** | does A's material fully overlie B? | `deck_covers_seat_min = 0.10 mm` of overlap |
| **Ligament** | is the material left between them thicker than the minimum printable wall? | ≥ 2 extrusion widths ≈ **0.80 mm** |
| **Merge** | do they simply join? | **free** — a merge is not an interference |

Worked, both directions, from one session: a deck opening's north edge sits **0.130 mm** from where a standoff tangents it, and both are plastic on the top shell. A keepout reading says fail; the truth is that 0.130 mm is the *margin by which the deck fully covers the standoff's top face*, and covering it is the requirement (the insert bore needs material all round). Nothing thin exists anywhere. The other direction is a retention fence overlapping a boss — legal, for the same reason, stated for a different pair.

This makes `batteries.md` §7's carve-out ("a boss is not a component") an **instance of a stated rule** rather than a one-off. When two features of one printed part are close, name which of the three rules applies before writing the assertion — the first attempt at both cases above asserted the wrong inequality and had to be rewritten.

## 5. FDM printability

**Choose the print orientation FIRST, then forbid geometry that violates it.** The orientation is a design constraint, not a post-process decision.

For a shell with an integrated reference face (a plate, a deck, a fascia):
- **Reference face down on the bed.** All features then grow away from the bed and the cavity opens at the top of the print.
- Consequence, and it is a hard rule: **nothing may stand proud of the reference face.** Any raised boss, roof, or plateau above it breaks the orientation in both directions and forces supports over the whole face. If a tall part cannot fit under the deck, the answer is an **open window in the deck**, not a raised bay. (Cite: a roofed variant of a module bay modelled cleanly and passed every clearance check, and was still unprintable without support — it is retained as a resin-only option behind a flag.)
- Features you *want* on the first layer, because that is where dimensional accuracy lives: precision cutouts, insert-bore caps, counterbore pockets.
- For the mating lid: **outer face down**, counterbores become first-layer pockets, bosses and ribs grow up.
- Acceptable remaining overhangs: a shallow lid rabbet at the very top of the print, and short bridges over slots — **≲10 mm at any width, up to ~15 mm where the bridged section is ≤3 mm wide.** The limit needs the width term: 12 mm of bridge 2.5 mm wide (a wall's own thickness, flat, PETG at 0.20 mm layers) is routine; 10 mm of bridge 40 mm wide is not. A single scalar cannot express that, so a correct design either fails the rule or quietly raises it.
- **Take a per-shell bridge census**, in the same words as §4's per-wall opening census: **every unsupported span enumerated with its length AND its width, in the stated print orientation.** Anything not on that list is a defect. One assertion is not a census, and the name of a single assertion can hide the gap: a suite asserted `at_most("longest bridge in the top shell (the slide slot)", 7.00, 10.0)` while the **USB-C notch floor spanned 12.00 mm in the same shell** — the docstring had called that opening "no bridge at all" because it is open at the *top of the wall*, which is true in the wall's frame and exactly backwards in the print's, where the top of the wall is the first layer and the notch floor resumes in mid-air 12 mm across. A check named "longest bridge" was asserting the shorter one.
- **Support-free is a machine-checked assertion**, not an intention: for each solid, assert no feature's z extends beyond the reference plane in the forbidden direction.

Geometry rules:
- **Interior fillet radius ≤ what the mating part's corner allows.** A cavity fillet larger than the mating part's own corner radius fouls it. For a square-cornered PCB in a filleted cavity the cap is small (~1.0 mm for a 0.3 mm clearance); compute it and assert it.
- **Rabbet** the lid into the wall rather than butting it: depth ~1.2 mm, air gap ~0.15 mm per side. Self-locating and it hides the seam.
- Ribs/fences for retention: 1.6 mm thick, 3–4 mm tall, with a wire-exit notch where a lead has to leave.
- Wall 2.0–2.5 mm for a hand-held enclosure. Thin a wall locally with a **recessed panel** when a control must be reachable (see §6), keeping ≥0.8 mm.

Tolerance defaults (start here, then dial in one dimension at a time):

| Fit | Default |
|---|---|
| Press/clip fit for a moulded part (e.g. a switch into a plate cutout) | nominal **+ 0.15 mm** |
| Board-to-cavity clearance per side | **0.30 mm** |
| Lid ↔ rabbet air gap per side | **0.15 mm** |
| General slip-fit gap | **0.2–0.3 mm** |
| Clearance to any component (keepout) | **0.30 mm** |
| In-plane slop inside a retention fence | **0.6 mm** |
| Consumable swell / ageing allowance (cells) | **+0.4 mm** or vendor spec |
| Flying-lead outside diameter (`lead_od`) | **1.80 mm** for a 28 AWG twisted pair, **1.60 mm** for 30 AWG |

- Material: **PETG or ABS/ASA** for anything under screw preload. PLA creeps under preload and softens in a warm car.
- 0.16–0.20 mm layers, 4 perimeters, ≥25 % infill for a screwed enclosure.
- **Print a test coupon before a full part**: one cutout and one post/insert. Name the single parameter to tune first (usually the press-fit cutout) and the step size (±0.05 mm).
- Give each mirrored half its **own parameter instance** so fits can be dialled per side.

## 6. Reachability and openings

- A control's usable travel is `proud_of_edge − wall_thickness`. If the actuator stands only a few tenths proud, a full-thickness wall makes it unreachable: thin the wall with a recessed **port panel** (one recess carrying several openings) so a fingernail can reach it, and keep ≥0.8 mm of wall.
- **Third option: a bounded recess.** When `proud_of_edge < wall_min + cavity_inset` — no wall thin enough to leave the actuator proud is printable — the two halves of the rule above cannot both be satisfied, and that is not a design failure. The target becomes a **recessed actuator inside a slot big enough to admit a fingernail**, and the assertions move off the travel figure (which cannot be made positive) onto three others: recess depth ≤ a stated bound, panel wall ≥ 0.8 mm, and slot opening tall enough to reach into. (hexpad: an MSK12C02 slider stands 0.825 mm proud of the board edge, 0.525 mm past the wall's inner face after the 0.30 mm cavity inset, leaving a 0.53 mm wall if it were to stand proud of the *outer* face. Resolved as a 0.275 mm recess inside a 7.0 × 4.0 mm slot, asserted as `recess ≤ 0.60 AND panel wall ≥ 0.80 AND slot ≥ 3 mm tall`, and trivially operable with a fingernail.)
- A poke-hole for a recessed button: Ø3.0 with an outside countersink (Ø4.6 × 0.8). Note in the docs *how deep the button sits*, so the user brings the right tool.
- Cut openings from a **single recessed panel** rather than as independent pockets — one datum, one z reference, fewer interacting assertions.
- Emissive parts: check the light path before adding a diffuser. A reverse-mounted emitter shining *through* the board emits nothing on the other side, so a diffusing floor does nothing.

## 6a. Crossing the board plane

§6 covers things that go *out* through a wall. This is the other case: **a conductor that has to get from one face of a clamped PCB to the other, inside a sealed enclosure** — a cell in an underside bay whose connector ended up on the front face. It arises from a single upstream fact (which way the cable leaves its connector, §7's census below) and it has no default geometry, so it needs a pattern. **A pinched LiPo lead is a fire risk; this is not a cosmetic detail.**

Four constraints, all of which have to hold at once:

1. The only clear route is the **board-edge-to-wall gap**, which is `pcb_clear` — **0.300 mm** by default, flat enough to pinch a twisted pair.
2. Widening it needs `channel_w ≥ lead_od + keepout` of clear width **and** a minimum wall outboard of it: `channel_w + wall_min ≤ pcb_clear + wall`. Worked: `0.300 + 2.500 = 2.800` does not cover `1.80 + 0.30` of channel plus `0.80` of wall. **When it does not close, the wall thickens OUTWARD — the lead does not get thinner.** The outer envelope then stops being a rectangle, which is the correct outcome, not a failure.
3. The channel **must not reach down to the rabbet**, or the lid loses its seat across that whole span. (Found by nearly cutting it that way.)
4. The run has to be **computed and printed**, in the same spirit as §2's computed screw length — a pigtail is a purchased length. Three legs and 40.7 mm on the case this came from, and "it'll be fine" is how a build stops.

The alternatives are worse and worth stating so they are not re-proposed: a slot through the PCB cuts whatever routes across it (five band lanes, on the board this came from), and moving the cell re-opens the bay derivation in `batteries.md` §7.

## 7. Code-CAD doctrine

**Open with a census, and for every connector state where its CABLE goes** — in board coordinates, after the placement transform. **A connector's keepout is its cable, not its body.** The mating direction is in no machine-readable place: not in the footprint (a name containing `Vertical` is a convention, not data, and a footprint's own metadata can cite the wrong part outright — see `agents/resource-scout.md`), not in `pads_bbox` or `fab_items`, and `kicad_geom` cheerfully reports `protrudes: ["top"]` for a connector whose *cable* is the tall thing. So it comes from the part's KB card, where `mating_direction` is a required field of the connector section (`kb/README.md`), and it is restated here in board axes because the placement transform is what turns a footprint-local `+z` into "up, out of the front face". Cite: one vertical top-entry receptacle changing faces between revisions turned a one-line handoff note ("the lead points down into the bay, 6–8 mm from the cell") into a ~40 mm routed channel, a locally thickened wall, and all of §6a.

Then, the doctrine proper:

1. **Parametric generator + a numeric `verify()` that runs on every invocation, before export.** Non-zero failures raise and no geometry ships. Print the derived summary (heights, cavity, outer envelope, computed screw length) on every run — the numbers you would otherwise put in a doc and let rot.
2. **Every dimension is a named field on a params object.** Nothing is a literal inside geometry code. Left/right variants are separate instances of the same params class.
3. **Read mating geometry OUT OF the actual CAD/PCB files, never from a spec table alone.** Footprint positions, courtyards, the outline and hole positions come from the as-built, gate-passing board. A spec table is provenance, not an input — it drifts the moment a hole moves.
4. **Coordinate-frame conversion happens once, in one named helper, and is asserted.** PCB files are y-**south** and rotation-**clockwise**; a right-handed CAD frame is y-north and counter-clockwise. Converting one and not the other yields geometry that looks plausible and is wrong. Cite: components positioned relative to a *cell* instead of relative to the *rotated part* stayed put while the pads they served moved to the other end — traces then crossed features they had to avoid. **Anything that serves a rotated part's pad must be positioned through that part's own local frame.**
   **Asserted against what:** put a known-**asymmetric** feature through your own frame helper and assert it reproduces `kicad_geom`'s own reported `pads_bbox` for that part. One assertion proves the whole coordinate pipeline, and it must be an asymmetric part — a y-symmetric body reproduces itself under a sign error. In the style this file asks for: `local_rect()'s frame agrees with kicad_geom on SW7's pads (y 5.615..13.665)`.
   Cite: a case-handoff table gave an MSK12C02 slider knob at y 8.14…9.54 where the board says **y 9.790…11.090** — the handoff number **mirrored about the part centre (9.640)**, i.e. a rotation-sign error on a −90° part. Invisible on the switch's y-symmetric body (which the handoff got right to ±0.05) and visible only on the asymmetric slider lobe. Centring the slot on the handoff figure would have put **2.0 mm of wall squarely on top of the actuator**: a part that passes every clearance check and cannot be switched on.
   Corollary: **a case suite must ASSERT every handoff number it consumes**, so a stale table fails a check instead of steering a cut. `kicad_geom.py`'s docstring already warns that a rotation-sign error "is invisible on 0 and 180 degree parts and silently wrong on every 90/270 part" — and it still nearly cost a part, because the warning lived in a script's docstring and the error lived in a human table.
5. **Assert the mirror relationship**, don't assume it: `mirror(left_feature) == right_feature` for every hole, part centre and thumb/edge position, read from the right-hand board's own file. That assertion is what licenses one model to serve both halves.
6. **Assertion messages carry numbers and the offending name** (`"boss @(9.53,47.10) OD5.60: 0.42mm to cap 76.2,43.6 (need 3.10)"`). A boolean failure is a debugging session; a numbered failure is a one-line fix.
7. Export STEP **and** STL, plus cheap projected-view renders for eyeballing. Renders are nice-to-have — wrap them so a render failure never fails the build, and keep every render eye slightly **off-axis**: a true elevation view (eye exactly on an axis) puts every cylindrical standoff exactly edge-on, build123d's SVG exporter then hands a degenerate arc to svgpathtools and it raises `AssertionError: assert start != end` (`svgpathtools/path.py`, `Line.__init__`). The informative views of an enclosure *are* the elevations — that is where a USB notch and a switch slot are legible — so this is hit immediately; a few degrees off axis fixes it.
8. Report volume and bounding box per part on every run; it is the fastest signal that geometry silently changed.
9. **A footprint's 3D model transform: the model's origin is the footprint's own origin, on its MOUNTING FACE.** So a **reverse-mounted** part — body on the far face, working through a window in the PCB — needs an explicit offset or rotation, and which of the two (or both, or neither) is not derivable from anything in the file. A model that straddles the board plane is the tell: one measured LED model runs z −0.84…+0.79, and on a reverse-mount cell its body must sit *entirely* on one side. **Resolve it by rendering once, then record the resolved offset in the part's KB card**, so the next project inherits a number instead of a render loop. A model link is the one geometry input this doctrine cannot assert from the board file.
10. **A stand-in model must be STEP, must be named as a placeholder, and must take its dimensions from the design module.** All three, and the first is the one that bites: a hand-written `.wrl` box is text, needs no CAD dependency, and renders correctly in KiCad's 3D viewer — and **silently disappears from `kicad-cli pcb export step`**, which only consumes STEP/IGES. A project that took that route passes an "every footprint links a model" review, looks right on screen, and hands the enclosure phase an assembly STEP with no module and no display in it: exactly the parts most likely to collide with a shell. Name every one `*_PLACEHOLDER` so it reads as a stand-in in the model list, the BOM audit and the 3D view, and generate it from the design module's own dimensions rather than drawing it by hand. `preflight.py --project` resolves every `(model ...)` link and stats it — a footprint naming a model is not evidence that the model exists.
