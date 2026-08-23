#!/usr/bin/env python3
"""Numeric interference/stack-up checks for an enclosure, as a gate.

The enclosure phase's exit gate.  Geometry disputes get settled by running
numbers, not by arguing: every check prints the value it got and the value it
needed, so a failure tells you which named constant to nudge and by how much.

    python3 scripts/case_verify.py case/checks.py
    python3 scripts/case_verify.py case/checks.py --suite left --json

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
Board files are x east / y **south**; most CAD frames want y north.  Mixing
them is the classic way to get a case that verifies clean and prints mirrored.
"""

import argparse
import json
import math
import os
import sys

# The checks file is imported from the user's own tree; do not leave a
# __pycache__ directory in their project as a side effect of verifying it.
sys.dont_write_bytecode = True


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


def box_distance(a, b):
    """Distance between two axis-aligned boxes; 0 if they touch or overlap."""
    dx = max(a.x0 - b.x1, b.x0 - a.x1, 0.0)
    dy = max(a.y0 - b.y1, b.y0 - a.y1, 0.0)
    return math.hypot(dx, dy)


def gap(a, b):
    """Clear distance between two shapes, negative when they interfere."""
    return box_distance(a, b) - a.radius - b.radius


# -------------------------------------------------------------------- suite

class Suite(object):
    """Collects checks and their numbers. One instance per `checks(v)` call."""

    def __init__(self, name="", loud=True, only=None):
        self.name = name
        self.loud = loud
        self.only = only
        self.results = []            # (suite, section, ok, message)
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

    def check(self, ok, message):
        """Record one result. Every other method funnels through here."""
        if self._skipping:
            return bool(ok)
        self.results.append((self._suite, self._section, bool(ok), message))
        if self.loud:
            print("  %s %s" % ("ok  " if ok else "FAIL", message))
        return bool(ok)

    def clearance(self, a, b, minimum):
        """`a` must stand at least `minimum` mm clear of `b`."""
        got = gap(a, b)
        return self.check(got >= minimum,
                          "%s to %s: %.3fmm (need %.3f)"
                          % (a.name, b.name, got, minimum))

    def nearest(self, a, others, minimum):
        """Clearance to the closest of many obstacles — one line, not N.

        This is what keeps a check run readable when a part must clear every
        footprint on a face: the failure names the offender.
        """
        if not others:
            return self.check(True, "%s: no obstacles to clear" % a.name)
        worst = min(((gap(a, b), b.name) for b in others))
        return self.check(worst[0] >= minimum,
                          "%s to nearest of %d (%s): %.3fmm (need %.3f)"
                          % (a.name, len(others), worst[1], worst[0], minimum))

    def inside(self, part, region, margin=0.0):
        """`part` must sit wholly inside `region`, with `margin` to spare."""
        slack = min(part.x0 - part.radius - (region.x0 + margin),
                    part.y0 - part.radius - (region.y0 + margin),
                    (region.x1 - margin) - (part.x1 + part.radius),
                    (region.y1 - margin) - (part.y1 + part.radius))
        return self.check(slack >= 0.0,
                          "%s inside %s: %.3fmm to spare%s"
                          % (part.name, region.name, slack,
                             "" if not margin else " (margin %.3f)" % margin))

    def outside(self, part, region, margin=0.0):
        """`part` must not overlap `region` (a keepout, bay or cutout)."""
        got = gap(part, region)
        return self.check(got >= margin,
                          "%s clear of %s: %.3fmm (need %.3f)"
                          % (part.name, region.name, got, margin))

    def equals(self, name, got, want, tol=1e-6):
        return self.check(abs(got - want) <= tol,
                          "%s = %.4f (want %.4f +/- %g)" % (name, got, want, tol))

    def at_least(self, name, got, floor):
        return self.check(got >= floor,
                          "%s = %.4f (need >= %.4f)" % (name, got, floor))

    def at_most(self, name, got, ceiling):
        return self.check(got <= ceiling,
                          "%s = %.4f (need <= %.4f)" % (name, got, ceiling))

    def between(self, name, got, low, high):
        return self.check(low <= got <= high,
                          "%s = %.4f (need %.4f..%.4f)" % (name, got, low, high))

    def stack(self, name, terms, at_least=None, at_most=None, equals=None,
              tol=1e-6):
        """Sum a named stack-up and assert its total.

        `terms` is {label: mm}; negative terms subtract.  The printed line
        carries the whole sum, because a stack-up that fails is nearly always
        one term nobody wrote down — the screw that needed to be 14mm rather
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

        A mirrored variant that is subtly *not* a mirror is the hardest class
        of bug to see in a render and the cheapest to catch numerically.
        """
        want = sorted(round(2 * about - v, 6) for v in values)
        got = sorted(round(v, 6) for v in mirrored)
        ok = len(want) == len(got) and all(
            abs(a - b) <= tol for a, b in zip(want, got))
        return self.check(ok, "%s: mirror about %.4f %s"
                          % (name, about,
                             "matches (%d values)" % len(got) if ok
                             else "MISMATCH want %s got %s" % (want, got)))

    # -- reporting --------------------------------------------------------

    @property
    def failures(self):
        return [r for r in self.results if not r[2]]

    def summary(self):
        total, bad = len(self.results), len(self.failures)
        return {"checks": total, "passed": total - bad, "failed": bad,
                "failures": [{"suite": s, "section": sec, "message": m}
                             for s, sec, ok, m in self.results if not ok]}


# ---------------------------------------------------------------------- CLI

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


def run_checks(path, only=None, loud=True):
    module = load_checks_module(path)
    entry = getattr(module, "checks", None)
    if entry is None or not callable(entry):
        raise SystemExit(
            "error: %s defines no checks(v) function\n"
            "  fix: add `def checks(v):` and build assertions on `v` "
            "(see scripts/case_verify.py's docstring)" % path)
    suite = Suite(loud=loud, only=only)
    entry(suite)
    return suite


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("checks", help="a python file defining checks(v)")
    ap.add_argument("--suite", help="run only this named suite")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the final tally")
    ap.add_argument("--json", action="store_true",
                    help="emit the summary as JSON")
    args = ap.parse_args()

    suite = run_checks(args.checks, args.suite, loud=not (args.quiet or args.json))
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

    if not summary["checks"]:
        raise SystemExit("error: %s registered no checks — nothing was "
                         "verified" % args.checks)
    if summary["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
