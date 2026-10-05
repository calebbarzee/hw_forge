#!/usr/bin/env python3
"""Export a fab package from a gated KiCad project, then assert it is sane.

One self-contained directory per board: gerbers, excellon drill files split
into plated through-hole (PTH) and non-plated through-hole (NPTH) with map
PDFs and a drill report, pick-and-place for both sides, a grouped bill of
materials (BOM), and the zip a fab actually wants uploaded.

    python3 scripts/kicad_fab.py build/left -o fab/left
    python3 scripts/kicad_fab.py build/left -o fab/left \
        --profile build/left/fab-profile.json

Where the profile lives: one convention, and it is not negotiable.  The
profile sits next to the board project it describes, at
`<project_dir>/fab-profile.json`, never under the output directory.

This tool wipes its output directory on every run, so a profile stored inside
it is deleted by the very run that read it: the run prints `ok`, the profile is
gone, and the next run fails with "no such profile" at a distance from the
cause.  Verified, and now refused at startup.

Run this after `kicad_gate.py` passes and do not refill zones on the way out.
The gerbers must be a plot of exactly the board the design rule check (DRC)
gated, or the files you send the fab are not the board you checked.

The export writes a `<name>-manifest.txt` recording the board hash, the tool
versions, the assertion results and whatever verdict the gate left beside the
project, so "was this zip gated?" is answerable six months later without
archaeology.

Copper layers are read from the board file, so a two-layer and a four-layer
board need no different invocation.

The profile (optional) turns the export into a gate.  Without one, only
non-emptiness is asserted: every expected artifact exists and has bytes.
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
        "no_part_footprints": ["MountingHole:MountingHole_2.2mm_M2"],
        "assembly": "jlcpcb"
      },
      "assert": {
        "npth_holes": {"2.2": 6, "3.988": 22},
        "pth_min_holes": 100,
        "placements": {"top": 12, "bottom": 89},
        "expect_empty_layers": ["F.Paste"],
        "min_file_sizes": {"-F_Cu.gbr": 20000}
      }
    }

`bom.assembly` (optional, default none) turns on the same rule
`scripts/kicad_bom.py audit --assembly jlcpcb` applies: every populated,
non-DNP, non-`no_part_footprints` row must carry a non-empty LCSC part
number, on top of the Description/Manufacturer/MPN/Package/Datasheet check
that runs for every populated, non-DNP, non-`no_part_footprints` row
regardless of `bom.assembly`. A DNP row and a `no_part_footprints` entry (a
mounting hole declared this way rather than through `design.py`'s
`BOARD_INHERENT`, for a project whose schematic predates this doctrine) are
both exempted from every sourcing-field check, the same as `populate`
already marks them as never sourced.

`npth_holes` / `pth_holes` are {diameter_mm: expected_count}, matched with a
tolerance because excellon rounds.  Slots are counted by their minor axis,
which is how a fab tools them.

`placements` takes either a scalar total or a per-side split, and the split is
the one worth writing: the total is the one number a flip-sign error cannot
change.  Flip a part to the wrong face and a 33-placement board still has 33
placements, just 11/22 instead of 12/21.  The export is the last chance to
catch that before a stencil is cut.  Both `-pos-top.csv` and `-pos-bottom.csv`
are already written; the split checks them.

`expect_empty_layers` declares a layer that is supposed to have no apertures,
for example F.Paste on a board whose every surface-mount part is bottom-side.
Emptiness is counted in aperture definitions (`%AD`), not bytes: a paste layer
with nothing to stencil is 451 bytes of pure header, which passes any
non-emptiness test and is indistinguishable from a layer dropped by accident.

Declaring the set also makes it exhaustive: any other aperture-free layer then
fails, which is how a newly empty layer gets caught.  Declare nothing and
undeclared empty layers are reported as notes instead.

A declared-empty layer may also carry its reason, which is how the check stops
being bookkeeping:

      "assert": {
        "expect_empty_layers": [
          {"layer": "F.Paste",
           "because": "L1 puts every SMD part on the bottom face: one stencil,
                       one reflow pass"}
        ],
        "became_populated": ["F.Paste"]
      }

A paste layer crossing between empty and non-empty is a process change, not a
miscount, so it is reported as its own `process change` finding, printed last,
with the per-side placement split beside it.

The reason: a revision that moved two parts to the front face got

    F.Paste is declared empty but defines 3 aperture(s)

as one of four failures, in the same tone as "expected 38 holes, got 45" and
"placements top: expected 13, got 15".  Two of those four were bookkeeping.
That one meant the board now needs a second stencil and a second reflow pass,
which is the most consequential fact in the whole revision for whoever builds
it.  Every one of the four was fixed by the same gesture, editing the number,
and that gesture is what lets a process change through unremarked.

`became_populated` is the acknowledgement: it says a human has read the process
change and accepted it, so the export passes instead of failing, loudly, still
printing what changed and what it costs.  Removing the layer from
`expect_empty_layers` also passes, and says nothing.  Prefer the acknowledgement
for one revision, then clean both up.
"""

import argparse
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True      # never leave __pycache__ in a project tree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kicad_geom
import report as report_mod
from _kicad_env import cli_version, find_cli, run
from kicad_bom import sourced_field_problems

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

BOM_FIELDS = ("Reference,Value,Footprint,DNP,Description,Manufacturer,MPN,"
              "LCSC,Package,Datasheet")
BOM_LABELS = ("Refs,Value,Footprint,DNP,Description,Manufacturer,MPN,LCSC,"
              "Package,Datasheet")

# The sourcing columns carried through from the flat per-symbol export into
# the regrouped BOM, by their BOM_LABELS name. See templates/design.py's
# "Part fields" section for what each one means and who writes it.
BOM_EXTRA_FIELDS = ("Description", "Manufacturer", "MPN", "LCSC", "Package",
                    "Datasheet")


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
        # The first line, not the last: kicad-cli follows a usage error with
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
                   # grouping rules live in the profile, not in a command-line
                   # flag.
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


def side_column(refs, sides):
    """The assembly face(s) of one BOM group, told honestly.

    `sides` maps ref -> (placement_side, pad_side).  A footprint placed on one
    face whose copper pads are all on the other is a standard keyboard
    construction: a hotswap socket takes its switch in from the top and is
    soldered underneath.  Both the pos file and the BOM would otherwise report
    `top`, agree with each other, and mislead.  So the column says where the
    solder goes and names the disagreement.
    """
    faces, flipped = set(), set()
    for ref in refs:
        placed, pads = sides.get(ref, (None, None))
        if placed:
            faces.add(placed)
        if pads and pads not in ("both", placed):
            flipped.add(pads)
    if not faces:
        return ""
    text = "/".join(sorted(faces))
    if flipped:
        text += " (SOLDER %s: pads are there)" % "/".join(sorted(flipped))
    return text


def make_bom(flat_csv, out_csv, bom_profile, sides=None):
    """Regroup a flat per-symbol BOM into one line per distinct part.

    Grouped by (footprint, value, DNP), where DNP is the do-not-populate flag:
    a footprint alone merges parts that differ electrically, and a value alone
    merges a 0603 with an 0805.

    Also carries the sourcing columns (Description, Manufacturer, MPN, LCSC,
    Package, Datasheet -- BOM_EXTRA_FIELDS) through from the flat export, and
    checks every populated, non-DNP, non-board-feature group against
    `kicad_bom.sourced_field_problems`, the same rule
    `scripts/kicad_bom.py audit` applies to the schematic before this ever
    runs. A DNP group (`populate` == "no (DNP)") is exempt from that check
    the same way a `no_part_footprints` group is: it will never be
    populated, so it needs no sourcing fields. Returns (row_count,
    placement_count, bom_fails); a non-empty `bom_fails` is a hard failure
    the same as any other fab assertion, folded into `check()`'s failure
    list by the caller.
    """
    profile = bom_profile or {}
    sides = sides or {}
    rewrites = [(re.compile(pat), repl)
                for pat, repl in profile.get("value_rewrite", [])]
    notes_fp = profile.get("notes_by_footprint", {})
    notes_vf = profile.get("notes_by_value_footprint", {})
    no_part = set(profile.get("no_part_footprints", []))
    assembly = profile.get("assembly")

    groups, extras = {}, {}
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
            key = (footprint, value, dnp)
            groups.setdefault(key, []).append(ref)
            # First row seen for a group sets its sourcing fields. Parts that
            # share a footprint, value and DNP state are meant to be the same
            # physical part, so their descriptive fields should already agree;
            # this does not re-verify that, it just avoids overwriting with a
            # later row's (identical, in the normal case) values.
            extras.setdefault(key, {f: (row.get(f) or "").strip()
                                    for f in BOM_EXTRA_FIELDS})

    rows, bom_fails = [], []
    for key, refs in groups.items():
        footprint, value, dnp = key
        note = notes_vf.get("%s|%s" % (value, footprint)) or \
            notes_fp.get(footprint, "")
        populate = ("n/a (board feature)" if footprint in no_part
                    else ("no (DNP)" if dnp else "yes"))
        fields = extras.get(key, {})
        if populate not in ("n/a (board feature)", "no (DNP)"):
            for rule, detail in sourced_field_problems(fields, value,
                                                        assembly):
                bom_fails.append("%s (%s): %s [%s]"
                                 % (collapse(refs), value, detail, rule))
        rows.append([collapse(refs), value, footprint,
                     fields.get("Description", ""),
                     fields.get("Manufacturer", ""), fields.get("MPN", ""),
                     fields.get("LCSC", ""), fields.get("Package", ""),
                     fields.get("Datasheet", ""), len(refs),
                     side_column(refs, sides), populate, note])
    rows.sort(key=lambda r: natkey(r[0].split(",")[0].split("-")[0]))

    with open(out_csv, "w", newline="") as fh:
        # Header lines are prose for a human, not CSV data: through
        # csv.writer, any line containing a comma comes out quoted and its
        # neighbours do not.  These lines are meant to be read before anything
        # is placed, so the formatting must not look broken.  Only the table
        # gets the writer.
        for line in profile.get("header", []):
            fh.write(line + "\n")
        writer = csv.writer(fh)
        writer.writerow(["Item", "Refs", "Value", "Footprint", "Description",
                         "Manufacturer", "MPN", "LCSC", "Package",
                         "Datasheet", "Qty", "Side", "Populate", "Notes"])
        for i, row in enumerate(rows, 1):
            writer.writerow([i] + row)
        writer.writerow([])
        writer.writerow(["", "TOTAL placements", "", "", "", "", "", "", "",
                         "", sum(r[9] for r in rows), "", "", ""])
    return len(rows), sum(r[9] for r in rows), bom_fails


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


def apertures(path):
    """Number of aperture definitions (`%AD`) in a gerber.

    The honest measure of "does this layer plot anything".  File size is not:
    an aperture-free paste layer is ~451 bytes of header and passes every
    non-emptiness test.
    """
    n = 0
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                if line.startswith("%AD"):
                    n += 1
    except OSError:
        return None
    return n


def placement_rows(path):
    """Number of placement rows in a pos CSV, or None if it is absent."""
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        rows = [l for l in fh.read().splitlines() if l.strip()]
    return max(0, len(rows) - 1)                 # minus the header row


def paste_side(layer):
    """'top' / 'bottom' for a paste layer, else None."""
    if not layer.endswith(".Paste"):
        return None
    return "bottom" if layer.startswith("B.") else "top"


def check(outdir, name, layers, assertions):
    """Assert the export is sane.

    Returns (failures, notes, changes) as string lists.  `changes` is the
    process-change bucket: a paste layer that has crossed between empty and
    non-empty means a stencil and a reflow pass have been added or removed, and
    reporting that as one more count mismatch is how it gets edited away.
    """
    fails, notes, changes = [], [], []
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

    # Placements: a scalar total, or a per-side split checked against the two
    # per-side files.  The split is what catches a part flipped to the wrong
    # face, which leaves the total untouched.
    want = assertions.get("placements")
    if want is None:
        want = assertions.get("placements_by_side")
    if isinstance(want, dict):
        for side, expected in sorted(want.items()):
            suffix = {"top": "-pos-top.csv", "front": "-pos-top.csv",
                      "bottom": "-pos-bottom.csv", "back": "-pos-bottom.csv",
                      "all": "-pos-all.csv", "total": "-pos-all.csv"}.get(side)
            if suffix is None:
                fails.append("placements: unknown side %r (use top/bottom/all)"
                             % side)
                continue
            got = placement_rows(os.path.join(outdir, name + suffix))
            if got is None:
                fails.append("placements %s: %s%s missing"
                             % (side, name, suffix))
            elif got != expected:
                fails.append("placements %s: expected %d, got %d"
                             % (side, expected, got))
        top = placement_rows(os.path.join(outdir, name + "-pos-top.csv"))
        bot = placement_rows(os.path.join(outdir, name + "-pos-bottom.csv"))
        every = placement_rows(os.path.join(outdir, name + "-pos-all.csv"))
        if None not in (top, bot, every) and top + bot != every:
            fails.append("pos files disagree: %d top + %d bottom != %d all"
                         % (top, bot, every))
    elif want is not None:
        got = placement_rows(os.path.join(outdir, name + "-pos-all.csv"))
        if got is not None and got != want:
            fails.append("pos file has %d placements, expected %d"
                         % (got, want))

    # Emptiness by aperture count, not bytes.  A declared empty-layer set is
    # exhaustive: that is what makes a newly empty layer a failure instead of
    # a silence.
    # A declared layer is either a bare name or {"layer": ..., "because": ...}:
    # an assertion that carries the reason it exists is the difference between
    # a number to edit and a decision to re-make.
    declared, because = [], {}
    for entry in (assertions.get("expect_empty_layers") or []):
        if isinstance(entry, dict):
            layer = entry.get("layer")
            if not layer:
                fails.append("expect_empty_layers entry %r has no \"layer\""
                             % entry)
                continue
            declared.append(layer)
            if entry.get("because"):
                because[layer] = " ".join(str(entry["because"]).split())
        else:
            declared.append(entry)
    acknowledged = set(assertions.get("became_populated") or [])

    counts = {}
    for layer in layers:
        path = os.path.join(outdir, "%s-%s.gbr" % (name, layer.replace(".", "_")))
        got = apertures(path)
        if got is not None:
            counts[layer] = got
    for layer in declared:
        if layer not in counts:
            fails.append("expect_empty_layers names %s, which this export "
                         "does not plot" % layer)
            continue
        if counts[layer] == 0:
            continue
        side = paste_side(layer)
        if side is None:
            fails.append("%s is declared empty but defines %d aperture(s)"
                         % (layer, counts[layer]))
            continue
        # The process change.  Routed to its own bucket whether or not it was
        # acknowledged: acknowledging it decides the exit status, never whether
        # it is said out loud.
        line = ("%s was declared EMPTY and now defines %d aperture(s): this "
                "board needs a %s-side stencil and a %s-side reflow pass it "
                "did not need before" % (layer, counts[layer], side, side))
        if layer in because:
            line += "\n            it was empty because: %s" % because[layer]
        if layer not in acknowledged:
            # One short line in the failure list; the detail lives in the
            # process-change section, so the two are not printed twice.
            fails.append("%s: PROCESS CHANGE, not a count to edit: see below. "
                         "Acknowledge it by\n      adding %r to "
                         "\"became_populated\" in the profile, or drop it from "
                         "expect_empty_layers\n      once the new process is "
                         "the intended one." % (layer, layer))
        else:
            line += "\n            acknowledged in the profile "
            line += "(\"became_populated\")."
        changes.append(line)
    for layer, got in sorted(counts.items()):
        if got or layer in declared:
            continue
        line = ("%s plots no apertures (%d bytes of header only)"
                % (layer, os.path.getsize(os.path.join(
                    outdir, "%s-%s.gbr" % (name, layer.replace(".", "_"))))))
        # The change in the other direction: a paste layer that has become
        # empty is one stencil and one reflow pass fewer, which is just as much
        # a process change and just as easy to read as a plotting failure.
        side = paste_side(layer)
        if side is not None and declared:
            changes.append("%s is now EMPTY: no %s-side stencil and no "
                           "%s-side reflow pass is needed any more; every SMD "
                           "part is on the other face" % (layer, side, side))
        if declared:
            fails.append(line + " and is not in expect_empty_layers")
        else:
            notes.append(line + ": declare it in expect_empty_layers if "
                                "that is intended")
    return fails, notes, changes


# ------------------------------------------------------------------- manifest

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def gate_verdict(project_dir, pcb):
    """What the gate left beside this project, as report lines.

    `kicad_gate.py` writes erc.json / drc.json next to the project.  Reading
    them back is not the same thing as gating.  It is the difference between a
    directory of gerbers that claims nothing and one that records which report
    was on disk, what it said, and whether it predates the board file it is
    supposed to describe.

    A gate report older than the board is not a gate of this board, and that is
    the check nobody remembers to do.
    """
    lines = []
    board_mtime = os.path.getmtime(pcb) if os.path.exists(pcb) else 0
    for base in ("erc.json", "drc.json"):
        path = os.path.join(project_dir, base)
        if not os.path.exists(path):
            lines.append("  %-9s ABSENT: no gate report beside the project"
                         % base)
            continue
        try:
            doc = json.load(open(path))
            counts = [(label, len([v for v in items
                                   if v.get("severity") == "error"]),
                       len(items))
                      for label, items in report_mod.sections(doc)]
            verdict = ", ".join("%s %d error(s)/%d item(s)" % c
                                for c in counts)
        except (ValueError, OSError) as exc:
            verdict = "unreadable: %s" % exc
        stale = "" if os.path.getmtime(path) >= board_mtime else \
            "  STALE: older than the board file"
        lines.append("  %-9s %s%s" % (base, verdict, stale))
    return lines


def write_manifest(path, project_dir, name, sch, pcb, layers, profile_path,
                   profile, bom_stats, fails, notes, cli, changes=()):
    """Stamp the provenance of this export into the output directory."""
    lines = ["# %s: fab package manifest" % name,
             "# Written by hw_forge scripts/kicad_fab.py. A directory of "
             "gerbers is not",
             "# self-evidently a plot of a validated board; this file is the "
             "evidence.",
             "",
             "exported     %s (local time)"
             % time.strftime("%Y-%m-%d %H:%M:%S"),
             "project      %s" % os.path.abspath(project_dir),
             "board        %s" % os.path.basename(pcb),
             "  sha256     %s" % sha256(pcb),
             "  bytes      %d" % os.path.getsize(pcb),
             "schematic    %s" % os.path.basename(sch),
             "  sha256     %s" % sha256(sch),
             "profile      %s" % (os.path.abspath(profile_path)
                                  if profile_path else "NONE: "
                                  "non-emptiness only"),
             ]
    if profile_path:
        lines.append("  sha256     %s" % sha256(profile_path))
    lines += ["layers       %s" % ",".join(layers),
              "bom          %d line(s), %d placement(s)" % bom_stats,
              "tools        kicad-cli %s; python %s"
              % (cli_version(cli) or "?", sys.version.split()[0]),
              "",
              "gate reports found beside the project:"]
    lines += gate_verdict(project_dir, pcb)
    lines += ["",
              "assertions   %s"
              % ("PASS (%d assertion group(s) in the profile)"
                 % len(profile.get("assert") or {}) if not fails
                 else "FAIL (%d)" % len(fails))]
    for line in fails:
        lines.append("  FAIL       %s" % line)
    for line in notes:
        lines.append("  note       %s" % line)
    # In the manifest as its own heading, not folded in with the assertions:
    # anyone reading this file back later needs to know the assembly process
    # changed, and that is not the same class of fact as a count that moved.
    if changes:
        lines.append("")
        lines.append("PROCESS CHANGE: this package is not assembled the way "
                     "the previous one was:")
        for line in changes:
            lines.append("  %s" % line.replace("\n            ", "\n    "))
    lines.append("")
    lines.append("This manifest is NOT a substitute for running "
                 "scripts/kicad_gate.py.")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


# ----------------------------------------------------------------------- main

def fab(project_dir, outdir, profile=None, name=None, cli=None, no_x2=False,
        clean=True, profile_path=None):
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

    # Read the board once: the BOM's Side column, and the "placed on one face,
    # soldered on the other" report, are facts about the board that kicad-cli's
    # own exports discard.
    sides, flipped = {}, []
    try:
        board = kicad_geom.read_board(pcb)
    except (SystemExit, ValueError, OSError):
        board = None
    for fp in (board or {}).get("footprints", []):
        ref = fp.get("ref")
        if not ref:
            continue
        sides[ref] = (fp.get("side"), fp.get("pad_side"))
        if fp.get("pad_side") not in (None, "both", fp.get("side")):
            flipped.append((ref, fp["side"], fp["pad_side"], fp.get("lib")))

    lines, placements, bom_fails = make_bom(
        flat, os.path.join(outdir, name + "-bom.csv"), profile.get("bom"),
        sides)
    os.remove(flat)
    print("  bom     %d lines, %d placements" % (lines, placements))
    top = placement_rows(os.path.join(outdir, name + "-pos-top.csv"))
    bot = placement_rows(os.path.join(outdir, name + "-pos-bottom.csv"))
    if None not in (top, bot):
        print("  sides   %d top, %d bottom" % (top, bot))

    zip_path, members = zip_gerbers(outdir, name)
    if zip_path:
        print("  zip     %d files -> %s" % (members,
                                            os.path.basename(zip_path)))

    assertions = profile.get("assert") or {}
    fails, notes, changes = check(outdir, name, layers, assertions)
    # BOM completeness first: a missing Description or LCSC number is the
    # thing a human is most likely to only discover at order time, and it is
    # cheap to fix right here, before the placement/hole assertions below.
    fails = bom_fails + fails

    # Reported, never failed: a footprint on one face with all its copper on
    # the other is correct and standard (a hotswap socket takes its switch in
    # from the top and is soldered underneath).  The pos file reports the
    # footprint's own layer, so it reads Side=top while the part must be
    # soldered on the back; both files agree with each other and both mislead.
    # Say so here, where an assembler-facing document is being written.
    grouped = {}
    for ref, placed, pads, lib in flipped:
        grouped.setdefault((lib, placed, pads), []).append(ref)
    for (lib, placed, pads), refs in sorted(grouped.items()):
        notes.append("%s (%s) placed %s, every pad %s: SOLDER ON THE %s"
                     % (collapse(refs), lib, placed, pads, pads.upper()))

    write_manifest(os.path.join(outdir, name + "-manifest.txt"), project_dir,
                   name, sch, pcb, layers, profile_path, profile,
                   (lines, placements), fails, notes, cli, changes)

    files = [f for f in sorted(os.listdir(outdir))
             if os.path.isfile(os.path.join(outdir, f))]
    total = sum(os.path.getsize(os.path.join(outdir, f)) for f in files)

    for line in notes:
        print("  note    %s" % line)
    if fails:
        print("  FAILED (%d):" % len(fails))
        for line in fails:
            print("    %s" % line)
    # Printed last, after the failures, deliberately: a process change is the
    # one finding here that changes what the assembler does, and the per-side
    # split is printed beside it because that is the number that explains it.
    # It is the last thing on screen whether the export passed or failed.
    if changes:
        print("  PROCESS CHANGE (%d): answer this before exporting again: "
              "did the number of\n  reflow passes change?" % len(changes))
        for line in changes:
            print("    %s" % line)
        if None not in (top, bot):
            print("    per-side placement split now: %d top, %d bottom"
                  % (top, bot))
    if fails:
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
        # Refuse before doing any work: this tool wipes its output directory,
        # so a profile living inside it is destroyed by the run that reads it.
        # The run would succeed and the next one would fail with "no such
        # profile", a long way from the cause.  Verified behaviour, now a
        # startup error.
        if not args.keep:
            out_real = os.path.realpath(args.out)
            prof_real = os.path.realpath(args.profile)
            if prof_real == out_real or prof_real.startswith(
                    out_real + os.sep):
                raise SystemExit(
                    "error: the profile lives inside the output directory\n"
                    "  profile: %s\n"
                    "  outdir:  %s (wiped on every run: the profile would be "
                    "deleted)\n"
                    "  fix: keep the profile next to the board project, "
                    "<project_dir>/fab-profile.json"
                    % (prof_real, out_real))
        with open(args.profile) as fh:
            profile = json.load(fh)

    if fab(args.project_dir, args.out, profile, args.name, no_x2=args.no_x2,
           clean=not args.keep, profile_path=args.profile):
        sys.exit(1)


if __name__ == "__main__":
    main()
