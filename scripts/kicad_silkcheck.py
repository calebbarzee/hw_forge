#!/usr/bin/env python3
"""Silkscreen readability checker: floors, overlaps, orientation, labels.

Design rule check (DRC) answers "is this geometrically legal" and has nothing
to say about "can a human read this at assembly time" -- a board with 0
`silk_*` DRC findings can still ship with every reference designator hidden,
every label upside down, or no board name at all (see
`references/silkscreen.md` for the measured case this tool was written
against: z_board combo's first iteration passed DRC clean with 9 of 123
reference designators visible and zero board-level text of any kind).

This is that missing check, run against the `.kicad_pcb` directly -- no
`pcbnew`, so it runs in the same shell as the rest of the gate:

    python3 scripts/kicad_silkcheck.py board.kicad_pcb
    python3 scripts/kicad_silkcheck.py board.kicad_pcb --json
    python3 scripts/kicad_silkcheck.py board.kicad_pcb \\
        --require "RST" --require "LEFT" --require "RIGHT"
    python3 scripts/kicad_silkcheck.py board.kicad_pcb --require-file labels.json

Six checks, each independently configurable (the floors and coefficients
below are this tool's defaults, not a claim about every board's fab or font):

  text_too_small / text_too_thin    visible silk text under the size/stroke
                                     floor (JLCPCB's published minimum, see
                                     kb/fabs/jlcpcb.md: 1.0mm / 0.15mm).
  text_over_pad                     visible silk text bbox overlapping a
                                     pad/hole/via bbox by less than the
                                     required clearance (default 0.25mm).
  text_over_text                    two visible silk texts on the same
                                     physical layer overlapping.
  text_rotation                     visible silk text whose rotation, relative
                                     to the declared reading orientation for
                                     its layer, is not in {0, 90} degrees.
  refdes_far                        a visible reference designator further
                                     than a threshold (default 8mm) from its
                                     own footprint's placement point.
  label_missing                     a required label (from --require /
                                     --require-file) with no matching visible
                                     silk text anywhere on the board.

A text item's real glyph extent is not available without loading a font, so
the overlap/floor checks use an axis-aligned estimate calibrated against
KiCad's own `PCB_TEXT.GetBoundingBox()` at 1.0mm text height (measured, not
guessed -- see kb/keyboards/silkscreen-readability.md): width = (0.5 + chars)
* char-width-mm, height = 1.8 * text-height-mm, both scaled by the text's own
size relative to 1.0mm. `--char-width-mm` / `--char-base-mm` /
`--height-factor` override the calibration for a different font or a
different fab's default text; the defaults are conservative (they slightly
overestimate real KiCad stroke-font glyphs), so a real KiCad render is never
tighter than what this tool checked.

Position and rotation are read the same way `kicad_geom.py` reads them: a
footprint's child items store their position in the footprint's own local
frame (rotated by the footprint's placement, then translated), and reused
from that module rather than re-derived, including its rotation sign
convention (`references/kicad-api.md` has the trap this avoids). A property's
or `fp_text`'s own rotation field is written ABSOLUTE already (verified
against `pcbnew.PCB_TEXT.GetTextAngleDegrees()` on a rotated footprint, not
assumed), so it is read directly, with no addition of the parent's rotation.

Exit status: 0 with no violations, 1 otherwise -- the same contract as
`kicad_gate.py` and `report.py --strict`.
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kicad_geom as kg

SILK_LAYERS = ("F.SilkS", "B.SilkS")


# ------------------------------------------------------------------ parsing

def _read_effects(node):
    """(size_w, size_h, thickness, mirrored) for a property/fp_text/gr_text
    node's `(effects ...)` child, or KiCad's own defaults if absent."""
    size_w = size_h = 1.0
    thickness = 0.0
    mirrored = False
    effects = kg.kid(node, "effects")
    if effects:
        font = kg.kid(effects, "font")
        if font:
            size = kg.kid(font, "size")
            if size:
                dims = kg.nums(size, 2)
                if len(dims) == 2:
                    size_w, size_h = dims
            thick = kg.kid(font, "thickness")
            if thick:
                tn = kg.nums(thick, 1)
                if tn:
                    thickness = tn[0]
        justify = kg.kid(effects, "justify")
        if justify and "mirror" in kg.atoms(justify):
            mirrored = True
    return size_w, size_h, thickness, mirrored


def _read_at(node):
    """(x, y, rot) from a node's `(at ...)` child, 0.0 for any missing field."""
    at = kg.kid(node, "at")
    coords = kg.nums(at) if at else []
    x = coords[0] if coords else 0.0
    y = coords[1] if len(coords) > 1 else 0.0
    rot = coords[2] if len(coords) > 2 else 0.0
    return x, y, rot


def _footprint_texts(node, ref, fx, fy, frot):
    """Every property/fp_text child of one footprint, in board coordinates."""
    out = []
    sources = ([(p, "property:%s" % (kg.atoms(p)[1] if len(kg.atoms(p)) > 1
                                     else "?"), kg.atoms(p)[2]
                if len(kg.atoms(p)) > 2 else "")
               for p in kg.kids(node, "property")]
              + [(t, "fp_text:%s" % (kg.atoms(t)[1] if len(kg.atoms(t)) > 1
                                     else "?"), kg.atoms(t)[2]
                 if len(kg.atoms(t)) > 2 else "")
                for t in kg.kids(node, "fp_text")])
    for item, source, text in sources:
        lx, ly, lrot = _read_at(item)
        rx, ry = kg.rotate(lx, ly, frot)
        w, h, thickness, mirrored = _read_effects(item)
        out.append({
            "ref": ref, "source": source, "text": text,
            "layer": kg.layer_of(item), "x": round(rx + fx, 4),
            "y": round(ry + fy, 4),
            # a property's/fp_text's own rotation field is absolute already
            # (verified against pcbnew.PCB_TEXT.GetTextAngleDegrees(), see
            # this module's docstring) -- no addition of frot here.
            "rot": lrot, "w": w, "h": h, "thickness": thickness,
            "hidden": kg.kid(item, "hide") is not None,
            "mirrored": mirrored,
        })
    return out


def load_board(path):
    """(texts, obstacle_boxes, footprints) for one .kicad_pcb.

    texts: every property/fp_text/gr_text item, board coordinates.
    obstacle_boxes: every pad (copper and NPTH) and via bbox, {ref, num, box}.
    footprints: {ref, x, y, rot} per footprint, for the refdes-distance check.
    """
    root = kg.parse_file(path)
    texts = []
    for gt in kg.kids(root, "gr_text"):
        atoms = kg.atoms(gt)
        text = atoms[1] if len(atoms) > 1 else ""
        x, y, rot = _read_at(gt)
        w, h, thickness, mirrored = _read_effects(gt)
        texts.append({"ref": None, "source": "gr_text", "text": text,
                      "layer": kg.layer_of(gt), "x": x, "y": y, "rot": rot,
                      "w": w, "h": h, "thickness": thickness,
                      "hidden": False, "mirrored": mirrored})

    obstacles = []
    footprints = []
    for node in kg.kids(root, "footprint"):
        fx, fy, frot = _read_at(node)
        ref = ""
        for prop in kg.kids(node, "property"):
            names = kg.atoms(prop)
            if len(names) >= 3 and names[1] == "Reference":
                ref = names[2]
        footprints.append({"ref": ref, "x": fx, "y": fy, "rot": frot})
        texts.extend(_footprint_texts(node, ref, fx, fy, frot))
        for pad in kg.kids(node, "pad"):
            box = kg._pad_bbox(pad, (fx, fy), frot)
            if box:
                num = kg.atoms(pad)[1] if len(kg.atoms(pad)) > 1 else ""
                obstacles.append({"ref": ref, "num": num, "box": box})

    for via in kg.kids(root, "via"):
        vx, vy, _ = _read_at(via)
        size = kg.kid(via, "size")
        dims = kg.nums(size, 1) if size else []
        if not dims:
            continue
        d = dims[0]
        obstacles.append({"ref": "via", "num": "",
                          "box": [vx - d / 2.0, vy - d / 2.0,
                                  vx + d / 2.0, vy + d / 2.0]})
    return texts, obstacles, footprints


# ------------------------------------------------------------------- checks

def _text_bbox(t, args):
    scale = t["h"] / args.text_height_mm if args.text_height_mm else 1.0
    w = (args.char_base_mm + max(1, len(t["text"])) * args.char_width_mm) * scale
    h = args.height_factor * t["h"]
    rot_mod = round(t["rot"]) % 180
    tw, th = (w, h) if rot_mod == 0 else (h, w)
    return (t["x"] - tw / 2.0, t["y"] - th / 2.0,
            t["x"] + tw / 2.0, t["y"] + th / 2.0)


def _overlap(a, b, clearance=0.0):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + clearance < bx0 or bx1 + clearance < ax0
               or ay1 + clearance < by0 or by1 + clearance < ay0)


def _item(desc, x, y):
    return {"description": desc, "pos": {"x": round(x, 4), "y": round(y, 4)}}


def check(texts, obstacles, footprints, args):
    violations = []
    # Every footprint carries Value/Footprint/Datasheet/Description properties
    # on F.Fab (hidden by convention, but not always -- e.g. a stock
    # MountingHole's "${REFERENCE}" text ships visible on F.Fab). Silk
    # readability is a silk-layer question; F.Fab is a different physical
    # layer that never prints on the board at all.
    visible = [t for t in texts
              if not t["hidden"] and t["layer"] in SILK_LAYERS]

    for t in visible:
        if t["h"] < args.text_height_mm - 1e-6:
            violations.append({
                "type": "text_too_small", "severity": "error",
                "description": "silk text under the %.2fmm height floor"
                               % args.text_height_mm,
                "items": [_item("%r (%.3fmm) on %s"
                                % (t["text"], t["h"], t["layer"]),
                                t["x"], t["y"])]})
        if t["thickness"] and t["thickness"] < args.stroke_mm - 1e-6:
            violations.append({
                "type": "text_too_thin", "severity": "error",
                "description": "silk text under the %.2fmm stroke floor"
                               % args.stroke_mm,
                "items": [_item("%r (%.3fmm) on %s"
                                % (t["text"], t["thickness"], t["layer"]),
                                t["x"], t["y"])]})

    for t in visible:
        bbox = _text_bbox(t, args)
        for ob in obstacles:
            if not _overlap(bbox, ob["box"], args.pad_clearance_mm):
                continue
            owner = ("via" if ob["ref"] == "via"
                     else "%s pad %s" % (ob["ref"], ob["num"]))
            violations.append({
                "type": "text_over_pad", "severity": "error",
                "description": "silk text within %.2fmm of a pad/hole/via"
                               % args.pad_clearance_mm,
                "items": [_item("%r on %s" % (t["text"], t["layer"]),
                                t["x"], t["y"]),
                         _item(owner, (ob["box"][0] + ob["box"][2]) / 2.0,
                              (ob["box"][1] + ob["box"][3]) / 2.0)]})

    for i, a in enumerate(visible):
        for b in visible[i + 1:]:
            if a["layer"] != b["layer"]:
                continue
            if _overlap(_text_bbox(a, args), _text_bbox(b, args),
                       args.text_gap_mm):
                violations.append({
                    "type": "text_over_text", "severity": "error",
                    "description": "two silk texts closer than %.2fmm on %s"
                                   % (args.text_gap_mm, a["layer"]),
                    "items": [_item("%r" % a["text"], a["x"], a["y"]),
                             _item("%r" % b["text"], b["x"], b["y"])]})

    reading = {"F.SilkS": args.reading_rotation_f,
              "B.SilkS": args.reading_rotation_b}
    for t in visible:
        base = reading.get(t["layer"], 0.0)
        norm = (t["rot"] - base) % 360.0
        if min(abs(norm - 0.0), abs(norm - 90.0), abs(norm - 360.0)) > 0.05:
            violations.append({
                "type": "text_rotation", "severity": "error",
                "description": "silk text rotation %.1f not in {0, 90} "
                               "relative to the %.1f reading orientation "
                               "for %s" % (t["rot"], base, t["layer"]),
                "items": [_item("%r" % t["text"], t["x"], t["y"])]})

    for fp in footprints:
        ref_text = next((t for t in visible
                         if t["ref"] == fp["ref"]
                         and t["source"] == "property:Reference"), None)
        if ref_text is None:
            continue
        dist = ((ref_text["x"] - fp["x"]) ** 2
               + (ref_text["y"] - fp["y"]) ** 2) ** 0.5
        if dist > args.ref_distance_mm:
            violations.append({
                "type": "refdes_far", "severity": "warning",
                "description": "reference designator further than %.1fmm "
                               "from its footprint" % args.ref_distance_mm,
                "items": [_item("%s (%.2fmm away)" % (fp["ref"], dist),
                                ref_text["x"], ref_text["y"])]})

    required = list(args.require or [])
    if args.require_file:
        try:
            with open(args.require_file) as fh:
                required += json.load(fh)
        except (OSError, ValueError) as exc:
            raise SystemExit("error: cannot read --require-file %s: %s"
                              % (args.require_file, exc))
    haystack = " ".join(t["text"].upper() for t in visible)
    for label in required:
        if label.upper() not in haystack:
            violations.append({
                "type": "label_missing", "severity": "error",
                "description": "required label not found on any visible "
                               "silk text",
                "items": [_item(repr(label), 0.0, 0.0)]})

    return violations


# --------------------------------------------------------------------- main

def _print_human(board, violations, texts):
    visible = sum(1 for t in texts if not t["hidden"])
    print("%s: %d silk text item(s), %d visible" % (board, len(texts), visible))
    if not violations:
        print("  silkcheck   ok")
        return
    from collections import Counter
    counts = Counter(v["type"] for v in violations)
    errs = sum(1 for v in violations if v["severity"] == "error")
    print("  silkcheck   %s  %s" % ("FAIL" if errs else "warn",
                                    ", ".join("%s x%d" % (k, n)
                                              for k, n in counts.most_common())))
    for v in violations:
        print("    %s [%s]  %s" % (v["type"], v["severity"], v["description"]))
        for it in v["items"]:
            print("      - %s  (%.3f, %.3f)"
                  % (it["description"], it["pos"]["x"], it["pos"]["y"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("board", help="a .kicad_pcb file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--text-height-mm", type=float, default=1.0,
                    help="silk text height floor (default: JLCPCB's 1.0mm)")
    ap.add_argument("--stroke-mm", type=float, default=0.15,
                    help="silk stroke width floor (default: JLCPCB's 0.15mm)")
    ap.add_argument("--pad-clearance-mm", type=float, default=0.25,
                    help="minimum silk-text-to-pad/hole/via clearance")
    ap.add_argument("--text-gap-mm", type=float, default=0.20,
                    help="minimum silk-text-to-silk-text clearance")
    ap.add_argument("--reading-rotation-f", type=float, default=0.0,
                    help="legal reading rotation (degrees) for F.SilkS")
    ap.add_argument("--reading-rotation-b", type=float, default=0.0,
                    help="legal reading rotation (degrees) for B.SilkS")
    ap.add_argument("--ref-distance-mm", type=float, default=8.0,
                    help="max distance from a footprint's placement point "
                         "to its own visible reference designator")
    ap.add_argument("--char-width-mm", type=float, default=1.0,
                    help="glyph-width coefficient at --text-height-mm=1.0 "
                         "(calibrated default, see this module's docstring)")
    ap.add_argument("--char-base-mm", type=float, default=0.5,
                    help="fixed per-string width overhead at "
                         "--text-height-mm=1.0")
    ap.add_argument("--height-factor", type=float, default=1.8,
                    help="text bbox height as a multiple of --text-height-mm")
    ap.add_argument("--require", action="append",
                    help="a label that must appear in some visible silk "
                         "text (repeatable)")
    ap.add_argument("--require-file",
                    help="a JSON file holding a list of required labels")
    args = ap.parse_args()

    if not os.path.isfile(args.board):
        kind = "a directory" if os.path.isdir(args.board) else "no such file"
        raise SystemExit("error: %s: %s\n  fix: pass a .kicad_pcb file"
                          % (kind, args.board))

    texts, obstacles, footprints = load_board(args.board)
    violations = check(texts, obstacles, footprints, args)

    if args.json:
        json.dump({"board": args.board, "text_items": len(texts),
                   "visible_text_items": sum(1 for t in texts
                                             if not t["hidden"]),
                   "violations": violations}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_human(args.board, violations, texts)

    errs = [v for v in violations if v["severity"] == "error"]
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
