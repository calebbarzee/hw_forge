#!/usr/bin/env python3
"""The gate: run ERC and DRC on a KiCad project and fail the build on any error.

This is the machine-checkable exit contract for the schematic and PCB phases.
It runs

    kicad-cli sch erc --severity-error --format json --exit-code-violations
    kicad-cli pcb drc --schematic-parity --severity-error --format json \
                      --exit-code-violations

writes `erc.json` / `drc.json` beside the project, prints one line per check
(ERC / DRC / parity / unconnected) with per-violation-type counts on failure,
and exits nonzero if anything failed.  `--schematic-parity` is not optional:
without it the DRC passes on a board whose netlist has drifted from the
schematic, which is the failure mode a generated board is most prone to.

    python3 scripts/kicad_gate.py path/to/project_dir
    python3 scripts/kicad_gate.py path/to/project_dir --name boardname

The project name is auto-discovered from the .kicad_pro / .kicad_sch /
.kicad_pcb in the directory; --name is only needed when a directory holds more
than one project.  A missing schematic or board is reported as a failing check,
never skipped silently.
"""

import argparse
import os
import sys

# Set before any sibling import: these tools run against other people's
# project trees and must not leave __pycache__ directories behind.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report as report_mod
from _kicad_env import cli_version, find_cli, run

ERC_FLAGS = ["--severity-error", "--format", "json", "--exit-code-violations"]
DRC_FLAGS = ["--schematic-parity", "--severity-error", "--format", "json",
             "--exit-code-violations"]

# kicad-cli returns 5 for "ran fine, found violations".  Anything else nonzero
# is a tool/usage failure and must be reported differently: a broken invocation
# that we counted as "violations" would look like a design problem.
EXIT_VIOLATIONS = 5


def discover(project_dir, name=None):
    """(name, sch_path, pcb_path). Raises SystemExit on an ambiguous dir."""
    if not os.path.isdir(project_dir):
        raise SystemExit("error: no such directory: %s\n"
                         "  fix: pass the directory that holds the "
                         ".kicad_pro/.kicad_sch/.kicad_pcb" % project_dir)
    if name is None:
        stems = set()
        for entry in sorted(os.listdir(project_dir)):
            stem, ext = os.path.splitext(entry)
            if ext in (".kicad_pro", ".kicad_sch", ".kicad_pcb"):
                stems.add(stem)
        if not stems:
            raise SystemExit(
                "error: no KiCad project found in %s\n"
                "  fix: run the project's generator first, or scaffold one: "
                "python3 scripts/kicad_scaffold.py %s NAME"
                % (project_dir, project_dir))
        if len(stems) > 1:
            raise SystemExit(
                "error: %d projects in %s (%s)\n"
                "  fix: pick one with --name NAME"
                % (len(stems), project_dir, ", ".join(sorted(stems))))
        name = stems.pop()
    base = os.path.join(project_dir, name)
    return name, base + ".kicad_sch", base + ".kicad_pcb"


def run_check(cli, subcmd, flags, src, out_json):
    """Run one kicad-cli check.

    Returns (state, detail) where state is 'ok', 'violations', 'missing' or
    'error'.  The JSON report is the source of truth for the printed summary;
    the exit code only tells us whether to look at it.
    """
    if not os.path.exists(src):
        return "missing", "no such file: %s" % src
    proc = run([cli] + subcmd + flags + ["-o", out_json, src])
    if proc.returncode == 0:
        return "ok", ""
    if proc.returncode == EXIT_VIOLATIONS and os.path.exists(out_json):
        return "violations", out_json
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return "error", (detail[-1] if detail else "kicad-cli exited %d"
                     % proc.returncode)


def gate(project_dir, name=None, cli=None, quiet=False):
    """Run both checks. Returns the number of failing checks."""
    name, sch, pcb = discover(project_dir, name)
    if cli is None:
        cli, how = find_cli()
        if not cli:
            raise SystemExit(
                "error: kicad-cli not found (%s)\n"
                "  fix: install KiCad 10, or set "
                "KICAD_ROOT=/Applications/KiCad/KiCad.app/Contents\n"
                "  check: python3 scripts/preflight.py" % how)

    say = (lambda *a: None) if quiet else print
    say("--- %s ---" % name)
    failures = 0

    erc_json = os.path.join(project_dir, "erc.json")
    state, detail = run_check(cli, ["sch", "erc"], ERC_FLAGS, sch, erc_json)
    if state == "ok":
        say("  %-11s ok" % "ERC")
    elif state == "violations":
        failures += max(1, report_mod.summarise(erc_json))
    else:
        say("  %-11s %s  %s" % ("ERC", state.upper(), detail))
        failures += 1

    drc_json = os.path.join(project_dir, "drc.json")
    state, detail = run_check(cli, ["pcb", "drc"], DRC_FLAGS, pcb, drc_json)
    if state in ("ok", "violations") and os.path.exists(drc_json):
        # Always print all three DRC sections from the report, pass or fail:
        # a clean run should show *what* was checked, not just silence.
        failures += report_mod.summarise(drc_json)
    else:
        say("  %-11s %s  %s" % ("DRC", state.upper(), detail))
        failures += 1

    return failures


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project_dir", help="directory holding the KiCad project")
    ap.add_argument("--name", help="project basename (default: auto-discover)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the heading and ok lines")
    args = ap.parse_args()

    cli, how = find_cli()
    if not cli:
        raise SystemExit(
            "error: kicad-cli not found (%s)\n"
            "  fix: install KiCad 10, or set "
            "KICAD_ROOT=/Applications/KiCad/KiCad.app/Contents\n"
            "  check: python3 scripts/preflight.py" % how)
    if cli_version(cli) is None:
        raise SystemExit("error: %s will not run (found via %s)\n"
                         "  fix: python3 scripts/preflight.py" % (cli, how))

    failures = gate(args.project_dir, args.name, cli, args.quiet)
    if failures:
        print("  %d check(s) failed" % failures, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
