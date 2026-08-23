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
    python3 scripts/kicad_geom.py --diff old.kicad_pcb new.kicad_pcb
    python3 scripts/kicad_geom.py --diff old.kicad_pcb new.kicad_pcb \
                                  --as-constants

Coordinates are raw KiCad board coordinates: millimetres, x east, **y south**.
Enclosure code almost always wants y negated to get a right-handed frame; do
that conversion at the boundary, once, and keep every table in board coords.

Three traps this file exists to encapsulate:

  * Footprint rotation is stored counterclockwise-as-seen-on-screen, and file
    coordinates are y-south, so in file coordinates the rotation is
    **clockwise** for a positive angle.  A sign error here is invisible on 0
    and 180 degree parts and silently wrong on every 90/270 part.
  * A pad's `(at ...)` is footprint-local and must be rotated by the parent
    footprint's angle before it means anything.  Absolute hole positions are
    what the case needs; the local ones are a trap for the unwary.
  * **A footprint's `side` says where it is PLACED, not where its hardware
    is.**  `side` is read from the footprint's `layer`, and a hotswap keyboard
    socket is a *front*-face footprint whose pads are declared on B.Cu and
    whose 1.85 mm of socket body plus 2.20 mm of switch pin live entirely
    UNDER the board.  Filtering `side == "bottom"` to build an underside
    clearance ledger therefore misses every switch cell on the board — and
    every clearance check passes, because the ledger never contained them.
    (Measured on a 6-key board: the underside free band read 14.96 mm that
    way; including the sockets the real figure is 5.52 mm.)  So each footprint
    also carries:

        pad_side    "top" / "bottom" / "both" — where its COPPER is
        through_hole  whether any pad is drilled
        protrudes   the faces whose obstacle ledger must contain this part:
                    its own side, plus the opposite face when the pads are
                    there, plus the opposite face for through-hole parts whose
                    clipped solder tails stand proud on the far side.

    Build an underside ledger from `protrudes`, never from `side`.

JSON KEYS PER FOOTPRINT — these are the names `--json` emits, and the printed
table's column headings match them so a consumer never has to guess
(`ROTATION`, not `ROT`):

    ref value lib layer      identity, as the file has it
    designator               the ref PARSED: {"prefix": "DISP", "index": 1}
    x y rotation             placement: board coords, degrees
    side                     the footprint's own layer — PLACEMENT ONLY
    pad_side through_hole
    protrudes                where the HARDWARE is (see the trap above)
    courtyard                F.CrtYd/B.CrtYd bbox, board coords
    pads_bbox                union of every copper pad, board coords
    body_bbox                F.Fab/B.Fab bbox — the part BODY, board coords
    fab_items                each Fab graphic separately: kind, layer, bbox
    obstacle_above           what really stands ABOVE the board: {bbox, basis,
    obstacle_below           courtyard_dropped} — or null where nothing does

`designator` exists because **reference designators are not a prefix-free
code** and `ref.startswith("D")` is a trap: `D`/`DISP`, `R`/`RN`, `C`/`CN`,
`J`/`JP`.  A height ledger that dispatched on `startswith("D")` gave a nice!view
(`DISP1`) an SOD-123 diode's height and reported 8 diodes on a 7-diode board.
Switch on `designator["prefix"] == "D"`, never on the string.

`obstacle_above` / `obstacle_below` answer the question a deck window or a
battery bay actually asks — *what is in the way on this face* — instead of
leaving each project to pick between `courtyard`, `body_bbox` and their union.
The three cases (`references/mechanical.md` §4) and the `basis` each reports:

    courtyard∪body   the default: a part whose hardware can exceed its own
                     courtyard (a socketed module's courtyard is drawn round
                     its pad grid and comes out SMALLER than the part).
    body             a THROUGH-HOLE part whose courtyard is inflated by its own
                     pad row — flat copper and silk, nothing a deck can hit.
                     `courtyard_dropped` says how much was excluded, so the
                     choice is visible rather than implied.  (Measured: ENC1's
                     courtyard runs 3.0 mm further north than anything that
                     stands above the board; sizing a deck window on the union
                     left a mounting boss 0.020 mm of seat.)
    courtyard        no Fab body to union with — the courtyard is all the file
                     knows, and the part's body then has to come from its
                     datasheet or KB card and be asserted.

`courtyard`, `pads_bbox` and `body_bbox` are rotation-resolved, and `None` when
the footprint carries no such geometry.

An enclosure's obstacle ledger is made of courtyards — but the courtyard is
*not* automatically the larger box.  A socketed module's courtyard is routinely
drawn around its pad grid and comes out SMALLER than the part body, so an
obstacle rect is `courtyard ∪ body_bbox` (see references/mechanical.md §4).
That is why `body_bbox` is exported rather than left to a handoff table in
prose: the Fab outline *is* the part's own body, it is right there in the file,
and a number that has to be retyped is a number that drifts.

`fab_items` is the same argument one step down.  A protruding actuator — a
slide-switch knob, a button plunger, a connector shell — is usually its own
group of Fab lines, and the case has to slot exactly that.  Every item is
reported separately, in board coordinates with the rotation already applied, so
the caller unions the ones it means instead of writing a bespoke pcbnew script.

THE ADOPTION DIFF (`--diff OLD NEW`).  A generated board's docstring says never
to hand-edit the `.kicad_pcb`, and that is right — but dragging four footprints
in pcbnew is the *normal* way a person says "put the encoder over here", so the
round trip needs a defined re-entry path rather than a prohibition.  `--diff`
is the machine-readable half of it: per-ref Δx / Δy / Δrot / **Δside**, refs
added and removed, and changes to the `protrudes` SETS.

Both halves of that matter, and the second is the one nothing else catches:

  * **A hand placement is an `(x, y, rot, layer)` tuple and all four are the
    spec.** A rotation adopted at 180° instead of 0° reverses which pad of a
    two-terminal part faces the net leaving it, which is a routing topology
    change (measured cost: two vias).  A part that came back on the other
    *face* is a bigger change than any position move.
  * **A keepout derived from a component bound is invalidated by that
    component LEAVING**, not only by it moving.  Two parts moving to the front
    face took the protrude-below set from 37 refs to 35 — and they were the two
    that bounded a battery bay, whose plan area then grew ~68 % with every
    remaining ref still perfectly in the ledger.  A stale ledger that is merely
    *conservative* is the failure mode nobody looks for.

`--as-constants` prints the moved set as a python dict ready to paste into an
emitter, because transcribing eight coordinates by hand out of a JSON dump is a
transcription risk with no checker behind it: a board generated from the wrong
adopted coordinate is perfectly clean.  Adopt, regenerate, then run `--diff
--strict` between the backup and the regenerated board and require **no**
differences — that last step is what makes the whole round trip safe.
"""

import argparse
import json
import math
import re
import sys

# Board-level graphic items that can carry the outline.
GRAPHIC_ITEMS = ("gr_rect", "gr_line", "gr_arc", "gr_circle", "gr_poly")
FP_GRAPHIC_ITEMS = ("fp_rect", "fp_line", "fp_arc", "fp_circle", "fp_poly")
OUTLINE_LAYER = "Edge.Cuts"
COURTYARD_LAYERS = ("F.CrtYd", "B.CrtYd")
# The Fab layers carry the part's own BODY outline (and often its actuator),
# which is the rect the courtyard is not.
FAB_LAYERS = ("F.Fab", "B.Fab")


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


def _union(boxes):
    """Bounding box of a list of [x0,y0,x1,y1], or None."""
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [round(min(b[0] for b in boxes), 4),
            round(min(b[1] for b in boxes), 4),
            round(max(b[2] for b in boxes), 4),
            round(max(b[3] for b in boxes), 4)]


def _graphic_bbox(node, head, origin, angle):
    """Bbox of one footprint graphic, in board coordinates."""
    pts = [rotate(px, py, angle) for px, py in _bbox_points(node, head)]
    if not pts:
        return None
    return [min(p[0] for p in pts) + origin[0],
            min(p[1] for p in pts) + origin[1],
            max(p[0] for p in pts) + origin[0],
            max(p[1] for p in pts) + origin[1]]


def _pad_bbox(node, origin, angle):
    """Bbox of one pad's copper, in board coordinates.

    The pad's own `(at x y rot)` rotation composes with the footprint's, so the
    corners are built in the pad's frame first and only then rotated by the
    parent angle.  A circle/oval is bounded by its size box, which is what a
    clearance ledger wants anyway.
    """
    at, size = kid(node, "at"), kid(node, "size")
    if at is None or size is None:
        return None
    coords = nums(at)
    lx = coords[0] if coords else 0.0
    ly = coords[1] if len(coords) > 1 else 0.0
    pad_rot = coords[2] if len(coords) > 2 else 0.0
    dims = nums(size, 2)
    if len(dims) < 2:
        return None
    hw, hh = dims[0] / 2.0, dims[1] / 2.0
    pts = []
    for cx, cy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
        rx, ry = rotate(cx, cy, pad_rot)
        rx, ry = rotate(rx + lx, ry + ly, angle)
        pts.append((rx + origin[0], ry + origin[1]))
    return [min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts)]


# A reference designator is PREFIX + digits, and the prefixes are not a
# prefix-free code (`D`/`DISP`, `R`/`RN`, `C`/`CN`, `J`/`JP`), so the split has
# to be parsed rather than guessed with startswith().
_DESIGNATOR = re.compile(r"^([A-Za-z_]+?)(\d+)$")


def designator(ref):
    """{'prefix': 'DISP', 'index': 1} — or index None for an unparseable ref.

    A digitless ref is itself a defect (it poisons kicad-cli's annotation
    check, see references/kicad-api.md §4), so it is reported with the whole
    string as the prefix and a null index rather than silently split.
    """
    match = _DESIGNATOR.match(ref or "")
    if not match:
        return {"prefix": ref or "", "index": None}
    return {"prefix": match.group(1), "index": int(match.group(2))}


# How much wider than the part body a courtyard may be drawn around a pad row
# before the excess stops being explainable as pad-plus-clearance.  Courtyards
# are conventionally the pad extent plus 0.25…0.5 mm.
PAD_COURTYARD_SLOP = 0.75


def _obstacle_rect(courtyard, body, pads_bbox, through_hole):
    """({bbox, basis, courtyard_dropped}) — what physically stands on a face.

    See the module docstring for the three cases.  `courtyard_dropped` is the
    furthest the courtyard reaches past the chosen bbox, so a consumer can see
    exactly how much was excluded and on what grounds.
    """
    if not body:
        if not courtyard:
            return None if not pads_bbox else {
                "bbox": list(pads_bbox), "basis": "pads",
                "courtyard_dropped": 0.0}
        return {"bbox": list(courtyard), "basis": "courtyard",
                "courtyard_dropped": 0.0}
    if not courtyard:
        return {"bbox": list(body), "basis": "body", "courtyard_dropped": 0.0}

    def excess(outer, inner):
        """How far `outer` reaches past `inner`, per side, clamped at 0."""
        return [max(inner[0] - outer[0], 0.0), max(inner[1] - outer[1], 0.0),
                max(outer[2] - inner[2], 0.0), max(outer[3] - inner[3], 0.0)]

    over_body = excess(courtyard, body)
    dropped = round(max(over_body), 4)
    # The pad-row-inflated case: a through-hole part whose courtyard exceeds its
    # body only where its own PADS also do.  Then the excess is flat copper and
    # silk — nothing that stands above the board.  Both conditions are needed:
    # the excess must be real, and the pads must account for it.  A courtyard
    # that is merely a uniform margin round the body keeps the conservative
    # union.
    if through_hole and pads_bbox and dropped > 0.01:
        pads_over_body = excess(pads_bbox, body)
        if max(pads_over_body) > 0.01 and all(
                c <= p + PAD_COURTYARD_SLOP
                for c, p in zip(over_body, pads_over_body)):
            return {"bbox": list(body), "basis": "body",
                    "courtyard_dropped": dropped}
    return {"bbox": _union([courtyard, body]), "basis": "courtyard∪body",
            "courtyard_dropped": 0.0}


def _pad_faces(pad_layer_names):
    """'top' / 'bottom' / 'both' / None from a set of pad layer names."""
    faces = set()
    for name in pad_layer_names:
        if name.startswith("*."):                    # *.Cu = every copper face
            return "both"
        if name.endswith(".Cu"):
            faces.add("bottom" if name.startswith("B.") else "top")
    if not faces:
        return None
    return faces.pop() if len(faces) == 1 else "both"


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
          "y": round(y, 4), "rotation": rot, "side": side, "layer": layer,
          "designator": designator(ref)}

    holes = []
    pad_boxes, pad_layer_names, through = [], set(), False
    for pad in kids(node, "pad"):
        hole = _pad_hole(pad, ref or lib, (x, y), rot)
        if hole:
            holes.append(hole)
        pad_type = atoms(pad)[2] if len(atoms(pad)) > 2 else ""
        if pad_type == "thru_hole":
            through = True
        if pad_type != "np_thru_hole":               # NPTH carries no copper
            pad_layer_names.update(layers_of(pad))
            box = _pad_bbox(pad, (x, y), rot)
            if box:
                pad_boxes.append(box)

    courtyard = _union([_graphic_bbox(item, head, (x, y), rot)
                        for head in FP_GRAPHIC_ITEMS
                        for item in kids(node, head)
                        if layer_of(item) in COURTYARD_LAYERS])

    # Fab geometry, item by item: the body outline, and any actuator drawn on
    # the same layer.  Kept separate (rather than only unioned) because the
    # thing a case slots is usually one group of these, not all of them.
    fab_items = []
    for head in FP_GRAPHIC_ITEMS:
        for item in kids(node, head):
            if layer_of(item) not in FAB_LAYERS:
                continue
            box = _graphic_bbox(item, head, (x, y), rot)
            if box:
                fab_items.append({"kind": head, "layer": layer_of(item),
                                  "bbox": [round(v, 4) for v in box]})
    body = _union([f["bbox"] for f in fab_items])

    # `protrudes` is the hardware fact; `side` is only the placement fact.
    pad_side = _pad_faces(pad_layer_names)
    other = "bottom" if side == "top" else "top"
    faces = {side}
    if pad_side in ("top", "bottom") and pad_side != side:
        faces.add(pad_side)
    if pad_side == "both" or through:
        faces.add(other)                             # tails stand proud
    # One obstacle rect per face the hardware actually reaches, so the
    # enclosure phase reads a decision instead of making one.  `protrudes` is
    # what decides which faces get one; the rect is the same on both, because
    # the file knows the part's plan extent and not its per-face silhouette.
    pads_box = _union(pad_boxes)
    rect = _obstacle_rect(courtyard, body, pads_box, through)
    fp.update({"courtyard": courtyard,
               "body_bbox": body,
               "fab_items": fab_items,
               "pads_bbox": pads_box,
               "pad_layers": sorted(pad_layer_names),
               "pad_side": pad_side,
               "through_hole": through,
               "protrudes": sorted(faces),
               "obstacle_above": rect if "top" in faces else None,
               "obstacle_below": rect if "bottom" in faces else None})

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

    def wh(box):
        return ("%sx%s" % (fmt(box[2] - box[0]), fmt(box[3] - box[1]))
                if box else "-")

    # Column headings are the JSON keys, deliberately: ROTATION, not ROT.
    print("  %-10s %-18s %9s %9s %8s %-6s %-12s %-12s %s"
          % ("REF", "VALUE", "X", "Y", "ROTATION", "SIDE", "COURTYARD",
             "BODY_BBOX", "PROTRUDES"))
    for f in rows:
        print("  %-10s %-18s %s %s %8g %-6s %-12s %-12s %s%s"
              % (f["ref"] or "-", (f["value"] or "-")[:18],
                 fmt(f["x"], 9), fmt(f["y"], 9), f["rotation"], f["side"],
                 wh(f.get("courtyard")), wh(f.get("body_bbox")),
                 ",".join(f.get("protrudes") or []),
                 "  <- pads are %s" % f["pad_side"]
                 if f.get("pad_side") not in (None, f["side"]) else ""))
    if max_rows and len(fps) > max_rows:
        print("  ... %d more (use --json for all)" % (len(fps) - max_rows))

    # The courtyard-smaller-than-the-body trap, called out by name: an obstacle
    # rect for one of these must be courtyard ∪ body_bbox, or a deck window
    # sized on the courtyard reaches over a part that is really there.
    smaller = []
    for f in fps:
        crt, body = f.get("courtyard"), f.get("body_bbox")
        if not crt or not body:
            continue
        over = max(crt[0] - body[0], crt[1] - body[1],
                   body[2] - crt[2], body[3] - crt[3])
        if over > 0.01:
            smaller.append((f["ref"] or f["lib"], over))
    if smaller:
        print("\n%d footprint(s) whose BODY overhangs their own COURTYARD — "
              "obstacle rects\nfor these are `courtyard ∪ body_bbox`, never "
              "the courtyard alone:" % len(smaller))
        for ref, over in sorted(smaller, key=lambda r: -r[1]):
            print("  %-10s body reaches %smm past the courtyard"
                  % (ref, fmt(over)))

    # The other direction, and the one that costs a mounting boss: a courtyard
    # inflated by a through-hole part's own pad row is not an obstacle.
    inflated = [(f["ref"] or f["lib"], f["obstacle_above"]
                 or f["obstacle_below"])
                for f in fps
                if (f.get("obstacle_above") or f.get("obstacle_below") or {})
                .get("basis") == "body"]
    inflated = [(ref, o) for ref, o in inflated
                if o and o["courtyard_dropped"] > 0.01]
    if inflated:
        print("\n%d through-hole footprint(s) whose COURTYARD is inflated by "
              "their own pad row —\n`obstacle_above`/`obstacle_below` are the "
              "BODY for these, and the excess is flat\ncopper a deck cannot "
              "hit:" % len(inflated))
        for ref, o in sorted(inflated, key=lambda r: -r[1]["courtyard_dropped"]):
            print("  %-10s courtyard reaches %smm past the body (dropped)"
                  % (ref, fmt(o["courtyard_dropped"])))

    # The one line that stops an underside ledger being built from `side`.
    liars = [f for f in fps
             if f.get("pad_side") not in (None, "both", f["side"])]
    if liars:
        print("\n%d footprint(s) placed on one face with all copper on the "
              "other — their\nhardware is NOT where `side` says. Build "
              "obstacle ledgers from `protrudes`:" % len(liars))
        for f in liars:
            print("  %-10s placed %-6s pads %-6s  %s"
                  % (f["ref"] or f["lib"], f["side"], f["pad_side"],
                     f["lib"]))
    for key, where, consequence in (
            ("courtyard", "F.CrtYd/B.CrtYd",
             "no courtyard means no DRC courtyard check and no obstacle rect"),
            ("body_bbox", "F.Fab/B.Fab",
             "the part's body must then come from its datasheet or KB card, "
             "and be asserted")):
        missing = [f for f in fps if not f.get(key)]
        if missing:
            print("\n%d footprint(s) with no %s geometry (%s) — %s:"
                  % (len(missing), key, where, consequence))
            print("  %s" % ", ".join(sorted(f["ref"] or f["lib"]
                                            for f in missing)))


# ------------------------------------------------------------------- the diff

# Below this, a placement "change" is the file's own 4-decimal rounding.
MOVE_TOL = 1e-4


def _turn(degrees):
    """A rotation delta as the smallest equivalent turn, in (-180, 180].

    Rotation is modular, so a bare subtraction can report a 270 degree change
    for a 90 degree turn — and the sign of a rotation delta is what tells you
    which way a two-terminal part's pads swapped.
    """
    turn = round(degrees, 4) % 360.0
    return round(turn - 360.0 if turn > 180.0 else turn, 4)


def diff_boards(old, new):
    """Placement differences between two parsed boards.

    Keyed on ref, because that is the only stable identity a footprint has
    across a hand edit and a regeneration (position is what changed, and the
    KIID is minted fresh on every save — see kicad_digest.py).
    """
    was = {f["ref"]: f for f in old["footprints"] if f["ref"]}
    now = {f["ref"]: f for f in new["footprints"] if f["ref"]}
    moved = []
    for ref in sorted(set(was) & set(now)):
        a, b = was[ref], now[ref]
        delta = {"ref": ref,
                 "dx": round(b["x"] - a["x"], 4),
                 "dy": round(b["y"] - a["y"], 4),
                 "drot": _turn(b["rotation"] - a["rotation"]),
                 "side": None if a["side"] == b["side"]
                         else "%s -> %s" % (a["side"], b["side"]),
                 "protrudes": None
                 if a.get("protrudes") == b.get("protrudes")
                 else "%s -> %s" % (",".join(a.get("protrudes") or []),
                                    ",".join(b.get("protrudes") or [])),
                 "x": b["x"], "y": b["y"], "rotation": b["rotation"],
                 "to_side": b["side"]}
        if (abs(delta["dx"]) > MOVE_TOL or abs(delta["dy"]) > MOVE_TOL
                or abs(delta["drot"]) > MOVE_TOL or delta["side"]
                or delta["protrudes"]):
            moved.append(delta)

    def by_face(board):
        out = {}
        for face in ("top", "bottom"):
            out[face] = sorted(f["ref"] for f in board["footprints"]
                               if face in (f.get("protrudes") or []))
        return out

    faces_was, faces_now = by_face(old), by_face(new)
    return {"added": sorted(set(now) - set(was)),
            "removed": sorted(set(was) - set(now)),
            "moved": moved,
            "protrudes": {face: {"was": len(faces_was[face]),
                                 "now": len(faces_now[face]),
                                 "gained": sorted(set(faces_now[face])
                                                  - set(faces_was[face])),
                                 "lost": sorted(set(faces_was[face])
                                                - set(faces_now[face]))}
                          for face in ("top", "bottom")},
            "footprints": {"was": len(was), "now": len(now)}}


def print_diff(old, new, result):
    print("--- placement diff: %s -> %s ---" % (old["source"], new["source"]))
    for ref in result["added"]:
        fp = [f for f in new["footprints"] if f["ref"] == ref][0]
        print("  + added    %-10s %s,%s rot %g %s"
              % (ref, fmt(fp["x"]), fmt(fp["y"]), fp["rotation"], fp["side"]))
    for ref in result["removed"]:
        print("  - removed  %-10s" % ref)
    for d in result["moved"]:
        bits = []
        if abs(d["dx"]) > MOVE_TOL:
            bits.append("dx %+.4f" % d["dx"])
        if abs(d["dy"]) > MOVE_TOL:
            bits.append("dy %+.4f" % d["dy"])
        if abs(d["drot"]) > MOVE_TOL:
            bits.append("drot %+g" % d["drot"])
        if d["side"]:
            bits.append("side %s" % d["side"])
        if d["protrudes"]:
            bits.append("protrudes %s" % d["protrudes"])
        print("  ~ moved    %-10s %s" % (d["ref"], "  ".join(bits)))

    # The set change, not only the per-ref deltas: a keepout derived from a
    # component bound is invalidated by that component LEAVING the face.
    for face in ("top", "bottom"):
        p = result["protrudes"][face]
        if p["was"] == p["now"] and not p["gained"] and not p["lost"]:
            continue
        marks = ["+%s" % r for r in p["gained"]] + \
                ["-%s" % r for r in p["lost"]]
        print("  ! protrudes %-6s %d -> %d refs   %s"
              % (face, p["was"], p["now"], ", ".join(marks)))
        if p["lost"]:
            print("              RE-DERIVE every keepout bounded by %s: a "
                  "ledger that LOST a\n              part is still green and "
                  "now merely conservative — the one failure\n              "
                  "mode nobody looks for." % ", ".join(p["lost"]))
        if p["gained"]:
            print("              %s now stand%s on this face and must be IN "
                  "its ledger."
                  % (", ".join(p["gained"]),
                     "" if len(p["gained"]) > 1 else "s"))

    total = (len(result["added"]) + len(result["removed"])
             + len(result["moved"]))
    if not total:
        print("  no placement differences (%d footprints, to %g mm)"
              % (result["footprints"]["now"], MOVE_TOL))
    else:
        print("  %d difference(s): %d added, %d removed, %d moved  "
              "(%d -> %d footprints)"
              % (total, len(result["added"]), len(result["removed"]),
                 len(result["moved"]), result["footprints"]["was"],
                 result["footprints"]["now"]))
    return total


def print_constants(new, result):
    """The moved set as a pasteable python dict.

    Transcribing coordinates by hand out of a dump is a transcription risk with
    no checker behind it: a board generated from the wrong adopted coordinate is
    perfectly clean.  All four fields are emitted because all four are the spec.
    """
    rows = [(d["ref"], d["x"], d["y"], d["rotation"], d["to_side"])
            for d in result["moved"]]
    for ref in result["added"]:
        fp = [f for f in new["footprints"] if f["ref"] == ref][0]
        rows.append((ref, fp["x"], fp["y"], fp["rotation"], fp["side"]))
    print("\n# adopted from %s — %d footprint(s)" % (new["source"], len(rows)))
    print("# (x, y, rotation, side) in board coords: x east, y SOUTH.")
    print("# Regenerate, then `kicad_geom.py --diff BACKUP REGENERATED "
          "--strict`\n# must report no differences: that is the check that "
          "makes adoption safe.")
    print("ADOPTED = {")
    for ref, x, y, rot, side in sorted(rows):
        # repr(float), not %g: a coordinate that prints as `5` instead of `5.0`
        # is an int literal in the emitter, and integer division is one edit
        # away from silently truncating a placement.
        print('    "%s": (%r, %r, %r, "%s"),'
              % (ref, round(x, 4), round(y, 4), round(float(rot), 4), side))
    print("}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("board", nargs="+", help="a .kicad_pcb file (two with "
                                            "--diff)")
    ap.add_argument("--json", action="store_true",
                    help="emit the full geometry as JSON")
    ap.add_argument("--max-rows", type=int, default=0,
                    help="truncate the footprint table (0 = all)")
    ap.add_argument("--diff", action="store_true",
                    help="compare two boards' placements: per-ref dx/dy/drot/"
                         "dside, refs added or removed, and protrudes-set "
                         "changes")
    ap.add_argument("--as-constants", action="store_true",
                    help="with --diff, also print the moved set as a python "
                         "dict ready to paste into an emitter")
    ap.add_argument("--strict", action="store_true",
                    help="with --diff, exit 1 if the two boards differ — the "
                         "check that verifies a regeneration reproduced the "
                         "placements it adopted")
    args = ap.parse_args()

    if args.diff or args.as_constants:
        if len(args.board) != 2:
            ap.error("--diff takes exactly two board files (OLD NEW)")
        old, new = read_board(args.board[0]), read_board(args.board[1])
        result = diff_boards(old, new)
        if args.json:
            json.dump(result, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            changes = (len(result["added"]) + len(result["removed"])
                       + len(result["moved"]))
        else:
            changes = print_diff(old, new, result)
        if args.as_constants:
            print_constants(new, result)
        if args.strict and changes:
            print("  %d placement difference(s) and --strict is set" % changes,
                  file=sys.stderr)
            sys.exit(1)
        return

    if len(args.board) != 1:
        ap.error("pass one board file, or two with --diff")
    board = read_board(args.board[0])
    if args.json:
        json.dump(board, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_table(board, args.max_rows)


if __name__ == "__main__":
    main()
