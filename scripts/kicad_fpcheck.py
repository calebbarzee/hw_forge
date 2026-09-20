#!/usr/bin/env python3
"""Check a footprint's pad geometry against the physical package it claims to be.

hw_forge's gates compare board to schematic: electrical rule check (ERC),
design rule check (DRC), schematic parity, unconnected nets. None of them
compare board to the physical part, because none of them has a notion of a
part's real body and lead geometry at all. Two incidents are the reason this
script exists.

  * A keyboard project's per-key diode used the stock footprint
    `Diode_SMD:D_SOD-123` for a `1N4148W`. At assembly, the footprint was
    slightly too large for the diode actually supplied. See
    `kb/keyboards/diode-footprint-vs-part.md`.
  * A blog-documented agent design (a6mzero.com, "This PCB is brought to you
    by Fable 5") selected a W25Q128JVS SPI flash in SOIC-8 wide (7.5 mm body)
    and laid down SOP-8 narrow (3.9 mm body) pads -- a different, incompatible
    footprint family, not a tolerance problem. A second part on the same
    board had a boost-converter transistor whose real package was smaller
    than the pads drawn for it. Every DRC passed; both were caught only when
    the files reached JLCPCB for assembly. See
    `kb/parts/package-family-traps.md`.

Every design rule check in KiCad, and every gate `kicad_gate.py` runs, is
blind to both failures, because they check whether the copper is internally
consistent, never whether it matches the part's own geometry. This script
adds that comparison, offline, from a table this repository ships and cites.

What it computes, per footprint, from the footprint's OWN LOCAL frame (never
the board placement's rotation -- a package's length and width are properties
of the part, not of where a generator happened to place it):

    pad count            copper-bearing pads (SMD, thru_hole; a np_thru_hole
                          mounting pad carries no copper and is not a lead)
    pad outer span        both axes, sorted long/short so the check does not
                          have to know which axis a given library authored
                          as "along" versus "across"
    pad inner gap         for a two-pad part only: the facing edge-to-edge
                          gap between the two pads
    pad pitch             the smallest pairwise pad-centre distance -- for a
                          multi-row IC this is exactly the row pitch; for a
                          three-terminal SOT it is the same-side lead
                          spacing; a two-pad part has no pitch (see gap above)
    package family        from the declared-package resolution below

Declared package: three sources, tried in order, and the report always names
which one fired.

  1. `--design design.py`'s own `PACKAGES` dict (see `templates/design.py`),
     keyed by reference then by value. This is the explicit, human- or
     agent-written statement of what a part is supposed to be, independent
     of whatever footprint got laid down for it -- the only source that can
     catch the blog's failure, where the WRONG footprint was linked to a
     correctly-chosen part.
  2. A `Package` (or `package`) property on the footprint itself, e.g. one
     `resource-scout` wrote down during part resolution. Also independent of
     the footprint's own name.
  3. A heuristic read of the footprint's own name against `packages.json`'s
     `name_aliases` (longest match wins, so "SOD-123F" beats "SOD-123" on a
     name containing both). This is the weakest source, because it derives
     the declaration FROM the very thing it would be checking -- so a family
     mismatch can only be reported when the declared source is 1 or 2. At
     priority 3 the dimension checks still run (do these pads look like a
     self-consistently named part?), but the family-agreement check does not
     fire, since there is nothing independent to compare against.

A source 1 or 2 declaration that does not match any `packages.json` key --
a typo, e.g. `"SOD-124-TYPO"` -- is not the same thing as no declaration at
all, and is reported differently: FAIL, naming the declared string, its
source, and the closest matching keys (`difflib.get_close_matches`), rather
than the SKIP a genuinely undeclared part gets. A typo silently falling
through to SKIP would turn off the check the declaration was meant to
enable; this is one of the two incidents this script exists to catch, not
a reason to stop looking.

Two check modes.

`--declared-only` compares package FAMILY strings only: does the declared
package and the footprint's own name agree on which of `packages.json`'s
entries this is. No dimension lookup is needed, which is deliberate -- it is
exactly the blog's failure (SOIC-8 wide declared, SOP-8 narrow laid down) and
it fires even for a part this table has no numbers for.

The default (full) mode adds dimension checks against the declared package's
`packages.json` entry: pad count, pitch, outer span on both axes, and --
for two-terminal chip and diode packages only -- inner gap versus the
part's own body length.

Why the gap check is two-terminal-only, and what it means when it fires:

A chip resistor, capacitor, or short-gull-wing diode (SOD-*) has no real lead
frame: the body's own end terminations sit on the pads directly, so the body
must be at least as long as the gap between the pads' facing inner edges, or
it cannot bridge them. That is exactly the keyboard incident's failure mode:
a supplied part physically shorter than the footprint expects does not
visually or mechanically span the pads. So for these families, `gap_mm` >
the package's own `body_length_mm` is a FAIL, named "footprint too large".

A leaded IC or transistor (SOT, SOIC, TSSOP, MSOP, QFN, DFN, TO-252) has
leads that do the bridging, splayed out from the body edge to the pad; the
gap between pad rows is routinely LARGER than the body by design (that is
where the gull-wing bend lives), so a gap-vs-body comparison is not
physically meaningful for them. `packages.json` marks each entry's
`gap_check` accordingly, and this script honours it rather than guessing.

A known false positive: a "reversible" footprint (common in the keyboard
community for a part that can be soldered either way up, doubling each pad
across F.Cu and B.Cu so one footprint serves both orientations) has twice the
real pad count. This script has no notion of that convention and reports a
pad-count FAIL against a plain two-terminal package for one. Measured case:
`zboard_kbd.pretty/D_SOD-123_rev.kicad_mod` reports 4 pads against SOD-123's
declared 2. That is not a geometry defect; verify a "pad count" FAIL by hand
before trusting it on a footprint whose name marks it reversible (commonly a
`_rev` suffix), and treat this as a documented gap rather than a false
report of a real one.

What this script does NOT see, stated precisely because both halves matter.

It compares a footprint's geometry against a DECLARED package -- what the
design says the part should be. It has no way to see what a fab actually
solders down. The keyboard incident's diode was specified consistently
(`1N4148W`, footprint `D_SOD-123`, and every major manufacturer's `1N4148W`
datasheet nominally IS a SOD-123 part) -- the design file was internally
consistent throughout. What failed was the physical unit a supplier shipped,
which this script cannot know about without a component to measure. That is
a receiving-inspection problem, not a design-file problem, and closing it
needs a different mechanism (see `docs/BACKLOG.md` B3 and
`agents/fab-docs-engineer.md`'s pre-upload check). This script closes the
half that IS a design-file problem: a footprint that disagrees with its own
declared package, which is exactly what the blog incident was.

Runs under system python3, stdlib only. Imports the s-expression parser from
`kicad_geom.py` (same directory) rather than re-implementing one.

    python3 scripts/kicad_fpcheck.py board.kicad_pcb
    python3 scripts/kicad_fpcheck.py board.kicad_pcb --design kicad/design.py
    python3 scripts/kicad_fpcheck.py lib/hexpad_kbd.pretty --declared-only
    python3 scripts/kicad_fpcheck.py one.kicad_mod --json

Exit status is nonzero if any footprint's verdict is FAIL.
"""

import argparse
import difflib
import glob
import importlib.util
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_geom  # noqa: E402  (reuse its s-expression parser and pad math)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACKAGES = os.path.join(HERE, "packages.json")

# ------------------------------------------------------------ named constants
#
# Tolerance bands. Nudge these, do not argue about a single footprint's
# numbers by hand -- the same doctrine the rest of hw_forge uses for board
# geometry applies here: a disagreement is a reason to widen or narrow a
# band, with the reason recorded, not a one-off exception.

PITCH_WARN_MM = 0.10           # pitch off nominal by more than this: WARN
PITCH_FAIL_MM = 0.25           # ...by more than this: FAIL (wrong pitch family)
SPAN_OVER_WARN_MM = 0.20       # outer span over nominal by more than this: WARN
SPAN_OVER_FAIL_MM = 0.50       # ...FAIL: the "footprint too large" signature
SPAN_UNDER_WARN_MM = 0.30      # outer span under nominal by more than this: WARN
GAP_MARGIN_MM = 0.10           # gap within this of the body length: WARN (thin margin)

# A no-lead package's exposed pad is drawn many times the area of a lead pad.
# KiCad's own stock QFN/DFN footprints number it as a plain digit (pad "17"
# on a 16-lead part), not as a text ref like "EP", so it cannot be found by
# name -- area is the only reliable signal. See exclude_exposed_pad().
EP_AREA_RATIO = 3.0


# --------------------------------------------------------------- footprint IO

def load_packages(path):
    with open(path) as fh:
        return json.load(fh)["packages"]


def load_design_packages(path):
    """Import a design.py by file path and return its PACKAGES dict, or {}.

    design.py is pure stdlib per hw_forge doctrine (templates/design.py), so
    importing it directly under system python3 is safe -- the same guarantee
    `python3 design.py` as a smoke check already rests on.
    """
    spec = importlib.util.spec_from_file_location("hwforge_design_pkgcheck",
                                                   path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "PACKAGES", {})


def iter_footprint_nodes(path):
    """Yield one raw footprint s-expression node per footprint in `path`.

    `path` is a .kicad_pcb, a single .kicad_mod, or a .pretty directory.
    """
    if os.path.isdir(path):
        for modfile in sorted(glob.glob(os.path.join(path, "*.kicad_mod"))):
            for node in iter_footprint_nodes(modfile):
                yield node
        return
    root = kicad_geom.parse_file(path)
    if not root:
        return
    if root[0] == "kicad_pcb":
        for node in kicad_geom.kids(root, "footprint"):
            yield node
    elif root[0] == "footprint":
        yield root
    else:
        raise SystemExit(
            "error: %s is neither a .kicad_pcb nor a .kicad_mod (root is %r)\n"
            "  fix: pass a board, one footprint file, or a .pretty directory"
            % (path, root[0]))


def footprint_identity(node):
    lib = kicad_geom.atoms(node)[1] if len(kicad_geom.atoms(node)) > 1 else ""
    ref = value = ""
    properties = {}
    for prop in kicad_geom.kids(node, "property"):
        names = kicad_geom.atoms(prop)
        if len(names) >= 3:
            properties[names[1]] = names[2]
            if names[1] == "Reference":
                ref = names[2]
            elif names[1] == "Value":
                value = names[2]
    return {"lib": lib, "ref": ref, "value": value, "properties": properties}


def footprint_pads(node):
    """Copper-bearing pads, in the footprint's OWN local frame.

    Calls kicad_geom's own pad-bbox math with origin (0, 0) and angle 0, so
    wherever this footprint is placed and rotated on a real board never
    enters the geometry -- a package's length, width and pitch are
    properties of the part, not of the placement. This is the same helper
    `kicad_geom.py` uses internally for its own board-coordinate pad boxes;
    only the origin/angle arguments differ.
    """
    out = []
    for pad in kicad_geom.kids(node, "pad"):
        atoms = kicad_geom.atoms(pad)
        number = atoms[1] if len(atoms) > 1 else ""
        pad_type = atoms[2] if len(atoms) > 2 else ""
        if pad_type == "np_thru_hole":
            continue                              # no copper: not a lead
        box = kicad_geom._pad_bbox(pad, (0.0, 0.0), 0.0)
        if not box:
            continue
        out.append({"number": number, "type": pad_type,
                    "bbox": [round(v, 4) for v in box],
                    "area": round((box[2] - box[0]) * (box[3] - box[1]), 6)})
    return out


def exclude_exposed_pad(pads):
    """(lead_pads, exposed_pad_or_None).

    Only pads with four or more siblings are candidates, so a two-pad diode
    is never mistaken for a one-lead-plus-thermal-pad part.
    """
    if len(pads) < 4:
        return pads, None
    areas = sorted(p["area"] for p in pads)
    median = areas[len(areas) // 2]
    if median <= 0:
        return pads, None
    big = [p for p in pads if p["area"] > EP_AREA_RATIO * median]
    if len(big) == 1:
        return [p for p in pads if p is not big[0]], big[0]
    return pads, None


# ------------------------------------------------------------------ measuring

def measure(pads):
    """{'pad_count', 'span_long', 'span_short', 'pitch', 'gap'}."""
    xs0 = [p["bbox"][0] for p in pads]
    xs1 = [p["bbox"][2] for p in pads]
    ys0 = [p["bbox"][1] for p in pads]
    ys1 = [p["bbox"][3] for p in pads]
    span_x = max(xs1) - min(xs0)
    span_y = max(ys1) - min(ys0)
    span_long, span_short = ((span_x, span_y) if span_x >= span_y
                             else (span_y, span_x))

    # Pitch: the smallest pairwise pad-centre distance. For a multi-row IC
    # that is exactly the row pitch; for a 3-pin SOT it is the same-side
    # lead spacing. Meaningless (and not computed) for a two-pad part, which
    # reports its one spacing as `gap` instead.
    pitch = None
    if len(pads) >= 3:
        centres = [((p["bbox"][0] + p["bbox"][2]) / 2.0,
                    (p["bbox"][1] + p["bbox"][3]) / 2.0) for p in pads]
        dists = [math.hypot(a[0] - b[0], a[1] - b[1])
                 for i, a in enumerate(centres) for b in centres[i + 1:]]
        dists = [d for d in dists if d > 1e-6]
        if dists:
            pitch = min(dists)

    # Gap: the two pads' facing inner edges, along whichever axis separates
    # their centres the most (so an off-axis or slightly staggered pair
    # still measures the gap that matters).
    gap = None
    if len(pads) == 2:
        a, b = pads[0]["bbox"], pads[1]["bbox"]
        ca = ((a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0)
        cb = ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
        if abs(ca[0] - cb[0]) >= abs(ca[1] - cb[1]):
            left, right = (a, b) if ca[0] < cb[0] else (b, a)
            gap = right[0] - left[2]
        else:
            lo, hi = (a, b) if ca[1] < cb[1] else (b, a)
            gap = hi[1] - lo[3]

    return {"pad_count": len(pads), "span_long": round(span_long, 4),
            "span_short": round(span_short, 4),
            "pitch": round(pitch, 4) if pitch is not None else None,
            "gap": round(gap, 4) if gap is not None else None}


# ------------------------------------------------------- declared-package ID

def heuristic_family(name, table):
    """Longest matching `name_aliases` substring wins, case-insensitive."""
    low = (name or "").lower()
    best, best_len = None, 0
    for key, entry in table.items():
        for alias in entry.get("name_aliases", []):
            if alias in low and len(alias) > best_len:
                best, best_len = key, len(alias)
    return best


def normalize_family(raw, table):
    """A free-text or exact package string -> a packages.json key, or None."""
    if raw in table:
        return raw
    low = raw.lower()
    for key in table:
        if key.lower() == low:
            return key
    return heuristic_family(raw, table)


def resolve_declared(fp, design_packages, table):
    """(family_or_None, source_label, independent_bool, unresolved_raw).

    `independent` is True only for sources 1 and 2 (design.py, a footprint
    property): a declaration that comes from somewhere OTHER than the
    footprint's own name, and so can actually disagree with it.

    `unresolved_raw` is the exact declared string when a source 1 or 2
    declaration exists but does not match any `packages.json` key (a typo,
    e.g. "SOD-124-TYPO") -- None whenever there is no such declaration, or
    it resolved cleanly. A caller uses this to tell "nothing was declared"
    (family None, unresolved_raw None -- SKIP, nothing to check) apart from
    "something was declared and it is wrong" (family None, unresolved_raw
    set -- FAIL, the declaration itself is broken).
    """
    if design_packages:
        for lookup_key in (fp["ref"], fp["value"]):
            if lookup_key and lookup_key in design_packages:
                raw = design_packages[lookup_key]
                fam = normalize_family(raw, table)
                source = "design.py PACKAGES[%r] = %r" % (lookup_key, raw)
                return (fam, source, True, None if fam else raw)
    unresolved = None
    for propname in ("Package", "package"):
        val = fp["properties"].get(propname)
        if val:
            fam = normalize_family(val, table)
            source = "footprint property %s=%r" % (propname, val)
            if fam:
                return fam, source, True, None
            if unresolved is None:
                unresolved = (source, val)
    if unresolved is not None:
        source, raw = unresolved
        return None, source, True, raw
    lcsc = (fp["properties"].get("LCSC") or fp["properties"].get("LCSC Part"))
    fam = heuristic_family(fp["lib"], table)
    source = "heuristic from the footprint's own name %r" % fp["lib"]
    if lcsc:
        source += (" (an LCSC field, %r, is present but its package cannot "
                   "be resolved offline -- see this script's module "
                   "docstring)" % lcsc)
    return fam, source, False, None


# ---------------------------------------------------------------- the checks

def worst(findings):
    sevs = {f[0] for f in findings}
    if "FAIL" in sevs:
        return "FAIL"
    if "WARN" in sevs:
        return "WARN"
    return "PASS"


def check_footprint(declared, source, independent, name_family,
                    measured, ep, table, declared_only, unresolved_raw=None):
    """(verdict, [(severity, message), ...], entry_or_None)."""
    findings = []

    if declared is None:
        if unresolved_raw is not None:
            # A declaration exists (design.py PACKAGES[...] or a footprint
            # property) but does not match any packages.json key -- a typo,
            # not an absent declaration. Silently falling through to SKIP
            # here is exactly the bug this branch fixes: it let a typo like
            # "SOD-124-TYPO" disable the check instead of failing it.
            suggestions = difflib.get_close_matches(
                unresolved_raw, sorted(table.keys()), n=3)
            msg = ("declared package %r (%s) does not match any "
                   "packages.json entry" % (unresolved_raw, source))
            msg += (" -- closest match(es): %s" % ", ".join(suggestions)
                   if suggestions else " -- no close match in packages.json")
            findings.append(("FAIL", msg))
            # Still run the family comparison against the footprint-name
            # heuristic, if one exists, so a real family disagreement is not
            # hidden behind the typo report.
            if name_family:
                findings.append(("INFO",
                    "the footprint's own name still reads as %s -- compare "
                    "that against the corrected declaration" % name_family))
            return worst(findings), findings, None
        return "SKIP", [("INFO", "no declared package and no name-based "
                         "guess -- nothing to check")], None

    if independent and name_family and name_family != declared:
        findings.append(("FAIL",
            "package family mismatch: declared %s (%s) but the footprint's "
            "own name reads as %s -- these are different physical parts"
            % (declared, source, name_family)))
    elif not independent:
        findings.append(("INFO",
            "no independent package declaration (no design.py PACKAGES "
            "entry and no Package/LCSC property); %s" % source))

    entry = table.get(declared)
    if declared_only:
        return worst(findings), findings, entry

    if entry is None:
        findings.append(("WARN",
            "declared package %r has no entry in packages.json -- add one "
            "to check geometry, not just the family name" % declared))
        return worst(findings), findings, None

    m = measured

    want_n = entry["pad_count"]
    if entry.get("has_exposed_pad") and ep is None:
        findings.append(("WARN",
            "%s normally has an exposed pad; none was found on this "
            "footprint (or the area heuristic missed it)" % declared))
    if m["pad_count"] != want_n:
        findings.append(("FAIL",
            "pad count %d does not match %s's %d leads"
            % (m["pad_count"], declared, want_n)))

    if entry.get("pitch_mm") is not None and m["pitch"] is not None:
        d = abs(m["pitch"] - entry["pitch_mm"])
        if d > PITCH_FAIL_MM:
            findings.append(("FAIL",
                "pad pitch %.3f mm is %.3f mm off %s's nominal %.3f mm"
                % (m["pitch"], d, declared, entry["pitch_mm"])))
        elif d > PITCH_WARN_MM:
            findings.append(("WARN",
                "pad pitch %.3f mm is %.3f mm off %s's nominal %.3f mm"
                % (m["pitch"], d, declared, entry["pitch_mm"])))

    for axis, key in (("long", "span_long_mm"), ("short", "span_short_mm")):
        want = entry.get(key)
        got = m["span_long"] if axis == "long" else m["span_short"]
        if want is None:
            continue
        over = got - want
        tag = "" if axis == "long" else " (short axis)"
        if over > SPAN_OVER_FAIL_MM:
            findings.append(("FAIL",
                "pad outer span%s %.3f mm exceeds %s's nominal %.3f mm by "
                "%.3f mm -- footprint too large for the part"
                % (tag, got, declared, want, over)))
        elif over > SPAN_OVER_WARN_MM:
            findings.append(("WARN",
                "pad outer span%s %.3f mm exceeds %s's nominal %.3f mm by "
                "%.3f mm" % (tag, got, declared, want, over)))
        elif axis == "long" and -over > SPAN_UNDER_WARN_MM:
            findings.append(("WARN",
                "pad outer span%s %.3f mm is %.3f mm under %s's nominal "
                "%.3f mm -- leads may overhang the pads"
                % (tag, got, -over, declared, want)))

    if entry.get("gap_check") and m["gap"] is not None:
        body = entry["body_length_mm"]
        if m["gap"] > body:
            findings.append(("FAIL",
                "pad inner gap %.3f mm is WIDER than %s's own body "
                "(%.3f mm) -- the body cannot reach both pads"
                % (m["gap"], declared, body)))
        elif body - m["gap"] < GAP_MARGIN_MM:
            findings.append(("WARN",
                "pad inner gap %.3f mm leaves only %.3f mm of %s's body "
                "overhanging the pads -- little margin"
                % (m["gap"], body - m["gap"], declared)))

    return worst(findings), findings, entry


# ---------------------------------------------------------------------- main

def run(path, table, design_packages, declared_only):
    results = []
    for node in iter_footprint_nodes(path):
        fp = footprint_identity(node)
        pads = footprint_pads(node)
        if not pads:
            results.append({"ref": fp["ref"] or fp["lib"], "lib": fp["lib"],
                            "value": fp["value"], "declared": None,
                            "declared_source": None, "measured": None,
                            "verdict": "SKIP",
                            "findings": [{"severity": "INFO",
                                         "message": "no copper pads (e.g. a "
                                                    "mounting hole)"}]})
            continue
        lead_pads, ep = exclude_exposed_pad(pads)
        measured = measure(lead_pads)
        declared, source, independent, unresolved_raw = resolve_declared(
            fp, design_packages, table)
        name_family = heuristic_family(fp["lib"], table)
        verdict, findings, entry = check_footprint(
            declared, source, independent, name_family, measured, ep,
            table, declared_only, unresolved_raw)
        results.append({"ref": fp["ref"] or fp["lib"], "lib": fp["lib"],
                        "value": fp["value"], "declared": declared,
                        "declared_source": source, "measured": measured,
                        "verdict": verdict,
                        "findings": [{"severity": s, "message": msg}
                                    for s, msg in findings]})
    return results


def print_report(path, results, declared_only, verbose=False):
    print("%s%s" % (path, "  (--declared-only: family agreement only, no "
                    "dimensions)" if declared_only else ""))
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    heuristic = 0
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        if any("heuristic from the footprint" in f["message"]
               for f in r["findings"]):
            heuristic += 1
        # Quiet by default: one line per WARN or FAIL, with its findings.
        # PASS and SKIP are counted in the summary; --verbose lists them.
        if not verbose and r["verdict"] in ("PASS", "SKIP"):
            continue
        m = r["measured"]
        numbers = ("pads=%d span=%s/%s pitch=%s gap=%s"
                  % (m["pad_count"], m["span_long"], m["span_short"],
                     m["pitch"] if m["pitch"] is not None else "-",
                     m["gap"] if m["gap"] is not None else "-")
                  if m else "-")
        print("  %-10s %-6s declared=%-14s %-32s %s"
              % (r["ref"], r["verdict"], r["declared"] or "-",
                 r["lib"][:32], numbers))
        for f in r["findings"]:
            print("      %-5s %s" % (f["severity"], f["message"]))
    print("\n%d footprint(s): %d pass, %d warn, %d fail, %d skipped (nothing "
          "to check)"
          % (len(results), counts["PASS"], counts["WARN"], counts["FAIL"],
             counts["SKIP"]))
    if heuristic and not declared_only:
        print("%d checked against a package guessed from the footprint's own "
              "name only (no design.py PACKAGES entry, no Package or LCSC "
              "property): a self-consistency check, not a verification. "
              "Declare the package to make it one." % heuristic)
    if not verbose and (counts["PASS"] or counts["SKIP"]):
        print("(--verbose lists every PASS and SKIP footprint)")


def main():
    ap = argparse.ArgumentParser(
        description="Check a footprint's pad geometry against the physical "
                    "package it claims to be.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help=".kicad_pcb, .kicad_mod, or a .pretty "
                                "directory")
    ap.add_argument("--design", metavar="FILE",
                    help="a design.py to read a PACKAGES table from "
                         "(priority 1 for the declared package)")
    ap.add_argument("--packages", default=DEFAULT_PACKAGES,
                    help="the package dimension table (default: "
                         "packages.json beside this script)")
    ap.add_argument("--declared-only", action="store_true",
                    help="check package FAMILY agreement only -- catches "
                         "the blog incident (SOIC-8 wide declared, SOP-8 "
                         "narrow laid down) with no dimension table needed")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="list every footprint, including PASS and SKIP "
                         "(default: WARN and FAIL only, plus the summary)")
    args = ap.parse_args()

    table = load_packages(args.packages)
    design_packages = (load_design_packages(args.design) if args.design
                       else {})

    results = run(args.path, table, design_packages, args.declared_only)

    if args.json:
        json.dump({"source": args.path, "declared_only": args.declared_only,
                  "results": results}, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_report(args.path, results, args.declared_only, args.verbose)

    if any(r["verdict"] == "FAIL" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
