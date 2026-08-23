#!/usr/bin/env python3
"""Read geometry out of a .kicad_pcb without KiCad: outline, holes, placements.

A dependency-free s-expression parser.  The point is to let the *enclosure*
phase derive its numbers from the as-built board file rather than from a spec
table that can drift: hole positions, the outline rectangle and every
footprint's position/rotation/side come from the file DRC already gated.
Runs under any python3, including the one your CAD library lives in, so a
case script can `import kicad_geom` instead of transcribing coordinates.

    python3 scripts/kicad_geom.py board.kicad_pcb
    python3 scripts/kicad_geom.py board.kicad_pcb --json | jq .outline

Coordinates are raw KiCad board coordinates: millimetres, x east, **y south**.
Enclosure code almost always wants y negated to get a right-handed frame; do
that conversion at the boundary, once, and keep every table in board coords.

Two traps this file exists to encapsulate:

  * Footprint rotation is stored counterclockwise-as-seen-on-screen, and file
    coordinates are y-south, so in file coordinates the rotation is
    **clockwise** for a positive angle.  A sign error here is invisible on 0
    and 180 degree parts and silently wrong on every 90/270 part.
  * A pad's `(at ...)` is footprint-local and must be rotated by the parent
    footprint's angle before it means anything.  Absolute hole positions are
    what the case needs; the local ones are a trap for the unwary.
"""

import argparse
import json
import math
import sys

# Board-level graphic items that can carry the outline.
GRAPHIC_ITEMS = ("gr_rect", "gr_line", "gr_arc", "gr_circle", "gr_poly")
FP_GRAPHIC_ITEMS = ("fp_rect", "fp_line", "fp_arc", "fp_circle", "fp_poly")
OUTLINE_LAYER = "Edge.Cuts"


# --------------------------------------------------------------- s-expressions

def tokenize(text):
    """Yield '(' , ')' and atoms.  Quoted atoms keep their escapes resolved."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "()":
            yield ch
            i += 1
        elif ch in " \t\r\n":
            i += 1
        elif ch == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            i += 1                                  # closing quote
            yield "".join(buf)
        else:
            start = i
            while i < n and text[i] not in ' \t\r\n()"':
                i += 1
            yield text[start:i]


def parse(text):
    """Parse one s-expression document into nested lists of strings."""
    stack, root = [], None
    for tok in tokenize(text):
        if tok == "(":
            node = []
            if stack:
                stack[-1].append(node)
            stack.append(node)
        elif tok == ")":
            node = stack.pop()
            if not stack:
                root = node
        elif stack:
            stack[-1].append(tok)
    if root is None:
        raise ValueError("no complete s-expression found")
    return root


def parse_file(path):
    with open(path) as fh:
        return parse(fh.read())


def kids(node, name):
    """Direct child lists whose head atom is `name`."""
    return [c for c in node
            if isinstance(c, list) and c and c[0] == name]


def kid(node, name):
    got = kids(node, name)
    return got[0] if got else None


def atoms(node):
    """The plain-string members of a node, head included."""
    return [c for c in node if isinstance(c, str)]


def nums(node, count=None):
    """Trailing numeric atoms of a node, e.g. (at 1.5 2 90) -> [1.5, 2.0, 90.0]."""
    out = []
    for a in atoms(node)[1:]:
        try:
            out.append(float(a))
        except ValueError:
            break
    return out if count is None else out[:count]


def layer_of(node):
    lay = kid(node, "layer")
    return atoms(lay)[1] if lay and len(atoms(lay)) > 1 else None


def layers_of(node):
    lay = kid(node, "layers")
    return atoms(lay)[1:] if lay else []


# ------------------------------------------------------------------- geometry

def rotate(px, py, degrees):
    """Rotate a footprint-local point by a footprint angle, in file coords.

    KiCad's stored angle is counterclockwise on screen; file y runs south, so
    the matrix that reproduces it in file coordinates is the clockwise one.
    This is verified against pcbnew's own pad positions, not assumed.
    """
    if not degrees:
        return px, py
    rad = math.radians(degrees)
    cos, sin = math.cos(rad), math.sin(rad)
    return px * cos + py * sin, -px * sin + py * cos


def _bbox_points(node, head):
    """Every point that constrains the bbox of one graphic item."""
    pts = []
    if head in ("gr_rect", "fp_rect", "gr_line", "fp_line"):
        for tag in ("start", "end"):
            got = kid(node, tag)
            if got:
                pts.append(tuple(nums(got, 2)))
    elif head in ("gr_arc", "fp_arc"):
        # start/mid/end bound the arc's chord and its bulge point; a true arc
        # bbox can exceed this, so an arc-heavy outline is bounded, not exact.
        for tag in ("start", "mid", "end"):
            got = kid(node, tag)
            if got:
                pts.append(tuple(nums(got, 2)))
    elif head in ("gr_circle", "fp_circle"):
        centre, end = kid(node, "center"), kid(node, "end")
        if centre and end:
            cx, cy = nums(centre, 2)
            ex, ey = nums(end, 2)
            r = math.hypot(ex - cx, ey - cy)
            pts += [(cx - r, cy - r), (cx + r, cy + r)]
    elif head in ("gr_poly", "fp_poly"):
        poly = kid(node, "pts")
        if poly:
            pts += [tuple(nums(p, 2)) for p in kids(poly, "xy")]
    return [p for p in pts if len(p) == 2]


def _outline_item(node, head, owner, origin, angle):
    """One Edge.Cuts graphic, in board coordinates."""
    ox, oy = origin
    pts = []
    for px, py in _bbox_points(node, head):
        rx, ry = rotate(px, py, angle) if owner else (px, py)
        pts.append((round(rx + ox, 4), round(ry + oy, 4)))
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"kind": head, "owner": owner, "points": pts,
            "bbox": [min(xs), min(ys), max(xs), max(ys)]}


def _pad_hole(node, ref, origin, angle):
    """A drilled pad as an absolute hole record, or None if it has no drill."""
    drill = kid(node, "drill")
    if drill is None:
        return None
    pad_type = atoms(node)[2] if len(atoms(node)) > 2 else ""
    if pad_type not in ("thru_hole", "np_thru_hole"):
        return None
    at = kid(node, "at")
    lx, ly = (nums(at, 2) + [0.0, 0.0])[:2] if at else (0.0, 0.0)
    rx, ry = rotate(lx, ly, angle)

    # (drill 2.2) is round; (drill oval 3.0 1.4) is a slot.  Fabs tool slots
    # by their minor axis, which is what a hole-diameter assertion must use.
    dnums = nums(drill)
    oval = "oval" in atoms(drill)
    diameter = min(dnums) if (oval and dnums) else (dnums[0] if dnums else 0.0)
    return {"x": round(rx + origin[0], 4), "y": round(ry + origin[1], 4),
            "diameter": round(diameter, 4),
            "shape": "oval" if oval else "round",
            "drill": [round(d, 4) for d in dnums],
            "plated": pad_type == "thru_hole",
            "owner": ref, "pad": atoms(node)[1] if len(atoms(node)) > 1 else ""}


def _footprint(node):
    """{ref, value, lib, x, y, rotation, side}, plus its holes and outline bits."""
    lib = atoms(node)[1] if len(atoms(node)) > 1 else ""
    at = kid(node, "at")
    coords = nums(at) if at else []
    x = coords[0] if coords else 0.0
    y = coords[1] if len(coords) > 1 else 0.0
    rot = coords[2] if len(coords) > 2 else 0.0
    layer = layer_of(node) or "F.Cu"
    side = "bottom" if layer.startswith("B.") else "top"

    ref = value = ""
    for prop in kids(node, "property"):
        names = atoms(prop)
        if len(names) >= 3 and names[1] == "Reference":
            ref = names[2]
        elif len(names) >= 3 and names[1] == "Value":
            value = names[2]

    fp = {"ref": ref, "value": value, "lib": lib, "x": round(x, 4),
          "y": round(y, 4), "rotation": rot, "side": side, "layer": layer}

    holes = []
    for pad in kids(node, "pad"):
        hole = _pad_hole(pad, ref or lib, (x, y), rot)
        if hole:
            holes.append(hole)

    outline = []
    for head in FP_GRAPHIC_ITEMS:
        for item in kids(node, head):
            if layer_of(item) == OUTLINE_LAYER:
                got = _outline_item(item, head, ref or lib, (x, y), rot)
                if got:
                    outline.append(got)
    return fp, holes, outline


def read_board(path):
    """Parse a board into a plain-dict geometry summary."""
    root = parse_file(path)
    if not root or root[0] != "kicad_pcb":
        raise SystemExit("error: %s is not a .kicad_pcb (root is %r)\n"
                         "  fix: pass the board file, not the project or "
                         "schematic" % (path, root[0] if root else None))

    footprints, holes, outline = [], [], []
    for head in GRAPHIC_ITEMS:
        for item in kids(root, head):
            if layer_of(item) == OUTLINE_LAYER:
                got = _outline_item(item, head, None, (0.0, 0.0), 0.0)
                if got:
                    outline.append(got)
    for fp_node in kids(root, "footprint"):
        fp, fp_holes, fp_outline = _footprint(fp_node)
        footprints.append(fp)
        holes += fp_holes
        outline += fp_outline

    # Vias are drilled and plated, so a fab's PTH tool list includes them.
    for via in kids(root, "via"):
        at, drill = kid(via, "at"), kid(via, "drill")
        if not (at and drill):
            continue
        vx, vy = nums(at, 2)
        holes.append({"x": round(vx, 4), "y": round(vy, 4),
                      "diameter": round(nums(drill)[0], 4), "shape": "round",
                      "drill": [round(nums(drill)[0], 4)], "plated": True,
                      "owner": "via", "pad": ""})

    board_rects = [o for o in outline
                   if o["kind"] == "gr_rect" and o["owner"] is None]
    return {"source": path,
            "units": "mm",
            "coordinate_frame": "KiCad board coords: x east, y south",
            "outline": _outline_summary(outline, board_rects),
            "holes": sorted(holes, key=lambda h: (h["diameter"], h["y"], h["x"])),
            "footprints": sorted(footprints,
                                 key=lambda f: (f["ref"] or f["lib"]))}


def _outline_summary(outline, board_rects):
    # bbox from board-level Edge.Cuts only: footprint-level Edge.Cuts items are
    # interior milled windows and must not be allowed to define the perimeter.
    board_level = [o for o in outline if o["owner"] is None]
    if board_level:
        xs = [v for o in board_level for v in (o["bbox"][0], o["bbox"][2])]
        ys = [v for o in board_level for v in (o["bbox"][1], o["bbox"][3])]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    else:
        bbox = None
    return {"bbox": bbox,
            "width": round(bbox[2] - bbox[0], 4) if bbox else None,
            "height": round(bbox[3] - bbox[1], 4) if bbox else None,
            "rects": [{"bbox": r["bbox"],
                       "width": round(r["bbox"][2] - r["bbox"][0], 4),
                       "height": round(r["bbox"][3] - r["bbox"][1], 4)}
                      for r in board_rects],
            "interior_cutouts": len([o for o in outline
                                     if o["owner"] is not None]),
            "items": len(outline)}


# ---------------------------------------------------------------------- report

def fmt(value, width=0):
    """Number with up to 4 decimals, trailing zeros stripped.

    Deliberately not %g: %g would print 47.625 as 47.62 at 4 significant
    figures, and a hole coordinate that reads 47.62 when the board says 47.625
    is exactly the kind of quiet rounding the enclosure phase must never
    inherit from this tool.
    """
    text = ("%.4f" % value).rstrip("0").rstrip(".")
    return text.rjust(width) if width else (text or "0")


def group_holes(holes, plated):
    """{diameter: [hole, ...]} for one plating class."""
    out = {}
    for h in holes:
        if h["plated"] is plated:
            out.setdefault(h["diameter"], []).append(h)
    return out


def print_table(board, max_rows=0):
    out = board["outline"]
    print("board   %s" % board["source"])
    if out["bbox"]:
        print("outline %s x %s mm   bbox %s   (%d Edge.Cuts items, "
              "%d interior cutouts)"
              % (fmt(out["width"]), fmt(out["height"]),
                 " ".join(fmt(v) for v in out["bbox"]),
                 out["items"], out["interior_cutouts"]))
    else:
        print("outline NONE - no board-level Edge.Cuts geometry")
    for rect in out["rects"]:
        print("  rect  %s x %s at %s,%s"
              % (fmt(rect["width"]), fmt(rect["height"]),
                 fmt(rect["bbox"][0]), fmt(rect["bbox"][1])))

    for plated, label in ((False, "NPTH"), (True, "PTH")):
        groups = group_holes(board["holes"], plated)
        total = sum(len(v) for v in groups.values())
        print("\n%s holes: %d in %d tool size(s)" % (label, total, len(groups)))
        for dia in sorted(groups):
            hs = groups[dia]
            shapes = sorted({h["shape"] for h in hs})
            owners = sorted({h["owner"] for h in hs})
            owner = owners[0] if len(owners) == 1 else "%d owners" % len(owners)
            print("  %smm  x%-4d %-6s %s" % (fmt(dia, 6), len(hs),
                                              "/".join(shapes), owner))
            if len(hs) <= 8:
                for h in sorted(hs, key=lambda h: (h["y"], h["x"])):
                    print("            %s %s  %s"
                          % (fmt(h["x"], 9), fmt(h["y"], 9), h["owner"]))

    fps = board["footprints"]
    print("\nfootprints: %d  (%d top, %d bottom)"
          % (len(fps), sum(f["side"] == "top" for f in fps),
             sum(f["side"] == "bottom" for f in fps)))
    rows = fps if not max_rows else fps[:max_rows]
    print("  %-10s %-22s %9s %9s %6s %s"
          % ("REF", "VALUE", "X", "Y", "ROT", "SIDE"))
    for f in rows:
        print("  %-10s %-22s %s %s %6g %s"
              % (f["ref"] or "-", (f["value"] or "-")[:22],
                 fmt(f["x"], 9), fmt(f["y"], 9), f["rotation"], f["side"]))
    if max_rows and len(fps) > max_rows:
        print("  ... %d more (use --json for all)" % (len(fps) - max_rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("board", help="a .kicad_pcb file")
    ap.add_argument("--json", action="store_true",
                    help="emit the full geometry as JSON")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="truncate the footprint table (0 = all)")
    args = ap.parse_args()

    board = read_board(args.board)
    if args.json:
        json.dump(board, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_table(board, args.max_rows)


if __name__ == "__main__":
    main()
