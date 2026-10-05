#!/usr/bin/env python3
"""Scaffold a KiCad project directory: library tables, .kicad_pro, DRC severities.

Creates the three files a generated project needs before a generator can emit
into it, so nothing depends on the user's global KiCad configuration.  DRC
here is KiCad's design rule check:

  sym-lib-table / fp-lib-table   project-local libraries, auto-discovered from
                                 a sibling `lib/` directory (or given by flag)
  NAME.kicad_pro                 design rules, one Default net class, and any
                                 DRC severity overrides
  NAME.kicad_dru                 the baseline custom rules (see "Custom rules")
  hwforge-overrides.json         the durable record of those overrides

    python3 scripts/kicad_scaffold.py build/left boardname
    python3 scripts/kicad_scaffold.py build/left boardname \\
        --severity npth_inside_courtyard=warning
    python3 scripts/kicad_scaffold.py build/left --repatch
    python3 scripts/kicad_scaffold.py build/left --repatch \\
        --severity npth_inside_courtyard=warning     # adds it to the sidecar
    python3 scripts/kicad_scaffold.py build/left boardname \\
        --stock-fp-lib Resistor_THT --stock-sym-lib Device

Library tables.  A table is written only when a flag (--sym-lib, --fp-lib,
--stock-sym-lib, --stock-fp-lib) or a lib/ library supplies rows for it, or
when no table exists yet (an empty one).  An existing table with nothing to
replace it is left untouched, so a hand-added row survives the scaffolder
run every `make <target>` performs.  A `--stock-*-lib NAME` row points at
KiCad's own library through ${KICAD<major>_FOOTPRINT_DIR} or
${KICAD<major>_SYMBOL_DIR} (major from this kicad-cli, default 10) and is
described "KiCad stock library"; a project row is described "<name> project
footprints" or "<name> project symbols".

The project file.  An existing NAME.kicad_pro is merged into, not replaced:
the design rules, severities, net classes and file name this script owns
are written over what is there, and every other key (text variables, board
setup KiCad added, sheet lists) is kept.

Evolving the override set.  `--repatch` restores what the sidecar holds, so
adding a demotion to a project's scaffolder flags and then only ever running
`--repatch` changes nothing: the board keeps failing DRC on a rule the project
believes it demoted, and nothing says why.  Two fixes, both here now:

  * `--repatch` accepts `--severity` / `--design-rule` / `--net-class` and
    merges them into the sidecar first.  Overrides are additive by nature, so
    this is the same operation as scaffolding, minus the library tables.
  * `--repatch` prints what it restored, and warns when the flags it was handed
    are wider than what the sidecar held.  That mismatch is otherwise silent.

The post-SaveBoard re-patch: read this before writing a generator.

`pcbnew.SaveBoard()` rewrites the sibling `.kicad_pro` from the board object's
own project settings.  A board built with `CreateEmptyBoard()`, which is what
every from-scratch generator does, carries pcbnew's defaults rather than the
file this script wrote, so the save silently reverts everything in it.

Measured on KiCad 10.0.5: a scaffolded `npth_inside_courtyard: warning` comes
back as `error`, and `min_clearance: 0.2` comes back as `0.0`.  The DRC then
fails on a rule the project deliberately demoted, and the board looks broken
when only the project file is.

(A board obtained with `LoadBoard()` keeps the settings it loaded, so an
edit-in-place tool is not exposed.  The from-scratch generator is.)

Overrides must therefore be applied after the last save, not before, which
means something has to remember them across the save.

That something is `hwforge-overrides.json`: a sidecar pcbnew does not touch.
A generator's save path is:

    pcbnew.SaveBoard(out, board)
    import kicad_scaffold; kicad_scaffold.repatch(os.path.dirname(out))

or, equivalently, `kicad_scaffold.py <dir> --repatch` as the next Makefile
line.  `kicad_zonefill.py` already does this for you.

Demote a rule only with a comment saying why the violation is intended.  A
severity override is a design decision on the record, not a way to quiet a
gate.

Fab-relevant DRC checks are promoted too.  KiCad 10.0.5 ships 62 rule
severities; on a real project 19 sit at `warning` and 5 at `ignore`, and the
gate's `--severity-error` filters every one of them out.  `FAB_SEVERITIES`
below promotes the ones that describe a board a fab cannot build or an
assembler will build wrong, each with its reason; `LEFT_SEVERITIES` records
the rest and why they stay.  Measured before choosing (2026-10-03, five gated
boards: hexpad, z_board left/right/combo, mic_buffer): the promoted set fires
only `hole_to_hole` x3 on mic_buffer, a real drill-web defect; promoting
`missing_courtyard` to error would fire 6, 22, 22 and 117 times on community
keyboard footprints, so it moves from `ignore` to `warning` instead.

Custom rules.  `NAME.kicad_dru` starts from
`templates/drc-baseline.kicad_dru`: fab floors KiCad's board defaults are
looser than (PTH hole-to-hole, annular ring, via drill) and connector copper
to edge.  The Makefile runs this script on every `make <target>`, so the rule
file is managed like this:

  * The baseline is written only when NAME.kicad_dru is absent.  An existing
    file is never rewritten, so a project's edits to it (a tuned value, an
    added rule) survive every regeneration.
  * The fork rules live in one block between the lines
    `# hw_forge fork rules begin` and `# hw_forge fork rules end`.  This
    script edits only the lines between those markers, and the markers
    themselves; every other line is left as it is.
  * `--fork-rules` inserts the block (or refreshes its contents from the
    template) when `preflight.fork_drc_probe()` says the kicad-cli in use is
    the fork.  When the probe says stock, an existing block is removed, with
    or without `--fork-rules`, and a WARNING says so.  When the probe cannot
    run, the file is left as it is and a WARNING says so.
  * `--reinstall-rules` overwrites the file with the baseline (plus the fork
    block under the rule above): the deliberate way to discard local edits.

The fork block holds constraints (decoupling_distance, current,
via_under_smd, model_clearance, model_height, zone_islands, zone_min_channel,
thermal_copper, connector_edge, reference_copper) only the forked kicad-cli
compiles.  It is removed on a stock binary because stock kicad-cli 10.0.5 does
not reject a rule file holding an unknown keyword: it drops the WHOLE file,
silently, with exit 0, and every baseline rule in it stops running with it
(measured: a bogus keyword took a firing hole_to_hole rule from 112 hits to
0).  `preflight.py --project` fails a project whose rule file names a fork
keyword when the kicad-cli in use is stock.

Schematic parity is promoted by default; read this before demoting one.

KiCad 10 ships every schematic-parity check at `warning`, and the pipeline's
own gate invocation is `--severity-error`, so all five are filtered out before
anything counts them.  The measured consequence: a board missing eight parts
and mis-wiring twenty-one nets gated green, printing `parity ok`, while
`--severity-all` on that same board reported 31 parity issues.

That was not one project's misconfiguration.  It was every hw_forge project,
because nothing promoted them.

So `PARITY_SEVERITIES` below is written into every scaffolded project as a
default.  Every other default here is a fab capability limit; these five are
the pipeline's own contract with itself, and the flag alone never enforced it.
A project that genuinely wants one relaxed demotes it explicitly
(`--severity net_conflict=warning`), which puts the decision on the record
where a demotion belongs.
"""

import argparse
import glob
import json
import os
import sys

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
# The five schematic-parity checks, promoted to error in every new project.
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

# Fab-relevant checks KiCad 10.0.5 ships below error, promoted.  A board that
# trips one of these is a board a fab rejects or an assembler builds wrong.
FAB_SEVERITIES = {
    "connection_width": "error",        # a copper neck under min_connection
                                        # etches open; silent while that is 0
    "copper_sliver": "error",           # a sliver under the fab floor lifts
                                        # and shorts; fabs flag it at DFM
    "duplicate_footprints": "error",    # two footprints, one ref: the BOM and
                                        # placement file disagree with the board
    "footprint_type_mismatch": "error",  # SMD/THT attr decides what the
                                        # placement file lists
    "hole_to_hole": "error",            # drill web under the fab minimum
                                        # breaks bits (JLC 0.45 PTH)
    "holes_co_located": "error",        # overlapping drills: a fab reject
                                        # (kb/fabs/jlcpcb.md)
    "mirrored_text_on_front_layer": "error",    # prints backwards
    "nonmirrored_text_on_back_layer": "error",  # prints backwards
    "padstack": "error",                # an invalid pad (hole past its copper)
    "text_height": "error",             # under min_text_height the fab cannot
                                        # print it legibly
    "text_thickness": "error",          # same, for stroke width
    "track_dangling": "error",          # a stub to nowhere: unfinished route
                                        # or an antenna
    "via_dangling": "error",            # a drill hit that connects nothing
    "missing_courtyard": "warning",     # from ignore: a part with no courtyard
                                        # is invisible to courtyards_overlap.
                                        # Not error: 6/22/22/117 hits measured
                                        # on proven community footprints; the
                                        # fit contract uses body_bbox instead.
}
# Left where KiCad ships them, deliberately.  Not applied; this is the record.
LEFT_SEVERITIES = {
    "footprint_filters_mismatch": "ignore: generated designs pick footprints "
                                  "in design.py; filters are a browsing aid",
    "footprint_symbol_field_mismatch": "warning: the BOM is exported from the "
                                       "schematic (kicad_bom.py), so a stale "
                                       "board-side field is not what is ordered",
    "isolated_copper": "warning: floating copper is not a fab defect; island "
                       "removal is kicad_zonefill.py's, the check is BACKLOG B5",
    "lib_footprint_issues": "warning: fires on library-table resolution, which "
                            "differs per machine (measured on the fork probe "
                            "board); preflight --project checks the tables",
    "missing_tuning_profile": "warning: length tuning only; no generic board "
                              "has a profile",
    "silk_edge_clearance": "warning: the fab clips silk at the edge; "
                           "kicad_silkcheck.py gates readability",
    "silk_over_copper": "warning: the fab clips silk off pads; "
                        "kicad_silkcheck.py gates text over pads",
    "silk_overlap": "warning: readability, which kicad_silkcheck.py gates",
    "track_not_centered_on_via": "ignore: connectivity still holds by "
                                 "overlap, and the unconnected check catches a "
                                 "real break",
    "tuning_profile_track_geometries": "ignore: length tuning only",
}

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "templates")
BASELINE_RULES = os.path.join(TEMPLATES, "drc-baseline.kicad_dru")
FORK_RULES = os.path.join(TEMPLATES, "drc-fork.kicad_dru")
FORK_BEGIN = "# hw_forge fork rules begin"
FORK_END = "# hw_forge fork rules end"
# Written by earlier versions, which appended the fork rules from this line
# to the end of the file; read so such a file can be refreshed or cleaned.
LEGACY_FORK_MARKER = ("# --- hw_forge fork rules: "
                      "templates/drc-fork.kicad_dru ---")

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
STOCK_DESCR = "KiCad stock library"
DEFAULT_MAJOR = 10


def kicad_major():
    """The major version of the kicad-cli in use, or DEFAULT_MAJOR."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from _kicad_env import cli_version, find_cli, kicad_version_tuple
        cli, _how = find_cli()
        tup = kicad_version_tuple(cli_version(cli) or "") if cli else ()
        return tup[0] if tup else DEFAULT_MAJOR
    except Exception:                                  # pragma: no cover
        return DEFAULT_MAJOR


def stock_rows(names, kind, major=None):
    """[(name, uri)] for KiCad stock libraries: kind "fp" or "sym"."""
    major = major or kicad_major()
    if kind == "fp":
        return [(n, "${KICAD%d_FOOTPRINT_DIR}/%s.pretty" % (major, n))
                for n in names]
    return [(n, "${KICAD%d_SYMBOL_DIR}/%s.kicad_sym" % (major, n))
            for n in names]


# ------------------------------------------------------------------ libraries

def discover_libs(project_dir):
    """(symbol_libs, footprint_libs) as [(name, uri)] from a sibling lib/ dir.

    Looks at `<project>/lib` then `<project>/../lib`.  The second is the usual
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
        stock = uri.startswith(("${KICAD", "$(KICAD"))
        body += LIB_ROW % (name, uri, STOCK_DESCR if stock else descr % name)
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
    introduced or changed.  That is what the caller prints, because "the
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

    Any severities/rules passed here are merged into the sidecar first, so
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
            print("no %s in %s: nothing to restore. If a generator's "
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
            # not in this list is a demotion that is not in effect, which is
            # what this output exists to make visible.
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
            # whose parity gate cannot fail.  --repatch is the only scaffolder
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


def split_fork_block(lines):
    """(start, end) line indices of the fork block, end exclusive, or None.

    The block runs from FORK_BEGIN to FORK_END inclusive.  A legacy file's
    block runs from LEGACY_FORK_MARKER to the end of the file, which is how
    earlier versions wrote it.  A begin marker with no end marker is an
    error: guessing where the block stops could delete a user's own lines.
    """
    for i, line in enumerate(lines):
        if line.strip() == FORK_BEGIN:
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == FORK_END:
                    return i, j + 1
            raise SystemExit("error: %r has no matching %r line; restore it "
                             "or run with --reinstall-rules"
                             % (FORK_BEGIN, FORK_END))
        if line.strip() == LEGACY_FORK_MARKER:
            return i, len(lines)
    return None


def fork_block_lines():
    """The fork template between its markers, without its (version 1)."""
    with open(FORK_RULES) as fh:
        body = [l for l in fh.read().splitlines()
                if l.strip() != "(version 1)"]
    return [FORK_BEGIN] + body + [FORK_END]


def _probe_fork():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import preflight
    from _kicad_env import find_cli
    cli, _how = find_cli()
    return preflight.fork_drc_probe(cli)


def install_rules(project_dir, name, fork=False, quiet=False,
                  reinstall=False):
    """Manage NAME.kicad_dru as the module docstring's "Custom rules" says.

    Writes the baseline only when the file is absent or `reinstall` is set.
    Otherwise edits only the fork block between FORK_BEGIN and FORK_END:
    inserted or refreshed with `fork` on a fork binary, removed on a stock
    one.  Returns the path when the file was written, else None.
    """
    path = os.path.join(project_dir, name + ".kicad_dru")
    fresh = reinstall or not os.path.exists(path)
    old = None                    # what is on disk; None when rewriting
    if fresh:
        with open(BASELINE_RULES) as fh:
            text = fh.read()
    else:
        with open(path) as fh:
            old = text = fh.read()
    lines = text.splitlines()
    span = split_fork_block(lines)
    notes = []
    if fork or span:
        state, detail = _probe_fork()
        if state == "fork" and fork:
            block = fork_block_lines()
            lines = (lines[:span[0]] + block + lines[span[1]:] if span
                     else lines + block)
            notes.append("fork block %s" % ("refreshed" if span
                                             else "inserted"))
        elif state == "stock" and span:
            lines = lines[:span[0]] + lines[span[1]:]
            notes.append("fork block removed")
            print("  WARNING: removed the fork rules from %s: this kicad-cli "
                  "is stock (%s), and a stock binary drops a rule file that "
                  "names a fork keyword whole, silently"
                  % (os.path.basename(path), detail))
        elif state == "stock":
            print("  WARNING: --fork-rules not installed in %s: this "
                  "kicad-cli is stock (%s).  Set KICAD_CLI to the forked "
                  "kicad-cli to install them" % (os.path.basename(path),
                                                 detail))
        elif state != "fork":
            print("  WARNING: fork probe failed (%s); %s left as it is"
                  % (detail, os.path.basename(path)))
    text = "\n".join(lines) + "\n"
    if text == old:
        if not quiet:
            print("  rules     kept %s (exists; --reinstall-rules overwrites "
                  "it)" % os.path.basename(path))
        return None
    with open(path, "w") as fh:
        fh.write(text)
    if not quiet:
        print("  rules     %s %s%s" % (
            "reinstalled" if reinstall else "wrote" if fresh else "updated",
            os.path.basename(path),
            " (%s)" % ", ".join(notes) if notes else ""))
    return path


def merge_project(pro_path, name, rules, net_class, severities):
    """The .kicad_pro to write: the existing file with this script's keys
    set, or a minimal one when there is none."""
    fresh = project_doc(name, rules, net_class, severities)
    try:
        with open(pro_path) as fh:
            pro = json.load(fh)
    except (OSError, ValueError):
        return fresh, False
    design = pro.setdefault("board", {}).setdefault("design_settings", {})
    design.setdefault("rules", {}).update(rules)
    design.setdefault("rule_severities", {}).update(severities)
    design.setdefault("defaults", {}).setdefault(
        "board_outline_line_width", 0.1)
    # setdefault first: the right-hand side reads net_settings, and a
    # .kicad_pro without that key must not raise KeyError.
    nets = pro.setdefault("net_settings", {})
    nets["classes"] = [net_class] + [
        c for c in (nets.get("classes") or [])
        if c.get("name") != net_class.get("name")]
    pro.setdefault("meta", {})["filename"] = name + ".kicad_pro"
    pro["meta"].setdefault("version", 1)
    pro.setdefault("sheets", fresh["sheets"])
    pro.setdefault("text_variables", {})
    return pro, True


def scaffold(project_dir, name, severities=None, rules=None, net_class=None,
             sym_libs=None, fp_libs=None, quiet=False, fork_rules=False,
             custom_rules=True, reinstall_rules=False, stock_sym=None,
             stock_fp=None):
    os.makedirs(project_dir, exist_ok=True)
    # Rules first: an unterminated fork block then stops before anything
    # else is written.
    if custom_rules:
        install_rules(project_dir, name, fork=fork_rules, quiet=quiet,
                      reinstall=reinstall_rules)
    # Parity promotions go first, so a project's own flags can still demote
    # one deliberately.  The override is the record of that decision.
    merged_sev = dict(FAB_SEVERITIES)
    merged_sev.update(PARITY_SEVERITIES)
    merged_sev.update(severities or {})
    demoted = sorted(r for r, level in merged_sev.items()
                     if r in PARITY_SEVERITIES and level != "error")
    severities = merged_sev
    merged_rules = dict(DEFAULT_RULES)
    merged_rules.update(rules or {})
    merged_net = dict(DEFAULT_NET_CLASS)
    merged_net.update(net_class or {})

    found_syms, found_fps = discover_libs(project_dir)
    major = kicad_major() if (stock_sym or stock_fp) else DEFAULT_MAJOR
    syms = (list(sym_libs or found_syms)
            + stock_rows(stock_sym or (), "sym", major))
    fps = (list(fp_libs or found_fps)
           + stock_rows(stock_fp or (), "fp", major))
    tables = []
    for fname, header, rows, descr in (
            ("sym-lib-table", SYM_TABLE_HEADER, syms, "%s project symbols"),
            ("fp-lib-table", FP_TABLE_HEADER, fps, "%s project footprints")):
        path = os.path.join(project_dir, fname)
        if rows or not os.path.exists(path):
            write_lib_table(path, header, rows, descr)
            tables.append("%s: %d row(s) written" % (fname, len(rows)))
        else:
            tables.append("%s: kept (no flag or lib/ library supplies rows)"
                          % fname)

    pro_path = os.path.join(project_dir, name + ".kicad_pro")
    pro, merged = merge_project(pro_path, name, merged_rules, merged_net,
                                severities)
    with open(pro_path, "w") as fh:
        json.dump(pro, fh, indent=2)

    # Written even when empty: its presence is the signal to a generator that
    # `repatch()` is the project's convention, and it is where the next
    # severity override goes.
    #
    # `merged_rules`, not `rules`: the whole point of the sidecar is that
    # SaveBoard() reverts the .kicad_pro to pcbnew's defaults (min_clearance
    # measured coming back as 0.0), so --repatch has to restore the scaffolded
    # state, not only the fraction of it that happened to arrive on the command
    # line.  Persisting only the command-line rules made every project restate
    # hw_forge's own defaults as --design-rule flags to get them back.
    #
    # That failure was silent, because the net-class clearance is persisted and
    # governs track-to-track spacing, so a board could pass a DRC that no
    # longer enforced the board minimum with nothing to say so.
    save_overrides(project_dir, {"rule_severities": severities,
                                 "rules": merged_rules,
                                 "net_classes": [merged_net]})
    if not quiet:
        print("scaffolded %s (%s): %s; %s %s; %d severity override(s)"
              % (project_dir, name, "; ".join(tables),
                 "merged into" if merged else "wrote",
                 os.path.basename(pro_path), len(severities)))
        if severities:
            for rule, level in sorted(severities.items()):
                print("  severity  %s -> %s%s"
                      % (rule, level,
                         "   (hw_forge parity default)"
                         if rule in PARITY_SEVERITIES and level == "error"
                         else "   (hw_forge fab default)"
                         if FAB_SEVERITIES.get(rule) == level else ""))
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
    ap.add_argument("--stock-sym-lib", action="append", metavar="NAME",
                    help="a KiCad stock symbol library row, URI "
                         "${KICAD<major>_SYMBOL_DIR}/NAME.kicad_sym "
                         "(repeatable)")
    ap.add_argument("--stock-fp-lib", action="append", metavar="NAME",
                    help="a KiCad stock footprint library row, URI "
                         "${KICAD<major>_FOOTPRINT_DIR}/NAME.pretty "
                         "(repeatable)")
    ap.add_argument("--fork-rules", action="store_true",
                    help="insert templates/drc-fork.kicad_dru as a marked "
                         "block in NAME.kicad_dru when the kicad-cli in use "
                         "evaluates the fork constraints "
                         "(preflight.fork_drc_probe); a stock binary gets "
                         "the block removed instead")
    ap.add_argument("--reinstall-rules", action="store_true",
                    help="overwrite NAME.kicad_dru with the baseline, "
                         "discarding local edits (default: an existing file "
                         "is kept, and only its fork block is managed)")
    ap.add_argument("--no-rules", action="store_true",
                    help="do not write NAME.kicad_dru")
    args = ap.parse_args()

    net_class = parse_pairs(args.net_class)
    for key in list(net_class):
        if key != "name":
            net_class[key] = float(net_class[key])

    if args.repatch:
        # Flags given with --repatch are merged into the sidecar, so an
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
             fp_libs=list(parse_pairs(args.fp_lib).items()) or None,
             fork_rules=args.fork_rules, custom_rules=not args.no_rules,
             reinstall_rules=args.reinstall_rules,
             stock_sym=args.stock_sym_lib, stock_fp=args.stock_fp_lib)


if __name__ == "__main__":
    main()
