#!/usr/bin/env python3
"""Environment doctor: prove the toolchain works before designing anything.

Run this first, every session.  A toolchain problem that surfaces mid-design
gets mistaken for a design problem.  That is how KiCad 10's `Flip()` enum
change presented: 295 phantom violations from the design rule check (DRC) on a
previously clean board.

Checking versions up front, and diffing one throwaway regeneration against a
known-good artifact, separates "the tools changed" from "my design is wrong".

    python3 scripts/preflight.py
    python3 scripts/preflight.py --project build/left
    python3 scripts/preflight.py --project build/left --smoke

Every failing line carries the exact command that fixes it.  Exit status is 0
only when nothing failed; warnings do not fail the run.

With --project it also checks the project: every library-table URI resolves
(KiCad path variables such as ${KICAD10_FOOTPRINT_DIR} resolved from the
environment, KiCad's own kicad_common.json, or the install; one it cannot
resolve is a warning naming it, never an ok), every 3D model link of the
project's own footprints and of every footprint placed on a board resolves,
`design.py` imports under the system python and under KiCad's bundled one,
and a project Makefile carries the shipped template's version stamp
(templates/Makefile, `hw_forge Makefile template version: N`).

--smoke needs a project whose board is already known good (its gate passes).
It re-runs the gate, then regenerates or reloads the board through pcbnew and
re-gates it, and diffs the violation counts.  A clean board that comes back
dirty after a round-trip is a toolchain regression, not a design error, so stop
and fix the toolchain.
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True      # a doctor must not modify what it examines
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _kicad_env import (cli_version, find_cli, find_python, have_pcbnew,
                        kicad_version_tuple, run)

# KiCad 10 is the version every trap documented in this repo was measured on.
# 9 mostly works; 8's headless zone filler does not.  KiCad 11 removes the
# pcbnew module built with SWIG (the Simplified Wrapper and Interface
# Generator) in favour of the inter-process communication (IPC) API, so it
# needs a migration rather than a warning.
MIN_KICAD = (9, 0)
KNOWN_GOOD_KICAD = (10, 0)
TOO_NEW_KICAD = (11, 0)


class Report(object):
    """Collects pass/warn/fail lines. Every failure carries its fix command."""

    def __init__(self):
        self.rows = []       # (state, label, detail, fix)

    def ok(self, label, detail=""):
        self.rows.append(("ok", label, detail, ""))

    def warn(self, label, detail="", fix=""):
        self.rows.append(("warn", label, detail, fix))

    def fail(self, label, detail="", fix=""):
        self.rows.append(("FAIL", label, detail, fix))

    @property
    def failed(self):
        return [r for r in self.rows if r[0] == "FAIL"]

    @property
    def warned(self):
        return [r for r in self.rows if r[0] == "warn"]

    def render(self):
        width = max([len(r[1]) for r in self.rows] or [0])
        for state, label, detail, fix in self.rows:
            print("  %-4s %-*s %s" % (state, width, label, detail))
            if fix:
                for line in fix.splitlines():
                    print("       %s%s" % (" " * width, line))
        print()
        n_fail, n_warn = len(self.failed), len(self.warned)
        total = len(self.rows)
        if n_fail:
            print("%d of %d checks FAILED%s: fix the lines above before "
                  "starting design work"
                  % (n_fail, total, ", %d warning(s)" % n_warn if n_warn else ""))
        elif n_warn:
            print("all %d checks passed, %d warning(s)" % (total, n_warn))
        else:
            print("all %d checks passed" % total)


# ------------------------------------------------------------- toolchain

def check_toolchain(rep):
    """Returns (cli, kpy); either may be None if unusable."""
    cli, how = find_cli()
    if not cli:
        rep.fail("kicad-cli", how,
                 "fix: install KiCad 10 from https://kicad.org/download/\n"
                 "fix: or point at an existing install:\n"
                 "     export KICAD_ROOT=/Applications/KiCad/KiCad.app/Contents")
        cli = None
    else:
        version = cli_version(cli)
        if not version:
            rep.fail("kicad-cli", "%s will not execute (via %s)" % (cli, how),
                     "fix: xattr -dr com.apple.quarantine "
                     "/Applications/KiCad/KiCad.app\n"
                     "fix: or reinstall KiCad")
            cli = None
        else:
            tup = kicad_version_tuple(version)
            detail = "%s  (%s, via %s)" % (version, cli, how)
            if tup and tup >= TOO_NEW_KICAD:
                rep.warn("kicad-cli", detail,
                         "note: KiCad 11 drops the SWIG `pcbnew` module for "
                         "the IPC API (kipy).\n"
                         "fix: port generators to kipy, or keep a KiCad 10 "
                         "install and set KICAD_ROOT to it")
            elif tup and tup < MIN_KICAD:
                rep.fail("kicad-cli", detail,
                         "fix: upgrade to KiCad 10; KiCad 8's headless zone "
                         "filler aborts without a display")
            elif tup and tup[:2] != KNOWN_GOOD_KICAD:
                rep.warn("kicad-cli", detail,
                         "note: this pipeline's traps were measured on KiCad "
                         "%d.%d" % KNOWN_GOOD_KICAD)
            else:
                rep.ok("kicad-cli", detail)

    kpy, how = find_python()
    if not kpy:
        rep.fail("kicad python", how,
                 "fix: install KiCad 10 (its bundle ships the only "
                 "interpreter that can import pcbnew on macOS)\n"
                 "fix: or set KICAD_PYTHON=/path/to/python3")
        return cli, None

    ok, detail = have_pcbnew(kpy)
    if not ok:
        rep.fail("pcbnew import", "%s: %s" % (kpy, detail),
                 "fix: run generators with KiCad's bundled interpreter:\n"
                 "     KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/"
                 "Python.framework/Versions/Current/bin/python3\n"
                 "     $KPY scripts/kicad_zonefill.py BOARD.kicad_pcb")
        return cli, None

    rep.ok("kicad python", "%s  (pcbnew %s, via %s)" % (kpy, detail, how))
    check_pcbnew_api(rep, kpy)
    return cli, kpy


def check_pcbnew_api(rep, kpy):
    """Assert the pcbnew APIs whose behaviour this pipeline depends on."""
    probe = (
        "import pcbnew, json\n"
        "out = {}\n"
        "out['flip_tb'] = hasattr(pcbnew, 'FLIP_DIRECTION_TOP_BOTTOM')\n"
        "out['zone_filler'] = hasattr(pcbnew, 'ZONE_FILLER')\n"
        "out['island_area'] = hasattr(pcbnew, 'ISLAND_REMOVAL_MODE_AREA')\n"
        "print(json.dumps(out))\n")
    proc = run([kpy, "-c", probe])
    if proc.returncode != 0:
        rep.fail("pcbnew API probe", (proc.stderr or "").strip()[:200],
                 "fix: reinstall KiCad 10")
        return
    try:
        got = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        rep.warn("pcbnew API probe", "unexpected output", "")
        return

    if got.get("flip_tb"):
        # The trap: BOARD_ITEM.Flip() takes a FLIP_DIRECTION enum in KiCad 10,
        # and that enum's LEFT_RIGHT member is 0.  So the KiCad 8 idiom
        # `Flip(centre, False)` silently became a left-right mirror, which is a
        # top-bottom mirror plus 180 degrees. Every back-side footprint came
        # out rotated 180, pads swapped ends, and a clean board reported 295
        # violations. Always pass FLIP_DIRECTION_TOP_BOTTOM explicitly.
        rep.ok("Flip() enum", "FLIP_DIRECTION_TOP_BOTTOM present: pass it "
                              "explicitly, never False")
    else:
        rep.warn("Flip() enum", "FLIP_DIRECTION_TOP_BOTTOM missing "
                                "(pre-KiCad-10 signature)",
                 "note: on this build Flip(centre, False) means top-bottom;\n"
                 "      on KiCad 10 the same call means LEFT-RIGHT and rotates "
                 "every back-side part 180 degrees")
    if got.get("zone_filler"):
        rep.ok("ZONE_FILLER", "headless zone fill available")
    else:
        rep.fail("ZONE_FILLER", "pcbnew has no ZONE_FILLER",
                 "fix: upgrade to KiCad 10")
    if got.get("island_area"):
        rep.ok("island removal", "ISLAND_REMOVAL_MODE_AREA available: use it "
                                 "for via-fed zones")
    else:
        rep.warn("island removal", "ISLAND_REMOVAL_MODE_AREA missing",
                 "note: connectivity-based island removal does not count vias "
                 "and will delete a via-fed pour")


def compiles(path):
    """Does this file parse? (None on success, else the error message.)

    Uses the builtin `compile`, not py_compile: py_compile writes a .pyc into
    the target's __pycache__, and a doctor must not modify what it examines.
    """
    try:
        with open(path) as fh:
            compile(fh.read(), path, "exec")
    except (SyntaxError, ValueError) as exc:
        return "%s: %s" % (type(exc).__name__, exc)
    except OSError as exc:
        return str(exc)
    return None


def check_self(rep):
    """Every sibling script must at least parse."""
    here = os.path.dirname(os.path.abspath(__file__))
    scripts = sorted(glob.glob(os.path.join(here, "*.py")))
    # kicad_zonefill imports pcbnew at module scope by design, so parsing is
    # as far as a check under the system python can go.
    broken = [os.path.basename(p) for p in scripts if compiles(p)]
    if broken:
        rep.fail("hw_forge scripts", "will not compile: %s" % ", ".join(broken),
                 "fix: this is a bug in hw_forge, not your project")
    else:
        rep.ok("hw_forge scripts", "%d script(s) compile" % len(scripts))


def check_router(rep):
    """Non-fatal: is a Specctra-speaking autorouter reachable.

    Only the hybrid-routing flow (references/autorouting.md) needs this, and
    only for boards that opt into it, so a missing router is a warning, not a
    failure. Scripted routing is unaffected either way.

    Discovery (`find_java` / `find_freerouting_jar`) lives in kicad_route.py
    and is shared, not duplicated, here and in scripts/hw_install.py --check,
    so all three tools agree on where the toolchain lives. `find_java`
    itself now probes every candidate JRE's own version rather than trusting
    a fixed path order: verified 2026-09-20, macOS's own /usr/bin/java
    (OpenJDK 21) cannot run the pinned Freerouting v2.4.1 jar (needs Java
    25), while /opt/homebrew/opt/openjdk/bin/java (Homebrew) does.
    """
    import kicad_route
    java, java_how = kicad_route.find_java()
    jar, jar_how = kicad_route.find_freerouting_jar()
    router_fix = ("fix: python3 scripts/hw_install.py --router    "
                 "(pinned version + checksum + smoke test)")
    if java and jar:
        rep.ok("autorouter", "freerouting jar via %s, java via %s"
               % (jar_how, java_how))
    elif java:
        rep.warn("autorouter", "java ok (%s), no freerouting jar (%s)"
                 % (java_how, jar_how),
                 router_fix + "\n" + kicad_route.jar_install_hint())
    elif jar:
        rep.warn("autorouter", "freerouting jar found (%s), no java (%s)"
                 % (jar_how, java_how), kicad_route.java_install_hint())
    else:
        rep.warn("autorouter", "no java and no freerouting jar; the hybrid "
                 "autorouting flow is unavailable, scripted routing is "
                 "unaffected",
                 router_fix + "\n" + kicad_route.jar_install_hint())


# ------------------------------------------------- fork DRC capability probe

# DRC constraints that only the forked kicad-cli compiles.  A rule file naming
# any of them must never reach a stock binary: stock 10.0.5 does not refuse
# such a file, it drops the WHOLE file without a message and exits 0, so every
# stock rule in it stops running too (measured 2026-10-03: a file holding a
# track_width rule and a connector_edge rule gave 150 track_width hits on the
# fork and 0 on stock).  The fork exits 3 with "DRC incomplete: could not
# compile custom design rules." on a keyword it does not know.
FORK_KEYWORDS = ("decoupling_distance", "current", "via_under_smd",
                 "model_clearance", "model_height", "zone_islands",
                 "zone_min_channel", "thermal_copper", "connector_edge",
                 "reference_copper")
_FORK_KEYWORD = re.compile(r"\(\s*constraint\s+(%s)\b" % "|".join(FORK_KEYWORDS))

# The probe board: a 30 x 30 mm outline and one footprint J1 whose 5 x 5 mm
# courtyard sits 3 mm from the west edge, so a connector_edge (max 0.5mm)
# rule must fire on any binary that evaluates it.
_PROBE_PCB = """(kicad_pcb
	(version 20260206)
	(generator "pcbnew")
	(generator_version "10.0")
	(general (thickness 1.6))
	(paper "A4")
	(layers
		(0 "F.Cu" signal)
		(2 "B.Cu" signal)
		(25 "Edge.Cuts" user)
		(31 "F.CrtYd" user "F.Courtyard")
		(29 "B.CrtYd" user "B.Courtyard")
	)
	(setup (pad_to_mask_clearance 0))
	(net 0 "")
	(footprint "probe:J"
		(layer "F.Cu")
		(uuid "11111111-1111-1111-1111-111111111111")
		(at 5.5 15)
		(property "Reference" "J1" (at 0 -4 0) (layer "F.Cu") (uuid "11111111-1111-1111-1111-111111111112") (hide yes) (effects (font (size 1 1) (thickness 0.15))))
		(property "Value" "probe" (at 0 4 0) (layer "F.Cu") (uuid "11111111-1111-1111-1111-111111111113") (hide yes) (effects (font (size 1 1) (thickness 0.15))))
		(fp_poly (pts (xy -2.5 -2.5) (xy 2.5 -2.5) (xy 2.5 2.5) (xy -2.5 2.5))
			(stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "11111111-1111-1111-1111-111111111114"))
	)
	(gr_rect (start 0 0) (end 30 30) (stroke (width 0.05) (type default)) (fill no) (layer "Edge.Cuts") (uuid "22222222-2222-2222-2222-222222222222"))
)
"""
_PROBE_DRU = """(version 1)
(rule "probe_connector_edge"
	(constraint connector_edge (max 0.5mm))
	(condition "A.Reference == 'J1'"))
"""


# Constraint keywords stock KiCad 10.0.5 compiles: the switch in
# DRC_RULES_PARSER::parseConstraint (pcbnew/drc/drc_rule_parser.cpp at tag
# 10.0.5), plus the three deprecated spellings it still accepts with a
# warning (mechanical_clearance, mechanical_hole_clearance, hole).  Any other
# keyword makes stock drop the whole file, silently, exit 0.
STOCK_CONSTRAINTS = (
    "annular_width", "assertion", "bridged_mask", "clearance",
    "connection_width", "courtyard_clearance", "creepage", "diff_pair_gap",
    "diff_pair_uncoupled", "disallow", "edge_clearance", "hole",
    "hole_clearance", "hole_size", "hole_to_hole", "length",
    "mechanical_clearance", "mechanical_hole_clearance",
    "min_resolved_spokes", "physical_clearance", "physical_hole_clearance",
    "silk_clearance", "skew", "solder_mask_expansion", "solder_mask_sliver",
    "solder_paste_abs_margin", "solder_paste_rel_margin", "text_height",
    "text_thickness", "thermal_relief_gap", "thermal_spoke_width",
    "track_angle", "track_segment_length", "track_width", "via_count",
    "via_dangling", "via_diameter", "zone_connection")
_ANY_CONSTRAINT = re.compile(r"\(\s*constraint\s+([A-Za-z_][A-Za-z0-9_]*)")

# The per-violation keys the fork's report contract adds (reports.md in the
# fork, schema drc.v1.json).  Each is null when it does not apply, never
# missing, so presence of the key is the signal, not its value.
MACHINE_KEYS = ("rule", "rule_source", "constraint", "actual", "required")

_CAPS = {}                  # per process only: one probe per run, no disk cache


def drc_capabilities(cli):
    """What this kicad-cli's DRC and ERC accept and write, probed once.

    Returns a dict:

      severity_override      `pcb drc --help` lists --severity-override
      strict_rules           `pcb drc --help` lists --strict-rules
      erc_severity_override  `sch erc --help` lists --severity-override
      machine_fields         the probe report's violations carry MACHINE_KEYS
                             and its items carry `reference`
      fork_rules             "fork" | "stock" | "error", fork_drc_probe's verdict
      detail                 that verdict's detail string

    The flags are read from the help text, the fields from one DRC run on the
    probe board below.  Memoised per process and per binary, never on disk:
    a rebuilt fork must be re-probed by the next run.
    """
    key = os.path.realpath(cli) if cli else None
    if key in _CAPS:
        return _CAPS[key]
    caps = {"severity_override": False, "strict_rules": False,
            "erc_severity_override": False, "machine_fields": False,
            "fork_rules": "error", "detail": "no kicad-cli"}
    if cli:
        try:
            drc = run([cli, "pcb", "drc", "--help"])
            erc = run([cli, "sch", "erc", "--help"])
            drc_help = (drc.stdout or "") + (drc.stderr or "")
            erc_help = (erc.stdout or "") + (erc.stderr or "")
            caps["severity_override"] = "--severity-override" in drc_help
            caps["strict_rules"] = "--strict-rules" in drc_help
            caps["erc_severity_override"] = "--severity-override" in erc_help
        except OSError as exc:
            caps["detail"] = str(exc)
            _CAPS[key] = caps
            return caps
        state, detail, report = _probe_run(cli)
        caps["fork_rules"], caps["detail"] = state, detail
        caps["machine_fields"] = has_machine_fields(report)
    _CAPS[key] = caps
    return caps


def has_machine_fields(report):
    """True when any finding in a DRC/ERC report carries the fork's keys."""
    if not isinstance(report, dict):
        return False
    found = [v for key in ("violations", "schematic_parity",
                           "unconnected_items")
             for v in report.get(key) or []]
    found += [v for sheet in report.get("sheets") or []
              for v in sheet.get("violations") or []]
    return any(all(k in v for k in MACHINE_KEYS)
               and all("reference" in item for item in v.get("items") or [])
               for v in found)


def unknown_constraints(path, known):
    """Constraint keywords in rule file `path` that are not in `known`."""
    try:
        with open(path, errors="replace") as fh:
            text = "\n".join(l for l in fh.read().splitlines()
                             if not l.lstrip().startswith("#"))
    except OSError:
        return []
    return sorted(set(_ANY_CONSTRAINT.findall(text)) - set(known))


def fork_drc_probe(cli):
    """("fork" | "stock" | "error", detail): does `cli` evaluate fork rules?

    Decided by the JSON report holding a violation of type connector_edge,
    never by stdout or the exit code: on a fork keyword stock prints nothing
    and exits 0.  A lib_footprint_issues finding also appears on both
    binaries, in a number that depends on the machine's library tables, so
    the count is not a signal either.  Shares drc_capabilities()'s one run.
    """
    caps = drc_capabilities(cli)
    return caps["fork_rules"], caps["detail"]


def _probe_run(cli):
    """(state, detail, report_or_None): one DRC run on the probe board."""
    tmp = tempfile.mkdtemp(prefix="hwforge_forkprobe_")
    try:
        for name, text in (("probe.kicad_pcb", _PROBE_PCB),
                           ("probe.kicad_dru", _PROBE_DRU),
                           ("probe.kicad_pro", '{ "meta": { "filename": '
                                               '"probe.kicad_pro", '
                                               '"version": 3 } }\n')):
            with open(os.path.join(tmp, name), "w") as fh:
                fh.write(text)
        out = os.path.join(tmp, "probe.json")
        proc = run([cli, "pcb", "drc", "--severity-all", "--format", "json",
                    "-o", out, os.path.join(tmp, "probe.kicad_pcb")])
        if not os.path.exists(out):
            return "error", ((proc.stderr or proc.stdout or "").strip()
                             .splitlines() or ["no report"])[-1], None
        with open(out) as fh:
            report = json.load(fh)
        hit = [v for v in report.get("violations") or []
               if v.get("type") == "connector_edge"]
        if hit:
            return ("fork", hit[0].get("description", "connector_edge fired"),
                    report)
        return ("stock", "no connector_edge violation in the probe report",
                report)
    except (OSError, ValueError) as exc:
        return "error", str(exc), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fork_keywords_in(path):
    """The fork-only constraint keywords a rule file names."""
    try:
        with open(path, errors="replace") as fh:
            text = "\n".join(l for l in fh.read().splitlines()
                             if not l.lstrip().startswith("#"))
    except OSError:
        return []
    return sorted(set(_FORK_KEYWORD.findall(text)))


def check_fork_drc(rep, cli):
    """Non-fatal: can this kicad-cli run templates/drc-fork.kicad_dru?"""
    state, detail = fork_drc_probe(cli)
    if state == "fork":
        rep.ok("fork DRC rules", "this kicad-cli evaluates them (%s); "
               "kicad_scaffold.py --fork-rules may install "
               "templates/drc-fork.kicad_dru" % detail)
    elif state == "stock":
        rep.warn("fork DRC rules", "this kicad-cli does not evaluate the "
                 "fork constraints (%s); the baseline rules apply" % detail,
                 "note: never install drc-fork.kicad_dru for this binary. "
                 "Stock kicad-cli drops a\n     rule file holding one "
                 "unknown keyword WHOLE, silently, exit 0: every stock\n"
                 "     rule in the file would stop running with it.")
    else:
        rep.warn("fork DRC rules", "probe did not run: %s" % detail, "")
    caps = drc_capabilities(cli)
    if not cli:
        return
    have = [name for name, key in (("--severity-override", "severity_override"),
                                   ("--strict-rules", "strict_rules"),
                                   ("machine fields", "machine_fields"))
            if caps[key]]
    if len(have) == 3:
        rep.ok("DRC report contract", "%s: kicad_gate.py enforces parity and "
               "fab severities by override, and tells a bad rule file (exit 8) "
               "from a load failure (exit 3)" % ", ".join(have))
    else:
        rep.ok("DRC report contract", "stock (%s): kicad_gate.py enforces "
               "severities through the .kicad_pro and scans the rule file "
               "for keywords this binary drops" % (", ".join(have) or
                                                    "no fork flags or fields"))


# --------------------------------------------------------------- project

def check_project(rep, project_dir, cli, kpy=None):
    """Check one project directory: files, lib tables, generators, venv."""
    if not os.path.isdir(project_dir):
        rep.fail("project dir", "no such directory: %s" % project_dir,
                 "fix: pass an existing directory to --project")
        return None

    stems = {os.path.splitext(e)[0] for e in os.listdir(project_dir)
             if os.path.splitext(e)[1] in (".kicad_pro", ".kicad_sch",
                                           ".kicad_pcb")}
    kicad_dirs = []
    if stems:
        kicad_dirs = [(project_dir, s) for s in sorted(stems)]
    else:
        # A project root usually holds board variants one level down.
        for entry in sorted(os.listdir(project_dir)):
            sub = os.path.join(project_dir, entry)
            if not os.path.isdir(sub):
                continue
            sub_stems = {os.path.splitext(e)[0] for e in os.listdir(sub)
                         if os.path.splitext(e)[1] == ".kicad_pcb"}
            kicad_dirs += [(sub, s) for s in sorted(sub_stems)]

    if not kicad_dirs:
        rep.warn("kicad projects", "none found under %s" % project_dir,
                 "fix: scaffold one: python3 scripts/kicad_scaffold.py "
                 "%s NAME" % os.path.join(project_dir, "boardname"))
    else:
        rep.ok("kicad projects", "%d found: %s"
               % (len(kicad_dirs),
                  ", ".join(n for _, n in kicad_dirs[:6])
                  + (" ..." if len(kicad_dirs) > 6 else "")))

    for directory, name in kicad_dirs:
        check_lib_tables(rep, directory, name, cli)

    check_models(rep, project_dir, kicad_dirs)
    check_board_models(rep, kicad_dirs)
    check_rule_files(rep, kicad_dirs, cli)
    check_generators(rep, project_dir, kpy)
    check_makefile(rep, project_dir)
    check_case_env(rep, project_dir)
    return kicad_dirs


def check_rule_files(rep, kicad_dirs, cli):
    """A project rule file naming fork keywords, on a stock kicad-cli, is a
    FAIL: that binary drops the whole file, stock rules included, and the
    gate then passes on rules it never ran."""
    risky = []
    for directory, name in kicad_dirs or ():
        path = os.path.join(directory, name + ".kicad_dru")
        found = fork_keywords_in(path)
        if found:
            risky.append((path, found))
    if not risky:
        return
    state, detail = fork_drc_probe(cli)
    for path, found in risky:
        label = "rules %s" % os.path.basename(path)
        if state == "fork":
            rep.ok(label, "fork keywords %s, and this kicad-cli evaluates "
                   "them" % ", ".join(found))
        else:
            rep.fail(label, "names fork-only keywords (%s) and this kicad-cli "
                     "does not evaluate them (%s): it drops the WHOLE file, "
                     "stock rules included" % (", ".join(found), detail),
                     "fix: run DRC with the forked kicad-cli (KICAD_CLI=...), "
                     "or remove the fork block\n     from the rule file "
                     "(kicad_scaffold.py DIR NAME removes it on a stock "
                     "kicad-cli)")


# KiCad's own path variables, by suffix, and the directory each names under
# the install's shared-data root.
_KICAD_VAR = re.compile(r"^KICAD(\d*)_(FOOTPRINT|SYMBOL|3DMODEL|TEMPLATE)_DIR$")
_VAR_DIRS = {"FOOTPRINT": "footprints", "SYMBOL": "symbols",
             "3DMODEL": "3dmodels", "TEMPLATE": "template"}
_VAR_REF = re.compile(r"\$\{([A-Za-z0-9_]+)\}|\$\(([A-Za-z0-9_]+)\)")


def kicad_share_dirs(cli=None):
    """Candidate shared-data roots: KICAD_ROOT, the install kicad-cli is in,
    the platform defaults."""
    roots = []
    bases = [os.environ.get("KICAD_ROOT")] if os.environ.get("KICAD_ROOT") \
        else []
    if cli:
        real = os.path.realpath(cli)
        bases.append(os.path.dirname(os.path.dirname(real)))   # .../Contents
        bases.append(os.path.dirname(os.path.dirname(real)))   # .../usr
    bases += ["/Applications/KiCad/KiCad.app/Contents", "/usr", "/usr/local"]
    for base in bases:
        for rel in ("SharedSupport", os.path.join("share", "kicad")):
            path = os.path.join(base, rel)
            if os.path.isdir(path) and path not in roots:
                roots.append(path)
    return roots


def kicad_user_vars(major):
    """Path variables the user set in KiCad (kicad_common.json), {} if none."""
    home = os.path.expanduser("~")
    for base in (os.path.join(home, "Library", "Preferences", "kicad"),
                 os.path.join(home, ".config", "kicad"),
                 os.path.join(os.environ.get("APPDATA", ""), "kicad")):
        path = os.path.join(base, "%d.0" % major, "kicad_common.json")
        try:
            with open(path) as fh:
                return dict(((json.load(fh).get("environment") or {})
                             .get("vars") or {}))
        except (OSError, ValueError, AttributeError):
            continue
    return {}


def resolve_kicad_var(name, cli=None, major=None):
    """(value, source) for a KiCad path variable, or (None, why)."""
    if os.environ.get(name):
        return os.environ[name], "environment"
    if major:
        user = kicad_user_vars(major)
        if user.get(name):
            return user[name], "kicad_common.json"
    m = _KICAD_VAR.match(name)
    if not m:
        return None, "not a KiCad path variable this check knows"
    if m.group(1) and major and int(m.group(1)) != major:
        return None, ("names KiCad %s, and this install is KiCad %d"
                      % (m.group(1), major))
    for root in kicad_share_dirs(cli):
        path = os.path.join(root, _VAR_DIRS[m.group(2)])
        if os.path.isdir(path):
            return path, "install"
    return None, "no %s directory in any KiCad install found" % _VAR_DIRS[
        m.group(2)]


def _cli_major(cli):
    tup = kicad_version_tuple(cli_version(cli) or "") if cli else ()
    return tup[0] if tup else None


def expand_uri(uri, kiprjmod, cli=None, major=None):
    """(path, None) with every variable resolved, or (None, var name)."""
    def sub(m):
        name = m.group(1) or m.group(2)
        if name == "KIPRJMOD":
            return kiprjmod
        value, _src = resolve_kicad_var(name, cli, major)
        if value is None:
            raise KeyError(name)
        return value
    try:
        return _VAR_REF.sub(sub, uri), None
    except KeyError as exc:
        return None, exc.args[0]


def check_lib_tables(rep, directory, name, cli=None):
    """Every library URI in the project's tables must resolve on disk.

    A URI that names a variable is resolved first (KIPRJMOD, then KiCad's
    own path variables); one that still names a variable this check cannot
    resolve is a warning naming it, because an unresolved URI was never
    checked and must not count as one that resolves.
    """
    label = "libs %s" % name
    missing, unresolved, total = [], {}, 0
    major = _cli_major(cli)
    for table in ("sym-lib-table", "fp-lib-table"):
        path = os.path.join(directory, table)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            text = fh.read()
        for uri in re.findall(r'\(uri\s+"([^"]+)"\)', text):
            total += 1
            resolved, var = expand_uri(uri, directory, cli, major)
            if resolved is None:
                unresolved.setdefault(var, []).append(uri)
            elif not os.path.exists(resolved):
                missing.append(uri)
    if not total:
        rep.warn(label, "no project library tables",
                 "fix: python3 scripts/kicad_scaffold.py %s %s"
                 % (directory, name))
        return
    checked = total - sum(len(v) for v in unresolved.values())
    if missing:
        rep.fail(label, "%d of %d library URI(s) do not resolve: %s"
                 % (len(missing), total, ", ".join(missing[:3])),
                 "fix: generate the libraries, or re-scaffold:\n"
                 "     python3 scripts/kicad_scaffold.py %s %s"
                 % (directory, name))
    elif checked:
        rep.ok(label, "%d of %d library URI(s) resolve on disk%s"
               % (checked, total, "" if not unresolved else
                  "; %d not checked, below" % (total - checked)))
    for var, uris in sorted(unresolved.items()):
        rep.warn(label, "%d URI(s) name ${%s}, which this machine does not "
                 "resolve, so they were not checked: %s"
                 % (len(uris), var, ", ".join(uris[:2])),
                 "fix: set %s in KiCad (Preferences > Configure Paths) or "
                 "the environment,\n     or use a KiCad %s variable"
                 % (var, major or "10"))


# A footprint's 3D model link.  KiCad writes `(model "path" ...)`; the path may
# be quoted or bare and may be anchored on a path variable.
_MODEL_LINK = re.compile(r'\(model\s+"?([^"\n\)]+?)"?\s*(?:\(|$)',
                         re.MULTILINE)
# The 3D-model path variables KiCad itself defines.  They are user-global,
# which is exactly what a portable repo cannot rely on, so they are resolved
# here against the discovered install rather than the user's KiCad config.
_MODEL_VARS = ("KICAD10_3DMODEL_DIR", "KICAD9_3DMODEL_DIR",
               "KICAD8_3DMODEL_DIR", "KICAD_3DMODEL_DIR")


def model_roots():
    """Candidate directories the KiCad 3D-model path variables resolve to."""
    roots = []
    for var in _MODEL_VARS:
        if os.environ.get(var):
            roots.append(os.environ[var])
    root = os.environ.get("KICAD_ROOT")
    bases = [root] if root else []
    bases += ["/Applications/KiCad/KiCad.app/Contents", "/usr", "/usr/local"]
    for base in bases:
        for rel in (os.path.join("SharedSupport", "3dmodels"),
                    os.path.join("share", "kicad", "3dmodels")):
            path = os.path.join(base, rel)
            if os.path.isdir(path):
                roots.append(path)
    return roots


def resolve_model(link, footprint_path, project_dir, kiprjmod=None):
    """An absolute path for one `(model ...)` link, or None if unresolvable.

    `${KIPRJMOD}` is resolved against the directory holding the footprint
    library, not the board project: a shared library serving two board variants
    at different depths resolves differently for each, which is a real trap and
    not this checker's to fix (it is reported, below, as ambiguous).
    """
    path = link.strip().replace("\\", "/")
    for var in _MODEL_VARS:
        for form in ("${%s}" % var, "$(%s)" % var):
            if form in path:
                for root in model_roots():
                    candidate = path.replace(form, root)
                    if os.path.exists(candidate):
                        return candidate
                return None
    lib_dir = (os.path.abspath(kiprjmod) if kiprjmod else
               os.path.dirname(os.path.dirname(os.path.abspath(
                   footprint_path))))
    for anchor in ("${KIPRJMOD}", "$(KIPRJMOD)"):
        if anchor in path:
            for base in (lib_dir, os.path.abspath(project_dir)):
                candidate = os.path.normpath(path.replace(anchor, base))
                if os.path.exists(candidate):
                    return candidate
            return None
    if "${" in path or "$(" in path:
        return None                          # some other global variable
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    candidate = os.path.normpath(os.path.join(lib_dir, path))
    return candidate if os.path.exists(candidate) else None


def check_models(rep, project_dir, kicad_dirs=None):
    """Every `(model ...)` a project's own footprints name must resolve.

    A footprint naming a model is not evidence that the model exists.

    Measured: a provenance table recorded a stock model as `verified-in-cad`,
    meaning "file exists, path confirmed by direct filesystem check", for a
    path that exists in no KiCad install.  The check had read the footprint's
    own `(model ...)` line and recorded the reference as the referent.  That is
    a "the model is fine" claim which becomes an empty 3D view at the exact
    moment (a case phase, a stack-up review) the model was supposed to do work.

    So the evidence for a model row is a `stat` of the resolved path, and this
    is the generic version of it: resolve every link in the project's own
    library and name the ones that are not there.  It also reports footprints
    with no model link at all, which is the machine-checkable half of an
    "every footprint links a 3D model" requirement.
    """
    pretty = sorted(glob.glob(os.path.join(project_dir, "**", "*.pretty"),
                              recursive=True))
    mods = [p for d in pretty
            for p in sorted(glob.glob(os.path.join(d, "*.kicad_mod")))]
    if not mods:
        return
    missing, links, no_link = [], 0, []
    for path in mods:
        try:
            with open(path, errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        found = _MODEL_LINK.findall(text)
        if not found:
            no_link.append(os.path.basename(path)[:-len(".kicad_mod")])
            continue
        for link in found:
            links += 1
            if resolve_model(link, path, project_dir) is None:
                missing.append("%s -> %s"
                               % (os.path.basename(path)[:-len(".kicad_mod")],
                                  link.strip()))
    label = "3d models"
    if missing:
        rep.fail(label, "%d of %d model link(s) do not resolve: %s"
                 % (len(missing), links, "; ".join(missing[:3])
                    + (" ..." if len(missing) > 3 else "")),
                 "fix: vendor the model, or correct the (model ...) path in "
                 "the footprint.\n     A footprint naming a model is not "
                 "evidence that the model exists;\n     the evidence is a "
                 "stat of the resolved path, which is this check.")
    elif links:
        rep.ok(label, "%d model link(s) in %d footprint(s) resolve"
               % (links, len(mods) - len(no_link)))
    if no_link:
        rep.warn(label + " (unlinked)",
                 "%d footprint(s) link no 3D model: %s"
                 % (len(no_link), ", ".join(no_link[:6])
                    + (" ..." if len(no_link) > 6 else "")),
                 "fix: only a defect if this project requires a model per "
                 "footprint (a case\n     phase does). A STAND-IN must be "
                 "STEP, not WRL; see references/mechanical.md §7.")


def check_board_models(rep, kicad_dirs):
    """Every `(model ...)` of a footprint placed on a board must resolve.

    `check_models` reads a project's own footprint libraries; a stock
    footprint placed from KiCad's library carries its model link into the
    board file, and that link can name a file no install ships.  Measured:
    Connector_Wire:SolderWire-* footprints link
    Connector_Wire.3dshapes/SolderWire-*.step, and KiCad 10.0.5 has no
    Connector_Wire.3dshapes directory at all.
    """
    import kicad_geom
    for directory, name in kicad_dirs or ():
        pcb = os.path.join(directory, name + ".kicad_pcb")
        if not os.path.exists(pcb):
            continue
        try:
            board = kicad_geom.read_board(pcb)
        except Exception as exc:                       # pragma: no cover
            rep.warn("3d models %s" % name, "board not read: %s" % exc, "")
            continue
        links, missing = 0, []
        for fp in board["footprints"]:
            for model in fp.get("models") or ():
                if model.get("hidden"):
                    continue
                links += 1
                if resolve_model(model["path"], pcb, directory,
                                 kiprjmod=directory) is None:
                    missing.append("%s -> %s" % (fp["ref"], model["path"]))
        label = "3d models %s (placed)" % name
        if missing:
            rep.fail(label, "%d of %d model link(s) on the board do not "
                     "resolve: %s" % (len(missing), links, "; ".join(
                         missing[:3]) + (" ..." if len(missing) > 3 else "")),
                     "fix: point the link at a model that exists (vendor a "
                     "STEP, kicad_fplib.py fork),\n     or drop the link in "
                     "the board emitter for a part with no body\n     "
                     "(footprint.Models().clear()); a link to nothing exports "
                     "no body")
        elif links:
            rep.ok(label, "%d model link(s) on the board resolve" % links)


# The template Makefile's version line, and the targets a project Makefile
# copied from an older template is most likely to lack.
_MAKEFILE_STAMP = re.compile(r"hw_forge Makefile template version:\s*(\d+)")


def _template_makefile():
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "templates", "Makefile")


def _phony_targets(text):
    names = set()
    for m in re.finditer(r"^\.PHONY:((?:.*\\\n)*.*)$", text, re.M):
        for word in m.group(1).replace("\\\n", " ").split():
            if "$" not in word and "(" not in word:
                names.add(word)
    return names


def check_makefile(rep, project_dir):
    """A project Makefile copied from the template carries its version line;
    an older or missing one is a WARN with the diff command."""
    template = _template_makefile()
    try:
        with open(template) as fh:
            ttext = fh.read()
    except OSError:
        return
    tver = _MAKEFILE_STAMP.search(ttext)
    tver = int(tver.group(1)) if tver else 0
    cands = [os.path.join(project_dir, "Makefile"),
             os.path.join(project_dir, "kicad", "Makefile")]
    for path in cands:
        if not os.path.isfile(path):
            continue
        with open(path, errors="replace") as fh:
            text = fh.read()
        if "kicad_gate.py" not in text and "hw_forge" not in text:
            continue                         # not a hw_forge project Makefile
        got = _MAKEFILE_STAMP.search(text)
        pver = int(got.group(1)) if got else None
        lacking = sorted(_phony_targets(ttext) - _phony_targets(text))
        label = "Makefile"
        fix = "diff: diff -u %s %s" % (path, template)
        if pver is None or pver < tver:
            rep.warn(label, "%s is %s; the shipped template is version %d%s"
                     % (path, "unstamped (copied before stamps existed)"
                        if pver is None else "template version %d" % pver,
                        tver, "; lacks target(s): %s" % ", ".join(lacking[:8])
                        if lacking else ""),
                     fix + "\nfix: merge the template's generic half (below "
                     "the project configuration block)")
        elif lacking:
            rep.warn(label, "%s is template version %d but lacks target(s): "
                     "%s" % (path, pver, ", ".join(lacking[:8])), fix)
        else:
            rep.ok(label, "%s matches template version %d" % (path, tver))
        return


def check_generators(rep, project_dir, kpy=None):
    """A generator that will not import cannot be debugged from a DRC report."""
    candidates = []
    for pattern in ("design*.py", "gen_*.py", "*/design*.py", "*/gen_*.py"):
        candidates += sorted(glob.glob(os.path.join(project_dir, pattern)))
    if not candidates:
        return
    broken = [(os.path.basename(p), compiles(p)) for p in candidates
              if compiles(p)]
    if broken:
        rep.fail("generators",
                 "will not compile: %s" % ", ".join(n for n, _ in broken),
                 "fix: %s" % broken[0][1])
    else:
        rep.ok("generators", "%d file(s) compile" % len(candidates))

    # design.py must import under both interpreters: the schematic emitter
    # runs on system python, the board emitter on KiCad's.
    designs = [p for p in candidates
               if os.path.basename(p).startswith("design")]
    code = ("import sys, importlib.util as u;"
            "s=u.spec_from_file_location('d', %r);"
            "m=u.module_from_spec(s);s.loader.exec_module(m)")
    pythons = [("system python", sys.executable)]
    if kpy:
        pythons.append(("KiCad python", kpy))
    for path in designs:
        label = "import %s" % os.path.relpath(path, project_dir)
        bad, good = [], []
        for what, py in pythons:
            proc = run([py, "-c", code % path])
            if proc.returncode != 0:
                detail = (proc.stderr or "").strip().splitlines()
                bad.append("%s (%s): %s" % (what, py, detail[-1] if detail
                                            else "import failed"))
            else:
                good.append(what)
        if bad:
            rep.fail(label, "; ".join(bad),
                     "fix: the logical design must import cleanly under both "
                     "interpreters\n     (the schematic emitter runs on the "
                     "system python, the board emitter on KiCad's)")
        elif kpy:
            rep.ok(label, "imports under %s" % " and ".join(good))
        else:
            rep.warn(label, "imports under the system python; not checked "
                     "under KiCad's (none found)",
                     "fix: install KiCad 10, or set KICAD_PYTHON")


def check_case_env(rep, project_dir):
    """If there is a case/, its computer-aided design environment must work."""
    case_dirs = [d for d in (os.path.join(project_dir, "case"), project_dir)
                 if os.path.isdir(d) and
                 glob.glob(os.path.join(d, "*case*.py"))]
    if not case_dirs:
        return
    case_dir = case_dirs[0]
    venvs = [p for p in (os.path.join(case_dir, ".venv"),
                         os.path.join(project_dir, ".venv"))
             if os.path.isdir(p)]
    if not venvs:
        rep.warn("case venv", "no .venv beside the case scripts",
                 "fix: python3 -m venv %s && %s/bin/pip install build123d"
                 % (os.path.join(case_dir, ".venv"),
                    os.path.join(case_dir, ".venv")))
        return
    venv = venvs[0]
    py = os.path.join(venv, "bin", "python3")
    if not os.path.exists(py):
        py = os.path.join(venv, "Scripts", "python.exe")
    if not os.path.exists(py):
        rep.fail("case venv", "%s has no interpreter" % venv,
                 "fix: rm -rf %s && python3 -m venv %s" % (venv, venv))
        return
    proc = run([py, "-c", "import build123d;print(build123d.__version__)"])
    if proc.returncode != 0:
        rep.fail("build123d", "not importable in %s" % venv,
                 "fix: %s/bin/pip install build123d" % venv)
    else:
        rep.ok("build123d", "%s  (%s)" % ((proc.stdout or "?").strip(), venv))


# ----------------------------------------------------------------- smoke

def violation_counts(report_path):
    """{section: n} from a design-rule or electrical-rule JSON report."""
    with open(report_path) as fh:
        doc = json.load(fh)
    if "sheets" in doc:
        return {"ERC": sum(len(s.get("violations", []))
                           for s in doc["sheets"])}
    return {k: len(doc.get(k) or []) for k in
            ("violations", "schematic_parity", "unconnected_items")}


def copy_lib_table(src, dst, original_dir):
    """Copy a library table, re-anchoring ${KIPRJMOD} to the original project.

    Library URIs are written relative to the project directory, so a plain
    copy into a scratch dir silently breaks every one of them.  A board whose
    footprint libraries do not resolve reports a pile of DRC violations that
    look exactly like design errors.

    That false alarm is the thing a smoke test exists to rule out, so rewrite
    the variable to the real path instead of copying the file verbatim.
    """
    with open(src) as fh:
        text = fh.read()
    anchored = os.path.abspath(original_dir)
    text = text.replace("${KIPRJMOD}", anchored).replace("$(KIPRJMOD)",
                                                         anchored)
    with open(dst, "w") as fh:
        fh.write(text)


def smoke(rep, project_dir, kicad_dirs, cli, kpy):
    """Round-trip a known-good board and diff its DRC counts.

    This is the check that tells a toolchain regression from a design error.
    Load the board through pcbnew, save it to a scratch copy, re-run DRC, and
    compare: a board that was clean and comes back dirty was broken by the
    tools, not by you.  Nothing is written inside the project.
    """
    if not (cli and kpy):
        rep.fail("smoke test", "needs both kicad-cli and pcbnew",
                 "fix: resolve the toolchain failures above first")
        return
    if not kicad_dirs:
        rep.fail("smoke test", "no board to test",
                 "fix: point --project at a directory with a generated board")
        return

    import kicad_gate
    directory, name = kicad_dirs[0]
    pcb = os.path.join(directory, name + ".kicad_pcb")
    if not os.path.exists(pcb):
        rep.fail("smoke test", "no board file at %s" % pcb,
                 "fix: run the project's generator first")
        return

    scratch = tempfile.mkdtemp(prefix="hwforge-smoke-")
    try:
        # Baseline: DRC the board as it stands, in scratch so the project is
        # never written to.
        # .kicad_dru is load-bearing: a project's custom DRC rules live there
        # and kicad-cli picks them up from the project directory automatically.
        # Omit it and the copy reports every violation those rules legitimately
        # relax, which is the false alarm a smoke test exists to rule out.  In
        # the case that caught this, it was 44 phantom copper_edge_clearance
        # errors.
        for ext in (".kicad_pcb", ".kicad_pro", ".kicad_sch", ".kicad_dru"):
            src = os.path.join(directory, name + ext)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(scratch, name + ext))
        if os.path.exists(os.path.join(directory, "hwforge-overrides.json")):
            shutil.copy2(os.path.join(directory, "hwforge-overrides.json"),
                         os.path.join(scratch, "hwforge-overrides.json"))
        for table in ("sym-lib-table", "fp-lib-table"):
            src = os.path.join(directory, table)
            if os.path.exists(src):
                copy_lib_table(src, os.path.join(scratch, table), directory)

        before = os.path.join(scratch, "before.json")
        state, detail = kicad_gate.run_check(
            cli, ["pcb", "drc"], kicad_gate.DRC_FLAGS,
            os.path.join(scratch, name + ".kicad_pcb"), before)
        if state not in ("ok", "violations"):
            rep.fail("smoke baseline", detail,
                     "fix: resolve the DRC invocation failure above")
            return
        baseline = violation_counts(before)

        # Round-trip through pcbnew: load, fill zones if any, save.
        here = os.path.dirname(os.path.abspath(__file__))
        proc = run([kpy, os.path.join(here, "kicad_zonefill.py"),
                    os.path.join(scratch, name + ".kicad_pcb")])
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            rep.fail("smoke round-trip",
                     detail[-1] if detail else "zonefill failed",
                     "fix: this is a pcbnew/toolchain failure, not a design "
                     "error: do not start design work until it passes")
            return

        after = os.path.join(scratch, "after.json")
        state, detail = kicad_gate.run_check(
            cli, ["pcb", "drc"], kicad_gate.DRC_FLAGS,
            os.path.join(scratch, name + ".kicad_pcb"), after)
        if state not in ("ok", "violations"):
            rep.fail("smoke round-trip", detail, "fix: see above")
            return
        roundtrip = violation_counts(after)

        deltas = {k: roundtrip.get(k, 0) - baseline.get(k, 0)
                  for k in set(baseline) | set(roundtrip)}
        summary = ", ".join("%s %d->%d" % (k, baseline.get(k, 0),
                                           roundtrip.get(k, 0))
                            for k in sorted(deltas))
        if any(v > 0 for v in deltas.values()):
            rep.fail("smoke test", "%s regressed after a pcbnew round-trip "
                                   "(%s)" % (name, summary),
                     "fix: TOOLCHAIN REGRESSION: a board that was clean came "
                     "back dirty.\n"
                     "     Do not debug the design. Check the KiCad version "
                     "against the\n"
                     "     one the generators were written for, and read the "
                     "new violation\n"
                     "     types: pad-role or rotation errors point at the "
                     "Flip() enum trap.")
        elif sum(baseline.values()):
            rep.warn("smoke test", "%s was already dirty (%s)"
                     % (name, summary),
                     "note: baseline is not clean, so this proves only that "
                     "the round-trip changed nothing")
        else:
            rep.ok("smoke test", "%s clean before and after a pcbnew "
                                 "round-trip (%s)" % (name, summary))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", help="also check this project directory")
    ap.add_argument("--smoke", action="store_true",
                    help="round-trip a known-good board through pcbnew and "
                         "diff DRC counts (needs --project)")
    args = ap.parse_args()

    print("--- hw_forge preflight ---")
    print("  platform %s, python %s" % (sys.platform,
                                        sys.version.split()[0]))
    for var in ("KICAD_ROOT", "KICAD_CLI", "KICAD_PYTHON"):
        if os.environ.get(var):
            print("  %s=%s" % (var, os.environ[var]))
    print()

    rep = Report()
    cli, kpy = check_toolchain(rep)
    check_self(rep)
    check_router(rep)
    check_fork_drc(rep, cli)

    kicad_dirs = None
    if args.project:
        kicad_dirs = check_project(rep, args.project, cli, kpy)
    if args.smoke:
        if not args.project:
            rep.fail("smoke test", "--smoke needs --project",
                     "fix: python3 scripts/preflight.py --project DIR --smoke")
        else:
            smoke(rep, args.project, kicad_dirs, cli, kpy)

    rep.render()
    if rep.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
