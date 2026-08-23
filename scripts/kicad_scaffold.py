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
    python3 scripts/kicad_scaffold.py build/left --repatch \\
        --severity npth_inside_courtyard=warning     # ADDS it to the sidecar

EVOLVING THE OVERRIDE SET.  `--repatch` restores what the sidecar holds, so
adding a demotion to a project's scaffolder flags and then only ever running
`--repatch` changes nothing: the board keeps failing DRC on a rule the project
believes it demoted, and nothing says why.  Two fixes, both here now:

  * `--repatch` accepts `--severity` / `--design-rule` / `--net-class` and
    MERGES them into the sidecar first.  Overrides are additive by nature, so
    this is the same operation as scaffolding, minus the library tables.
  * `--repatch` prints what it restored, and warns when the flags it was handed
    are *wider* than what the sidecar held — the silent case that cost the
    confusion.

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

SCHEMATIC PARITY IS PROMOTED BY DEFAULT — read this before demoting one.

KiCad 10 ships **every** schematic-parity check at `warning`, and the
pipeline's own gate invocation is `--severity-error`, so all five are filtered
out before anything counts them.  The measured consequence: a board missing
eight parts and mis-wiring twenty-one nets gated green, printing `parity ok`
(hexpad rev 3; `--severity-all` on the same board reported 31 parity issues).
That is not a project misconfiguration — it was every hw_forge project, because
nothing promoted them.

So `PARITY_SEVERITIES` below is written into every scaffolded project as a
DEFAULT.  Every other default here is a fab capability limit; these five are
the pipeline's own contract with itself, and the flag alone never enforced it.
A project that genuinely wants one relaxed demotes it explicitly
(`--severity net_conflict=warning`), which puts the decision on the record
where a demotion belongs.
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
# The five schematic-parity checks, PROMOTED TO ERROR in every new project.
# KiCad ships all five at `warning`; `--severity-error` (the gate) then filters
# them out, so `--schematic-parity` cannot fail a build until these exist.  See
# the module docstring.  Ordered as KiCad names them.
PARITY_SEVERITIES = {
    "missing_footprint": "error",           # a symbol with no footprint placed
    "extra_footprint": "error",             # a footprint with no symbol
    "net_conflict": "error",                # a pad wired to a different net
    "footprint_symbol_mismatch": "error",   # pad set != pin set
    "lib_footprint_mismatch": "error",      # board copy != library original
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


def merge_into_overrides(project_dir, severities=None, rules=None,
                         net_class=None, quiet=True):
    """Add overrides to the sidecar without rewriting the library tables.

    Returns (overrides, added) where `added` names only the keys this call
    introduced or changed — which is what the caller prints, because "the
    sidecar already had that" and "the sidecar has it now" are different
    answers to "why is my demotion not taking effect".
    """
    overrides = load_overrides(project_dir)
    added = []

    sev = dict(overrides.get("rule_severities") or {})
    for rule, level in (severities or {}).items():
        if sev.get(rule) != level:
            added.append("severity %s=%s" % (rule, level))
        sev[rule] = level

    merged_rules = dict(overrides.get("rules") or {})
    for key, value in (rules or {}).items():
        if merged_rules.get(key) != value:
            added.append("rule %s=%s" % (key, value))
        merged_rules[key] = value

    classes = overrides.get("net_classes") or [dict(DEFAULT_NET_CLASS)]
    if net_class:
        default = dict(classes[0])
        for key, value in net_class.items():
            if default.get(key) != value:
                added.append("net-class %s=%s" % (key, value))
            default[key] = value
        classes = [default] + list(classes[1:])

    overrides = {"rule_severities": sev, "rules": merged_rules,
                 "net_classes": classes}
    save_overrides(project_dir, overrides)
    if added and not quiet:
        for line in added:
            print("  added to %s: %s" % (OVERRIDES_FILE, line))
    return overrides, added


def repatch(project_dir, name=None, quiet=True, severities=None, rules=None,
            net_class=None):
    """Re-apply hwforge-overrides.json to every .kicad_pro in the directory.

    Idempotent and safe to call when there is nothing to do, so a generator
    can call it unconditionally after SaveBoard.  Returns the list of files
    changed.

    Any severities/rules passed here are merged into the sidecar FIRST, so
    `--repatch --severity foo=warning` is how an override set grows.  Without
    that, a project that added a demotion to its scaffolder flags and only ever
    ran `--repatch` would keep failing DRC on a rule it believed it demoted.
    """
    if severities or rules or net_class:
        merge_into_overrides(project_dir, severities, rules, net_class,
                             quiet=quiet)
    overrides = load_overrides(project_dir)
    if not overrides:
        if not quiet:
            print("no %s in %s — nothing to restore. If a generator's "
                  "SaveBoard() ran,\n  the project file is now pcbnew's "
                  "defaults: scaffold it once with the full flag set."
                  % (OVERRIDES_FILE, project_dir))
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
            # Print what was restored, not just how many: a demotion that is
            # not in this list is a demotion that is not in effect, and that
            # is the whole failure this output exists to make visible.
            sev = overrides.get("rule_severities") or {}
            rul = overrides.get("rules") or {}
            print("re-patched %s" % pro_path)
            for rule, level in sorted(sev.items()):
                print("  severity  %s -> %s" % (rule, level))
            for key, value in sorted(rul.items()):
                print("  rule      %s = %s" % (key, value))
            if not sev and not rul:
                print("  (sidecar holds no severities or design rules)")
            # A sidecar written before parity was promoted restores a project
            # whose parity gate cannot fail.  --repatch is the ONLY scaffolder
            # call a mature generator makes, so this is where that gets seen.
            stale = sorted(r for r in PARITY_SEVERITIES if sev.get(r) != "error")
            if stale:
                print("  note: %d schematic-parity check(s) are not promoted "
                      "to error in this\n        sidecar (%s).\n        KiCad "
                      "ships them at `warning`, so --severity-error filters "
                      "them out and\n        the gate prints `parity ok` "
                      "unenforceably. fix:\n"
                      "          python3 %s %s --repatch %s"
                      % (len(stale), ", ".join(stale),
                         os.path.basename(__file__), project_dir,
                         " ".join("--severity %s=error" % r for r in stale)))
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
    # Parity promotions FIRST, so a project's own flags can still demote one
    # deliberately — the override is the record of that decision.
    merged_sev = dict(PARITY_SEVERITIES)
    merged_sev.update(severities or {})
    demoted = sorted(r for r, level in merged_sev.items()
                     if r in PARITY_SEVERITIES and level != "error")
    severities = merged_sev
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
    #
    # `merged_rules`, not `rules`: the whole point of the sidecar is that
    # SaveBoard() reverts the .kicad_pro to pcbnew's defaults (min_clearance
    # measured coming back as 0.0), so --repatch has to restore the SCAFFOLDED
    # state, not only the fraction of it that happened to arrive on the command
    # line.  Persisting CLI-only rules made every project restate hw_forge's
    # own defaults as --design-rule flags to get them back — and the failure
    # was silent, because the net-class clearance IS persisted and governs
    # track-to-track spacing, so a board could pass a DRC that no longer
    # enforced the board minimum with nothing to say so.
    save_overrides(project_dir, {"rule_severities": severities,
                                 "rules": merged_rules,
                                 "net_classes": [merged_net]})
    if not quiet:
        print("scaffolded %s (%s): %d symbol lib(s), %d footprint lib(s), "
              "%d severity override(s)" % (project_dir, name, n_sym, n_fp,
                                           len(severities)))
        if severities:
            for rule, level in sorted(severities.items()):
                print("  severity  %s -> %s%s"
                      % (rule, level,
                         "   (hw_forge parity default)"
                         if rule in PARITY_SEVERITIES and level == "error"
                         else ""))
            print("  remember: re-run with --repatch after pcbnew.SaveBoard()")
        if demoted:
            # Loud, because it un-gates the check most likely to catch a
            # generated board drifting from its own schematic.
            print("  WARNING: %d schematic-parity check(s) DEMOTED below error "
                  "(%s).\n           `--schematic-parity` can no longer fail "
                  "the gate for these.\n           Record why, next to the "
                  "flag that demoted them." % (len(demoted),
                                               ", ".join(demoted)))
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

    net_class = parse_pairs(args.net_class)
    for key in list(net_class):
        if key != "name":
            net_class[key] = float(net_class[key])

    if args.repatch:
        # Flags given with --repatch are MERGED into the sidecar, so an
        # override set can grow without a full re-scaffold.  Warning when the
        # sidecar was narrower than the flags is the point: that mismatch is
        # exactly the state in which a project's demotion silently does
        # nothing.
        before = load_overrides(args.dir)
        touched = repatch(args.dir, args.name, quiet=False,
                          severities=parse_pairs(args.severity),
                          rules=parse_pairs(args.design_rule, numeric=True),
                          net_class=net_class)
        wanted = parse_pairs(args.severity)
        missing = sorted(k for k, v in wanted.items()
                         if (before.get("rule_severities") or {}).get(k) != v)
        if missing:
            print("  note: %d override(s) were NOT in %s before this run (%s)."
                  "\n        A --repatch-only build would not have applied "
                  "them." % (len(missing), OVERRIDES_FILE,
                             ", ".join(missing)))
        if not touched:
            print("nothing to re-patch in %s (no %s, or no .kicad_pro)"
                  % (args.dir, OVERRIDES_FILE))
        return
    if not args.name:
        ap.error("NAME is required unless --repatch is given")

    scaffold(args.dir, args.name,
             severities=parse_pairs(args.severity),
             rules=parse_pairs(args.design_rule, numeric=True),
             net_class=net_class,
             sym_libs=list(parse_pairs(args.sym_lib).items()) or None,
             fp_libs=list(parse_pairs(args.fp_lib).items()) or None)


if __name__ == "__main__":
    main()
