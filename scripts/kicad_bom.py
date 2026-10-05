#!/usr/bin/env python3
"""Audit and export a bill of materials (BOM) that a buyer can act on.

Two failures motivated this script, both reported by a user after using
hw_forge to design a real board.

  1. **Descriptions were empty or useless.** `kicad-cli sch export bom` only
     ever emits what a symbol's own properties carry, and a schematic
     generator that never wrote Description, Manufacturer, MPN, Package,
     Datasheet or a distributor part number produces a BOM of bare values:
     "100n", "470", "1N4148W". Verified directly: exporting
     `hexpad.kicad_sch` with the full field list produced 34 rows with every
     one of those six columns empty (`.tmp/hexpad_bom_probe.csv`).
  2. **Board-inherent geometry showed up as parts to buy.** The same export
     listed four mounting holes (H1-H4) as BOM rows. A mounting hole is a
     property of the board, not a component an assembler sources and
     solders on; the same is true of a fiducial, a test point, a logo, a
     net tie, and a cutout with no part mounted in it.

Both failures are silent under every gate hw_forge already runs: ERC, DRC,
schematic parity and `kicad_fpcheck.py` all compare the board to itself or
to its own schematic, never to what a human would need to place an order.
This script is that comparison.

    python3 scripts/kicad_bom.py audit SCHEMATIC.kicad_sch \\
        [--board BOARD.kicad_pcb] [--design design.py] \\
        [--assembly jlcpcb|none] [--json]
    python3 scripts/kicad_bom.py export SCHEMATIC.kicad_sch -o OUT.csv \\
        [--assembly jlcpcb]

`audit` reads the schematic (and, optionally, the board) directly as
s-expressions -- no kicad-cli invocation, no pcbnew -- and checks every
symbol instance against one of two rulebooks depending on what kind of
thing it is:

  * A **board-inherent** symbol (a mounting hole, fiducial, test point,
    logo, net tie, or edge connector formed by the board itself) must be
    excluded from the bill of materials on both the schematic side
    (`in_bom no`) and, when a board file is given, the footprint side
    (`(attr ... exclude_from_bom ...)`).
  * A **sourced** part (anything else) must carry a buyer-usable
    Description, Manufacturer, MPN, Package and Datasheet, plus an LCSC
    part number when `--assembly jlcpcb` -- unless it is marked `(dnp yes)`,
    in which case it will never be populated and is exempt from every
    missing-field check (an INFO line names the exemption). A DNP part with
    a present-but-broken field, e.g. a Description that just repeats the
    Value, is not exempt from that check: DNP only excuses a field from
    being required, not from being wrong when it is there.

`export` runs the real `kicad-cli sch export bom` with the full field list,
grouped by Value plus Footprint plus MPN, `--exclude-dnp`, then re-reads the
CSV it wrote and fails if any required column is empty on any row.
`--exclude-dnp` drops every DNP row before the CSV is even written, which is
the same exemption `audit` applies by reading `(dnp yes)` itself: the two
commands agree on which parts need sourcing fields, they just reach that
agreement by different means (kicad-cli's own flag versus this script's own
parse). A board-inherent symbol correctly marked `in_bom no` never reaches
this CSV at all -- kicad-cli drops it at export time, confirmed against
KiCad 10.0.5: the deprecated `--include-excluded-from-bom` flag has no
effect, so there is no way to make an excluded symbol reappear. That is the
mechanism this script's `audit` step exists to get right before export ever
runs.

Field names, verified against a real project's placed symbol instances and
against KiCad 10's own stock footprint library rather than assumed:

    schematic symbol instance (a bare boolean, not a named property):
        (symbol
            (lib_id "Mechanical:MountingHole")
            (at 444.5 368.3 0)
            (unit 1)
            (exclude_from_sim no)
            (in_bom no)              <- board-inherent: excluded here
            (on_board yes)
            (dnp no)                 <- populated: sourcing fields required
            ...)

    footprint (attr ...), read directly from KiCad 10's shipped library:
        MountingHole_2.2mm_M2.kicad_mod:        (attr exclude_from_pos_files exclude_from_bom)
        TestPoint_THTPad_D2.0mm...kicad_mod:    (attr exclude_from_pos_files exclude_from_bom)
        Fiducial_1mm_Mask2mm.kicad_mod:         (attr smd exclude_from_bom)

    a normal sourced descriptive field, a named property like any other:
        (property "Description" "100nF X7R ceramic capacitor, 0603"
            (at 444.5 368.3 0)
            (effects (font (size 1.27 1.27)) (hide yes)))

A third kind sits between the two:

  * An **off-board** part (kind `off_board`) is a pad set whose BOM row is
    the off-board part it receives: a panel connector on a pigtail soldered
    to wire pads, a microphone capsule on leads, a battery on a lead pair.
    The part is bought, so the symbol stays `in_bom yes` and carries every
    sourcing field a sourced part does.  Nothing is placed on the board by a
    machine, so the footprint carries `exclude_from_pos_files`.  And the
    footprint must not carry `exclude_from_bom`: KiCad's schematic parity
    compares that attribute with the symbol's `in_bom`, so a stock
    `Connector_Wire:SolderWire-*` footprint (which ships with both
    attributes) fails parity as `footprint_symbol_mismatch` until the
    generator clears it.  Before this kind existed both choices failed:
    `in_bom no` failed SOURCED_EXCLUDED_FROM_BOM, `in_bom yes` failed parity
    (hypercardiod_mic GAPS.md gap 6).

    Declared by design.py `BOARD_INHERENT[ref] = "off_board"` or by an
    `offboard` block in `PARTS[ref]` (the fit contract's off-board record);
    a footprint from `Connector_Wire:SolderWire*` is taken as off-board when
    neither says otherwise.

See `templates/design.py`'s "Board-inherent kinds" and "Part fields"
sections for the doctrine this script gates, and `commands/hw-bom.md` for
the fill-in procedure.

Limitation: this reads one `.kicad_sch` file's own top-level symbol
instances. A hierarchical design whose sub-sheets live in separate files is
not walked; run this against each sheet file, or flatten first. Every
project this script has been run against (hexpad, z_board) is a single
flat sheet.
"""

import argparse
import csv
import importlib.util
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kicad_geom  # noqa: E402  (reuse its s-expression tokenizer/parser)
from _kicad_env import find_cli, run  # noqa: E402

# ------------------------------------------------------------ named constants

# "A sentence a buyer can act on" is not a formal grammar, so word count plus
# "not just the value" is the cheapest proxy that still catches the measured
# failure: every one of 34 rows in the probe export had Description empty,
# and the next-cheapest mistake is copying the value into it verbatim.
MIN_DESC_WORDS = 4

# Reference-prefix heuristic: the convention this script's own doctrine
# (templates/design.py) asks a project to follow. An explicit design.py
# BOARD_INHERENT entry always wins over this; the prefix is the fallback for
# a project that has not written one.
PREFIX_KIND = {
    "H": "mounting_hole",
    "MH": "mounting_hole",
    "FID": "fiducial",
    "TP": "test_point",
    "LOGO": "logo",
    "NT": "net_tie",
}

# Library-name heuristic, checked against both the symbol's lib_id and its
# Footprint property, substring, case-insensitive. Longest/most specific
# names first is not needed here: the names do not collide with each other.
LIB_KIND_HINTS = (
    ("MountingHole", "mounting_hole"),
    ("Fiducial", "fiducial"),
    ("TestPoint", "test_point"),
    ("Logo", "logo"),
    ("NetTie", "net_tie"),
    ("EdgeConnector", "edge_connector"),
)

# What kicad-cli's own drill/pos exporters would still count as a plated or
# through-hole feature -- a board-inherent kind whose footprint, if it kept
# a copper pad rather than being purely a marker, should also stay out of
# the placement file. Checked as a NOTE, not a FAIL: exclude_from_pos_files
# is doctrine (templates/design.py), not a hard gate this script enforces,
# because a fiducial legitimately omits it (see the module docstring).
POS_FILE_RELEVANT_KINDS = {"mounting_hole", "test_point"}

# A pad set whose BOM row is the off-board part it receives (module
# docstring).  Not board-inherent: it is sourced, and stays on the BOM.
OFF_BOARD = "off_board"
OFF_BOARD_LIB_HINTS = ("Connector_Wire:SolderWire",)

REQUIRED_SOURCED_FIELDS = ("Manufacturer", "MPN", "Package", "Datasheet")

# The full field list `export` asks kicad-cli for, and the CSV column labels
# it prints them under. QUANTITY is a kicad-cli 10 generated field (verified
# via `kicad-cli sch export bom --help`), not a symbol property.
FULL_FIELDS = ("Reference", "Value", "Footprint", "Description",
               "Manufacturer", "MPN", "LCSC", "Package", "Datasheet",
               "QUANTITY")
FULL_LABELS = ("Refs", "Value", "Footprint", "Description", "Manufacturer",
               "MPN", "LCSC", "Package", "Datasheet", "Qty")

# The columns `export` re-checks for emptiness, keyed by the label above.
REQUIRED_LABELS = ("Description", "Manufacturer", "MPN", "Package",
                    "Datasheet")


# --------------------------------------------------------- shared field rules
#
# Exported so scripts/kicad_fab.py's `make_bom` can apply the same rule to
# its own regrouped BOM rows, instead of a second, driftable copy of "what
# counts as a complete part".

def sourced_field_problems(fields, value, assembly=None,
                            min_words=MIN_DESC_WORDS):
    """[(rule, detail), ...] for one sourced part's field set.

    `fields` maps property/column name -> string value (may be missing or
    blank). Empty return means the part is complete. `assembly` is
    "jlcpcb", or None/"none" when no assembly service applies.
    """
    problems = []
    desc = (fields.get("Description") or "").strip()
    if not desc:
        problems.append(("SOURCED_MISSING_DESCRIPTION",
                         "Description is empty"))
    elif len(desc.split()) < min_words:
        problems.append(("SOURCED_DESCRIPTION_TOO_SHORT",
                         "Description is %d word(s), want >= %d: %r"
                         % (len(desc.split()), min_words, desc)))
    elif desc.strip().lower() == (value or "").strip().lower():
        problems.append(("SOURCED_DESCRIPTION_EQUALS_VALUE",
                         "Description just repeats the value: %r" % desc))
    for field in REQUIRED_SOURCED_FIELDS:
        rule = "SOURCED_MISSING_%s" % field.upper()
        if not (fields.get(field) or "").strip():
            problems.append((rule, "%s is empty" % field))
    if assembly == "jlcpcb" and not (fields.get("LCSC") or "").strip():
        problems.append(("SOURCED_MISSING_LCSC",
                         "LCSC is empty (required when assembly=jlcpcb)"))
    return problems


# ------------------------------------------------------------------- loading

def load_design_table(path, attr):
    """`getattr(imported design.py, attr, {})`, or {} if no path is given.

    Same mechanism as kicad_fpcheck.py's load_design_packages: design.py is
    pure stdlib per hw_forge doctrine, so importing it directly under
    system python3 is safe.
    """
    if not path:
        return {}
    spec = importlib.util.spec_from_file_location(
        "hwforge_design_bomcheck_%s" % attr, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, attr, {}) or {}


# -------------------------------------------------------------- schematic IO

def iter_symbol_instances(sch_path):
    """Yield each top-level placed `(symbol ...)` node in a .kicad_sch.

    Deliberately `kicad_geom.kids(root, "symbol")`, direct children only:
    the `(lib_symbols (symbol "Name" ...) ...)` cache is nested one level
    deeper and is never returned by this.
    """
    root = kicad_geom.parse_file(sch_path)
    if not root or root[0] != "kicad_sch":
        raise SystemExit("error: %s is not a .kicad_sch (root is %r)"
                         % (sch_path, root[0] if root else None))
    return kicad_geom.kids(root, "symbol")


def symbol_fields(node):
    """(ref, value, lib_id, in_bom, dnp, fields) for one placed symbol.

    `dnp` is the do-not-populate token, `(dnp yes|no)`, sitting at the same
    level as `(in_bom yes)` on every placed symbol instance (verified
    against a real KiCad 10 .kicad_sch; see this module's docstring).
    """
    lib_id_node = kicad_geom.kid(node, "lib_id")
    lib_atoms = kicad_geom.atoms(lib_id_node) if lib_id_node else []
    lib_id = lib_atoms[1] if len(lib_atoms) > 1 else ""

    in_bom_node = kicad_geom.kid(node, "in_bom")
    in_bom_atoms = kicad_geom.atoms(in_bom_node) if in_bom_node else []
    # Absent means the file predates this check or the instance is
    # malformed; KiCad's own default for a freshly placed symbol is "yes",
    # so an absent tag is treated the same way a real "yes" would be.
    in_bom = in_bom_atoms[1] if len(in_bom_atoms) > 1 else "yes"

    dnp_node = kicad_geom.kid(node, "dnp")
    dnp_atoms = kicad_geom.atoms(dnp_node) if dnp_node else []
    # Same reasoning as in_bom above: KiCad's own default for a freshly
    # placed symbol is "no" (populated), so an absent tag reads as "no".
    dnp = dnp_atoms[1] if len(dnp_atoms) > 1 else "no"

    ref = value = ""
    fields = {}
    for prop in kicad_geom.kids(node, "property"):
        names = kicad_geom.atoms(prop)
        if len(names) >= 3:
            fields[names[1]] = names[2]
            if names[1] == "Reference":
                ref = names[2]
            elif names[1] == "Value":
                value = names[2]
    return ref, value, lib_id, in_bom, dnp, fields


def board_footprint_attrs(board_path):
    """{ref: [attr tokens]} for every footprint in a .kicad_pcb.

    A footprint with no `(attr ...)` block at all (KiCad omits it when
    nothing is set, as a stock MountingHole footprint without its own
    exclusion tokens does) maps to an empty list, not an absence, so a
    lookup miss always means "no matching footprint on this board".
    """
    root = kicad_geom.parse_file(board_path)
    if not root or root[0] != "kicad_pcb":
        raise SystemExit("error: %s is not a .kicad_pcb (root is %r)"
                         % (board_path, root[0] if root else None))
    out = {}
    for fp in kicad_geom.kids(root, "footprint"):
        ref = ""
        for prop in kicad_geom.kids(fp, "property"):
            names = kicad_geom.atoms(prop)
            if len(names) >= 3 and names[1] == "Reference":
                ref = names[2]
        if not ref:
            continue
        attr_node = kicad_geom.kid(fp, "attr")
        out[ref] = kicad_geom.atoms(attr_node)[1:] if attr_node else []
    return out


# --------------------------------------------------------------- kind rules

def kind_of(ref, value, lib_id, footprint, board_inherent, parts=None):
    """(kind, source) for a symbol, or (None, None) when it is sourced.

    Priority: an explicit design.py BOARD_INHERENT entry (by ref, then by
    value, matching PACKAGES's own fallback order) always wins, then a PARTS
    row with an `offboard` block (kind off_board). Below that, the
    reference-prefix and library-name heuristics, which exist so an
    undeclared board-inherent part is still caught rather than silently
    treated as something to buy.
    """
    for key in (ref, value):
        if key and key in board_inherent:
            return board_inherent[key], "design.py BOARD_INHERENT[%r]" % key
    for key in (ref, value):
        row = (parts or {}).get(key) if key else None
        if isinstance(row, dict) and row.get("offboard"):
            return OFF_BOARD, "design.py PARTS[%r].offboard" % key
    for needle in OFF_BOARD_LIB_HINTS:
        if needle.lower() in (footprint or "").lower():
            return OFF_BOARD, "footprint library %r" % footprint
    prefix = kicad_geom.designator(ref)["prefix"].upper()
    if prefix in PREFIX_KIND:
        return PREFIX_KIND[prefix], "reference prefix %r" % prefix
    for needle, kind in LIB_KIND_HINTS:
        low = needle.lower()
        if low in (lib_id or "").lower():
            return kind, "symbol library %r" % lib_id
        if low in (footprint or "").lower():
            return kind, "footprint library %r" % footprint
    return None, None


def off_board_findings(ref, source, in_bom, attrs):
    """Findings for an off_board part's BOM row and its footprint's attrs."""
    out = []
    if in_bom == "no":
        out.append(("FAIL", "OFF_BOARD_EXCLUDED_FROM_BOM",
                    "kind=off_board (%s) but in_bom=no: the off-board part "
                    "is bought, so the schematic emitter must set in_bom yes"
                    % source))
    if attrs is None:
        return out
    tokens = attrs.get(ref)
    if tokens is None:
        out.append(("FAIL", "OFF_BOARD_NO_FOOTPRINT",
                    "kind=off_board but no footprint with Reference=%s was "
                    "found on the given board" % ref))
        return out
    if "exclude_from_bom" in tokens:
        out.append(("FAIL", "OFF_BOARD_FOOTPRINT_EXCLUDE",
                    "kind=off_board but the footprint carries "
                    "exclude_from_bom (stock SolderWire footprints do): "
                    "schematic parity fails footprint_symbol_mismatch "
                    "against in_bom yes. fix: the board emitter clears it, "
                    "fp.SetExcludedFromBOM(False)"))
    if "exclude_from_pos_files" not in tokens:
        out.append(("FAIL", "OFF_BOARD_POS_FILE",
                    "kind=off_board but the footprint lacks "
                    "exclude_from_pos_files: the placement file would ask a "
                    "machine to place a hand-wired part. fix: "
                    "fp.SetExcludedFromPosFiles(True)"))
    return out


# ------------------------------------------------------------------- audit

def audit(sch_path, board_path=None, design_path=None, assembly=None,
          min_desc_words=MIN_DESC_WORDS):
    """[{ref, value, kind, in_bom, dnp, findings: [(status, rule, detail)]}, ...]"""
    board_inherent = load_design_table(design_path, "BOARD_INHERENT")
    parts = load_design_table(design_path, "PARTS")
    attrs = board_footprint_attrs(board_path) if board_path else None

    results = []
    seen = set()
    for node in iter_symbol_instances(sch_path):
        ref, value, lib_id, in_bom, dnp, fields = symbol_fields(node)
        # Power-flag and no-connect symbols (#PWR01, #FLG01, ...) and bare
        # power-symbol library placements are not components; nothing a
        # human sources or solders.
        if not ref or ref.startswith("#") or lib_id.startswith("power:"):
            continue
        if ref in seen:
            continue
        seen.add(ref)

        footprint_prop = fields.get("Footprint", "")
        kind, kind_source = kind_of(ref, value, lib_id, footprint_prop,
                                    board_inherent, parts)
        findings = []

        if kind == OFF_BOARD:
            # Its sourcing fields are checked below, as a sourced part's.
            findings += off_board_findings(ref, kind_source, in_bom, attrs)
        if kind and kind != OFF_BOARD:
            if in_bom != "no":
                findings.append((
                    "FAIL", "BOARD_INHERENT_IN_BOM",
                    "kind=%s (%s) but in_bom=%s -- the schematic emitter "
                    "must set in_bom no for this ref"
                    % (kind, kind_source, in_bom)))
            if attrs is not None:
                tokens = attrs.get(ref)
                if tokens is None:
                    findings.append((
                        "FAIL", "BOARD_INHERENT_NO_FOOTPRINT",
                        "kind=%s but no footprint with Reference=%s was "
                        "found on the given board" % (kind, ref)))
                elif "exclude_from_bom" not in tokens:
                    findings.append((
                        "FAIL", "BOARD_INHERENT_FOOTPRINT_EXCLUDE",
                        "kind=%s but the footprint's (attr ...) does not "
                        "carry exclude_from_bom: got %s"
                        % (kind, tokens or ["<none>"])))
                elif (kind in POS_FILE_RELEVANT_KINDS
                      and "exclude_from_pos_files" not in tokens):
                    findings.append((
                        "NOTE", "BOARD_INHERENT_POS_FILE",
                        "kind=%s and exclude_from_bom is set, but "
                        "exclude_from_pos_files is not -- this ref will "
                        "still appear as a phantom placement row"
                        % kind))
        else:
            if in_bom == "no" and kind != OFF_BOARD:
                findings.append((
                    "FAIL", "SOURCED_EXCLUDED_FROM_BOM",
                    "no board-inherent kind matched this ref, but "
                    "in_bom=no -- a real part will not appear on the BOM "
                    "at all"))
            problems = sourced_field_problems(
                fields, value, assembly, min_desc_words)
            if dnp == "yes":
                # A DNP part is never populated, so it is exempt from every
                # check that a buyer-facing sourcing field is missing -- the
                # same exemption `export` gets for free from kicad-cli's own
                # --exclude-dnp. Any other problem (e.g. a present
                # Description that just repeats the value) still fails.
                exempt = [(rule, detail) for rule, detail in problems
                         if rule.startswith("SOURCED_MISSING_")]
                other = [(rule, detail) for rule, detail in problems
                        if not rule.startswith("SOURCED_MISSING_")]
                for rule, detail in other:
                    findings.append(("FAIL", rule, detail))
                if exempt:
                    findings.append((
                        "INFO", "DNP_EXEMPT",
                        "dnp=yes -- exempting %s from %d missing-field "
                        "check(s): %s"
                        % (ref, len(exempt),
                           ", ".join(rule for rule, _ in exempt))))
            else:
                for rule, detail in problems:
                    findings.append(("FAIL", rule, detail))

        if not findings:
            findings.append(("PASS", "-", "complete"))
        results.append({"ref": ref, "value": value,
                        "kind": kind or "sourced", "in_bom": in_bom,
                        "dnp": dnp, "findings": findings})

    def _sort_key(r):
        d = kicad_geom.designator(r["ref"])
        return (d["prefix"], d["index"] if d["index"] is not None else -1)

    results.sort(key=_sort_key)
    return results


def print_audit(sch_path, results, verbose=False):
    print("--- kicad_bom audit: %s ---" % sch_path)
    fails = notes = 0
    for r in results:
        worst = "PASS"
        for status, _, _ in r["findings"]:
            if status == "FAIL":
                worst = "FAIL"
            elif status == "NOTE" and worst != "FAIL":
                worst = "NOTE"
        if worst == "PASS" and not verbose:
            continue
        print("  %-8s %-14s in_bom=%-3s  %s"
             % (r["ref"], r["kind"], r["in_bom"], worst))
        for status, rule, detail in r["findings"]:
            if status == "PASS" and not verbose:
                continue
            print("      %-4s %-32s %s" % (status, rule, detail))
            if status == "FAIL":
                fails += 1
            elif status == "NOTE":
                notes += 1
    total = len(results)
    sourced = sum(1 for r in results if r["kind"] == "sourced")
    off = [r["ref"] for r in results if r["kind"] == OFF_BOARD]
    inherent = total - sourced - len(off)
    dnp = sum(1 for r in results if r["dnp"] == "yes")
    print("  %d symbol(s): %d sourced, %d off-board%s, %d board-inherent, "
          "%d dnp" % (total, sourced, len(off),
                      " (%s)" % ", ".join(off) if off else "", inherent, dnp))
    if fails:
        print("  FAILED (%d finding(s) across %d symbol(s))"
             % (fails, sum(1 for r in results
                          if any(s == "FAIL" for s, _, _ in r["findings"]))))
    else:
        print("  ok      every symbol audited clean%s"
             % (" (%d note(s))" % notes if notes else ""))
    return fails


# ------------------------------------------------------------------- export

def export_bom(sch_path, out_csv, assembly=None, cli=None):
    """Run kicad-cli's own BOM exporter, then check the CSV it wrote.

    Returns (row_count, failures). A board-inherent symbol correctly marked
    `in_bom no` is dropped by kicad-cli itself and never appears in
    `out_csv`, so nothing here needs to re-derive board-inherent status.
    """
    if cli is None:
        cli, how = find_cli()
        if not cli:
            raise SystemExit("error: kicad-cli not found (%s)\n"
                             "  fix: install KiCad 10, or set "
                             "KICAD_ROOT=/Applications/KiCad/KiCad.app/"
                             "Contents\n"
                             "  check: python3 scripts/preflight.py" % how)

    argv = [cli, "sch", "export", "bom", "-o", out_csv,
            "--fields", ",".join(FULL_FIELDS),
            "--labels", ",".join(FULL_LABELS),
            "--group-by", "Value,Footprint,MPN",
            "--sort-field", "Reference",
            "--exclude-dnp",
            sch_path]
    proc = run(argv)
    if proc.returncode != 0:
        lines = [l for l in ((proc.stderr or "") + "\n"
                             + (proc.stdout or "")).splitlines()
                if l.strip()]
        raise SystemExit("error: bom export failed (kicad-cli exit %d)\n  %s"
                         % (proc.returncode,
                            lines[0] if lines else "no output"))

    fails = []
    with open(out_csv, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        refs = row.get("Refs", "?")
        value = row.get("Value", "")
        for rule, detail in sourced_field_problems(
                {k: row.get(k, "") for k in REQUIRED_LABELS + ("LCSC",)},
                value, assembly):
            fails.append("%s (%s): %s [%s]" % (refs, value, detail, rule))
    return len(rows), fails


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_audit = sub.add_parser("audit", help="check a schematic's BOM fields "
                                            "before export")
    ap_audit.add_argument("schematic")
    ap_audit.add_argument("--board", help="cross-check footprint attr "
                                          "tokens against this board")
    ap_audit.add_argument("--design", help="design.py to read "
                                           "BOARD_INHERENT from")
    ap_audit.add_argument("--assembly", choices=["jlcpcb", "none"],
                          default="none", help="require an LCSC part "
                          "number on every sourced part when jlcpcb "
                          "(default: none)")
    ap_audit.add_argument("--min-desc-words", type=int,
                          default=MIN_DESC_WORDS)
    ap_audit.add_argument("--json", action="store_true")
    ap_audit.add_argument("-v", "--verbose", action="store_true",
                          help="print every symbol, not only failures")

    ap_export = sub.add_parser("export", help="export the real BOM and "
                                              "fail on incomplete rows")
    ap_export.add_argument("schematic")
    ap_export.add_argument("-o", "--out", required=True)
    ap_export.add_argument("--assembly", choices=["jlcpcb", "none"],
                           default="none")

    args = ap.parse_args()

    if args.cmd == "audit":
        assembly = None if args.assembly == "none" else args.assembly
        results = audit(args.schematic, args.board, args.design, assembly,
                        args.min_desc_words)
        if args.json:
            print(json.dumps(results, indent=2))
            fails = sum(1 for r in results
                       for s, _, _ in r["findings"] if s == "FAIL")
        else:
            fails = print_audit(args.schematic, results, args.verbose)
        sys.exit(1 if fails else 0)

    if args.cmd == "export":
        assembly = None if args.assembly == "none" else args.assembly
        print("--- kicad_bom export: %s -> %s ---"
             % (args.schematic, args.out))
        count, fails = export_bom(args.schematic, args.out, assembly)
        print("  %d row(s) written" % count)
        if fails:
            print("  FAILED (%d incomplete row(s)):" % len(fails))
            for line in fails:
                print("    %s" % line)
            sys.exit(1)
        print("  ok      every row carries its required fields")


if __name__ == "__main__":
    main()
