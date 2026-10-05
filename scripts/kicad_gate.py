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

    parity      enforced (.kicad_pro) 5/5          <- a parity ok means something
    parity      UNENFORCED  3 of 5 below error ... <- a parity ok means nothing

`--strict-parity` turns that warning into a failing check, which is what CI
wants.  `kicad_scaffold.py` writes the five promotions into every new project,
so a scaffolded project is enforced from its first build; a project that
predates that fix (or that demoted one deliberately) is what this detects.

The forked kicad-cli.  `preflight.drc_capabilities()` probes the binary once
per run (its `pcb drc --help`, and one DRC of a probe board).  When it takes
`--severity-override`, the gate passes the five parity keys and every
`FAB_SEVERITIES` promotion on the command line, at the levels
`hwforge-overrides.json` records for them (hw_forge's defaults where it
records none), so a `.kicad_pro` that pcbnew's SaveBoard() reverted no longer
un-gates them:

    parity      enforced (override) 5/5

When it takes `--strict-rules`, the gate passes it, and a rule file that does
not compile fails as `rule file invalid (exit 8)`, distinct from a board that
did not load (`load failure (exit 3)`).  A binary without `--strict-rules`
(stock 10.0.5) drops such a file whole, silently, exit 0, so the gate instead
scans `NAME.kicad_dru` for constraint keywords that binary does not compile
and fails as `DRC rules DROPPED`.  On stock nothing else changes.

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
import re
import sys

# Set before any sibling import: these tools run against other people's
# project trees and must not leave __pycache__ directories behind.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report as report_mod
from _kicad_env import cli_version, find_cli, run
from kicad_scaffold import FAB_SEVERITIES, OVERRIDES_FILE, PARITY_SEVERITIES
from preflight import (FORK_KEYWORDS, STOCK_CONSTRAINTS, drc_capabilities,
                       unknown_constraints)

ERC_FLAGS = ["--severity-error", "--format", "json", "--exit-code-violations"]
DRC_FLAGS = ["--schematic-parity", "--severity-error", "--format", "json",
             "--exit-code-violations"]

# kicad-cli returns 5 for "ran fine, found violations".  Anything else nonzero
# is a tool/usage failure and must be reported differently: a broken invocation
# that we counted as "violations" would look like a design problem.
EXIT_VIOLATIONS = 5
# The fork's contract (tools/ai_pipeline/docs/reports.md in the fork): 1 is a
# bad argument, such as an unknown --severity-override key; 3 is a board or
# schematic that did not load; 8 is a rule file that did not compile, and is
# only returned under --strict-rules (without it the fork returns 3 for that
# too).  Stock 10.0.5 returns 0 on a rule file it cannot compile.
EXIT_ARGS = 1
EXIT_LOAD = 3
EXIT_RULES_INVALID = 8
STATE_TEXT = {
    "rules_invalid": "FAIL  rule file invalid (exit 8)",
    "load_failure": "FAIL  load failure (exit 3)",
    "bad_argument": "ERROR  bad argument (exit 1)",
}
SEVERITY_LEVELS = ("ignore", "warning", "error", "exclusion")


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


def severity_overrides(project_dir):
    """{key: level} the gate passes as --severity-override on a fork binary.

    hw_forge's defaults (PARITY_SEVERITIES over FAB_SEVERITIES, as
    kicad_scaffold.py merges them), then the project's own decision for any
    of those keys recorded in hwforge-overrides.json.  The sidecar is the
    record of a deliberate demotion; the .kicad_pro is not, because
    pcbnew's SaveBoard() reverts it.  Keys outside the two tables are left
    to the .kicad_pro.
    """
    levels = dict(FAB_SEVERITIES)
    levels.update(PARITY_SEVERITIES)
    try:
        with open(os.path.join(project_dir, OVERRIDES_FILE)) as fh:
            recorded = json.load(fh).get("rule_severities") or {}
    except (OSError, ValueError, AttributeError):
        recorded = {}
    for key in levels:
        if recorded.get(key) in SEVERITY_LEVELS:
            levels[key] = recorded[key]
    return levels


def drc_flags(caps, overrides=None):
    """DRC_FLAGS, plus the fork flags this binary accepts."""
    flags = list(DRC_FLAGS)
    if caps.get("strict_rules"):
        flags.append("--strict-rules")
    if caps.get("severity_override") and overrides:
        for key in sorted(overrides):
            flags += ["--severity-override", "%s=%s" % (key, overrides[key])]
    return flags


def say_dropped_rules(project_dir, name, caps):
    """On a binary without --strict-rules, name the constraint keywords in
    NAME.kicad_dru it cannot compile.  Returns 1 if any, else 0.

    Stock 10.0.5 drops such a file WHOLE, prints nothing and exits 0, so
    every custom rule in it stops running and nothing in the report says so.
    The keyword list is preflight.STOCK_CONSTRAINTS (read from 10.0.5's
    parser), plus FORK_KEYWORDS when the probe says the binary compiles them.
    """
    path = os.path.join(project_dir, name + ".kicad_dru")
    if caps.get("strict_rules") or not os.path.exists(path):
        return 0
    known = STOCK_CONSTRAINTS + (FORK_KEYWORDS
                                 if caps.get("fork_rules") == "fork" else ())
    bad = unknown_constraints(path, known)
    if not bad:
        return 0
    print("  %-11s DROPPED  %s names constraint(s) this kicad-cli does not "
          "compile: %s" % ("DRC rules", os.path.basename(path),
                           ", ".join(bad)))
    print("              WARNING: stock kicad-cli drops such a file WHOLE, "
          "silently, exit 0: no\n              custom rule in it ran, and the "
          "DRC lines above do not cover them. fix:\n"
          "                correct the keyword, or gate with the forked "
          "kicad-cli (KICAD_CLI=...)")
    return 1


def say_parity(say, project_dir, name, overrides=None):
    """Print whether a `parity ok` above this line means anything. Returns
    the number of parity checks that cannot fail the gate.

    `overrides` is the {key: level} map passed as --severity-override, or
    None on a binary without that flag.  With it, the .kicad_pro does not
    decide enforcement, and a .kicad_pro below error is only a note: the GUI
    and a stock kicad-cli still read it.

    The `enforced` line honours --quiet (it is an ok line); the UNENFORCED
    block never does.  A warning that says the gate above it did not run is
    not something a verbosity flag may hide, because hiding it reproduces the
    failure this check exists to detect.
    """
    enforced, unenforced, pro = parity_enforcement(project_dir, name)
    total = len(enforced) + len(unenforced)
    if overrides is not None:
        demoted = sorted(r for r in PARITY_SEVERITIES
                         if overrides.get(r) != "error")
        if not demoted:
            say("  %-11s enforced (override) %d/%d" % ("parity", total, total))
            if unenforced:
                say("              note: %s holds %d of %d below error; the "
                    "GUI and a stock kicad-cli\n              still read it. "
                    "fix:\n                python3 scripts/kicad_scaffold.py "
                    "%s --repatch %s"
                    % (os.path.basename(pro) if pro else "no .kicad_pro",
                       len(unenforced), total, project_dir,
                       " ".join("--severity %s=error" % r
                                for r in unenforced)))
            return 0
        print("  %-11s UNENFORCED  %d of %d parity checks demoted in %s"
              % ("parity", len(demoted), total, OVERRIDES_FILE))
        print("              %s" % ", ".join(
            "%s=%s" % (r, overrides[r]) for r in demoted))
        print("              the override follows the recorded demotion, so "
              "any `parity ok` above\n              does not cover them. "
              "fix, once the demotion is no longer wanted:")
        print("                python3 scripts/kicad_scaffold.py %s --repatch %s"
              % (project_dir, " ".join("--severity %s=error" % r
                                       for r in demoted)))
        return len(demoted)
    if not unenforced:
        say("  %-11s enforced (.kicad_pro) %d/%d"
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

    Returns (state, detail) where state is 'ok', 'violations', 'missing',
    'rules_invalid' (exit 8), 'load_failure' (exit 3), 'bad_argument'
    (exit 1) or 'error'.  The JSON report is the source of truth for the
    printed summary; the exit code only tells us whether to look at it.
    """
    if not os.path.exists(src):
        return "missing", "no such file: %s" % src
    proc = run([cli] + subcmd + flags + ["-o", out_json, src])
    if proc.returncode == 0:
        return "ok", ""
    if proc.returncode == EXIT_VIOLATIONS and os.path.exists(out_json):
        return "violations", out_json
    state = {EXIT_RULES_INVALID: "rules_invalid", EXIT_LOAD: "load_failure",
             EXIT_ARGS: "bad_argument"}.get(proc.returncode, "error")
    return state, cli_reason(proc)


def cli_reason(proc):
    """The line of kicad-cli's output that says why it failed.

    The fork's rule-parser error lists every keyword it knows after
    `Expected`; that list is cut, so the line keeps the keyword and position.
    """
    lines = [l.strip() for l in (proc.stderr or proc.stdout or "")
             .splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if line.startswith("ERROR:"):
            if i + 1 < len(lines) and lines[i + 1].startswith("in '"):
                line += " " + lines[i + 1]          # the file and position
            return re.sub(r"\.?\s*Expected .*?(?= in '|$)", "",
                          line[6:].strip())
    return lines[-1] if lines else "kicad-cli exited %d" % proc.returncode


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
        print("  %-11s %s  %s"
              % ("ERC", STATE_TEXT.get(state, state.upper()), detail))
        failures += 1

    # The board is skipped, not failed, when there is deliberately none yet.
    # --require-board turns the skip back into the failure a PCB-phase or
    # pre-export caller wants.
    if sch_only or (not os.path.exists(pcb) and not require_board):
        why = ("--sch-only" if sch_only
               else "no board file yet: %s" % os.path.basename(pcb))
        say("  %-11s SKIPPED  (%s)" % ("DRC", why))
        say("  verdict     PARTIAL: schematic only, the board is NOT gated")
        return failures, "partial"

    # A fork binary takes the severities on the command line, so enforcement
    # no longer depends on what the .kicad_pro holds; a stock one reads only
    # the .kicad_pro, which kicad_scaffold.py --repatch keeps current.
    caps = drc_capabilities(cli)
    overrides = (severity_overrides(project_dir)
                 if caps["severity_override"] else None)
    drc_json = os.path.join(project_dir, "drc.json")
    state, detail = run_check(cli, ["pcb", "drc"], drc_flags(caps, overrides),
                              pcb, drc_json)
    if state in ("ok", "violations") and os.path.exists(drc_json):
        # Always print all three DRC sections from the report, pass or fail:
        # a clean run should show what was checked, not just silence.
        failures += report_mod.summarise(drc_json)
    else:
        print("  %-11s %s  %s"
              % ("DRC", STATE_TEXT.get(state, state.upper()), detail))
        failures += 1
    failures += say_dropped_rules(project_dir, name, caps)

    # Printed after the DRC lines, deliberately: this qualifies the `parity`
    # line the report just printed, and a reader has to see them together.
    unenforced = say_parity(say, project_dir, name, overrides)
    if unenforced and strict_parity:
        failures += 1
    if overrides is not None:
        fab = sorted(k for k in FAB_SEVERITIES if k not in PARITY_SEVERITIES)
        moved = sorted(k for k in fab if overrides[k] != FAB_SEVERITIES[k])
        say("  %-11s %d by --severity-override: %d parity, %d fab%s"
            % ("severities", len(overrides), len(PARITY_SEVERITIES), len(fab),
               "; per %s: %s" % (OVERRIDES_FILE, ", ".join(
                   "%s=%s" % (k, overrides[k]) for k in moved))
               if moved else ""))

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
                         "below error severity (in the .kicad_pro, or with "
                         "--severity-override in hwforge-overrides.json), "
                         "i.e. when a `parity ok` could not have failed")
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
