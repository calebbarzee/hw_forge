#!/usr/bin/env python3
"""Export a fab package from a gated KiCad project, then assert it is sane.

One self-contained directory per board: gerbers, PTH/NPTH excellon with map
PDFs and a drill report, pick-and-place for both sides, a grouped BOM, and the
zip a fab actually wants uploaded.

    python3 scripts/kicad_fab.py build/left -o fab/left
    python3 scripts/kicad_fab.py build/left -o fab/left --profile fab/left.json

Run this *after* `kicad_gate.py` passes and do not refill zones on the way out:
the gerbers must be a plot of exactly the board DRC gated, or the files you
send the fab are not the board you checked.

Copper layers are read from the board file, so a two-layer and a four-layer
board need no different invocation.

The profile (optional) turns the export into a gate.  Without one, only
non-emptiness is asserted — every expected artifact exists and has bytes.
With one, the numbers a board can get silently wrong while still passing DRC
get checked too: hole diameters and counts, placement count, minimum file
sizes.  It also carries the per-project BOM normalisation, because "what this
part is called and what the assembler must know about it" is project
knowledge, not tool knowledge.

    {
      "bom": {
        "header": ["# myboard - fab BOM"],
        "value_rewrite": [["^SW_c\\\\d+_.*$", "MX hotswap socket"]],
        "notes_by_footprint": {"MountingHole:MountingHole_2.2mm_M2": "NPTH"},
        "notes_by_value_footprint": {
          "100n|Capacitor_SMD:C_0603_1608Metric": "one per LED, at its VDD pad"
        },
        "no_part_footprints": ["MountingHole:MountingHole_2.2mm_M2"]
      },
      "assert": {
        "npth_holes": {"2.2": 6, "3.988": 22},
        "pth_min_holes": 100,
        "placements": 101,
        "min_file_sizes": {"-F_Cu.gbr": 20000}
      }
    }

`npth_holes` / `pth_holes` are {diameter_mm: expected_count}, matched with a
tolerance because excellon rounds.  Slots are counted by their minor axis,
which is how a fab tools them.
"""

import argparse
import csv
import glob
import json
import os
import re
import shutil
import sys

sys.dont_write_bytecode = True      # never leave __pycache__ in a project tree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kicad_geom
from _kicad_env import find_cli, run

# Non-copper layers every fab package needs, in plot order.
TECH_LAYERS = ["F.Mask", "B.Mask", "F.Silkscreen", "B.Silkscreen",
               "F.Paste", "B.Paste", "Edge.Cuts"]

# Artifacts that must exist for any board, as filename suffixes.
REQUIRED_SUFFIXES = ["-job.gbrjob", "-PTH.drl", "-NPTH.drl",
                     "-PTH-drl_map.pdf", "-NPTH-drl_map.pdf",
                     "-drill-report.txt", "-pos-all.csv", "-pos-top.csv",
                     "-pos-bottom.csv", "-bom.csv", "-gerbers.zip"]

# Excellon writes diameters rounded to its own precision, so hole-diameter
# assertions compare within a tolerance rather than exactly.
DIA_TOL = 0.002

BOM_FIELDS = "Reference,Value,Footprint,DNP"
BOM_LABELS = "Refs,Value,Footprint,DNP"


# ------------------------------------------------------------------ discovery

def discover(project_dir, name=None):
    """(name, sch, pcb) for the single project in a directory."""
    if not os.path.isdir(project_dir):
        raise SystemExit("error: no such directory: %s" % project_dir)
    if name is None:
        stems = {os.path.splitext(e)[0] for e in os.listdir(project_dir)
                 if os.path.splitext(e)[1] in (".kicad_pro", ".kicad_sch",
                                               ".kicad_pcb")}
        if not stems:
            raise SystemExit("error: no KiCad project in %s\n"
                             "  fix: run the project's generator first"
                             % project_dir)
        if len(stems) > 1:
            raise SystemExit("error: %d projects in %s (%s)\n"
                             "  fix: pick one with --name NAME"
                             % (len(stems), project_dir,
                                ", ".join(sorted(stems))))
        name = stems.pop()
    base = os.path.join(project_dir, name)
    return name, base + ".kicad_sch", base + ".kicad_pcb"


def copper_layers(pcb_path):
    """Copper layer names enabled on the board, outer-first then inners."""
    root = kicad_geom.parse_file(pcb_path)
    block = kicad_geom.kid(root, "layers")
    names = []
    if block:
        for entry in block:
            if isinstance(entry, list):
                atoms = kicad_geom.atoms(entry)
                if len(atoms) > 1 and atoms[1].endswith(".Cu"):
                    names.append(atoms[1])
    return names or ["F.Cu", "B.Cu"]


# ---------------------------------------------------------------------- export

def cli_step(cli, argv, what):
    proc = run([cli] + argv)
    if proc.returncode != 0:
        # The *first* line, not the last: kicad-cli follows a usage error with
        # its whole help text, so the tail is never the reason.
        lines = [l for l in ((proc.stderr or "") + "\n"
                             + (proc.stdout or "")).splitlines() if l.strip()]
        raise SystemExit("error: %s failed (kicad-cli exit %d)\n  %s"
                         % (what, proc.returncode,
                            lines[0] if lines else "no output"))
    return proc


def export(cli, name, sch, pcb, outdir, layers, no_x2=False):
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, name)

    gerber_args = ["pcb", "export", "gerbers", "-o", outdir + os.sep,
                   "--layers", ",".join(layers),
                   # Fabs key on the .gbr/.gbrjob names, not Protel's cryptic
                   # .gtl/.gbl extensions; and silk must be subtracted from
                   # mask or legend ink lands on exposed pads.
                   "--no-protel-ext", "--subtract-soldermask"]
    if no_x2:
        gerber_args.append("--no-x2")
    gerber_args.append(pcb)
    cli_step(cli, gerber_args, "gerber export")

    cli_step(cli, ["pcb", "export", "drill", "-o", outdir + os.sep,
                   "--format", "excellon", "--drill-origin", "absolute",
                   "--excellon-units", "mm",
                   # Separate PTH/NPTH: a fab that drills mounting holes as
                   # plated will copper-line them, and a plated M2 hole under
                   # a screw head is a short waiting to happen.
                   "--excellon-separate-th",
                   "--excellon-zeros-format", "decimal",
                   "--generate-map", "--map-format", "pdf",
                   "--generate-report",
                   "--report-path", base + "-drill-report.txt",
                   pcb], "drill export")

    for side, suffix in (("both", "all"), ("front", "top"), ("back", "bottom")):
        cli_step(cli, ["pcb", "export", "pos", "-o",
                       "%s-pos-%s.csv" % (base, suffix), "--side", side,
                       "--format", "csv", "--units", "mm", pcb], "pos export")

    flat = os.path.join(outdir, ".bom-flat.csv")
    cli_step(cli, ["sch", "export", "bom", "-o", flat,
                   "--fields", BOM_FIELDS, "--labels", BOM_LABELS,
                   # One row per symbol: this tool does the grouping, so the
                   # grouping rules live in the profile and not in a CLI flag.
                   "--group-by", "", "--sort-field", "Reference",
                   "--ref-range-delimiter", "", sch], "bom export")
    return flat


def zip_gerbers(outdir, name):
    """Zip the gerber+drill set, the one artifact a fab wants uploaded."""
    members = []
    for pattern in ("*.gbr", "*.gbrjob", "*.drl"):
        members += sorted(glob.glob(os.path.join(outdir, pattern)))
    if not members:
        return None, 0
    zip_base = os.path.join(outdir, name + "-gerbers")
    staging = os.path.join(outdir, ".zipstage")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    try:
        for path in members:
            shutil.copy2(path, staging)
        # make_archive appends .zip; remove any stale one first so the archive
        # cannot accumulate files from an earlier layer stackup.
        if os.path.exists(zip_base + ".zip"):
            os.remove(zip_base + ".zip")
        shutil.make_archive(zip_base, "zip", staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return zip_base + ".zip", len(members)


# -------------------------------------------------------------------- the BOM

def natkey(ref):
    """R12 -> ('R', 12) so refs sort the way a human reads them."""
    m = re.match(r"^([A-Za-z_]+?)_?(\d+)$", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def collapse(refs):
    """R1,R2,R3,R7 -> 'R1-R3,R7'."""
    out, run_ = [], []

    def flush():
        if not run_:
            return
        out.append("%s-%s" % (run_[0], run_[-1]) if len(run_) > 2
                   else ",".join(run_))
        del run_[:]

    prev = None
    for ref in sorted(refs, key=natkey):
        key = natkey(ref)
        if prev and key[0] == prev[0] and key[1] == prev[1] + 1:
            run_.append(ref)
        else:
            flush()
            run_.append(ref)
        prev = key
    flush()
    return ",".join(out)


def make_bom(flat_csv, out_csv, bom_profile):
    """Regroup a flat per-symbol BOM into one line per distinct part.

    Grouped by (footprint, value, DNP): a footprint alone merges parts that
    differ electrically, and a value alone merges a 0603 with an 0805.
    """
    profile = bom_profile or {}
    rewrites = [(re.compile(pat), repl)
                for pat, repl in profile.get("value_rewrite", [])]
    notes_fp = profile.get("notes_by_footprint", {})
    notes_vf = profile.get("notes_by_value_footprint", {})
    no_part = set(profile.get("no_part_footprints", []))

    groups = {}
    with open(flat_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            ref = (row.get("Refs") or row.get("Reference") or "").strip()
            if not ref:
                continue
            # kicad-cli decorates any refdes it considers unannotated (one with
            # no numeric suffix, e.g. SW_PWR) with a trailing '?'. The board
            # says SW_PWR, so strip it or the BOM disagrees with the placement
            # file over a part that is perfectly well annotated.
            ref = ref.rstrip("?")
            value = (row.get("Value") or "").strip()
            footprint = (row.get("Footprint") or "").strip()
            dnp = (row.get("DNP") or "").strip().lower() in ("1", "true",
                                                             "yes", "dnp")
            for pattern, repl in rewrites:
                if pattern.match(value):
                    value = repl
                    break
            groups.setdefault((footprint, value, dnp), []).append(ref)

    rows = []
    for (footprint, value, dnp), refs in groups.items():
        note = notes_vf.get("%s|%s" % (value, footprint)) or \
            notes_fp.get(footprint, "")
        populate = ("n/a (board feature)" if footprint in no_part
                    else ("no (DNP)" if dnp else "yes"))
        rows.append([collapse(refs), value, footprint, len(refs), populate,
                     note])
    rows.sort(key=lambda r: natkey(r[0].split(",")[0].split("-")[0]))

    with open(out_csv, "w", newline="") as fh:
        writer = csv.writer(fh)
        for line in profile.get("header", []):
            writer.writerow([line])
        writer.writerow(["Item", "Refs", "Value", "Footprint", "Qty",
                         "Populate", "Notes"])
        for i, row in enumerate(rows, 1):
            writer.writerow([i] + row)
        writer.writerow([])
        writer.writerow(["", "TOTAL placements", "", "",
                         sum(r[3] for r in rows), "", ""])
    return len(rows), sum(r[3] for r in rows)


# ----------------------------------------------------------------- assertions

def drill_tools(path):
    """{diameter_mm: hit_count} from an excellon file."""
    tools, current, hits = {}, None, {}
    with open(path) as fh:
        for line in fh:
            m = re.match(r"^T(\d+)C([\d.]+)", line)
            if m:
                tools[m.group(1)] = float(m.group(2))
                continue
            m = re.match(r"^T(\d+)\s*$", line)
            if m:
                current = m.group(1)
                continue
            if current and line[:1] in ("X", "Y"):
                hits[current] = hits.get(current, 0) + 1
    out = {}
    for tool_id, dia in tools.items():
        out[dia] = out.get(dia, 0) + hits.get(tool_id, 0)
    return out


def match_diameter(tools, wanted):
    """Total hits for the tool nearest `wanted`, within DIA_TOL."""
    return sum(n for dia, n in tools.items() if abs(dia - wanted) <= DIA_TOL)


def check(outdir, name, layers, assertions):
    """Assert the export is sane. Returns a list of failure strings."""
    fails = []
    expected = ["-%s.gbr" % l.replace(".", "_") for l in layers]
    expected += REQUIRED_SUFFIXES
    expected += assertions.get("extra_files", [])

    # Always asserted, profile or not: an export of nothing must not look
    # like a success.
    for suffix in expected:
        path = os.path.join(outdir, name + suffix)
        if not os.path.exists(path):
            fails.append("missing %s" % os.path.basename(path))
        elif os.path.getsize(path) == 0:
            fails.append("empty %s" % os.path.basename(path))

    for suffix, min_size in (assertions.get("min_file_sizes") or {}).items():
        path = os.path.join(outdir, name + suffix)
        if os.path.exists(path) and os.path.getsize(path) < min_size:
            fails.append("%s is %d bytes, expected >= %d"
                         % (os.path.basename(path), os.path.getsize(path),
                            min_size))

    for key, label in (("npth_holes", "NPTH"), ("pth_holes", "PTH")):
        wanted = assertions.get(key) or {}
        path = os.path.join(outdir, "%s-%s.drl" % (name, label))
        if not wanted or not os.path.exists(path):
            continue
        tools = drill_tools(path)
        for dia_str, count in wanted.items():
            got = match_diameter(tools, float(dia_str))
            if got != count:
                fails.append("%s %smm: expected %d holes, got %d"
                             % (label, dia_str, count, got))

    pth = os.path.join(outdir, name + "-PTH.drl")
    min_pth = assertions.get("pth_min_holes")
    if min_pth is not None and os.path.exists(pth):
        total = sum(drill_tools(pth).values())
        if total < min_pth:
            fails.append("PTH drill has %d holes, expected >= %d"
                         % (total, min_pth))

    pos = os.path.join(outdir, name + "-pos-all.csv")
    want_placements = assertions.get("placements")
    if want_placements is not None and os.path.exists(pos):
        with open(pos) as fh:
            rows = [l for l in fh.read().splitlines() if l.strip()]
        got = len(rows) - 1                     # minus the header row
        if got != want_placements:
            fails.append("pos file has %d placements, expected %d"
                         % (got, want_placements))
    return fails


# ----------------------------------------------------------------------- main

def fab(project_dir, outdir, profile=None, name=None, cli=None, no_x2=False,
        clean=True):
    """Export and check one project. Returns the number of failures."""
    profile = profile or {}
    name, sch, pcb = discover(project_dir, name)
    for path, what in ((sch, "schematic"), (pcb, "board")):
        if not os.path.exists(path):
            raise SystemExit("error: no %s at %s\n"
                             "  fix: run the project's generator first"
                             % (what, path))
    if cli is None:
        cli, how = find_cli()
        if not cli:
            raise SystemExit("error: kicad-cli not found (%s)\n"
                             "  fix: install KiCad 10, or set "
                             "KICAD_ROOT=/Applications/KiCad/KiCad.app/Contents\n"
                             "  check: python3 scripts/preflight.py" % how)

    layers = profile.get("layers") or (copper_layers(pcb) + TECH_LAYERS)
    print("--- fab: %s ---" % name)
    print("  layers  %s" % ",".join(layers))

    if clean and os.path.isdir(outdir):
        shutil.rmtree(outdir)
    flat = export(cli, name, sch, pcb, outdir, layers, no_x2)

    lines, placements = make_bom(flat, os.path.join(outdir, name + "-bom.csv"),
                                 profile.get("bom"))
    os.remove(flat)
    print("  bom     %d lines, %d placements" % (lines, placements))

    zip_path, members = zip_gerbers(outdir, name)
    if zip_path:
        print("  zip     %d files -> %s" % (members,
                                            os.path.basename(zip_path)))

    assertions = profile.get("assert") or {}
    fails = check(outdir, name, layers, assertions)
    files = [f for f in sorted(os.listdir(outdir))
             if os.path.isfile(os.path.join(outdir, f))]
    total = sum(os.path.getsize(os.path.join(outdir, f)) for f in files)

    if fails:
        print("  FAILED (%d):" % len(fails))
        for line in fails:
            print("    %s" % line)
        return len(fails)
    print("  ok      %d files, %.0f KiB -> %s%s"
          % (len(files), total / 1024.0, outdir,
             "" if assertions else "  (no profile: non-emptiness only)"))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project_dir", help="directory holding the KiCad project")
    ap.add_argument("-o", "--out", required=True, help="output directory")
    ap.add_argument("--profile", help="profile JSON (BOM rules + assertions)")
    ap.add_argument("--name", help="project basename (default: auto-discover)")
    ap.add_argument("--no-x2", action="store_true",
                    help="plot plain RS-274X without X2 attributes, for a fab "
                         "whose CAM chokes on them")
    ap.add_argument("--keep", action="store_true",
                    help="do not wipe the output directory first")
    args = ap.parse_args()

    profile = {}
    if args.profile:
        if not os.path.exists(args.profile):
            raise SystemExit("error: no such profile: %s" % args.profile)
        with open(args.profile) as fh:
            profile = json.load(fh)

    if fab(args.project_dir, args.out, profile, args.name, no_x2=args.no_x2,
           clean=not args.keep):
        sys.exit(1)


if __name__ == "__main__":
    main()
