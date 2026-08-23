#!/usr/bin/env python3
"""Scaffold a KiCad project directory: library tables, .kicad_pro, DRC severities.

Creates the three files a generated project needs before a generator can emit
into it, so nothing depends on the user's global KiCad configuration:

  sym-lib-table / fp-lib-table   project-local libraries, auto-discovered from
                                 a sibling `lib/` directory (or given by flag)
  NAME.kicad_pro                 design rules, one Default net class, and any
                                 DRC severity overrides
  hwforge-overrides.json         the durable record of those overrides

    python3 scripts/kicad_scaffold.py build/left boardname
    python3 scripts/kicad_scaffold.py build/left boardname \\
        --severity npth_inside_courtyard=warning
    python3 scripts/kicad_scaffold.py build/left --repatch

THE POST-SaveBoard RE-PATCH — read this before writing a generator.

`pcbnew.SaveBoard()` rewrites the sibling `.kicad_pro` from the board object's
own project settings.  A board built with `CreateEmptyBoard()` — which is what
every from-scratch generator does — carries pcbnew's *defaults*, not the file
this script wrote, so the save silently reverts everything in it.  Measured on
KiCad 10.0.5: a scaffolded `npth_inside_courtyard: warning` comes back as
`error`, and `min_clearance: 0.2` comes back as `0.0`.  The DRC then fails on a
rule the project deliberately demoted, and the board looks broken when only the
project file is.

(A board obtained with `LoadBoard()` keeps the settings it loaded, so an
edit-in-place tool is not exposed.  The from-scratch generator is.)

Overrides must therefore be applied *after* the last save, not before, which
means something has to remember them across the save.

That something is `hwforge-overrides.json`: a sidecar pcbnew does not touch.
A generator's save path is:

    pcbnew.SaveBoard(out, board)
    import kicad_scaffold; kicad_scaffold.repatch(os.path.dirname(out))

or, equivalently, `kicad_scaffold.py <dir> --repatch` as the next Makefile
line.  `kicad_zonefill.py` already does this for you.

Demote a rule only with a comment saying why the violation is intended — a
severity override is a design decision on the record, not a way to quiet a
gate.
"""

import argparse
import glob
import json
import os

OVERRIDES_FILE = "hwforge-overrides.json"

# Conservative two-layer defaults: comfortably inside every budget fab's
# capability, so a project only widens them deliberately.  All overridable
# with --design-rule.
DEFAULT_RULES = {
    "min_clearance": 0.2,
    "min_track_width": 0.2,
    "min_through_hole_diameter": 0.3,
    "min_via_diameter": 0.45,
}
DEFAULT_NET_CLASS = {
    "name": "Default",
    "clearance": 0.2,
    "track_width": 0.25,
    "via_diameter": 0.6,
    "via_drill": 0.3,
}

SYM_TABLE_HEADER = "(sym_lib_table\n  (version 7)\n"
FP_TABLE_HEADER = "(fp_lib_table\n  (version 7)\n"
LIB_ROW = ('  (lib (name "%s")(type "KiCad")(uri "%s")(options "")'
           '(descr "%s"))\n')


# ------------------------------------------------------------------ libraries

def discover_libs(project_dir):
    """(symbol_libs, footprint_libs) as [(name, uri)] from a sibling lib/ dir.

    Looks at `<project>/lib` then `<project>/../lib` — the second is the usual
    layout, one shared library directory serving several board variants.  URIs
    are written relative to ${KIPRJMOD} so the project stays relocatable.
    """
    syms, fps = [], []
    for rel in ("lib", os.path.join("..", "lib")):
        libdir = os.path.join(project_dir, rel)
        if not os.path.isdir(libdir):
            continue
        for path in sorted(glob.glob(os.path.join(libdir, "*.kicad_sym"))):
            syms.append((os.path.splitext(os.path.basename(path))[0],
                         "${KIPRJMOD}/%s/%s" % (rel.replace(os.sep, "/"),
                                                os.path.basename(path))))
        for path in sorted(glob.glob(os.path.join(libdir, "*.pretty"))):
            fps.append((os.path.basename(path)[:-len(".pretty")],
                        "${KIPRJMOD}/%s/%s" % (rel.replace(os.sep, "/"),
                                               os.path.basename(path))))
        if syms or fps:
            break
    return syms, fps


def write_lib_table(path, header, rows, descr):
    body = header
    for name, uri in rows:
        body += LIB_ROW % (name, uri, descr % name)
    body += ")\n"
    with open(path, "w") as fh:
        fh.write(body)
    return len(rows)


def parse_pairs(items, numeric=False):
    """['a=b', ...] -> {'a': 'b'} , values coerced to float when asked."""
    out = {}
    for item in items or ():
        if "=" not in item:
            raise SystemExit("error: expected KEY=VALUE, got %r" % item)
        key, value = item.split("=", 1)
        if numeric:
            try:
                value = float(value)
            except ValueError:
                raise SystemExit("error: %s must be a number, got %r"
                                 % (key, value))
        out[key.strip()] = value
    return out


# ------------------------------------------------------- overrides + re-patch

def load_overrides(project_dir):
    path = os.path.join(project_dir, OVERRIDES_FILE)
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        return json.load(fh)


def save_overrides(project_dir, overrides):
    path = os.path.join(project_dir, OVERRIDES_FILE)
    with open(path, "w") as fh:
        json.dump(overrides, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def repatch(project_dir, name=None, quiet=True):
    """Re-apply hwforge-overrides.json to every .kicad_pro in the directory.

    Idempotent and safe to call when there is nothing to do, so a generator
    can call it unconditionally after SaveBoard.  Returns the list of files
    changed.
    """
    overrides = load_overrides(project_dir)
    if not overrides:
        return []
    pros = ([os.path.join(project_dir, name + ".kicad_pro")] if name
            else sorted(glob.glob(os.path.join(project_dir, "*.kicad_pro"))))
    touched = []
    for pro_path in pros:
        if not os.path.exists(pro_path):
            continue
        with open(pro_path) as fh:
            pro = json.load(fh)
        design = pro.setdefault("board", {}).setdefault("design_settings", {})
        if overrides.get("rule_severities"):
            design.setdefault("rule_severities", {}).update(
                overrides["rule_severities"])
        if overrides.get("rules"):
            design.setdefault("rules", {}).update(overrides["rules"])
        if overrides.get("net_classes"):
            pro.setdefault("net_settings", {})["classes"] = \
                overrides["net_classes"]
        with open(pro_path, "w") as fh:
            json.dump(pro, fh, indent=2)
        touched.append(pro_path)
        if not quiet:
            print("re-patched %s (%d severity override(s))"
                  % (pro_path, len(overrides.get("rule_severities", {}))))
    return touched


def project_doc(name, rules, net_class, severities):
    """A minimal .kicad_pro. KiCad fills in the rest of its defaults on open."""
    return {
        "board": {"design_settings": {
            "rules": rules,
            "defaults": {"board_outline_line_width": 0.1},
            "rule_severities": severities,
        }},
        "meta": {"filename": name + ".kicad_pro", "version": 1},
        "net_settings": {"classes": [net_class]},
        "sheets": [["00000000-0000-0000-0000-000000000000", "Root"]],
        "text_variables": {},
    }


def scaffold(project_dir, name, severities=None, rules=None, net_class=None,
             sym_libs=None, fp_libs=None, quiet=False):
    os.makedirs(project_dir, exist_ok=True)
    severities = dict(severities or {})
    merged_rules = dict(DEFAULT_RULES)
    merged_rules.update(rules or {})
    merged_net = dict(DEFAULT_NET_CLASS)
    merged_net.update(net_class or {})

    found_syms, found_fps = discover_libs(project_dir)
    syms = sym_libs if sym_libs else found_syms
    fps = fp_libs if fp_libs else found_fps
    n_sym = write_lib_table(os.path.join(project_dir, "sym-lib-table"),
                            SYM_TABLE_HEADER, syms, "%s project symbols")
    n_fp = write_lib_table(os.path.join(project_dir, "fp-lib-table"),
                           FP_TABLE_HEADER, fps, "%s project footprints")

    pro_path = os.path.join(project_dir, name + ".kicad_pro")
    with open(pro_path, "w") as fh:
        json.dump(project_doc(name, merged_rules, merged_net, severities),
                  fh, indent=2)

    # Written even when empty: its presence is the signal to a generator that
    # `repatch()` is the project's convention, and it is where the next
    # severity override goes.
    save_overrides(project_dir, {"rule_severities": severities,
                                 "rules": rules or {},
                                 "net_classes": [merged_net]})
    if not quiet:
        print("scaffolded %s (%s): %d symbol lib(s), %d footprint lib(s), "
              "%d severity override(s)" % (project_dir, name, n_sym, n_fp,
                                           len(severities)))
        if severities:
            for rule, level in sorted(severities.items()):
                print("  severity  %s -> %s" % (rule, level))
            print("  remember: re-run with --repatch after pcbnew.SaveBoard()")
    return pro_path


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="See the module docstring for the post-SaveBoard re-patch rule.")
    ap.add_argument("dir", help="project directory (created if absent)")
    ap.add_argument("name", nargs="?",
                    help="project basename, e.g. myboard (omit with --repatch)")
    ap.add_argument("--repatch", action="store_true",
                    help="re-apply %s to the project's .kicad_pro and exit; "
                         "run this after every pcbnew.SaveBoard()"
                         % OVERRIDES_FILE)
    ap.add_argument("--severity", action="append", metavar="RULE=LEVEL",
                    help="DRC severity override, e.g. "
                         "npth_inside_courtyard=warning (repeatable)")
    ap.add_argument("--design-rule", action="append", metavar="KEY=MM",
                    help="override a design rule, e.g. min_clearance=0.15")
    ap.add_argument("--net-class", action="append", metavar="KEY=VALUE",
                    help="override the Default net class, e.g. track_width=0.3")
    ap.add_argument("--sym-lib", action="append", metavar="NAME=URI",
                    help="symbol library row (default: discover ../lib)")
    ap.add_argument("--fp-lib", action="append", metavar="NAME=URI",
                    help="footprint library row (default: discover ../lib)")
    args = ap.parse_args()

    if args.repatch:
        touched = repatch(args.dir, args.name, quiet=False)
        if not touched:
            print("nothing to re-patch in %s (no %s, or no .kicad_pro)"
                  % (args.dir, OVERRIDES_FILE))
        return
    if not args.name:
        ap.error("NAME is required unless --repatch is given")

    net_class = parse_pairs(args.net_class)
    for key in list(net_class):
        if key != "name":
            net_class[key] = float(net_class[key])
    scaffold(args.dir, args.name,
             severities=parse_pairs(args.severity),
             rules=parse_pairs(args.design_rule, numeric=True),
             net_class=net_class,
             sym_libs=list(parse_pairs(args.sym_lib).items()) or None,
             fp_libs=list(parse_pairs(args.fp_lib).items()) or None)


if __name__ == "__main__":
    main()
