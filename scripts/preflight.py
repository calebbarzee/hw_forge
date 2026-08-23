#!/usr/bin/env python3
"""Environment doctor: prove the toolchain works before designing anything.

Run this first, every session.  A toolchain problem that surfaces mid-design
gets mistaken for a design problem and burns a whole session chasing a bug
that was never in the board — that is exactly how KiCad 10's `Flip()` enum
change presented (295 phantom DRC violations on a previously clean board).
Checking versions up front, and diffing one throwaway regeneration against a
known-good artifact, separates "the tools changed" from "my design is wrong"
in seconds.

    python3 scripts/preflight.py
    python3 scripts/preflight.py --project build/left
    python3 scripts/preflight.py --project build/left --smoke

Every failing line carries the exact command that fixes it.  Exit status is 0
only when nothing failed; warnings do not fail the run.

--smoke needs a project whose board is already known good (its gate passes).
It re-runs the gate, then regenerates or reloads the board through pcbnew and
re-gates it, and diffs the violation counts.  A clean board that comes back
dirty after a round-trip is a toolchain regression, not a design error — stop
and fix the toolchain.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True      # a doctor must not modify what it examines
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _kicad_env import (cli_version, find_cli, find_python, have_pcbnew,
                        kicad_version_tuple, run)

# KiCad 10 is the version every trap documented in this repo was measured on.
# 9 mostly works; 8's headless zone filler does not; 11 removes the SWIG
# pcbnew module in favour of the IPC API, so it needs a migration, not a warning.
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
            print("%d of %d checks FAILED%s — fix the lines above before "
                  "starting design work"
                  % (n_fail, total, ", %d warning(s)" % n_warn if n_warn else ""))
        elif n_warn:
            print("all %d checks passed, %d warning(s)" % (total, n_warn))
        else:
            print("all %d checks passed" % total)


# ------------------------------------------------------------- toolchain

def check_toolchain(rep):
    """Returns (cli, kpy) — either may be None if unusable."""
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
                         "fix: upgrade to KiCad 10 — KiCad 8's headless zone "
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
        # and that enum's LEFT_RIGHT member is 0 — so the KiCad 8 idiom
        # `Flip(centre, False)` silently became a left-right mirror, which is a
        # top-bottom mirror plus 180 degrees. Every back-side footprint came
        # out rotated 180, pads swapped ends, and a clean board reported 295
        # violations. Always pass FLIP_DIRECTION_TOP_BOTTOM explicitly.
        rep.ok("Flip() enum", "FLIP_DIRECTION_TOP_BOTTOM present — pass it "
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
        rep.ok("island removal", "ISLAND_REMOVAL_MODE_AREA available — use it "
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


# --------------------------------------------------------------- project

def check_project(rep, project_dir, cli):
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
        check_lib_tables(rep, directory, name)

    check_generators(rep, project_dir)
    check_case_env(rep, project_dir)
    return kicad_dirs


def check_lib_tables(rep, directory, name):
    """Every library URI in the project's tables must resolve on disk."""
    label = "libs %s" % name
    missing, total = [], 0
    for table in ("sym-lib-table", "fp-lib-table"):
        path = os.path.join(directory, table)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            text = fh.read()
        import re
        for uri in re.findall(r'\(uri\s+"([^"]+)"\)', text):
            total += 1
            resolved = uri.replace("${KIPRJMOD}", directory) \
                          .replace("$(KIPRJMOD)", directory)
            if "${" in resolved or "$(" in resolved:
                continue                     # a global var we cannot resolve
            if not os.path.exists(resolved):
                missing.append(uri)
    if not total:
        rep.warn(label, "no project library tables",
                 "fix: python3 scripts/kicad_scaffold.py %s %s"
                 % (directory, name))
    elif missing:
        rep.fail(label, "%d of %d library URI(s) do not resolve: %s"
                 % (len(missing), total, ", ".join(missing[:3])),
                 "fix: generate the libraries, or re-scaffold:\n"
                 "     python3 scripts/kicad_scaffold.py %s %s"
                 % (directory, name))
    else:
        rep.ok(label, "%d library URI(s) resolve" % total)


def check_generators(rep, project_dir):
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

    # design.py must import under *both* interpreters: the schematic emitter
    # runs on system python, the board emitter on KiCad's.
    designs = [p for p in candidates
               if os.path.basename(p).startswith("design")]
    for path in designs:
        proc = run([sys.executable, "-c",
                    "import sys, importlib.util as u;"
                    "s=u.spec_from_file_location('d', %r);"
                    "m=u.module_from_spec(s);s.loader.exec_module(m)" % path])
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().splitlines()
            rep.fail("import %s" % os.path.basename(path),
                     detail[-1] if detail else "import failed",
                     "fix: the logical design must import cleanly under "
                     "system python (it is shared by both emitters)")
        else:
            rep.ok("import %s" % os.path.basename(path),
                   "imports under system python")


def check_case_env(rep, project_dir):
    """If there is a case/, its CAD environment must be usable."""
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
    """{section: n} from a DRC/ERC JSON report."""
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
    copy into a scratch dir silently breaks every one of them — and a board
    whose footprint libraries do not resolve reports a pile of DRC violations
    that look exactly like design errors.  That false alarm would defeat the
    entire purpose of a smoke test, so rewrite the variable to the real path
    instead of copying the file verbatim.
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
        # relax — 44 phantom copper_edge_clearance errors, in the case that
        # caught this — which is precisely the false alarm a smoke test exists
        # to rule out.
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
                     "error — do not start design work until it passes")
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
                     "fix: TOOLCHAIN REGRESSION — a board that was clean came "
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

    kicad_dirs = None
    if args.project:
        kicad_dirs = check_project(rep, args.project, cli)
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
