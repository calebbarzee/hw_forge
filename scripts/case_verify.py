#!/usr/bin/env python3
"""Numeric interference/stack-up checks for an enclosure, as a gate.

The enclosure phase's exit gate.  Geometry disputes are settled by running
numbers: every check prints the value it got and the value it needed, so a
failure tells you which named constant to nudge and by how much.

    python3 scripts/case_verify.py case/checks.py
    python3 scripts/case_verify.py case/checks.py --suite left --json
    python3 scripts/case_verify.py case/checks.py --contract build/fit.json

Run this with the python your computer-aided design (CAD) library lives in.
This module is pure stdlib, so it runs under any interpreter.  But a real
enclosure suite has to assert that solids are valid and that nothing stands
proud of the print reference face, and neither is expressible without building
the geometry.

Under a system `python3` with no build123d those checks either vanish, leaving
a silently ungated phase, or the checks file dies on import.  A project venv is
the normal answer:

    case/.venv/bin/python scripts/case_verify.py case/checks.py

Register the CAD import itself as a check, carrying its own fix command, so a
missing dependency reports as one failing check instead of thirty missing ones.

One suite, two entry points.  The generator wants a numeric pass that runs on
every invocation before export; this script wants a file exposing `checks(v)`.
Write them once: the generator owns the `checks(v)`-shaped function against
this `Suite` interface, the checks file is a three-line re-export of it, and
the generator's `__main__` imports `case_verify.Suite` and runs the same
function before exporting.  Two suites drift; this cannot.

    # case/checks.py
    from mycase import run_checks as checks     # noqa: F401

Write the checks file against this module's `Suite`.  It must define
`checks(v)`; anything else in the file is yours.  Derive the numbers from the
board file (see kicad_geom.py) rather than retyping them, so the case cannot
drift from the PCB it has to fit:

    import sys
    sys.path.insert(0, "scripts")
    import kicad_geom

    PCB_THK = 1.60
    KEEPOUT = 0.30          # named constants: the nudge loop edits these
    BOSS_OD = 5.60

    def checks(v):
        board = kicad_geom.read_board("build/left/board.kicad_pcb")
        x0, y0, x1, y1 = board["outline"]["bbox"]
        cavity = v.rect("cavity", x0, y0, x1, y1)

        v.section("fasteners")
        for hole in board["holes"]:
            if hole["plated"] or abs(hole["diameter"] - 2.2) > 0.01:
                continue
            boss = v.circle("boss @%(x)g,%(y)g" % hole, hole["x"], hole["y"],
                            d=BOSS_OD)
            v.inside(boss, cavity)
            for fp in board["footprints"]:
                if fp["side"] != "bottom":
                    continue
                part = v.rect(fp["ref"], fp["x"] - 3, fp["y"] - 3,
                              fp["x"] + 3, fp["y"] + 3)
                v.clearance(boss, part, KEEPOUT)

        v.section("stack-up")
        # floor - counterbore + cavity + pcb + thread engagement
        v.stack("M2 screw length", {"floor": 2.6, "counterbore": -2.1,
                                    "cavity": 3.4, "pcb": PCB_THK,
                                    "engagement": 4.0}, at_most=8.0)

Coordinates are yours to choose, but pick one frame and say so in a comment.
Board files are x east / y south; most CAD frames want y north.  Mixing them is
the classic way to get a case that verifies clean and prints mirrored.

The revision contract.  When a case is rebuilt against a revised board, the
check set is as much an artifact as the check result, and a shrinking suite is
invisible from the outside:

    python3 scripts/case_verify.py checks.py --dump-names rev1-names.json
    ... revise the board, rebuild the case ...
    python3 scripts/case_verify.py checks.py --baseline rev1-names.json

The suite name is part of a check's identity, so it must never carry a
revision, a date, or a board hash.  `compare_names()` keys identity on
`(suite, name)`, so calling a suite `mycase (board rev 2)` retires the entire
baseline the moment the revision number changes.  Naming it that way is the
obvious thing to do, since the suite is verifying that board.

Measured: `416 check(s) now, 239 in the baseline: 416 added, 239 retired`, not
one of them for a geometric reason.  `--strict-baseline` in CI would have
failed the run with 239 unexplainable retirements and no way to tell which one
mattered.  Normalising the suite name recovered the real answer: 233 added, 59
retired.  Put the revision in a `v.section()` or in a check message, where
`name_of()` blanks the number anyway.

This script now defends itself against that.  A trailing `(rev N)` /
`(board rev N)` is stripped from both sides before comparing, `--map-suite
OLD=NEW` renames one explicitly, and a comparison whose suite-name sets are
disjoint while every baseline check retires is reported as the rename it is,
then retried blind to suite names, because that answer is nearly always the one
you wanted.

reports `added / retired / newly-failing / fixed`.  Retiring a check is often
correct.  A measured case: rev 1's tightest number was "display underside
clears the USB-C shell top" at 0.70 mm, and 0.00 mm at the assumption band's
floor; rev 2 moved the display 7 mm west so the two no longer overlap in plan
and the z clearance became geometrically moot, replaced by a plan check.

That is a design improvement, and from outside it is indistinguishable from
quietly dropping the check that was hardest to pass.  So a retirement with a
stated reason is knowledge, while a retirement with a smaller number is a
regression nobody can see.  `--strict-baseline` fails the run when a check
disappears, for the CI case where nothing should retire without a human saying
why.

The check count is never a target.  Re-derive it; do not force the previous
number.

Contract-driven checks
----------------------
Five checks read the board's fit contract (`kicad_geom.py BOARD --contract
FIT.json --design design.py`) instead of numbers a case file retyped:

    fit = v.contract("build/fit.json")      # or --contract FIT.json, below
    v.board_in_cavity(fit, shells=[top, bottom], frame=to_case)
    v.cavity_clearance(fit, shells=[top, bottom], frame=to_case,
                       exempt={"SW1": "plate-mounted switch, see §plate"})
    v.connector_openings(fit, shells=[top, bottom], frame=to_case)
    v.min_wall(top, name="top shell")
    v.fastener_stackup("M2 screw", screw_len=14, floor_thk=2.6,
                       counterbore=2.1, cavity=8.0, bore_depth=4.4,
                       contract=fit)

`frame(x, y, z) -> (X, Y, Z)` maps the contract's board frame (x east, y
south, z up, z = 0 on the top face) into the case model's frame: the one
named helper `references/mechanical.md` §7 item 4 asks for.  With `shells`
and `frame` the checks build boxes and probes in build123d and intersect them
with the real shells.  Without them, three of the checks take numbers in
board coordinates instead (`cavity=v.rect(...)`, `floor_z=`, `ceiling_z=`,
`openings={...}`), which is weaker, because those numbers are the case's own.

  board_in_cavity     the outline polygon, grown by `margin`, meets no
                      plastic in the board's own z slab (mounting holes and
                      cutouts excepted).
  cavity_clearance    every part's plan obstacle and z band, grown by
                      `margin`, meets no plastic.  A part is a box here: plan
                      bbox times z band.  A part whose plan changes with
                      height (an encoder shaft through a deck) is coarser than
                      a box can say; exempt it with the reason, and the
                      exemption is itself a recorded line.
  connector_openings  for every external mating face in the contract, a probe
                      from the part's leading face out through its wall, as
                      wide as its body plus `margin`, meets no plastic and ends
                      outside the case.  An opening on the wrong wall fails,
                      because the probe then runs into the right one.  A
                      connector with no mating record fails: an opening that
                      was never declared cannot be checked.
  min_wall            the thinnest local wall of one solid, by casting a ray
                      inward from sample points on every face, holds a floor
                      (MIN_WALL_MM, references/mechanical.md §5).  Samples sit
                      about `spacing` mm apart, capped at 64 per face axis.
  fastener_stackup    references/mechanical.md §2 as one assertion, with the
                      board thickness read from the contract.

A missing build123d is one failing check carrying its fix, never thirty
missing ones, and the module still imports without it.
"""

import argparse
import collections
import json
import math
import os
import re
import sys

# The checks file is imported from the user's own tree; do not leave a
# __pycache__ directory in their project as a side effect of verifying it.
sys.dont_write_bytecode = True

# Every comparison carries this slack, and it is not cosmetic.  A good design
# lands exactly on its own minimum: an Ø5.60 standoff around an Ø3.20 insert
# bore is the reference's 1.20 mm minimum wall, and in binary floating point
# `(5.60 - 3.20) / 2 == 1.1999999999999997`, so a bare `>=` fails the correct
# design.
#
# The incentive that creates is the dangerous part: the obvious way to make the
# red line green is to loosen the design (5.65 mm standoff) or the rule
# (1.19 mm), and both are wrong.  1 nm of slack is far below any manufacturable
# tolerance and removes the whole class of false failure.
# Pass `tol=0` on a check that must be exact to the bit.
TOL = 1e-6

# Contract-driven check defaults, each with its source.
FIT_MARGIN = 0.30      # mechanical.md §5 tolerance table: board-to-cavity
                       # clearance per side, and the component keepout
MIN_WALL_MM = 0.80     # mechanical.md §4a/§5: two extrusion widths at a
                       # 0.4 mm nozzle, the ligament and recessed-panel floor
PROBE_REACH = 15.0     # how far past a wall an opening probe runs; more than
                       # any wall mechanical.md §5 recommends (2.0 to 2.5 mm)
ENGAGEMENT_MIN = 2.5   # mechanical.md §2: M2-class band floor into an insert
SHOULDER_MIN = 0.45    # mechanical.md §2: floor left under a screw head
CORNER_RELIEF = 1.00   # mechanical.md §5: a cavity fillet of about 1.0 mm
                       # meets a square board corner, so the side margin
                       # starts this far from each outline vertex
CONTACT_VOLUME = 1e-3  # mm^3 of overlap below which two solids only touch


def load_contract(source):
    """A fit contract from a path, an already-loaded dict, or None."""
    if source is None or isinstance(source, dict):
        return source
    with open(source) as fh:
        return json.load(fh)


def _b3d():
    """The build123d module, or None.  Imported lazily: see the docstring."""
    try:
        import build123d
        return build123d
    except Exception:                                  # pragma: no cover
        return None


# ------------------------------------------------------------------- shapes

class Shape(object):
    """A named 2D obstacle: an axis-aligned box plus a radius.

    One representation covers all three cases the checks need.  A rect is a
    box with radius 0; a circle is a degenerate box (its centre) with a real
    radius; a point is both.  Distance between any two shapes is then the
    box-to-box distance minus both radii, which is exactly right for
    rect-rect, circle-rect and circle-circle.
    """

    def __init__(self, name, x0, y0, x1, y1, radius=0.0, kind="rect"):
        self.name = name
        self.x0, self.y0 = min(x0, x1), min(y0, y1)
        self.x1, self.y1 = max(x0, x1), max(y0, y1)
        self.radius = radius
        self.kind = kind

    @property
    def centre(self):
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def __repr__(self):
        return "<%s %s>" % (self.kind, self.name)


_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def name_of(message):
    """A check's stable identity: its message with every number blanked."""
    return _NUMBER.sub("#", message).strip()


def box_distance(a, b):
    """Distance between two axis-aligned boxes; 0 if they touch or overlap."""
    dx = max(a.x0 - b.x1, b.x0 - a.x1, 0.0)
    dy = max(a.y0 - b.y1, b.y0 - a.y1, 0.0)
    return math.hypot(dx, dy)


def gap(a, b):
    """Signed clear distance between two shapes; negative = they interfere.

    Separated in at least one axis, this is the box-to-box distance less both
    radii, which is exactly right for rect-rect, circle-rect and circle-circle.

    Overlapping in both axes, a clamped box distance is 0 and the whole answer
    disappears: every interference reads as "0.000 mm", so a shape 5 mm inside
    another is indistinguishable from one just touching it.

    So the overlapping case returns the penetration depth, the shallowest
    translation that would separate them, as a negative number.  That is what
    lets an interference be asserted (`Suite.interferes`) rather than only
    avoided, which is what a rejected design alternative needs.

    Clearance checks are unaffected: they compare against a non-negative
    minimum, so a pair that was failing still fails, with a number that now
    says how badly.
    """
    dx = max(a.x0 - b.x1, b.x0 - a.x1)
    dy = max(a.y0 - b.y1, b.y0 - a.y1)
    if dx >= 0.0 or dy >= 0.0:
        return box_distance(a, b) - a.radius - b.radius
    return max(dx, dy) - a.radius - b.radius


# -------------------------------------------------------------------- suite

class Suite(object):
    """Collects checks and their numbers. One instance per `checks(v)` call."""

    def __init__(self, name="", loud=True, only=None):
        self.name = name
        self.loud = loud
        self.only = only
        self.results = []            # (suite, section, ok, message, name)
        self.contract_path = None    # set by --contract; read by contract()
        self._section = ""
        self._suite = name
        self._skipping = bool(only) and bool(name) and name != only

    # -- structure --------------------------------------------------------

    def suite(self, name):
        """Start a named suite, e.g. one per variant. Honours --suite."""
        self._suite = name
        self._skipping = bool(self.only) and name != self.only
        if self.loud and not self._skipping:
            print("=== %s ===" % name)
        return self

    def section(self, title):
        self._section = title
        if self.loud and not self._skipping:
            print("--- %s ---" % title)

    # -- shape constructors ----------------------------------------------

    def rect(self, name, x0, y0, x1, y1):
        return Shape(name, x0, y0, x1, y1)

    def circle(self, name, cx, cy, d=None, r=None):
        if d is None and r is None:
            raise ValueError("circle(%r) needs d= or r=" % name)
        radius = r if r is not None else d / 2.0
        return Shape(name, cx, cy, cx, cy, radius, "circle")

    def point(self, name, x, y):
        return Shape(name, x, y, x, y, 0.0, "point")

    # -- the checks -------------------------------------------------------

    def check(self, ok, message, name=None):
        """Record one result. Every other method funnels through here.

        `name` is the check's stable identity for baseline comparison; when it
        is not given it is derived by replacing every number in the message
        with `#`.  That is the right split: the numbers are the volatile part
        and the words are what the check asserts, so a check whose value moved
        keeps its identity and a check that was replaced does not.
        """
        if self._skipping:
            return bool(ok)
        self.results.append((self._suite, self._section, bool(ok), message,
                             name or name_of(message)))
        if self.loud:
            print("  %s %s" % ("ok  " if ok else "FAIL", message))
        return bool(ok)

    def clearance(self, a, b, minimum, tol=TOL, name=None):
        """`a` must stand at least `minimum` mm clear of `b`.

        Pass `name=` where `b` is chosen dynamically (the nearest of a set, the
        tallest part over a region): otherwise `b`'s ref lands in the check's
        identity and the check retires the moment a different part wins.
        """
        got = gap(a, b)
        return self.check(got >= minimum - tol,
                          "%s to %s: %.3fmm (need %.3f)"
                          % (a.name, b.name, got, minimum), name)

    def nearest(self, a, others, minimum, tol=TOL, name=None):
        """Clearance to the closest of many obstacles: one line, not N.

        This is what keeps a check run readable when a part must clear every
        footprint on a face: the failure names the offender.

        The offender goes in the message, never in the identity.  The winning
        obstacle is the check's answer, and an identity coupled to its own
        answer retires whenever the answer changes.  "H4's boss clears every
        part on the underside" was never removed, weakened or even edited, and
        four of one revision's 48 retirements were nothing but a different part
        becoming the nearest one.  So the derived name counts the obstacles and
        omits the winner.
        """
        stable = name or name_of("%s to nearest of %d obstacles"
                                 % (a.name, len(others)))
        if not others:
            # Same identity as the populated case, deliberately: a part whose
            # obstacle set emptied has not retired its check, it has passed it.
            return self.check(True, "%s: no obstacles to clear" % a.name,
                              stable)
        worst = min(((gap(a, b), b.name) for b in others))
        return self.check(worst[0] >= minimum - tol,
                          "%s to nearest of %d (%s): %.3fmm (need %.3f)"
                          % (a.name, len(others), worst[1], worst[0], minimum),
                          stable)

    def interferes(self, a, b, at_least=0.0, tol=TOL, name=None):
        """`a` and `b` must overlap, by at least `at_least` mm of depth.

        The mirror of `clearance()`, and the only assertion shape a rejected
        alternative can use.  A role doc that asks for "what you modelled and
        dropped, with the reason" gets a far stronger artifact when the reason
        is an assertion, because then the rejection cannot be quietly
        un-rejected by a later revision.  (Cite: folding a connector notch into
        a deck rectangle eats 0.475 mm of a fastener seat, asserted as an
        interference so nobody can "fix" the rectangle back.)

        Without this, a generator had to reach into this module's internals for
        a private `gap()` to say the one thing its role doc asked for.
        """
        depth = -gap(a, b)
        return self.check(depth >= at_least - tol,
                          "%s interferes with %s: %.3fmm deep (need >= %.3f)"
                          % (a.name, b.name, depth, at_least), name)

    def gap(self, a, b):
        """Signed clear distance between two shapes; negative = interfering.

        Exported on the Suite so a generator can compute a clearance without
        importing module internals.  Asserting on it is `clearance()` or
        `interferes()`, but a derived number (a bay edge, a slot width) often
        needs the raw value.
        """
        return gap(a, b)

    def inside(self, part, region, margin=0.0, tol=TOL):
        """`part` must sit wholly inside `region`, with `margin` to spare."""
        slack = min(part.x0 - part.radius - (region.x0 + margin),
                    part.y0 - part.radius - (region.y0 + margin),
                    (region.x1 - margin) - (part.x1 + part.radius),
                    (region.y1 - margin) - (part.y1 + part.radius))
        return self.check(slack >= -tol,
                          "%s inside %s: %.3fmm to spare%s"
                          % (part.name, region.name, slack,
                             "" if not margin else " (margin %.3f)" % margin))

    def outside(self, part, region, margin=0.0, tol=TOL):
        """`part` must not overlap `region` (a keepout, bay or cutout)."""
        got = gap(part, region)
        return self.check(got >= margin - tol,
                          "%s clear of %s: %.3fmm (need %.3f)"
                          % (part.name, region.name, got, margin))

    def equals(self, name, got, want, tol=TOL):
        return self.check(abs(got - want) <= tol,
                          "%s = %.4f (want %.4f +/- %g)" % (name, got, want, tol))

    def at_least(self, name, got, floor, tol=TOL):
        return self.check(got >= floor - tol,
                          "%s = %.4f (need >= %.4f)" % (name, got, floor))

    def at_most(self, name, got, ceiling, tol=TOL):
        return self.check(got <= ceiling + tol,
                          "%s = %.4f (need <= %.4f)" % (name, got, ceiling))

    def between(self, name, got, low, high, tol=TOL):
        return self.check(low - tol <= got <= high + tol,
                          "%s = %.4f (need %.4f..%.4f)" % (name, got, low, high))

    def stack(self, name, terms, at_least=None, at_most=None, equals=None,
              tol=TOL):
        """Sum a named stack-up and assert its total.

        `terms` is {label: mm}; negative terms subtract.  The printed line
        carries the whole sum, because a stack-up that fails is nearly always
        one term nobody wrote down.  The screw that needed to be 14mm rather
        than 8mm shows up here as the arithmetic, not as a surprise at
        assembly.
        """
        total = sum(terms.values())
        detail = " + ".join("%s %.2f" % (k, v)
                            for k, v in sorted(terms.items()))
        ok, bounds = True, []
        if equals is not None:
            ok = ok and abs(total - equals) <= tol
            bounds.append("== %.3f" % equals)
        if at_least is not None:
            ok = ok and total >= at_least - tol
            bounds.append(">= %.3f" % at_least)
        if at_most is not None:
            ok = ok and total <= at_most + tol
            bounds.append("<= %.3f" % at_most)
        # A stack-up with no bound asserts nothing. Fail it rather than let a
        # gate report a green check that tested nothing.
        return self.check(ok and bool(bounds),
                          "%s = %.3f  [%s]  (need %s)"
                          % (name, total, detail, " and ".join(bounds)
                             or "NO BOUND GIVEN - pass at_least=/at_most=/equals="))

    def mirrors(self, name, values, mirrored, about, tol=1e-6):
        """Assert one set of coordinates is the mirror of another about `about`.

        A mirrored variant that is subtly not a mirror is very hard to see in
        a render, and a numeric comparison catches it directly.
        """
        want = sorted(round(2 * about - v, 6) for v in values)
        got = sorted(round(v, 6) for v in mirrored)
        ok = len(want) == len(got) and all(
            abs(a - b) <= tol for a, b in zip(want, got))
        return self.check(ok, "%s: mirror about %.4f %s"
                          % (name, about,
                             "matches (%d values)" % len(got) if ok
                             else "MISMATCH want %s got %s" % (want, got)))

    # -- contract-driven checks (see the module docstring) -----------------

    def contract(self, source=None):
        """Load a fit contract: a path, a dict, or `--contract` when None.

        Records one check that the file is a fit contract of a version this
        module reads, so a stale or foreign JSON fails here, by name.
        """
        source = source if source is not None else self.contract_path
        if source is None:
            self.check(False, "fit contract: none given (pass a path, or run "
                              "case_verify.py --contract FIT.json)",
                       name="fit contract loads")
            return None
        fit = load_contract(source)
        ok = (fit.get("schema") == "hw_forge.fit_contract"
              and fit.get("version") == 1)
        self.check(ok, "fit contract %s: schema %s v%s"
                   % (source if not isinstance(source, dict) else "(dict)",
                      fit.get("schema"), fit.get("version")),
                   name="fit contract loads")
        return fit if ok else None

    def _need_b3d(self):
        """build123d, or None after recording one failing check with the fix."""
        b3d = _b3d()
        if b3d is None and not getattr(self, "_b3d_reported", False):
            self._b3d_reported = True
            self.check(False, "build123d is not importable under %s: the "
                              "solid checks cannot run. fix: run with the "
                              "case venv python, e.g. case/.venv/bin/python "
                              "scripts/case_verify.py CHECKS.py"
                       % sys.executable, name="build123d importable")
        return b3d

    def _prism(self, b3d, frame, corners_xy, z0, z1):
        """A solid prism from a board-frame plan quad and z band, in the case
        frame.  Built as a loft of two quads, so any rigid frame works."""
        def ring(z):
            pts = [b3d.Vector(*frame(x, y, z)) for x, y in corners_xy]
            return b3d.Wire.make_polygon(pts, close=True)
        return b3d.Solid.make_loft([ring(z0), ring(z1)])

    @staticmethod
    def _box_corners(box, grow=0.0):
        x0, y0, x1, y1 = box
        return [(x0 - grow, y0 - grow), (x1 + grow, y0 - grow),
                (x1 + grow, y1 + grow), (x0 - grow, y1 + grow)]

    def _hits(self, solid, shells):
        """[(shell index, overlap volume)] above CONTACT_VOLUME."""
        out = []
        for i, shell in enumerate(shells):
            try:
                vol = (solid & shell).volume
            except Exception:                          # pragma: no cover
                vol = float("nan")
            if not vol <= CONTACT_VOLUME:              # catches nan too
                out.append((i, vol))
        return out

    def _where(self, solid, shells, frame_hint=""):
        """' at (x, y, z)' for the first overlap, case frame, or ''."""
        for shell in shells:
            try:
                got = solid & shell
                if got.volume > CONTACT_VOLUME:
                    c = got.center()
                    return " at (%.2f, %.2f, %.2f)" % (c.X, c.Y, c.Z)
            except Exception:                          # pragma: no cover
                continue
        return ""

    def _shell_name(self, shells, names, i):
        return names[i] if names and i < len(names) else "shell %d" % i

    def _exempt(self, check, ref, exempt):
        reason = (exempt or {}).get(ref)
        if reason:
            self.check(True, "%s %s: exempt (%s)" % (check, ref, reason),
                       name="%s %s exempt" % (check, ref))
        return bool(reason)

    def board_in_cavity(self, fit, cavity=None, margin=FIT_MARGIN,
                        shells=None, frame=None, shell_names=None,
                        corner_relief=CORNER_RELIEF, tol=TOL):
        """The board outline, grown by `margin`, fits the cavity.

        Numeric: `cavity` is a board-frame `v.rect`; every outline vertex must
        stand `margin` inside it.  Solid: the outline polygon, plus a strip
        `margin` wide outboard of every edge stopping `corner_relief` short of
        each end, extruded through the board's own thickness, minus mounting
        holes and cutouts, must meet no plastic in any shell.  The relief is
        where a cavity fillet meets a square board corner by design
        (mechanical.md §5); the outline itself still may not touch there.
        """
        if not fit or not fit["board"]["outline"]:
            return self.check(False, "board in cavity: no outline in the "
                                     "contract", name="board in cavity")
        poly = fit["board"]["outline"]["polygon"]
        thick = fit["board"]["thickness"]
        if shells is None:
            if cavity is None:
                return self.check(False, "board in cavity: pass cavity= "
                                         "(numeric) or shells= and frame=",
                                  name="board in cavity")
            slack = min(min(x - cavity.x0, cavity.x1 - x, y - cavity.y0,
                            cavity.y1 - y) for x, y in poly) - margin
            return self.check(slack >= -tol,
                              "board outline in %s: %.3fmm to spare beyond "
                              "the %.3f margin" % (cavity.name, slack, margin),
                              name="board outline in cavity")
        b3d = self._need_b3d()
        if b3d is None or frame is None:
            if frame is None:
                self.check(False, "board in cavity: solid mode needs frame=",
                           name="board in cavity")
            return False
        z0, z1 = -thick + 0.01, -0.01       # inside the slab: seats only touch
        # The outline itself, then one strip `margin` wide outboard of every
        # edge.  Strips rather than a rounded offset, because a cavity fillet
        # meets a square board corner by design (mechanical.md §5: the fillet
        # cap leaves about 0 at the corner and the full clearance on the sides).
        quads = [poly]
        sign = 1.0 if sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                          - poly[(i + 1) % len(poly)][0] * poly[i][1]
                          for i in range(len(poly))) > 0 else -1.0
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length <= 2.0 * corner_relief + 1e-6 or not margin:
                continue
            ux, uy = dx / length, dy / length
            a = (a[0] + ux * corner_relief, a[1] + uy * corner_relief)
            b = (b[0] - ux * corner_relief, b[1] - uy * corner_relief)
            nx, ny = sign * uy * margin, -sign * ux * margin
            quads.append([a, b, (b[0] + nx, b[1] + ny), (a[0] + nx, a[1] + ny)])
        slab = None
        for quad in quads:
            piece = self._prism(b3d, frame, quad, z0, z1)
            slab = piece if slab is None else slab + piece
        up = b3d.Vector(*frame(0, 0, z1)) - b3d.Vector(*frame(0, 0, z0))
        for hole in fit["mounting_holes"]:
            c = b3d.Vector(*frame(hole["x"], hole["y"], z0))
            slab = slab - b3d.Solid.make_cylinder(
                hole["diameter"] / 2.0, up.length,
                b3d.Plane(origin=c, z_dir=up.normalized()))
        for cut in fit["board"]["cutouts"]:
            if len(cut["polygon"]) >= 3:
                slab = slab - self._prism(b3d, frame, cut["polygon"], z0, z1)
        hits = self._hits(slab, shells)
        return self.check(not hits,
                          "board outline + %.3f side margin through its "
                          "%.2fmm slab meets %s%s" % (margin, thick, ", ".join(
                              "%s (%.3f mm^3)"
                              % (self._shell_name(shells, shell_names, i), v)
                              for i, v in hits) or "no plastic",
                              self._where(slab, shells) if hits else ""),
                          name="board outline in cavity (solid)")

    def cavity_clearance(self, fit, cavity=None, floor_z=None, ceiling_z=None,
                         margin=FIT_MARGIN, shells=None, frame=None,
                         shell_names=None, exempt=None, tol=TOL):
        """Every part body clears the cavity by its z band plus `margin`.

        A part with no z band fails: its height is unknown, so nothing about
        its fit is known.  Board-inherent parts (holes, fiducials) are
        skipped, because they have no body.

        Numeric mode: a floor_z or ceiling_z left as None means the case has
        no surface on that side to check, so that side's clearance is
        infinite and only the other bound is tested.  The line printed says
        which bound was not checked.  With both None the z test is not run.
        """
        if not fit:
            return False
        b3d = self._need_b3d() if shells is not None else None
        if shells is not None and (b3d is None or frame is None):
            if frame is None:
                self.check(False, "cavity clearance: solid mode needs frame=",
                           name="cavity clearance")
            return False
        ok_all = True
        for part in fit["parts"]:
            ref = part["ref"]
            if part.get("board_inherent"):
                continue
            if self._exempt("cavity clearance", ref, exempt):
                continue
            box, band = part.get("envelope"), part.get("z_band")
            if not box or not band:
                ok_all &= self.check(
                    False, "%s clears the cavity: unknown %s (declare "
                           "height_mm in design.py PARTS, or link a STEP "
                           "model)" % (ref, "height" if box else "plan box"),
                    name="%s clears the cavity" % ref)
                continue
            if shells is None:
                if cavity is not None:
                    part_shape = Shape(ref, *box)
                    ok_all &= self.inside(part_shape, cavity, margin, tol)
                if floor_z is None and ceiling_z is None:
                    continue
                lo = (band[0] - floor_z if floor_z is not None
                      else float("inf"))
                hi = (ceiling_z - band[1] if ceiling_z is not None
                      else float("inf"))
                ok_all &= self.check(min(lo, hi) >= margin - tol,
                                     "%s z %.3f..%.3f clears floor %s and "
                                     "ceiling %s: %.3fmm (need %.3f)"
                                     % (ref, band[0], band[1],
                                        "not checked" if floor_z is None
                                        else floor_z,
                                        "not checked" if ceiling_z is None
                                        else ceiling_z, min(lo, hi), margin),
                                     name="%s z clears the cavity" % ref)
                continue
            hits, worst = [], None
            for body in part.get("bodies") or [{"bbox": box, "z": band,
                                                 "source": "envelope"}]:
                solid = self._prism(b3d, frame,
                                    self._box_corners(body["bbox"], margin),
                                    body["z"][0] - margin,
                                    body["z"][1] + margin)
                got = self._hits(solid, shells)
                if got:
                    hits += got
                    worst = worst or body["source"] + self._where(solid, shells)
            ok_all &= self.check(
                not hits,
                "%s %d body box(es) (z %.3f..%.3f, %s) + %.3f margin meet %s"
                % (ref, len(part.get("bodies") or [1]), band[0], band[1],
                   worst or part.get("z_source"), margin,
                   ", ".join("%s (%.3f mm^3)"
                             % (self._shell_name(shells, shell_names, i), v)
                             for i, v in hits) or "no plastic"),
                name="%s clears the cavity (solid)" % ref)
        return ok_all

    def connector_openings(self, fit, shells=None, frame=None,
                           margin=FIT_MARGIN, reach=PROBE_REACH,
                           shell_names=None, openings=None, exempt=None,
                           tol=TOL):
        """Every external mating face has a clear path out through its wall.

        Solid: a probe the width of the part's envelope plus `margin` on each
        side, over its z band plus `margin`, runs from the part's leading face
        to `reach` mm past the board edge (or straight up/down for a top/bottom
        face) and must meet no plastic and end outside every shell.  Numeric:
        `openings={ref: {"wall": "east", "span": (a, b), "z": (z0, z1)}}`,
        board frame, must contain the contract's span and z band plus margin.
        """
        if not fit:
            return False
        b3d = self._need_b3d() if shells is not None else None
        if shells is not None and (b3d is None or frame is None):
            if frame is None:
                self.check(False, "connector openings: solid mode needs "
                                  "frame=", name="connector openings")
            return False
        ok_all, seen = True, 0
        for part in fit["parts"]:
            m, ref = part.get("mating"), part["ref"]
            # `connector` is in contracts written since the key was added;
            # an older contract only marks connectors by role.
            is_conn = part.get("connector", part.get("role") == "connector")
            if not m and is_conn and not part.get("board_inherent"):
                seen += 1
                if not self._exempt("opening", ref, exempt):
                    ok_all &= self.check(
                        False, "%s opening: connector has no mating record "
                               "(undeclared mating_direction)" % ref,
                        name="%s has a clear opening" % ref)
                continue
            if not m or m.get("kind") not in ("edge", "top", "bottom"):
                continue
            seen += 1
            if self._exempt("opening", ref, exempt):
                continue
            box, band = part.get("envelope"), part.get("z_band")
            if m.get("verdict") == "FAIL" or not box or not band:
                ok_all &= self.check(
                    False, "%s opening: cannot be checked (%s)"
                    % (ref, m.get("reason") if m.get("verdict") == "FAIL"
                       else "no plan box or no z band"),
                    name="%s has a clear opening" % ref)
                continue
            if shells is None:
                ok_all &= self._opening_numeric(part, openings or {}, margin,
                                                tol)
                continue
            solid, outer = self._probe(b3d, frame, part, margin, reach)
            hits = self._hits(solid, shells)
            # The far end must be outside the case's overall box: a probe
            # that stops in another internal pocket found no opening.
            lo = [min(sh.bounding_box().min.to_tuple()[k] for sh in shells)
                  for k in range(3)]
            hi = [max(sh.bounding_box().max.to_tuple()[k] for sh in shells)
                  for k in range(3)]
            end = outer.to_tuple()
            outside = any(end[k] < lo[k] - tol or end[k] > hi[k] + tol
                          for k in range(3))
            face = m.get("face_body") or {}
            band = face.get("z") or band
            ok_all &= self.check(
                not hits and outside,
                "%s %s opening (%s face, z %.3f..%.3f, +%.3f margin) meets %s"
                "%s" % (ref, m["wall"], m["direction_local"], band[0],
                        band[1], margin,
                        ", ".join("%s (%.3f mm^3)"
                                  % (self._shell_name(shells, shell_names, i),
                                     v) for i, v in hits) or "no plastic",
                        "" if outside else "; the probe ends INSIDE the case "
                        "(no opening through the wall, or raise reach=)"),
                name="%s has a clear opening" % ref)
        if not seen:
            self.check(True, "connector openings: no external mating face in "
                             "the contract", name="connector openings")
        return ok_all

    def _probe(self, b3d, frame, part, margin, reach):
        """(probe solid, its outer end point) for one mating part."""
        m = part["mating"]
        face = m.get("face_body") or {}
        box = face.get("bbox") or part["envelope"]
        band = face.get("z") or part["z_band"]
        z0, z1 = band[0] - margin, band[1] + margin
        if m["kind"] in ("top", "bottom"):
            corners = self._box_corners(box, margin)
            if m["kind"] == "top":
                lo, hi = band[1], band[1] + reach
            else:
                lo, hi = band[0] - reach, band[0]
            cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
            outer = b3d.Vector(*frame(cx, cy, hi if m["kind"] == "top"
                                      else lo))
            return self._prism(b3d, frame, corners, lo, hi), outer
        op = m["opening"]
        n = op["normal"][:2]
        t = (-n[1], n[0])
        (ax, ay), (bx, by) = op["span_points"]
        px, py = op["plane_point"]
        lead = -m["body_to_edge_mm"]          # leading face, along n from edge
        start, end = lead, reach
        a = (ax - t[0] * margin, ay - t[1] * margin)
        b = (bx + t[0] * margin, by + t[1] * margin)
        corners = [(a[0] + n[0] * start, a[1] + n[1] * start),
                   (b[0] + n[0] * start, b[1] + n[1] * start),
                   (b[0] + n[0] * end, b[1] + n[1] * end),
                   (a[0] + n[0] * end, a[1] + n[1] * end)]
        outer = b3d.Vector(*frame(px + n[0] * end, py + n[1] * end,
                                  (band[0] + band[1]) / 2.0))
        return self._prism(b3d, frame, corners, z0, z1), outer

    def _opening_numeric(self, part, openings, margin, tol):
        m, ref = part["mating"], part["ref"]
        got = openings.get(ref)
        if not got:
            return self.check(False, "%s opening: the case declares none "
                                     "(needed on the %s wall)" % (ref,
                                                                  m["wall"]),
                              name="%s has a clear opening" % ref)
        want_wall = m["wall"]
        if m["kind"] == "edge":
            pts = m["opening"]["span_points"]
            axis = 0 if abs(m["opening"]["normal"][0]) < 0.5 else 1
            need = (min(p[axis] for p in pts) - margin,
                    max(p[axis] for p in pts) + margin)
        else:
            box = part["envelope"]
            need = (box[0] - margin, box[2] + margin)
        band = part["z_band"]
        span, zs = got.get("span") or (0, 0), got.get("z") or (0, 0)
        slack = min(need[0] - span[0], span[1] - need[1],
                    band[0] - margin - zs[0], zs[1] - band[1] - margin)
        return self.check(got.get("wall") == want_wall and slack >= -tol,
                          "%s opening on %s (need %s): %.3fmm to spare"
                          % (ref, got.get("wall"), want_wall, slack),
                          name="%s has a clear opening" % ref)

    def min_wall(self, solid, floor_mm=MIN_WALL_MM, name="shell",
                 spacing=2.0, max_per_axis=64, exempt=None, tol=TOL):
        """The thinnest local wall of `solid` must be at least `floor_mm`.

        Samples each face on a grid (about `spacing` mm apart, inside the
        face's trimmed boundary), casts a ray inward along the face normal,
        and takes the distance to where it next leaves the material.  The
        grid runs in the face's own (u, v) parameters, one count per axis
        from that axis's extent, capped at `max_per_axis` (64) so one large
        face cannot cost thousands of ray casts.

        Residual gap: a thin region narrower than the sample spacing, or on
        a face longer than 64 x spacing (128 mm at the default), can fall
        between samples and be missed.  Lower `spacing` near a feature that
        must be proven.  A
        deliberate thin feature, such as the cap over a blind insert bore
        (mechanical.md §1, 0.5 to 0.6 mm), is excluded with `exempt=[(reason,
        (x0, y0, z0, x1, y1, z1))]` in the case frame, and each exemption is
        printed with how many samples it removed.
        """
        b3d = self._need_b3d()
        if b3d is None:
            return False
        worst, where, samples, skipped = float("inf"), None, 0, {}
        for face in solid.faces():
            nu, nv = self._grid(face, spacing, max_per_axis)
            for i in range(nu):
                for j in range(nv):
                    u, w = (i + 0.5) / nu, (j + 0.5) / nv
                    try:
                        p = face.position_at(u, w)
                        if not face.is_inside(p, 1e-4):
                            continue
                        normal = face.normal_at(p)
                    except Exception:                  # pragma: no cover
                        continue
                    box_hit = None
                    for reason, (x0, y0, z0, x1, y1, z1) in exempt or ():
                        if x0 <= p.X <= x1 and y0 <= p.Y <= y1 \
                                and z0 <= p.Z <= z1:
                            box_hit = reason
                            break
                    if box_hit:
                        skipped[box_hit] = skipped.get(box_hit, 0) + 1
                        continue
                    inward = -normal
                    try:
                        hits = solid.find_intersection_points(
                            b3d.Axis(p, inward))
                    except Exception:                  # pragma: no cover
                        continue
                    ds = [(h[0] - p).dot(inward) for h in hits]
                    ds = [d for d in ds if d > 1e-4]
                    if not ds:
                        continue
                    samples += 1
                    if min(ds) < worst:
                        worst, where = min(ds), p
        for reason, count in sorted(skipped.items()):
            self.check(True, "%s thinnest wall: exempt region (%s), %d "
                             "sample(s)" % (name, reason, count),
                       name="%s thin region exempt: %s" % (name, reason))
        if not samples:
            return self.check(False, "%s thinnest wall: no sample hit the "
                                     "solid" % name,
                              name="%s thinnest wall" % name)
        return self.check(worst >= floor_mm - tol,
                          "%s thinnest wall = %.3fmm at (%.2f, %.2f, %.2f) "
                          "over %d samples (need >= %.3f)"
                          % (name, worst, where.X, where.Y, where.Z, samples,
                             floor_mm),
                          name="%s thinnest wall" % name)

    @staticmethod
    def _grid(face, spacing, cap):
        """(nu, nv) samples so neighbours sit about `spacing` mm apart.

        Each axis count comes from the face's extent along that parameter
        direction: the distance between position_at(0, .5) and (1, .5) for
        u, and between (.5, 0) and (.5, 1) for v.  That chord understates a
        curved face's length, so curved faces are sampled at least as
        densely as a flat face of the same chord.  The earlier sqrt(area)
        rule gave a 100 x 2 mm strip the same count on both axes, about
        7 mm apart along its length.
        """
        def length(a, b):
            try:
                return (face.position_at(*a) - face.position_at(*b)).length
            except Exception:                          # pragma: no cover
                return math.sqrt(max(face.area, 0.0))
        lu = length((0.0, 0.5), (1.0, 0.5))
        lv = length((0.5, 0.0), (0.5, 1.0))
        return (max(2, min(cap, int(lu / spacing) + 1)),
                max(2, min(cap, int(lv / spacing) + 1)))

    def fastener_stackup(self, name, screw_len, floor_thk, counterbore,
                         cavity, bore_depth, pcb_thk=None, contract=None,
                         engagement_min=ENGAGEMENT_MIN, pitch=0.4,
                         tol=TOL):
        """mechanical.md §2: travel, engagement, and the head shoulder.

        travel = (floor - counterbore) + cavity + board; engagement =
        screw - travel, inside [max(engagement_min, 2 x pitch), bore_depth].
        The board thickness comes from the contract when one is given, so a
        thicker board cannot leave a screw length behind.
        """
        if pcb_thk is None:
            pcb_thk = (contract or {}).get("board", {}).get("thickness")
        if pcb_thk is None:
            return self.check(False, "%s: no board thickness (pass pcb_thk= "
                                     "or contract=)" % name, name=name)
        shoulder = floor_thk - counterbore
        travel = shoulder + cavity + pcb_thk
        engagement = screw_len - travel
        floor = max(engagement_min, 2.0 * pitch)
        self.check(shoulder >= SHOULDER_MIN - tol,
                   "%s shoulder under the head = %.3fmm (need >= %.3f)"
                   % (name, shoulder, SHOULDER_MIN))
        return self.check(
            floor - tol <= engagement <= bore_depth + tol,
            "%s: L%.2f - travel %.3f [shoulder %.2f + cavity %.2f + board "
            "%.2f] = engagement %.3fmm (need %.3f..%.3f)"
            % (name, screw_len, travel, shoulder, cavity, pcb_thk,
               engagement, floor, bore_depth))

    # -- reporting --------------------------------------------------------

    @property
    def failures(self):
        return [r for r in self.results if not r[2]]

    def summary(self):
        total, bad = len(self.results), len(self.failures)
        return {"checks": total, "passed": total - bad, "failed": bad,
                "failures": [{"suite": r[0], "section": r[1], "message": r[3]}
                             for r in self.results if not r[2]]}

    def names(self):
        """Every check's stable identity, for a baseline dump."""
        return [{"suite": r[0], "section": r[1], "name": r[4], "ok": r[2]}
                for r in self.results]


# ------------------------------------------------- command-line interface

def load_checks_module(path):
    """Import a checks file by path, without requiring it to be a package."""
    if not os.path.exists(path):
        raise SystemExit("error: no such checks file: %s" % path)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    if directory not in sys.path:
        sys.path.insert(0, directory)
    name = os.path.splitext(os.path.basename(path))[0]

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    except SyntaxError as exc:
        raise SystemExit("error: %s does not parse: %s" % (path, exc))
    return module


def run_checks(path, only=None, loud=True, contract=None):
    module = load_checks_module(path)
    entry = getattr(module, "checks", None)
    if entry is None or not callable(entry):
        raise SystemExit(
            "error: %s defines no checks(v) function\n"
            "  fix: add `def checks(v):` and build assertions on `v` "
            "(see scripts/case_verify.py's docstring)" % path)
    suite = Suite(loud=loud, only=only)
    suite.contract_path = contract or os.environ.get("HW_FORGE_CONTRACT")
    entry(suite)
    return suite


# A trailing revision tag in a suite name: "(rev 3)", "(board rev 3.1)",
# "(revision 2)".  Stripped from both sides before comparing, because a suite
# named after the board it verifies is the obvious convention and it silently
# retires the whole baseline.
_SUITE_REV = re.compile(r"\s*[\(\[]\s*(?:board\s+)?rev(?:ision)?\.?\s*"
                        r"[0-9][0-9.]*\s*[\)\]]\s*$", re.IGNORECASE)


def normalise_suite(name, mapping=None):
    """A suite name with any explicit rename applied and a rev tag stripped."""
    name = (mapping or {}).get(name, name)
    return _SUITE_REV.sub("", name or "").strip()


def compare_names(current, baseline, indent="  ", map_suite=None,
                  suite_blind=False):
    """Print added / retired / newly-failing / fixed. Returns (added, retired).

    Identities are compared as a multiset, because a suite legitimately
    registers the same check shape many times (one per fastener boss, one per
    key cell), and "there are three of these now, there were four" is a real
    answer that a set would swallow.

    Suite names are normalised first (`--map-suite`, then a trailing revision
    tag), and a comparison in which every baseline check retires against a
    disjoint set of suite names is reported as a rename and retried blind: that
    pattern is never a real revision.
    """
    def key(row):
        if suite_blind:
            return ("", row["name"])
        return (normalise_suite(row.get("suite"), map_suite), row["name"])

    def tally(rows):
        return collections.Counter(key(r) for r in rows)

    now, was = tally(current), tally(baseline)
    ok_now = {key(r): r["ok"] for r in current}
    ok_was = {key(r): r["ok"] for r in baseline}

    # The rename, caught before 239 lines of noise are printed as if they were
    # geometry.  Retried blind rather than refused: comparing on names alone is
    # the comparison the caller wanted, and the message says that is what
    # happened.
    if not suite_blind and was and not (set(now) & set(was)):
        suites_now = {s for s, _ in now}
        suites_was = {s for s, _ in was}
        if suites_now.isdisjoint(suites_was):
            print("%sSUITE RENAMED, not revised: %s -> %s. Every baseline "
                  "check would retire\n%sfor that reason alone: a suite name "
                  "is part of a check's identity, so it\n%smust not carry a "
                  "revision, a date or a board hash. Comparing on check\n"
                  "%snames only; fix the generator, or pass --map-suite "
                  "OLD=NEW."
                  % (indent, ", ".join(sorted(suites_was)) or "(unnamed)",
                     ", ".join(sorted(suites_now)) or "(unnamed)",
                     indent, indent, indent))
            return compare_names(current, baseline, indent, map_suite,
                                 suite_blind=True)

    added = sorted(k for k in now if k not in was)
    retired = sorted(k for k in was if k not in now)
    changed = sorted(k for k in now if k in was and now[k] != was[k])
    broke = sorted(k for k in now
                   if k in was and ok_was.get(k) and not ok_now.get(k))
    fixed = sorted(k for k in now
                   if k in was and not ok_was.get(k) and ok_now.get(k))

    for keys, label in ((added, "+ added  "), (retired, "- RETIRED"),
                        (broke, "! newly-failing"), (fixed, "  fixed  ")):
        for suite, name in keys:
            print("%s%s %s%s" % (indent, label,
                                 "%s: " % suite if suite else "", name))
    for suite, name in changed:
        print("%s~ count   %s%s  %d -> %d"
              % (indent, "%s: " % suite if suite else "", name, was[(suite,
                 name)], now[(suite, name)]))
    if not (added or retired or changed or broke or fixed):
        print("%ssame check set, same outcomes" % indent)
    print("%s%d check(s) now, %d in the baseline: %d added, %d retired"
          % (indent, sum(now.values()), sum(was.values()),
             sum(now[k] for k in added), sum(was[k] for k in retired)))
    if retired:
        print("%sSTATE A REASON for every retired check in your report: a "
              "retirement\n%swith a stated geometric reason is knowledge; one "
              "with a smaller number\n%sis a regression nobody can see."
              % (indent, indent, indent))
    return added, retired


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("checks", help="a python file defining checks(v)")
    ap.add_argument("--suite", help="run only this named suite")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the final tally")
    ap.add_argument("--json", action="store_true",
                    help="emit the summary as JSON")
    ap.add_argument("--dump-names", metavar="FILE",
                    help="write every check's stable identity to FILE, as the "
                         "baseline for a later revision")
    ap.add_argument("--baseline", metavar="FILE",
                    help="compare this run's check set against a --dump-names "
                         "file: added / retired / newly-failing / fixed")
    ap.add_argument("--strict-baseline", action="store_true",
                    help="with --baseline, fail the run if any check present "
                         "in the baseline no longer exists")
    ap.add_argument("--map-suite", action="append", metavar="OLD=NEW",
                    help="rename a baseline suite before comparing, for a "
                         "suite that was renamed between revisions "
                         "(repeatable)")
    ap.add_argument("--suite-blind", action="store_true",
                    help="compare check identities on the check name alone, "
                         "ignoring which suite registered them")
    ap.add_argument("--contract", metavar="FIT.json",
                    help="the board's fit contract (kicad_geom.py --contract); "
                         "a checks file reads it with v.contract()")
    args = ap.parse_args()

    map_suite = {}
    for item in args.map_suite or ():
        if "=" not in item:
            ap.error("--map-suite expects OLD=NEW, got %r" % item)
        old_name, new_name = item.split("=", 1)
        map_suite[old_name.strip()] = new_name.strip()

    suite = run_checks(args.checks, args.suite,
                       loud=not (args.quiet or args.json),
                       contract=args.contract)
    summary = suite.summary()

    if args.json:
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif summary["failed"]:
        print("\n%d of %d checks FAILED" % (summary["failed"],
                                            summary["checks"]))
        for fail in summary["failures"]:
            print("  %s%s" % ("%s: " % fail["section"] if fail["section"]
                              else "", fail["message"]))
    else:
        print("\nall %d checks passed" % summary["checks"])

    retired = []
    if args.dump_names:
        with open(args.dump_names, "w") as fh:
            json.dump({"checks": suite.names()}, fh, indent=2)
            fh.write("\n")
        print("\nwrote %d check name(s) to %s"
              % (summary["checks"], args.dump_names))
    if args.baseline:
        if not os.path.exists(args.baseline):
            raise SystemExit("error: no such baseline: %s" % args.baseline)
        with open(args.baseline) as fh:
            old = json.load(fh)
        print("\n--- check set vs %s ---" % args.baseline)
        _added, retired = compare_names(suite.names(),
                                        old.get("checks") or [],
                                        map_suite=map_suite,
                                        suite_blind=args.suite_blind)

    if not summary["checks"]:
        raise SystemExit("error: %s registered no checks; nothing was "
                         "verified" % args.checks)
    if summary["failed"]:
        sys.exit(1)
    if retired and args.strict_baseline:
        print("%d check(s) retired and --strict-baseline is set"
              % len(retired), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
