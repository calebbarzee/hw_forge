# Dry run: hexpad — the validation verdict

**Question the dry run had to answer:** can fresh agents, given nothing but this
skill, its references, its scripts and its knowledge base, design a real board
and a real enclosure end to end — and where does the pipeline make them stop and
think about hw_forge instead of about the hardware?

**Verdict: yes, and 60 places** — 49 from the first build, 11 more from a
user-directed revision of the same board. All 60 are logged, all 60 are triaged,
55 are fixed (round 2 is §4a). The board is fabbable and the case is verified;
nothing about the device was hard, which is exactly why it was the right test.

Subject: **hexpad**, a 6-key wireless macro pad — nice!nano v2 on sockets,
nice!view display, per-key SK6812MINI-E RGB, LiPo on a Pico-EZmate, MSK12C02
slide switch, printed two-shell enclosure with M2 heat-set inserts. Deliberately
trivial as hardware; it exercises the whole spine once — direct-wire keys, an SPI
peripheral, a socketed module, a battery, a plate-and-inserts enclosure — at a
scale where a wrong answer costs minutes.

---

## 1. What the dry run proved

**Every phase ran, and every phase's gate was met by machine check, not by
report.**

| # | Phase | Owner | Gate result |
|---|---|---|---|
| 0 | Spec lock | orchestrator + user | `SPEC.md`, locked decisions L1–L9 with a barrier clause |
| 1 | Libraries + research | `resource-scout` | every part resolved; `lib/PROVENANCE.md` per asset; nice!view pin order verified against two independently-authored sources, with the transcription caveat flagged |
| 2 | Logical design | inline | `design.py` imports clean under both interpreters; one table per fact |
| 3 | Schematic | `schematic-engineer` | **ERC 0** on the proto slice on its first run, then **ERC 0** on the full board on its first run; power decision record in `POWER.md` |
| 4 | PCB | `pcb-engineer` | **DRC 0 at error severity with schematic parity, 0 unconnected**, both variants, on the second regeneration; zones filled headlessly inside the generator |
| 5 | Fab outputs | `fab-docs-engineer` | correct 20-file package on the **first** invocation; every profile assertion passed |
| 6 | Enclosure | `case-engineer` | **215 numeric checks, all passing**; two valid closed solids; support-free in the stated orientation |
| 7 | Harvest | this document | 49 gaps triaged, 44 folded back in, gates re-run and still green — then 11 more from rev 2, all fixed (§4a) |

**The numbers, as re-verified by the orchestrator rather than as reported:**

```
kicad_gate.py hexpad/kicad        ERC ok / DRC ok / parity ok / unconnected ok   exit 0
kicad_gate.py hexpad/kicad/proto  ERC ok / DRC ok / parity ok / unconnected ok   exit 0
case_verify.py hexpad/case/checks.py                    all 215 checks passed   exit 0
kicad_fab.py hexpad/kicad --profile fab-hexpad.json     21 files, 461 KiB, ok    exit 0
```

Those are the **rev-1** figures, which is what this section is about; rev 2 is
the same gates on a revised board (§4a), at 239 case checks.

Board: 65.15 × 80.2 mm, 2 layers, 0.2 mm minimum clearance, 12 vias. 33
placements, 12 front / 21 back. 41 PTH holes over 2 tools, 36 NPTH holes over 5
tools, every diameter and count asserted against the profile rather than
eyeballed. 12 BOM lines with an explicit populate column. A 12-file gerber zip.

**The regression fixture held throughout.** z_board — `left`, `right`, `proto`
and the four-layer `combo` — reports ERC 0 / DRC 0 / parity 0 / unconnected 0
before and after every change in this harvest. That is what licenses the script
edits below: they were made against two boards, not one.

**What the pipeline's own doctrine got right, on evidence:**

- **Proto slice first** cost nothing and worked exactly as advertised: a one-key
  slice reached ERC 0 first, and the six-key board then reached ERC 0 on its
  first run.
- **Generate symbol and footprint from one pin table** was applied to every
  project-local part, and `mklib.py` additionally asserts the two vendored pairs
  against the pin tables — so the silent class of bug (a symbol whose numbering
  disagrees with its footprint) could not occur.
- **Read the enclosure's geometry out of the board file** caught real drift: the
  case model derives its outline, its four mount-hole positions and its obstacle
  ledger from the as-built board, and the one place where a spec number and the
  board disagreed, the board won and the report said so.
- **Nudge, don't prove** held: the board went to DRC 0 on its second
  regeneration, and the case suite grew to 215 checks without a single
  geometry dispute settled by hand arithmetic.

---

## 2. Gap statistics

94 gaps, one global sequence (the log's own numbering collision is gap 49 — see
below; the rev-2 and rev-3 entries both appended to the same sequence, which is
that fix working twice). Per-gap dispositions are inline in `hexpad/GAPS.md`.

| Bucket | Count | Meaning |
|---|---|---|
| **FIXED** | 89 | folded into hw_forge, with the landing file named (44 in round 1, 11 in round 2, 34 in round 3) |
| **BACKLOG** | 4 | real, not bounded today — `docs/BACKLOG.md` (gaps 3, 6, 11, 19) |
| **WONTFIX** | 1 | works as intended (gap 9) |

Four of round 3's 34 (#77, #79, #81, #83) count as FIXED because the doctrine
landed, and each left a **script** remainder in `docs/BACKLOG.md` (B5, B6). That
split is deliberate and worth keeping as a category: the rule that stops the bug
recurring is written; the tool that would catch it unaided is not.

By phase, which is the more interesting cut:

| Phase | Gaps | Character |
|---|---|---|
| 1 — research | 9 | almost all **doctrine**: what counts as verification, where assets live, what to do when a source is an image or does not exist |
| 2–3 — schematic | 12 | mixed: one gate that could not pass (10), one missing template (11), two wrong KB facts (14, 15), two reference rules contradicted by reality (18, 20) |
| 4 — PCB | 9 | mostly **what the tooling cannot say**: determinism (23), courtyard-vs-pads (25), a plane's own net (28) |
| 5 — fab | 10 | mostly **what the export cannot assert**: per-side split (31), empty layers (32), provenance (36), plus one verified bug (37) |
| 6 — enclosure | 9 | two outright bugs (41, 42), the rest reference rules with no reading for the case in hand |
| 4/6 rev 2 — revision | 11 | a different character again: two **regression contracts** the pipeline lacked (53, 60), two reference numbers that were simply wrong (56, 58), and the coordinate-frame self-check nothing named (55) |
| 1–6 rev 3 / 3.1 — re-spec | 34 | the character changes once more: one **gate that was decorative** (66), a family of 3D-model gaps that only appear when a case has to consume the board (67–72), an **adoption round trip** the generate-only doctrine had no path for (79–81), and eight case-phase rules with no reading for the case in hand (86–94) |

Two facts worth stating plainly:

- **Not one gap was a design failure.** No phase produced a board or a case that
  was wrong. Every gap is friction, a missing statement, or a tool that could
  not express something true.
- **Three gaps were fixed mid-run by the phases that hit them** (the refdes
  annotation trap into `kicad-api.md`, and two amendments to
  `local-libraries.md`), which is the harvest convention working as designed
  rather than waiting for phase 7.

---

## 3. The highest-value lessons

### A courtyard can be smaller than the part it holds

`references/mechanical.md` §4 said, in bold, that openings are checked against a
part's **courtyard**, not its nominal body. That is right when the courtyard is
the larger of the two — the normal case — and it is exactly backwards for a
socketed module. Measured on hexpad: `MCU_nice_nano_v2`'s courtyard is
**18.28 × 30.98 mm** against a nice!nano v2 body of **17.78 × 33.00 mm**,
because the courtyard was drawn around the 2×12 pad grid. Sizing the display-bay
window on courtyards alone would have left a **1.0 mm lip of plastic reaching
over a module that stands 1.30 mm proud of the plate** — a hard interference
that **every clearance check passes**, because the courtyard said there was
nothing there.

This is the single most valuable catch of the run, for three reasons: the
failure is silent, it is invisible to every gate, and the reference file was
actively pointing the wrong way. The fix is now `courtyard ∪ datasheet body`,
with the relation between the two **asserted** so a later footprint edit that
"fixes" the courtyard cannot silently move the window. Its sibling gap is the
same shape: a hotswap socket is a *front*-face footprint whose hardware lives
entirely **under** the board, so filtering `side == "bottom"` to build an
underside ledger missed every switch cell — reporting a free band of 14.96 mm
where the real figure is 5.52 mm. `kicad_geom.py` now derives `pad_side` and
`protrudes` from where the copper actually is, and says so out loud.

### The tool deleted its own configuration, and the run still said `ok`

`kicad_fab.py` wiped its output directory on every run, so a profile stored
inside that directory was destroyed **by the run that read it**. Verified during
the dry run: `-o out --profile out/p.json` printed `ok 20 files, 460 KiB` and
left no `p.json`. The run *succeeds*; the profile is gone; the **next** run fails
with "no such profile", a long way from the cause. And the toolkit shipped two
different conventions for where a profile lives, one of which was safe only by
accident — a sibling of the output directory, one path component from
self-destruction.

The lesson is not "add a guard" (though it is now a startup error naming the
mechanism). It is that **a destructive default plus two documented conventions
is a trap the documentation itself lays.** One location is now stated everywhere:
`<project_dir>/fab-profile.json`, next to the board it describes.

### Research honesty: "no source has this" is a real outcome

The case phase came back blocked on the one fact phase 1 had already flagged
`needs-verification`: the nice!view's own mounting standoff height. A dedicated
follow-up pass — reading the raw markdown behind the vendor's docs pages, not
just the rendered HTML — established that **there is no official number
anywhere**: the only dimensions on the vendor's own site live inside three PNGs
with zero alt text, which is not a fetch-tool limitation but how the page is
authored. The best available evidence was a third-party accessory's product
description ("7 mm") contradicted by a community wiki paraphrase of what may be
the same product ("5.0 mm").

The doctrine had two outcomes: resolved, or BARRIER — and the barrier clause is
about locked *spec decisions*, which a missing datasheet fact is not. So the
agent had to be told what to do. It is now the documented third outcome
(**UNRESOLVABLE**): hand the next phase a *named, tolerance-banded parameter*
with a recommended default and the disagreement stated plainly, so the design
proceeds parametrically and the number has exactly one place to change when
someone measures a physical unit. The corollary landed too: the conflict-
reporting gate was written for pin tables, and now covers any two-source fact,
with dimensional conflicts named as their own class and their own cost — a case
redesign, not a mis-wired board.

### Two smaller lessons that generalize further than they look

- **A correct design should not have to fail.** `case_verify.py` compared floats
  with a bare `>=`, so an Ø5.60 standoff around an Ø3.20 insert bore — exactly
  the reference's 1.20 mm minimum wall — reported FAIL, because
  `(5.60 - 3.20) / 2 == 1.1999999999999997`. Four of the first run's 208 checks
  failed that way and none were real. The dangerous part is the incentive: the
  obvious way to make the red line green is to loosen the *design* (5.65 mm) or
  the *rule* (1.19 mm), and both are wrong. A gate that punishes a correct
  design teaches people to weaken designs.
- **Assert the number an error cannot change, and you have asserted nothing.**
  The fab profile checked the placement *total* — 33 — which is the one number a
  flip-sign error leaves untouched: flip a part to the wrong face and hexpad
  still has 33 placements, just 11/22 instead of 12/21. The per-side split is now
  assertable, and the negative case is exercised in this harvest's regression
  run.

---

## 4. What changed in hw_forge

**Scripts** — one new, seven edited:

| Script | Change |
|---|---|
| `kicad_digest.py` | **new.** Canonical KIID-free board digest, promoted and generalized from the project's own `pcbdigest.py`: `--compare`, `--expect`, `--json`. A generated board is not byte-stable and cannot be (5744 of 10488 lines differ between two runs of an unchanged generator), so this is the only honest form of "regeneration is deterministic". |
| `kicad_gate.py` | `--sch-only`, plus auto-detection of a board-less project: DRC prints `SKIPPED` and an explicit `PARTIAL` verdict, exit 0. The phase-3 gate can now pass in the phase that names it. `--require-board` keeps the hard failure where a board must exist. |
| `kicad_fab.py` | per-side placement assertions; `expect_empty_layers` counted in `%AD` apertures rather than bytes; BOM header written as prose instead of ragged CSV; a **Side** column that names the front-face/back-copper disagreement; a `-manifest.txt` stamping board hash, tool versions, assertion results and the gate verdict found beside the project (flagged STALE when older than the board); and a startup refusal when the profile resolves inside the output directory. |
| `kicad_geom.py` | reports `courtyard` and `pads_bbox` per footprint (rotation-resolved, board coords), plus `pad_side` / `through_hole` / `protrudes` — the hardware fact, as opposed to `side`, which is only the placement fact. Prints a "placed on one face, all copper on the other" report and a no-courtyard summary. |
| `case_verify.py` | `TOL = 1e-6` on every comparison, with `tol=0` as the exact-mode opt-out; docstring now states which python to run it under and the one-suite/two-entry-points pattern. |
| `kicad_scaffold.py` | `save_overrides()` persists the whole scaffolded rule set, not only what arrived on the command line — the one-word fix that stops every project restating hw_forge's own defaults to survive `SaveBoard()`. |
| `_kicad_env.py` | the shared stderr filter drops `Fontconfig` noise as well as wx noise. Not cosmetic: callers report the *last* stderr line as the failure reason. |
| `preflight.py` | unchanged; it discovers the new script and reports 11 compiling. |

**Templates** — `Makefile` substantially rewritten (a `PROTO` notion gated first
and excluded from `fab`; per-target `<t>_DIR` with `.` for a single board at the
project root; an `erc` target; `fab: check`; a `determinism` target; a plugin-or-
checkout default for `HW_FORGE`; noise filtering on direct `kicad-cli` calls),
and a new `templates/.gitignore` carrying the commit-vs-ignore convention.

**References** — `electronics.md` §3 (the judgement rule when a *gated*
reference design omits the series resistor), §10.3 (rewritten: a plane's own net
may depend on its fill; the trap is a net whose pads sit outside their own
pour), §10.5 (a proto slice needs `PWR_FLAG`s); `mechanical.md` §4
(courtyard ∪ body), §6 (the bounded-recess third option), §7.7 (off-axis
renders); `batteries.md` §7 (plan constraint from full-height obstacles,
vertical constraint separately); `kicad-api.md` §4 (the KIID/determinism fact,
and the enumeration discipline for demoting a DRC rule).

**Process layer** — `SKILL.md` gains a stated project layout, the
legitimately-round-tripping geometry classes, and gap-log numbering authority;
`resource-scout.md` gains the UNRESOLVABLE outcome, the evidence-tier rule, the
image-primary fallback and the evidence/production directory split;
`fab-docs-engineer.md` gets two phase-keyed report templates and the ignore
convention at phase 5; `case-engineer.md` gets the checks-file pattern and the
CAD-python rule; `pcb-engineer.md` gets the `design.py` carve-out;
`schematic-engineer.md` gets the `--sch-only` gate; `hw-export.md` gets the
profile location, the gate-slice exception and the new assertions;
`hw-research.md` gets one provenance filename.

**Knowledge base** — `kb/README.md` gains four conventions (scoped negatives,
port-first pin-role facts, the UNSURE-is-a-harvest-trigger rule, and gap-log
numbering); `nice-nano-v2.md` has a wrong NFC-pin claim corrected in place and
gains the module's default peripheral pinmux table, enumerated once from the ZMK
firmware tree; `zmk-electrical.md` points at it; `nice-view-display.md`'s
phase-1 checklist item is re-scoped to the phase that can finish it.

---

## 4a. Addendum — rev 2, and what a REVISION tests that a build does not

After the first harvest the board was revised on user direction: the nice!nano
and nice!view **rotated 90°** onto the east edge, the MSK12C02 nested between
the module's pad rows, the board shrunk in y to **65.15 × 64.575 mm**, and the
case rebuilt against it. All gates green again — ERC 0 / DRC 0 with parity / 0
unconnected on both variants, an asserted fab package, and the case suite at
**239 checks, all passing** (up from 215). The rebuild took one regeneration
plus two fixes, both in check *expressions* rather than in geometry.

It logged **11 more gaps (#50–60), all bounded, all fixed.** What makes the
round worth its own section is that a revision exercises a different part of the
pipeline than a build does: not "can this be designed", but "can a change be
trusted".

**Headline lesson one — a rotation sign, caught by an asymmetric part.** The
PCB phase's handoff table put the MSK12C02's slider knob at y 8.14…9.54. The
board says **y 9.790…11.090** — the handoff value mirrored about the part centre,
9.640: a rotation-sign error on a −90° part. It is invisible on the switch's
y-symmetric *body*, which the same table got right to ±0.05, and shows only on
the asymmetric slider lobe. Centring the slot on the handoff number would have
put **2.0 mm of wall squarely on top of the actuator** — a part that passes every
clearance check and cannot be switched on.

What caught it was a trick nothing told anyone to use: **place a
known-asymmetric feature through your own frame helper and assert it reproduces
`kicad_geom`'s reported `pads_bbox` for that part.** One assertion proves
origin, mirror and rotation sign together. Two things follow, and both are now
doctrine: a case suite must *assert* every handoff number it consumes, so a
stale table fails a check instead of steering a cut; and handoff numbers should
not be typed at all, which is why `kicad_geom.py` now exports `body_bbox` and
`fab_items`. The tool prints the disputed number directly — three B.Fab lines at
y 9.79…11.09. The lesson generalizes past geometry: `kicad_geom.py`'s docstring
already warned that a rotation-sign error "is invisible on 0 and 180 degree
parts and silently wrong on every 90/270 part", and the warning still nearly
cost a part, **because the warning lived in a script's docstring and the error
lived in a human table.**

**Headline lesson two — H4, and one rule that two shells resolve differently.**
Rev 2's fourth mounting hole sits 2.275 mm from the east edge; a Ø5.60 seat
needs 2.800. `mechanical.md` §3's "every seat fully lands on the board" was
simply unsatisfiable — and the obvious fix silently broke a *different* rule:
the largest round post that fits (Ø4.55) leaves 0.675 mm of wall around the M2
insert against §1's 1.20 mm minimum, and that insert bursts out sideways on
installation. Two references in direct conflict at one hole, with nothing
ranking them.

The resolution is a real pattern, and it is **different on each shell**, which
is why no single rule covered it. On the shell that *owns* the wall: keep full
OD and **merge the seat into the wall** with a gusset — the material goes
outward, and H4's bore ends up with 3.475 mm to the wall's outer face, so the
constraint that was short becomes the one with the most margin. On the shell that
does not, there is nothing to merge into, so **clip every boss to the cavity**
inset by the lid gap and let the one that needs it come out D-shaped — asserting
the flat on the *solid*, not from the parameters. §3 now ranks §1 above itself
and carries the tree, and the general rule (every lid boss clipped to the mating
shell's cavity) is stated on its own, because without it a Ø5.60 boss interferes
by 0.375 mm and **nothing else in a suite notices** — every per-feature check is
about components, and a boss is not a component.

**Two more worth keeping.** A reference's own numbers can be wrong: §1's
capacity-plausibility band (0.10–0.12 mAh/mm³) contradicted **5 of §2's own 11
catalogue rows**, all of them the small cells whose behaviour §1 describes in
prose and then excludes numerically — so a project that turned the sentence into
an assertion, as the doctrine tells it to, got a false failure. And one ambiguous
noun was worth 500 mAh: §7's "bay rectangle" meant the rib fence in one reading
and the cell pocket in the other, and on a 15.6 mm shorter board that decided
between a 1000 mAh cell and a 500 mAh one.

**What a revision needs that a build does not: regression contracts.** Two of
the eleven gaps were the same shape at opposite ends of the pipeline — nothing
compared a rev's *warnings* against the previous rev's, and nothing could tell a
legitimately retired check from a quietly deleted one. Rev 2's first green build
carried warning classes rev 1 did not have, and rev 2 retired one real check
(rev 1's tightest number, 0.00 mm at its assumption band's floor) for an
entirely correct reason: the display moved 7 mm west and the clearance became
geometrically moot. Both are indistinguishable from the outside from something
going wrong. Now: `report.py --by-owner --baseline --strict` for finding classes,
`case_verify.py --dump-names / --baseline / --strict-baseline` for check sets, a
`make warnings` target, and a required `Retired:` line in the case agent's
report. The durable principle: **a retirement with a stated reason is knowledge;
a retirement with a smaller number is a regression nobody can see.**

**Round-2 score.** 11 gaps, 11 fixed — five into tooling (`kicad_scaffold.py`
`--repatch` merging new overrides instead of silently ignoring them,
`kicad_geom.py` body/Fab export plus JSON-key naming, `report.py --by-owner` and
`--baseline`, `case_verify.py --dump-names` and `--baseline`, a `make warnings`
target), six into references and agent files. And two round-1 gaps closed
*inside* rev 2, both paying for themselves immediately: the underside ledger is
now derived from `protrudes` (29 refs, where rev 1 hand-enumerated the same list
under 20 lines of comment explaining why the footprint's `side` lies), and the
courtyard-versus-body assertion is what sized rev 2's 43.85 mm display window.

---

## 4b. Addendum — rev 3 / 3.1: a re-spec, a decorative gate, and a hand edit

The user revised the spec again after reviewing rev 2, and this round is
materially different from the last two: not a build, and not a geometric
revision, but a **change of requirements** followed by **a person opening
pcbnew and dragging four parts.** Direct-pin scan became a COL2ROW diode matrix,
a rotary encoder was added, every footprint had to link a 3D model, the display
header moved west of the MCU pins, and the mounting holes were constrained to
the four board corners. Then rev 3.1 adopted hand placements — two of them onto
the other board face.

**34 more gaps (#61–94), all 34 addressed.** All gates green again on both
variants, the case suite at **416 checks, all passing**. What the round bought,
in order of value:

### The gate was decorative, and had been in both fixtures all along

The single most valuable finding of the whole dry run, and it is a *process*
finding rather than a design one. `--schematic-parity` was in the gate script, in
`references/kicad-api.md`, in `references/electronics.md` §10.2, in `SKILL.md`'s
phase-4 exit contract, and in `kicad_gate.py`'s own docstring — which stated, in
so many words, that the flag "is not optional: without it the DRC passes on a
board whose netlist has drifted from the schematic". Five places agreed. And the
check could not fail a build, because **KiCad ships all five parity checks at
`warning` severity and the gate filters on `--severity-error`.**

Measured mid-revision, with a rev-3 schematic and the rev-2 board still on disk:

```
kicad_gate.py kicad          ->  ERC ok   DRC ok   parity ok   unconnected ok   (exit 0)
same board, --severity-all   ->  31 schematic parity issues
                                 21 net_conflict, 8 missing_footprint, 2 footprint_symbol_mismatch
```

A green gate on a board missing eight parts and mis-wiring twenty-one nets.

The fix is three-layered, because one layer would not have been enough:
`kicad_scaffold.py` writes the five promotions as **defaults** (they are the
pipeline's contract with itself, not a fab capability limit); `kicad_gate.py`
**asserts the promotion before trusting a parity pass**, printing `parity
enforced at error severity (5/5)` or `parity UNENFORCED …` with the fix command,
and failing under `--strict-parity`; and the references stop implying the flag is
sufficient. A project that wants one relaxed demotes it explicitly and gets a
loud warning for doing so.

**Then the older fixture was audited, and the finding got worse.** z_board shares
the scaffolder, and every one of its four boards had all five parity rules
explicitly at `warning`, no overrides sidecar anywhere in the repo, and committed
`drc.json` artifacts recording `"included_severities": ["error"]` beside
`"schematic_parity": []` — the section was structurally unreachable. Re-run at
promoted severity: left, right and combo pass; **proto fails with two
`missing_footprint`.** A decoupling cap and an LED current-limit resistor are in
that slice's schematic and were never placed on its board. The gate had reported
it clean for its entire life.

The durable lesson generalises past KiCad: **a check whose severity is below the
severity you filter on is not a check.** Any gate built on a filtered report owes
an assertion that the thing it claims to check is inside the filter.

### The hand edit is a first-class workflow, not a mistake

`gen_pcb.py`'s docstring says, correctly and in capitals, never to hand-edit the
`.kicad_pcb`. The whole pipeline rests on that. But the user did — dragged four
footprints and tried to re-route — and **that is not a mistake, it is the normal
way a person expresses "put the encoder over here."** A generate-only doctrine
with no defined re-entry path just means the re-entry gets improvised.

So it is defined now (`agents/pcb-engineer.md`), and the tooling supports it:
`kicad_geom.py --diff OLD NEW` reports per-ref Δx/Δy/Δrot/**Δside**,
`--as-constants` prints the moved set as a pasteable dict, and `--strict` exits
nonzero on any difference. The procedure is back up → extract → adopt →
regenerate (discarding the hand routing) → **`--diff --strict` the backup against
the regenerated board.** That last step is the one that makes the whole thing
safe, because a board generated from the wrong adopted coordinate is perfectly
clean and no gate can see the transcription error.

Two facts had to be stated that nothing had stated: **a hand placement is an
`(x, y, rot, layer)` tuple and all four are the spec** (a part returning at
`rot 180` cost two vias by reversing which pad faced its departing net; two parts
returning on the other *face* orphaned their ground pads and needed stitch vias),
and **a keepout derived from a component bound is invalidated by that component
leaving.** The protrude-below set went 37 → 35 refs, those two were the parts
bounding the battery bay, the bay grew ~68 % in plan area, and every remaining
assertion stayed green. A stale ledger that is merely *conservative* is the
failure mode nobody looks for.

### Prose outlived its board, and the regression-note convention

Two gaps here share one shape: the pipeline gates *artifacts* and nothing gates
*claims*. A 284-line as-built assembly document, entirely correct for rev 2,
became actively wrong the instant the scan matrix changed — no diodes in its
populate list, a stale drill census, and a firmware section whose
`kscan-gpio-direct` map would have been copied straight into a real overlay. It
was caught by someone happening to read it for an unrelated number. Now
`kicad_digest.py --stamp DOC BOARD` verifies a `board-digest:` line against the
board's canonical digest, and re-stamping is the explicit act of saying "I have
re-read this."

The other is the **REGRESSION note**, a third outcome beside BARRIER and the
deviation report. Two locked decisions were each satisfiable and jointly cost a
property the *previous* revision had won: the display body came back over the
USB-C receptacle in plan, reintroducing a z clearance rev 2 had eliminated. No
gate objected, nothing was bent, and there was no channel for "this got worse in
a way nobody chose" except prose in a final report. The note names what was lost,
which decisions' interaction lost it, the number, and what it would cost to get
back — and the orchestrator must write it into `SPEC.md` and amend the KB card
that recorded the win.

### Round-3 score

34 gaps, 34 addressed. Eight landed in scripts — parity promotion
(`kicad_scaffold.py`), parity assertion (`kicad_gate.py`), obstacle rects /
designator parsing / the placement diff (`kicad_geom.py`), suite-name
normalisation, winner-free check identities and `interferes()` /`gap()`
(`case_verify.py`), the `process change` finding (`kicad_fab.py`), document
stamping (`kicad_digest.py`), model-link resolution (`preflight.py`), and the
rotating warnings baseline (`templates/Makefile`). The rest landed in references,
agent role docs and the KB conventions. Four left a script remainder in
`docs/BACKLOG.md` (B5: a zone-flooding pour checker wanted by three separate
gaps; B6: writing adopted placements back into a generator).

**Three earlier gaps closed and paid off inside this round**, which is now a
pattern rather than a coincidence: `protrudes` (#25/#41) made the underside
ledger derived, and rev 3.1 proved a derived ledger still needs a *set* diff
(#84); the courtyard-vs-body assertion (#45) sized rev 2's display window, and
rev 3 found the opposite failure where a pad row inflates a courtyard (#75); and
the revision regression contract (#53/#60) turned out to need three separate
mechanisms, one of which (#86) was quietly broken by the obvious suite-naming
convention until this round measured it — `416 added, 239 retired` where the
true answer was `233 added, 59 retired`.

---

## 5. What the dry run did not test

Stated so nobody reads more into the verdict than it earns:

- **Nothing was fabbed or printed.** Every claim here is `verified-in-cad`: a
  passing gate, an asserted export, a numeric `verify()` pass. The first
  physical build will find things no gate can (the MSK12C02 stock footprint's
  pad pitch — backlog B3 — is the known candidate).
- **One domain, one toolchain, one machine.** Keyboards, KiCad 10.0.5, macOS,
  build123d. The scripts' platform discovery is exercised only on darwin.
- **No mirrored variant and no four-layer board** in this run; those paths are
  covered by the z_board fixture instead.
- **Firmware was out of scope.** The design records its pin map and its
  devicetree implications; nothing was flashed.
- **The orchestrator was not itself a fresh agent** in every phase. Phase-to-
  phase handoffs were real, but a fully cold end-to-end run — one session, no
  human relay — remains untested.
