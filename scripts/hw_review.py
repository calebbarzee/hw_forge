#!/usr/bin/env python3
"""The pre-order review: every check, in order, and one readiness table.

The last gate before a board is ordered.  Each phase already has its own
check; this runs all of them against one project and prints one table, so
"ready to order" is a single exit code rather than a memory of which checks
someone ran.  `docs/QUALITY.md` names the property each row proves.

    python3 scripts/hw_review.py kicad/
    python3 scripts/hw_review.py kicad/left --design kicad/design.py \\
        --case case/checks.py --case-python case/.venv/bin/python \\
        --fab kicad/left/fab-profile.json --assembly jlcpcb
    python3 scripts/hw_review.py kicad/ --json

Rows, in order:

  preflight     preflight.py --project: toolchain, library tables, 3D model
                links, and a rule file a stock kicad-cli would silently drop
  gate          kicad_gate.py --require-board --strict-parity: ERC, DRC with
                schematic parity enforced, unconnected
  fpcheck       kicad_fpcheck.py: footprints against declared packages
  bom           kicad_bom.py audit: sourcing fields, board-inherent exclusion
  schrules      kicad_schrules.py: decoupling, bulk, LED data resistor,
                pull-ups, connector protection.  Rules from --rules FILE, else
                sch-rules.json in PROJECT_DIR or in --design's directory,
                else the script's defaults; never a parent directory, which
                may be outside the project.
  silkcheck     kicad_silkcheck.py: silk readability floors
  ifcheck       kicad_ifcheck.py: connectors against their standards.  An
                interface with no definition is a WARN (--allow-undefined);
                --strict-interfaces makes it a FAIL.
  fit contract  kicad_geom.py --contract: every connector declares a
                mating_direction and its face points out through its edge
                (the contract is kept for the case row).  SKIP when the board
                has no connector; WARN when any part height is unknown.
  case          case_verify.py --contract, when a checks file exists
  fab           kicad_fab.py into a scratch directory: export assertions
  3d            kicad_3d.py export + verify, when any footprint links a model

A row is PASS, FAIL, WARN or SKIP, and every SKIP or WARN says why.  A SKIP
is not a pass: it is a property nobody proved, and the table says which.  A
WARN is a row that ran but left something unproven (a part with no height, an
interface with no definition).  Exit 1 on any FAIL.  Every row runs even after an earlier one fails, because the point is
the whole list of what stands between this board and an order.

Runs under any python3; each check runs in its own process, under the
interpreter it needs (the case row under the case venv's python).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kicad_geom                                            # noqa: E402
from _kicad_env import find_cli                               # noqa: E402
from kicad_gate import discover                               # noqa: E402

PY = sys.executable
NOISE = re.compile(r"^Fontconfig|wxApp|^tput:")


def sh(argv, env=None, timeout=1800):
    """(exit code, combined output) with KiCad noise removed."""
    full = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **(env or {}))
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, env=full,
                              universal_newlines=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    text = "\n".join(l for l in (proc.stdout or "").splitlines()
                     if not NOISE.search(l))
    return proc.returncode, text


def last(text, pattern=None):
    """The last non-blank line, or the last one matching `pattern`."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if pattern:
        hit = [l for l in lines if re.search(pattern, l)]
        if hit:
            return hit[-1]
    return lines[-1] if lines else ""


def short(text, width=96):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= width else text[:width - 3] + "..."


def find_design(project_dir, given):
    if given:
        return given
    for cand in (os.path.join(project_dir, "design.py"),
                 os.path.join(project_dir, os.pardir, "design.py")):
        if os.path.isfile(cand):
            return os.path.normpath(cand)
    return None


def find_case(project_dir, given):
    if given:
        return given
    here = os.path.abspath(project_dir)
    for _ in range(3):
        cand = os.path.join(here, "case", "checks.py")
        if os.path.isfile(cand):
            return cand
        here = os.path.dirname(here)
    return None


def case_python(checks, given):
    """The python a case suite runs under: the flag, case/.venv, or ours."""
    if given:
        return given, "--case-python"
    venv = os.path.join(os.path.dirname(os.path.abspath(checks)), ".venv",
                        "bin", "python")
    if os.path.exists(venv) and os.path.exists(os.path.realpath(venv)):
        return venv, "case/.venv"
    return PY, "this interpreter (no usable case/.venv)"


# ------------------------------------------------------------------- the rows

def row_preflight(ctx):
    code, out = sh([PY, os.path.join(HERE, "preflight.py"), "--project",
                    ctx["dir"]])
    fails = [l.strip() for l in out.splitlines()
             if l.strip().startswith("FAIL")]
    return ("FAIL" if code else "PASS",
            fails[0] if fails else last(out, r"checks? passed|FAILED")), out


def row_gate(ctx):
    code, out = sh([PY, os.path.join(HERE, "kicad_gate.py"), ctx["dir"],
                    "--name", ctx["name"], "--require-board",
                    "--strict-parity"])
    lines = [l.strip() for l in out.splitlines()
             if re.match(r"\s*(ERC|DRC|parity|unconnected)\b", l)]
    return ("FAIL" if code else "PASS", "; ".join(lines)), out


def row_fpcheck(ctx):
    argv = [PY, os.path.join(HERE, "kicad_fpcheck.py"), ctx["pcb"]]
    if ctx["design"]:
        argv += ["--design", ctx["design"]]
    code, out = sh(argv)
    return ("FAIL" if code else "PASS",
            last(out, r"footprint\(s\):")), out


def row_bom(ctx):
    argv = [PY, os.path.join(HERE, "kicad_bom.py"), "audit", ctx["sch"],
            "--board", ctx["pcb"]]
    if ctx["design"]:
        argv += ["--design", ctx["design"]]
    if ctx["assembly"]:
        argv += ["--assembly", ctx["assembly"]]
    code, out = sh(argv)
    return ("FAIL" if code else "PASS", last(out, r"\d+")), out


def find_rules(project_dir, given, design_flag):
    """The sch-rules.json for the schrules row, or None for the defaults.

    --rules wins.  Otherwise only PROJECT_DIR and the directory of an
    explicit --design (the Makefile's directory when make runs the review)
    are searched: a parent of PROJECT_DIR may belong to another project.
    """
    if given:
        return given
    dirs = [project_dir]
    if design_flag:
        dirs.append(os.path.dirname(os.path.abspath(design_flag)))
    for d in dirs:
        rules = os.path.join(d, "sch-rules.json")
        if os.path.isfile(rules):
            return rules
    return None


def row_schrules(ctx):
    argv = [PY, os.path.join(HERE, "kicad_schrules.py"), ctx["sch"]]
    if ctx["rules"]:
        argv += ["--rules", ctx["rules"]]
    code, out = sh(argv)
    return ("FAIL" if code else "PASS", last(out, r"\d+ error")), out


def row_silk(ctx):
    code, out = sh([PY, os.path.join(HERE, "kicad_silkcheck.py"), ctx["pcb"]])
    head = [l.strip() for l in out.splitlines()
            if l.strip().startswith("silkcheck")]
    return ("FAIL" if code else "PASS", head[0] if head else last(out)), out


def row_ifcheck(ctx):
    argv = [PY, os.path.join(HERE, "kicad_ifcheck.py"), ctx["sch"], "--board",
            ctx["pcb"], "--json"]
    if not ctx["strict_interfaces"]:
        argv += ["--allow-undefined"]
    if ctx["design"]:
        argv += ["--design", ctx["design"]]
    code, out = sh(argv)
    try:
        data = json.loads(out[out.index("{"):])
    except ValueError:
        return ("FAIL", "ifcheck did not run: " + last(out)), out
    results = data.get("results") or []
    if not results:
        return ("SKIP", "no connector declares an interface (design.py "
                        "PARTS[ref].interface)"), out
    tally = {}
    for r in results:
        for row in r["rows"]:
            tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1
    bad = ["%s %s: %s" % (r["ref"], row["rule"], row["message"])
           for r in results for row in r["rows"] if row["verdict"] == "FAIL"]
    warn = ["%s %s: %s" % (r["ref"], row["rule"], row["message"])
            for r in results for row in r["rows"] if row["verdict"] == "WARN"]
    summary = "%d connector(s): %s" % (len(results), ", ".join(
        "%d %s" % (n, v) for v, n in sorted(tally.items())))
    if code:
        return ("FAIL", summary + ("; first: " + bad[0] if bad else "")), out
    if warn:
        return ("WARN", summary + "; first: " + warn[0]), out
    return ("PASS", summary), out


def row_contract(ctx):
    out_path = os.path.join(ctx["scratch"], "fit.json")
    argv = [PY, os.path.join(HERE, "kicad_geom.py"), ctx["pcb"],
            "--contract", out_path]
    if ctx["design"]:
        argv += ["--design", ctx["design"]]
    code, out = sh(argv)
    if not os.path.exists(out_path):
        return ("FAIL", "contract not written: " + last(out)), out
    ctx["contract"] = out_path
    with open(out_path) as fh:
        fit = json.load(fh)
    mating = [p for p in fit["parts"] if p.get("mating")]
    connectors = [p for p in fit["parts"] if p.get("connector")]
    z = fit["z_sources"]
    fails = ["%s: %s" % (f["ref"], f["message"]) if f["ref"] else f["message"]
             for f in fit["findings"] if f["severity"] == "FAIL"]
    undeclared = [p["ref"] for p in connectors if not p.get("mating")]
    reason = ("%d connector(s) (%s), %d mating face(s); heights %d declared, "
              "%d STEP, %d unknown"
              % (len(connectors), ", ".join(p["ref"] for p in connectors)
                 or "none", len(mating), z["declared"], z["step"], z["none"]))
    if undeclared:
        reason += "; %d undeclared mating_direction (%s)" % (
            len(undeclared), ", ".join(undeclared))
    if code or fails:
        return ("FAIL", reason + ("; first: " + fails[0] if fails else "")), out
    if not connectors:
        # A board with nothing to mate proved nothing about mating faces.
        return ("SKIP", "no connector on this board; " + reason), out
    if z["none"]:
        return ("WARN", "%s; %d WARN: part height unknown, so the case row "
                        "cannot clear it" % (reason, z["none"])), out
    return ("PASS", reason), out


def row_case(ctx):
    checks = ctx["case"]
    if not checks:
        return ("SKIP", "no case checks file (--case, or case/checks.py)"), ""
    if not ctx.get("contract"):
        return ("FAIL", "no fit contract to check the case against"), ""
    py, how = case_python(checks, ctx["case_python"])
    code, out = sh([py, os.path.join(HERE, "case_verify.py"), checks,
                    "--contract", ctx["contract"], "--quiet"],
                   env={"HW_FORGE_CONTRACT": ctx["contract"],
                        "HW_FORGE_ROOT": os.path.dirname(HERE),
                        "HW_FORGE_SCRIPTS": HERE})
    return ("FAIL" if code else "PASS",
            "%s (python: %s)" % (last(out, r"checks|FAILED|error"), how)), out


def row_fab(ctx):
    out_dir = os.path.join(ctx["scratch"], "fab")
    argv = [PY, os.path.join(HERE, "kicad_fab.py"), ctx["dir"], "-o", out_dir,
            "--name", ctx["name"]]
    profile = ctx["fab"] or (os.path.join(ctx["dir"], "fab-profile.json")
                             if os.path.isfile(os.path.join(
                                 ctx["dir"], "fab-profile.json")) else None)
    if profile:
        argv += ["--profile", profile]
    code, out = sh(argv)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    failed = [i for i, l in enumerate(lines) if l.startswith("FAILED")]
    if failed:
        why = " ".join(lines[failed[-1]:failed[-1] + 2])
    else:
        why = last(out, r"assert|ok|wrote|manifest")
    if not profile:
        why += " (no profile: artifacts checked, counts not asserted)"
    return ("FAIL" if code else "PASS", why), out


def row_3d(ctx):
    if ctx["no_3d"]:
        return ("SKIP", "--no-3d"), ""
    board = kicad_geom.read_board(ctx["pcb"])
    linked = [f for f in board["footprints"] if f.get("models")]
    if not linked:
        return ("SKIP", "no footprint links a 3D model"), ""
    step = os.path.join(ctx["scratch"], "assembly.step")
    code, out = sh([PY, os.path.join(HERE, "kicad_3d.py"), "export",
                    ctx["pcb"], "-o", step])
    if code or not os.path.exists(step):
        return ("FAIL", "STEP export failed: " + last(out)), out
    missing = re.search(r"(\d+) footprint\(s\) exported with NO body", out)
    code2, out2 = sh([PY, os.path.join(HERE, "kicad_3d.py"), "verify", step,
                      "--board", ctx["pcb"]])
    occ = last(out2, r"occurrences")
    if missing:
        return ("FAIL", "%s footprint(s) exported with no body; %s"
                % (missing.group(1), occ)), out + "\n" + out2
    return ("FAIL" if code2 else "PASS",
            "%d of %d footprints link a model; %s"
            % (len(linked), len(board["footprints"]), occ)), out + "\n" + out2


ROWS = [("preflight", row_preflight), ("gate", row_gate),
        ("fpcheck", row_fpcheck), ("bom", row_bom), ("schrules", row_schrules),
        ("silkcheck", row_silk),
        ("ifcheck", row_ifcheck), ("fit contract", row_contract),
        ("case", row_case), ("fab", row_fab), ("3d", row_3d)]


def review(args):
    name, sch, pcb = discover(args.project_dir, args.name)
    ctx = {"dir": args.project_dir, "name": name, "sch": sch, "pcb": pcb,
           "design": find_design(args.project_dir, args.design),
           "case": find_case(args.project_dir, args.case),
           "case_python": args.case_python, "fab": args.fab,
           "assembly": args.assembly, "no_3d": args.no_3d,
           "rules": find_rules(args.project_dir, args.rules, args.design),
           "strict_interfaces": args.strict_interfaces,
           "scratch": args.keep or tempfile.mkdtemp(prefix="hw_review_")}
    os.makedirs(ctx["scratch"], exist_ok=True)
    has_board, has_sch = os.path.exists(pcb), os.path.exists(sch)
    rows = []
    for label, fn in ROWS:
        needs_board = label not in ("preflight",)
        needs_sch = label in ("gate", "bom", "schrules", "ifcheck", "fab")
        start = time.time()
        if needs_board and not has_board:
            verdict, why, out = "FAIL", "no board file: %s" % pcb, ""
        elif needs_sch and not has_sch:
            verdict, why, out = "FAIL", "no schematic: %s" % sch, ""
        else:
            try:
                (verdict, why), out = fn(ctx)
            except Exception as exc:                   # a crashed check fails
                verdict, why, out = "FAIL", "%s: %s" % (type(exc).__name__,
                                                        exc), ""
        rows.append({"check": label, "verdict": verdict,
                     "seconds": round(time.time() - start, 1),
                     "reason": why, "output": out})
        if args.verbose:
            print("=== %s ===\n%s" % (label, out))
    if not args.keep:
        shutil.rmtree(ctx["scratch"], ignore_errors=True)
    return ctx, rows


def print_table(ctx, rows):
    print("--- hw_review: %s (%s) ---" % (ctx["dir"], ctx["name"]))
    print("  design %s   case %s" % (ctx["design"] or "none",
                                     ctx["case"] or "none"))
    print("  %-13s %-7s %6s  %s" % ("CHECK", "VERDICT", "SEC", "REASON"))
    for r in rows:
        print("  %-13s %-7s %6.1f  %s" % (r["check"], r["verdict"],
                                          r["seconds"], short(r["reason"])))
    fails = [r["check"] for r in rows if r["verdict"] == "FAIL"]
    skips = [r["check"] for r in rows if r["verdict"] in ("SKIP", "WARN")]
    print("  ready to order: %s" % (
        "NO, %d FAIL (%s)" % (len(fails), ", ".join(fails)) if fails
        else "yes" + (", with %d SKIP or WARN not proven (%s)"
                      % (len(skips), ", ".join(skips)) if skips else "")))
    return len(fails)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project_dir", help="directory holding the KiCad project")
    ap.add_argument("--name", help="project basename (default: auto-discover)")
    ap.add_argument("--design", help="design.py (default: PROJECT_DIR or its "
                                     "parent)")
    ap.add_argument("--case", metavar="CHECKS.py",
                    help="enclosure checks file (default: case/checks.py in "
                         "PROJECT_DIR or up to two parents)")
    ap.add_argument("--case-python", metavar="PY",
                    help="the python build123d lives in (default: "
                         "case/.venv/bin/python beside the checks file)")
    ap.add_argument("--fab", metavar="PROFILE",
                    help="kicad_fab.py profile (default: PROJECT_DIR/"
                         "fab-profile.json when present)")
    ap.add_argument("--assembly", choices=["jlcpcb", "none"],
                    help="require assembly sourcing fields in the BOM audit "
                         "(none: no assembly service)")
    ap.add_argument("--rules", metavar="FILE",
                    help="sch-rules.json for the schrules row (default: "
                         "PROJECT_DIR/sch-rules.json, else beside --design)")
    ap.add_argument("--strict-interfaces", action="store_true",
                    help="an interface with no definition is a FAIL in the "
                         "ifcheck row (default: WARN)")
    ap.add_argument("--no-3d", action="store_true",
                    help="skip the STEP assembly row (reported as SKIP)")
    ap.add_argument("--keep", metavar="DIR",
                    help="keep the contract, fab export and STEP in DIR")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print each check's full output")
    args = ap.parse_args()
    if not find_cli()[0]:
        raise SystemExit("error: kicad-cli not found\n  fix: python3 "
                         "scripts/preflight.py")
    ctx, rows = review(args)
    if args.json:
        json.dump({"project": ctx["dir"], "name": ctx["name"],
                   "design": ctx["design"], "case": ctx["case"],
                   "rows": rows,
                   "ready": not any(r["verdict"] == "FAIL" for r in rows)},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        fails = sum(1 for r in rows if r["verdict"] == "FAIL")
    else:
        fails = print_table(ctx, rows)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
