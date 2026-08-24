#!/usr/bin/env python3
"""The gate: run ERC and DRC on a KiCad project and fail the build on any error.

This is the machine-checkable exit contract for the schematic and PCB phases.
It runs the electrical rule check (ERC) and the design rule check (DRC):

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
    python3 scripts/kicad_gate.py path/to/project_dir --sch-only
    python3 scripts/kicad_gate.py path/to/project_dir --strict-parity

The flag is not the gate; the parity severities are.  `--schematic-parity` is
necessary and, on its own, not sufficient: KiCad 10 ships all five parity
checks at warning severity, so `--severity-error` filters every one of them
out before they are counted, and this script prints `parity ok` on a board it
never checked.

Measured on a project whose board was one revision stale: the gate reported
green (`ERC ok  DRC ok  parity ok  unconnected ok`) while `--severity-all` on
the same board reported 31 parity issues, eight missing footprints and
twenty-one net conflicts.  A second project's four boards were audited
afterwards and had never enforced parity either; one of its slices was hiding
two real missing footprints behind a green gate.

So this script reads the project's own `.kicad_pro` and reports whether the
parity result is enforceable:

    parity      enforced at error severity (5/5)   <- a parity ok means something
    parity      UNENFORCED  3 of 5 below error …   <- a parity ok means nothing

`--strict-parity` turns that warning into a failing check, which is what CI
wants.  `kicad_scaffold.py` writes the five promotions into every new project,
so a scaffolded project is enforced from its first build; a project that
predates that fix (or that demoted one deliberately) is what this detects.

The project name is auto-discovered from the .kicad_pro / .kicad_sch /
.kicad_pcb in the directory; --name is only needed when a directory holds more
than one project.

Schematic-only projects.  At the end of a correct schematic phase there is no
board file yet, and the phase's exit contract is "ERC 0".  A missing board must
therefore not be a failing check, or the gate can never pass in the phase that
names it.  Two ways to say so, and they print the same PARTIAL verdict:

  * `--sch-only`   deliberate: run ERC, do not look for a board at all.
  * auto-detect    a directory with a schematic and no `.kicad_pcb` reports
                   `DRC SKIPPED` and exits 0 on a clean ERC.

Both are loud: the summary line says the gate was partial, so a green line can
never be mistaken for a fully gated board.  Pass `--require-board` where a
board is expected to exist (a PCB-phase gate, a fab-export precondition, CI)
and a missing one should fail.  A missing schematic is always a failure, and a
board that exists is always gated.
"""

import argparse
import json
import os
import sys

# Set before any sibling import: these tools run against other people's
# project trees and must not leave __pycache__ directories behind.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report as report_mod
from _kicad_env import cli_version, find_cli, run
from kicad_scaffold import PARITY_SEVERITIES

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


def parity_enforcement(project_dir, name):
    """(enforced, unenforced, pro_path) for the five schematic-parity checks.

    A parity check absent from `rule_severities` runs at KiCad's own default,
    which is `warning` for all five.  So "absent" and "warning" are the same
    answer here, and both mean `--severity-error` never counted it.
    """
    pro = os.path.join(project_dir, name + ".kicad_pro")
    severities = {}
    found = os.path.exists(pro)
    if found:
        try:
            with open(pro) as fh:
                doc = json.load(fh)
            severities = (((doc.get("board") or {})
                           .get("design_settings") or {})
                          .get("rule_severities") or {})
        except (ValueError, OSError, AttributeError):
            severities = {}                  # unreadable: assume KiCad default
    rules = sorted(PARITY_SEVERITIES)
    enforced = [r for r in rules if severities.get(r) == "error"]
    return enforced, [r for r in rules if severities.get(r) != "error"], \
        (pro if found else None)


def say_parity(say, project_dir, name):
    """Print whether a `parity ok` above this line means anything. Returns
    the number of parity checks that cannot fail the gate.

    The `enforced` line honours --quiet (it is an ok line); the UNENFORCED
    block never does.  A warning that says the gate above it did not run is
    not something a verbosity flag may hide, because hiding it reproduces the
    failure this check exists to detect.
    """
    enforced, unenforced, pro = parity_enforcement(project_dir, name)
    total = len(enforced) + len(unenforced)
    if not unenforced:
        say("  %-11s enforced at error severity (%d/%d)"
            % ("parity", len(enforced), total))
        return 0
    print("  %-11s UNENFORCED  %d of %d parity checks are below error severity"
          % ("parity", len(unenforced), total))
    print("              in %s"
          % (os.path.basename(pro) if pro
             else "(no .kicad_pro in this directory)"))
    print("              %s" % ", ".join(unenforced))
    print("              KiCad ships all five at `warning`, so --severity-error "
          "filtered them\n              out: any `parity ok` above is NOT a "
          "gate. fix:")
    print("                python3 scripts/kicad_scaffold.py %s --repatch %s"
          % (project_dir, " ".join("--severity %s=error" % r
                                   for r in unenforced)))
    return len(unenforced)


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


def gate(project_dir, name=None, cli=None, quiet=False, sch_only=False,
         require_board=False, strict_parity=False):
    """Run both checks. Returns (failures, verdict).

    `verdict` is "full" when both the schematic and the board were gated and
    "partial" when the board was legitimately skipped, so a caller can print
    the difference rather than treating a schematic-only pass as a gated board.
    """
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

    # The board is skipped, not failed, when there is deliberately none yet.
    # --require-board turns the skip back into the failure a PCB-phase or
    # pre-export caller wants.
    if sch_only or (not os.path.exists(pcb) and not require_board):
        why = ("--sch-only" if sch_only
               else "no board file yet: %s" % os.path.basename(pcb))
        say("  %-11s SKIPPED  (%s)" % ("DRC", why))
        say("  verdict     PARTIAL — schematic only, the board is NOT gated")
        return failures, "partial"

    drc_json = os.path.join(project_dir, "drc.json")
    state, detail = run_check(cli, ["pcb", "drc"], DRC_FLAGS, pcb, drc_json)
    if state in ("ok", "violations") and os.path.exists(drc_json):
        # Always print all three DRC sections from the report, pass or fail:
        # a clean run should show what was checked, not just silence.
        failures += report_mod.summarise(drc_json)
    else:
        say("  %-11s %s  %s" % ("DRC", state.upper(), detail))
        failures += 1

    # Printed after the DRC lines, deliberately: this qualifies the `parity`
    # line the report just printed, and a reader has to see them together.
    unenforced = say_parity(say, project_dir, name)
    if unenforced and strict_parity:
        failures += 1

    return failures, "full"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project_dir", help="directory holding the KiCad project")
    ap.add_argument("--name", help="project basename (default: auto-discover)")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the heading and ok lines")
    ap.add_argument("--sch-only", action="store_true",
                    help="gate the schematic only (the phase-3 exit contract); "
                         "do not look for a board")
    ap.add_argument("--require-board", action="store_true",
                    help="fail if there is no board file, instead of skipping "
                         "DRC (use where a board must exist by now)")
    ap.add_argument("--strict-parity", action="store_true",
                    help="fail the gate when any schematic-parity check is "
                         "below error severity in the .kicad_pro, i.e. when a "
                         "`parity ok` could not have failed")
    args = ap.parse_args()
    if args.sch_only and args.require_board:
        ap.error("--sch-only and --require-board contradict each other")

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

    failures, _verdict = gate(args.project_dir, args.name, cli, args.quiet,
                              sch_only=args.sch_only,
                              require_board=args.require_board,
                              strict_parity=args.strict_parity)
    if failures:
        print("  %d check(s) failed" % failures, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
