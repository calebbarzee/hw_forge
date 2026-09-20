# hw_forge backlog

Work that is real, understood, and not bounded today. Everything here came out
of a validation run and was triaged deliberately: it is not a wishlist, and it
is not a list of things nobody looked at.

Each item names the gap numbers it covers in `hexpad/GAPS.md`, why it is
deferred rather than done, and what would have to be true to close it.

The criterion that put these here rather than into a harvest: a fix must be
verifiable in the same pass that writes it. Six of the nine below need a
mechanism the pipeline does not yet have (B1, B2, B5, B7, B8, B9). One needs a packaging
decision (B4), and one needs a cross-project convention before it can safely
write into someone's source (B6). Writing a doc line about any of them would
have produced a rule with nothing behind it; a recorded gap at least states what
is missing.

B3 moved out of that group: the mechanism it was blocked on now ships
(`scripts/kicad_fpcheck.py`, `scripts/packages.json`), so it stays in this
file only for the part of the original gap the mechanism does not cover. See
B3 below for exactly which part that is.

B5 and B6 are the deferred halves of gaps whose doctrine did land. That
distinction is worth preserving: the rule that stops the bug recurring is
written, and the tool that would catch it automatically is not. So the gaps read
as fixed in `hexpad/GAPS.md` and as open here.

| id | title | blocked on |
|---|---|---|
| **B1** | Shipping emitter templates vs. the adapt-a-sibling doctrine | a scope decision: does hw_forge own KiCad emitters, or a documented extraction procedure and a named canonical sibling? |
| **B2** | Two-source independence: detecting a shared ancestor | a machine-readable `lib/PROVENANCE.md`, so "these two assets cite the same URL" becomes a query on the phase-1 gate |
| **B3** | Verifying a stock footprint against the physical part | *(mechanism shipped)*; open remainder: a declared-package source per part family not yet in `packages.json`, and any check on the physical unit a supplier ships |
| **B4** | `/hw-kb` (and friends) outside a plugin install | the roadmap's plugin-packaging milestone: whether commands require a plugin install or must resolve from any project |
| **B5** | `kicad_pourcheck.py`: island count and narrowest channel per zone | the parser decision: extend the s-expression reader to zones, tracks, vias and nets, or accept a `pcbnew`-only tool |
| **B6** | Writing adopted placements back into a generator | a settled convention for where adopted placements live (a single `ADOPTED = {...}` in `design.py`) |
| **B7** | Acid-trap and vias-under-parts checks on autorouted copper | a geometry check with no mechanism today: acid traps need an angle and proximity check on trace joints; vias under parts need z-aware clearance, and `kicad_geom.py` has no z data |
| **B8** | Connector mating face against the board edge | a per-connector `mating_direction` the board file does not carry; the kb card format requires it, `kicad_geom.py` does not read it |
| **B9** | Local wall-thickness floor in `case_verify.py` | a minimum-thickness sweep over the shell solid, which needs build123d geometry queries the check runner does not expose yet |

---

## B1: Shipping emitter templates vs. the adapt-a-sibling doctrine

**Covers:** gap 11.

`templates/` ships `design.py`, `Makefile`, `.gitignore` and five role prompts.
It ships nothing for the `design.py → .kicad_sch` step, which is the deliverable
of phase 3. It ships nothing for the `one pin table → symbol + footprint` step
either, and that is a named cross-cutting rule with no template behind it. So a
new project is told to adapt a sibling project's `gen_sch.py`.

hexpad did exactly that, and reported what it copied: ~200 lines of pipeline
infrastructure with no hexpad in it.

- a balanced-paren s-expression (symbolic expression) walker
- symbol extraction out of the installed libraries with the `(extends …)` guard
- the `Lib:Name`-on-outer-symbol rewrite
- deterministic hashed UUIDs
- pin-position and pin-direction maths
- global-label wiring
- `no_connect` emission
- a `lib_symbols` cache

Only `build()`, `emit_support()` and a few sheet-layout constants were the
project's own.

Adapting beat rewriting. The cost is structural: a sibling project is now
load-bearing infrastructure that hw_forge does not own. A bug fixed in one
project's copy is not fixed in the next one, and hw_forge's own doctrine
("everything is code-generated from one source") rests on code the plugin cannot
version.

**Why deferred.** Shipping `templates/gen_sch.py` means owning a KiCad
s-expression emitter as pipeline code, and that is a scope decision rather than
an afternoon's work. It needs a stable contract with `design.py`: what shape a
part table has, what a sheet is, how a net gets a label. It also needs to
survive a KiCad file format bump, and it needs its own regression fixture.
Otherwise the first format change breaks every project that adopted it, and
hw_forge is on the hook for all of them.

`docs/ARCHITECTURE.md` §5 currently states the opposite position deliberately
("`design.py` and `gen_pcb.py` themselves stay project code"), and that position
has to be revisited, not quietly contradicted by a new template.

**To close:** decide the scope question first (does hw_forge own emitters, or
does it own a documented extraction procedure and a named canonical sibling?).
If emitters: ship `gen_sch.py` and `mklib.py` skeletons with a stub `build()`,
plus a fixture project that regenerates and gates in CI, so a format bump breaks
the plugin's own test rather than a user's board. If not: say so in `SKILL.md`,
name the canonical sibling to adapt, and list what is generic vs.
project-specific in it, which is most of the value at a fraction of the cost.

---

## B2: Two-source independence: detecting a shared ancestor

**Covers:** gaps 3 and 2.

The doctrine's definition of independence is "different lineage: a vendor
datasheet and a shipped reference board, not two blog posts copying each other".
That names the failure mode and gives no way to detect it.

hexpad's nice!view pin order was verified against two footprints separately
authored by different people, on different dates, in different repos, which is
independent by every checkable signal. Both cite the same vendor page as their
datasheet, and that page's pin table exists only as a PNG (Portable Network
Graphics) image. So the two sources may both be downstream of one photograph.
That is agreement between two transcriptions, not confirmation against a primary
source.

The doctrine half of this is now fixed (`agents/resource-scout.md`, "When the
primary source is an image"): the fallback is documented, and the transcription
caveat must be flagged inline in the provenance row and the report. What is not
fixed is the detection.

**Why deferred.** Detecting a shared ancestor needs something the pipeline does
not have. The candidates each cost real work:

- Parse the cited sources out of vendored assets and compare them transitively.
  This needs a provenance format machines read, not the markdown table humans
  read.
- Require a physical cross-check before a pin order is treated as fully
  verified: a photo of a purchased unit's silkscreen, or a continuity check.
  This needs hardware in the loop, and a way to record that evidence.
- Grant the scout a vision-capable fetch tool so the image primary can be read
  directly. This is not hw_forge's to grant, because it is the harness's tool
  list, and it would not help for a source that is a photograph of a part nobody
  has.

**To close:** make `lib/PROVENANCE.md` machine-readable enough that "these two
assets cite the same URL" is a query, and add that check to the phase-1 gate.
The physical-cross-check requirement can then be stated as the escalation for
the one case the query flags, instead of a blanket rule nobody can satisfy.

---

## B3: Verifying a stock footprint against the physical part

**Covers:** gap 19. **Mechanism shipped; part of the original gap remains open.**

Resolving a part to a stock KiCad footprint is the right call for cost and the
wrong thing to call verification. hexpad resolved five parts as "reference stock
KiCad, no copy needed". It then found that KiCad 10's
`Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02`, the footprint for a locked part,
places its three signal pads at x = −2.25, +0.75, +2.25 mm: spacings of 3.0 and
1.5, not a uniform three-terminal pitch. It may be correct for an offset-pin
variant. It could not be checked, because the LCSC (LCSC Electronics, the parts
distributor) datasheet was not reachable from that phase.

No gate could see this at the time. ERC does not know about pads. DRC and
schematic parity compare the board to the schematic, not to reality. A wrong
stock footprint was therefore invisible until a part would not sit on the pads,
which is after a fab order and an assembly attempt.

**What closed.** `scripts/kicad_fpcheck.py`, with `scripts/packages.json` as
its evidence source, checks a footprint's pad geometry (count, outer span on
both axes, pitch, and, for two-terminal chip and diode packages, the gap a
body must bridge) against the package the design declares the part to be, in
`design.py`'s new `PACKAGES` table (`templates/design.py`) or a `Package`
footprint property. `--declared-only` checks package FAMILY agreement alone,
with no dimension table needed. `agents/resource-scout.md` gate 7 requires it
at part resolution; `agents/fab-docs-engineer.md` requires it again before any
fab export. Two real incidents are its regression cases: a blog-documented
agent design that specified a SOIC-8 wide flash and laid down SOP-8 narrow
pads (`kb/parts/package-family-traps.md`), and the keyboard diode footprint
this same workstream investigated (`kb/keyboards/diode-footprint-vs-part.md`).

The evidence source that closed it is not the one this entry originally
proposed. Rather than a `kb/` library of pad geometry confirmed on a fabbed
board (which only accumulates coverage for parts a project has already built),
`packages.json` ships nominal geometry for ~26 common packages up front, each
number cited to a JEDEC/IPC designator, a manufacturer datasheet, or KiCad's
own stock footprint library. That covers the failure class both measured
incidents share, a common chip, diode, or IC package family, at zero prior
building.

**What is still open, precisely.**

- **The MSK12C02 case itself is still uncovered.** `packages.json` has no
  slide-switch or connector families; it covers chip passives, diodes, SOT/
  SOIC/TSSOP/MSOP/QFN/DFN/TO-252. Closing the measured case needs an entry
  added to `packages.json` for that family (the format is documented in the
  file's own `_read_me` field), which is now cheap but is not done.
- **The check needs a declared package to check against.** `design.py`'s
  `PACKAGES` table is opt-in; an unfilled one means every footprint checks
  only against its own name, which `kicad_fpcheck.py` reports honestly
  (verdict SKIP, or an INFO note) rather than silently passing, but it is
  still not a real check until someone fills the table in.
- **It cannot verify the physical unit a supplier ships**, only the design
  file's own consistency. The keyboard diode incident's root cause was a
  supplied part that did not match its own specified package
  (`1N4148W`/SOD-123 is nominally self-consistent across every major
  manufacturer's datasheet), a receiving-inspection or supply-chain
  substitution problem, not a design-file one. `kicad_fpcheck.py` closes the
  design-file half of the incident (would the design have been internally
  consistent) and cannot touch the other half. Closing that needs a
  component-measurement step with hardware in the loop, which is out of
  scope for a design-time pipeline.

**To close the remainder:** add package families as they come up (slide
switches, connectors, module sockets) rather than trying to front-load every
package that exists; each addition costs one `packages.json` entry with a
citation, following the file's existing shape.

`scripts/kicad_fplib.py` is the path from a FAIL this script prints to a
fabbed change: it forks the stock footprint into the project library,
applies the correction, and records the source, so the finding closes in the
library instead of stopping at a report (`kb/README.md`'s "where a fact
lives" table).

---

## B4: `/hw-kb` (and friends) outside a plugin install

**Covers:** gap 6.

`commands/hw-kb.md` exists, is well-specified, and matches `kb/README.md`'s
harvest convention exactly. It was not invokable during the dry run, because the
session was rooted in the project directory rather than in hw_forge, and slash
commands resolve against the project a session is rooted in.

The agent followed the procedure by hand, reading the command file and applying
its steps. That works and it is invisible: nothing in the pipeline says that is
what is supposed to happen. Meanwhile `commands/hw-research.md`'s own report
section tells the agent to run `/hw-kb harvest` as though it always resolves.

**Why deferred.** This is a packaging and installation question, not a wording
one, and the fix depends on how hw_forge is meant to be consumed. If the answer
is "install the plugin", then the docs should say that the commands require it
and stop implying they are always available. If the answer is "work from any
project", then something has to register the commands globally, and that is a
decision about the user's environment that a repo cannot make for itself. Either
way the fix touches installation, which the roadmap's "plugin packaging"
milestone owns.

**To close:** as part of plugin packaging, state the requirement once in
`README.md`'s install section and make every command file's cross-references
conditional on it. The stronger option: give each command's procedure a "read
this file and follow it directly" fallback line, so an agent operating
cross-project does the right thing by instruction rather than by improvisation.

---

## B5: `kicad_pourcheck.py`: island count and narrowest channel per zone

**Covers:** gaps 77, 83, and the script half of 81.

Three revisions lost copper to one class of failure, and every time it was
invisible until after a fill and a DRC run:

- a ~300 mm² GND island fenced in by two lanes and two buses, whose only escape
  was a 1.10 mm window with a 0.6 mm via keepout in the middle of it: 0.075 mm
  of pourable channel against a 0.20 mm `SetMinThickness`, and no clearance
  violation anywhere;
- 198 mm² of GND lost by extending an existing bus lane west, because the
  absence of copper along that lane was the pocket's only vent, and nothing in
  any artefact marks a vent;
- plane pads orphaned by a part changing faces, reported by zone position
  instead of by pad, so the message points at a zone corner and not at the part.

All three are computable at generation time from artefacts the generator already
holds. Flood the zone polygon minus (copper ⊕ clearance) on a `min_thickness`
grid, count components, and compare against the number of distinct pad groups.
Report per zone the island count, the narrowest channel, its coordinate, and the
two items bounding it. Plus the static half of the third: for every pad whose
net has a zone, assert the pad's layer set intersects that zone's layer,
reported by ref and pad number.

**Why deferred.** The doctrine half of all three landed this pass:

- the lane separation arithmetic (`2 × zone_clearance + min_thickness`, and
  `via_r + zone_clearance` more for a via) in `electronics.md` §7;
- the "extending a lane is a pour change, re-check island count" rule beside it;
- the face-change/plane-access rule in §10.3;
- and the upstream-of-DRC note in `kicad-api.md` §4.

The script did not land, because no hw_forge reader parses zones.
`kicad_geom.py` reads footprints, pads, holes and Edge.Cuts and has no notion of
a zone outline, a net, a track or a via. A polygon flood fill needs either that
parser extended by a large fraction of its own size, or a `pcbnew` dependency,
which makes the checker un-runnable under system python, i.e. un-runnable in the
same shell as the rest of the gate. Writing it against `drc.json` instead is not
an option either: that JSON is the output of the fill, which is the thing being
checked too late.

**To close:** decide the parser question first. Either extend the s-expression
reader to zones, tracks, vias and nets, which is the more durable answer and
unlocks several other checks. Or accept a `pcbnew`-only tool gated behind the
bundled interpreter, the way `gen_pcb.py` already is. Then the flood fill is ~60
lines, and the three measured cases above are its regression suite.

---

## B6: Writing adopted placements back into a generator

**Covers:** gap 79, second half.

`kicad_geom.py --diff --as-constants` prints the moved set as a pasteable python
dict, and `--diff --strict` verifies that a regeneration reproduced it to the
micron. That closes the verification half of the hand-placement round trip (see
`agents/pcb-engineer.md`). What is still manual is the paste: a human moves
eight numbers from stdout into the emitter's own constants.

**Why deferred.** Writing into someone's generator means knowing its shape, and
emitters legitimately differ: a dict keyed on ref, per-part named constants
(`ENC_XY = (2.50, 2.75)`), a table keyed on cell index. A tool that rewrote
python source would have to impose one convention on every project, or parse and
edit arbitrary assignments.

Getting that wrong fails silently: a board generated from the wrong adopted
coordinate is perfectly clean. The `--strict` re-diff catches exactly that
failure, which is why the remaining risk is acceptable and why automating the
paste is an ergonomics win rather than a correctness one.

**To close:** settle a convention for where adopted placements live, a single
`ADOPTED = {...}` in `design.py`, which is the shape `--as-constants` already
emits. `--adopt-into design.py` then becomes a safe in-place rewrite of one
named assignment.

---

## B7: Acid-trap and vias-under-parts checks on autorouted copper

**Covers:** a finding of the autorouting workstream (2026-09-20), not a
`hexpad/GAPS.md` gap.

`references/autorouting.md` §5 names two failure modes DRC does not catch. An
acid-trap wedge, where a free-angle router's rip-up-and-reroute pass leaves an
acute copper angle at a trace joint. And a via placed inside a courtyard with
no pad there to collide with, so no DRC violation fires, only a mechanical one
that the assembly or enclosure phase finds later. Neither has an automated
check in this pipeline.

**Why deferred.** The acid-trap check needs an angle and proximity pass over
every trace joint, which needs the s-expression reader to parse tracks (the
same parser decision B5 is blocked on). The via check needs to know which
footprints have hardware below their courtyard, which is z data
`kicad_geom.py` does not carry; `kicad_3d.py verify` reads it out of the STEP
assembly, but only after phase 5.

**To close:** settle B5's parser question first. With tracks parsed, the
acid-trap check is a per-joint angle test against a threshold. The via check
can then read `protrudes` from `kicad_geom.py` and flag any via inside a
courtyard whose part protrudes on that face. Until then the mitigation is a
rendered plot at high zoom over every autorouted corner, which is a human
look, not a gate.

---

## B8: Connector mating face against the board edge

**Covers:** a z_board finding reported 2026-09-20, not a `hexpad/GAPS.md` gap.

A USB-C receptacle was placed with its pad end at Edge.Cuts and its mating
face pointing inboard. DRC, courtyard checks, and the enclosure's numeric
checks were all clean, because none of them knows which way a connector
mates. The cable could not be plugged in.

**Why deferred.** The board file carries a footprint's position and rotation,
not its mating direction. `kb/README.md` already requires `mating_direction`
on every connector card, in footprint-local axes, and that is the missing
input: with it, the check is one rotation and one comparison against the
nearest board edge. Without a machine-readable place for it that
`kicad_geom.py` can read, the assertion has nothing to test.

**To close:** put `mating_direction` in `design.py`'s part table for every
connector (the same table B6 and the BOM contract are settling), have
`kicad_geom.py --json` rotate it into board axes, and add a phase-4 check
that every edge connector's mating face points outboard through the nearest
edge within a stated distance. Until then the pcb-engineer's per-wall opening
census states the mating direction in words for every connector, and the
orchestrator reads it.

---

## B9: Local wall-thickness floor in `case_verify.py`

**Covers:** a z_board finding reported 2026-09-20, not a `hexpad/GAPS.md` gap.

A case agent thinned one wall section to 0.35 mm to satisfy a recess target.
Every numeric check passed, because the checks assert clearances and
positions, and nothing asserts a floor on the thinnest local wall.

**Why deferred.** A local minimum-thickness sweep needs geometry queries over
the shell solid (a ray or offset test across the whole surface), which
`case_verify.py`'s registration framework does not expose. It is not a
one-line assertion.

**To close:** add a `min_wall(shell, floor_mm)` check to the framework that
offsets the shell inward by half the floor and asserts the result is still a
single non-empty solid, or samples the surface and measures thickness along
the normal. Set the floor from the printability rules in
`references/mechanical.md` (nozzle diameter times a stated multiple). Until
then the case-engineer's report must state the thinnest wall it produced.

---

## Not in this file

Two things worth stating so they are not mistaken for backlog:

- Every other gap from the dry run is either fixed or explicitly wontfix. Across
  three harvest rounds, gaps 1–94: 90 fixed, three deferred outright
  (3, 6, 11 → B1, B2, B4), and one wontfix (9, works-as-intended). Five of the
  90 (19, 77, 79, 81 and 83) were fixed as doctrine and mechanism, with a
  remainder deferred to B3, B5 or B6. Gap 19 joined that group in this
  workstream: `kicad_fpcheck.py` and `packages.json` are the mechanism; what
  it does not yet cover is B3's own remainder, above. See `hexpad/GAPS.md`
  for the per-gap disposition and `docs/DRYRUN-HEXPAD.md` for the verdict.
- The SWIG (Simplified Wrapper and Interface Generator) → IPC (inter-process
  communication) (`kipy`) migration is roadmap, not backlog. It is forced work
  with a known deadline (SWIG is deprecated in KiCad 9 and removed in 11), it is
  scheduled, and it is tracked in `README.md` and `docs/ARCHITECTURE.md` §6.
