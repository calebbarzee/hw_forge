#!/usr/bin/env python3
"""Read geometry out of a .kicad_pcb without KiCad: outline, holes, placements.

A dependency-free parser for KiCad's s-expression (symbolic expression) file
format.  The point is to let the enclosure phase derive its numbers from the
as-built board file rather than from a spec table that can drift: hole
positions, the outline rectangle and every footprint's position, rotation and
side come from the file the design rule check (DRC) already gated.

Runs under any python3, including the one your computer-aided design (CAD)
library lives in, so a case script can `import kicad_geom` instead of
transcribing coordinates.

    python3 scripts/kicad_geom.py board.kicad_pcb
    python3 scripts/kicad_geom.py board.kicad_pcb --json | jq .outline
    python3 scripts/kicad_geom.py --diff old.kicad_pcb new.kicad_pcb
    python3 scripts/kicad_geom.py --diff old.kicad_pcb new.kicad_pcb \
                                  --as-constants

Coordinates are raw KiCad board coordinates: millimetres, x east, y south.
Enclosure code almost always wants y negated to get a right-handed frame; do
that conversion at the boundary, once, and keep every table in board coords.

Three traps this file exists to encapsulate:

  * Footprint rotation is stored counterclockwise-as-seen-on-screen, and file
    coordinates are y-south, so in file coordinates the rotation is clockwise
    for a positive angle.  A sign error here is invisible on 0 and 180 degree
    parts and silently wrong on every 90/270 part.
  * A pad's `(at ...)` is footprint-local and must be rotated by the parent
    footprint's angle before it means anything.  Absolute hole positions are
    what the case needs; the local ones are a trap for the unwary.
  * A footprint's `side` says where it is placed, not where its hardware is.
    `side` is read from the footprint's `layer`, and a hotswap keyboard socket
    is a front-face footprint whose pads are declared on B.Cu and whose 1.85 mm
    of socket body plus 2.20 mm of switch pin live entirely under the board.

    Filtering `side == "bottom"` to build an underside clearance ledger
    therefore misses every switch cell on the board, and every clearance check
    passes because the ledger never contained them.  (Measured on a 6-key
    board: the underside free band read 14.96 mm that way; including the
    sockets the real figure is 5.52 mm.)  So each footprint also carries:

        pad_side    "top" / "bottom" / "both": where its copper is
        through_hole  whether any pad is drilled
        protrudes   the faces whose obstacle ledger must contain this part:
                    its own side, plus the opposite face when the pads are
                    there, plus the opposite face for through-hole parts whose
                    clipped solder tails stand proud on the far side.

    Build an underside ledger from `protrudes`, never from `side`.

JSON keys per footprint.  These are the names `--json` emits, and the printed
table's column headings match them so a consumer never has to guess
(`ROTATION`, not `ROT`):

    ref value lib layer      identity, as the file has it
    designator               the parsed ref: {"prefix": "DISP", "index": 1}
    x y rotation             placement: board coords, degrees
    side                     the footprint's own layer, placement only
    pad_side through_hole
    protrudes                where the hardware is (see the trap above)
    courtyard                F.CrtYd/B.CrtYd bbox, board coords
    pads_bbox                union of every copper pad, board coords
    body_bbox                F.Fab/B.Fab bbox: the part body, board coords
    fab_items                each Fab graphic separately: kind, layer, bbox
    obstacle_above           what really stands above the board: {bbox, basis,
    obstacle_below           courtyard_dropped}, or null where nothing does
    models                   each (model ...) link: path, offset, scale, rotate,
                             hidden
    fields                   the FIT_FIELDS footprint properties present

`designator` exists because reference designators are not a prefix-free code,
which makes `ref.startswith("D")` a trap: `D`/`DISP`, `R`/`RN`, `C`/`CN`,
`J`/`JP`.  A height ledger that dispatched on `startswith("D")` gave a nice!view
(`DISP1`) an SOD-123 diode's height and reported 8 diodes on a 7-diode board.
Switch on `designator["prefix"] == "D"`, never on the string.

`obstacle_above` / `obstacle_below` answer the question a deck window or a
battery bay actually asks, which is what is in the way on this face, instead of
leaving each project to pick between `courtyard`, `body_bbox` and their union.
The three cases (`references/mechanical.md` §4) and the `basis` each reports:

    courtyard∪body   the default: a part whose hardware can exceed its own
                     courtyard (a socketed module's courtyard is drawn round
                     its pad grid and comes out smaller than the part).
    body             a through-hole part whose courtyard is inflated by its own
                     pad row of flat copper and silk, nothing a deck can hit.
                     `courtyard_dropped` says how much was excluded, so the
                     choice is visible rather than implied.  (Measured: ENC1's
                     courtyard runs 3.0 mm further north than anything that
                     stands above the board; sizing a deck window on the union
                     left a mounting boss 0.020 mm of seat.)
    courtyard        no Fab body to union with, so the courtyard is all the
                     file knows, and the part's body then has to come from its
                     datasheet or KB card and be asserted.

`courtyard`, `pads_bbox` and `body_bbox` are rotation-resolved, and `None` when
the footprint carries no such geometry.

An enclosure's obstacle ledger is made of courtyards, but the courtyard is not
automatically the larger box.  A socketed module's courtyard is routinely drawn
around its pad grid and comes out smaller than the part body, so an obstacle
rect is `courtyard ∪ body_bbox` (see references/mechanical.md §4).

That is why `body_bbox` is exported rather than left to a handoff table in
prose: the Fab outline is the part's own body, it is right there in the file,
and a number that has to be retyped can drift from the file.

`fab_items` is the same argument one step down.  A protruding actuator (a
slide-switch knob, a button plunger, a connector shell) is usually its own
group of Fab lines, and the case has to slot exactly that.  Every item is
reported separately, in board coordinates with the rotation already applied, so
the caller unions the ones it means instead of writing a bespoke pcbnew script.

The adoption diff (`--diff OLD NEW`).  A generated board's docstring says never
to hand-edit the `.kicad_pcb`, and that is right.  But dragging four footprints
in pcbnew is the normal way a person says "put the encoder over here", so the
round trip needs a defined re-entry path rather than a prohibition.  `--diff`
is the machine-readable half of it: per-ref Δx / Δy / Δrot / Δside, refs added
and removed, and changes to the `protrudes` sets.

Both halves of that matter, and the second is the one nothing else catches:

  * A hand placement is an `(x, y, rot, layer)` tuple and all four are the
    spec.  A rotation adopted at 180° instead of 0° reverses which pad of a
    two-terminal part faces the net leaving it, which is a routing topology
    change (measured cost: two vias).  A part that came back on the other face
    is a bigger change than any position move.
  * A keepout derived from a component bound is invalidated by that component
    leaving, not only by it moving.  Two parts moving to the front face took
    the protrude-below set from 37 refs to 35, and they were the two that
    bounded a battery bay, whose plan area then grew ~68 % with every remaining
    ref still perfectly in the ledger.  A stale ledger that is merely
    conservative is the failure mode nobody looks for.

`--as-constants` prints the moved set as a python dict ready to paste into an
emitter, because transcribing eight coordinates by hand out of a JSON dump is a
transcription risk with no checker behind it: a board generated from the wrong
adopted coordinate is perfectly clean.  Adopt, regenerate, then run `--diff
--strict` between the backup and the regenerated board and require no
differences.  That last step is what makes the whole round trip safe.

The fit contract (`--contract OUT.json [--design design.py]`)
------------------------------------------------------------
The board-to-enclosure interface as one machine-readable file, so the case
reads a decision instead of retyping a number.  It is also a phase-4 gate:
the command exits 1 when a connector declares no mating_direction, or when its
mating face does not point out through a board edge within a stated distance
(`docs/BACKLOG.md` B8: a USB-C receptacle placed with its mating face inboard
passed every other check).

A part is a connector when design.py PARTS (or a footprint field) gives it a
`role`, an `interface` or a `mating_direction`, or when its reference prefix
is J, P, USB, CN or X, or when its footprint library name starts with
`Connector`.  Board-inherent parts (holes, fiducials, test points) are never
connectors.  Every connector without a mating_direction is a FAIL
("undeclared mating_direction"): a board whose connectors declare nothing must
not pass a check that tested nothing.

    python3 scripts/kicad_geom.py board.kicad_pcb --contract fit.json \
        --design design.py

Two inputs come from `design.py`'s `PARTS` table, keyed by ref then value,
because the board file carries neither (`templates/design.py`):

    mating_direction  "+x" "-x" "+y" "-y" "+z" "-z", footprint-local axes as
                      the library footprint is drawn (x right, y down, z out of
                      the mounting face), naming the outward normal of the
                      mating face: the way a plug is pulled out, the way a
                      cable leaves, the side a user reaches from.
    height_mm         body height above the mounting face, or
    z_band            [lo, hi] above the mounting face, for a part that also
                      reaches below it (a reverse-mount LED, a pin header).
    interface         the standard a connector follows (kicad_ifcheck.py);
                      marks the part as a connector.
    edge_max_mm       how far inboard of its edge the mating face may sit
                      (default EDGE_MAX_INSET_MM).  The face passes when the
                      edge its direction crosses faces the same way (within
                      45 degrees) and lies within this distance, even when
                      another edge is nearer.
    access            "external" (default) or "internal": a connector that
                      mates inside the enclosure (a battery lead) needs no
                      edge and no opening.
    mating_body       optional [x0, y0, x1, y1], library footprint-local: the
                      part of the body the opening is for (a slide switch's
                      knob, a button's plunger), with optional `mating_z`
                      [lo, hi] above the mounting face.  Without it, the body
                      reaching furthest in the mating direction is used.
    offboard          optional, for a part that lives on the enclosure and
                      is wired to this board's pads (a panel connector on a
                      pigtail, a capsule on leads): face, axis, at, datum,
                      segments, margin_mm, pigtail, as the `offboard` record
                      below.  It is carried into the contract's
                      `offboard[]`, and `case_verify.py connector_openings`
                      tests the opening against its body and mated plug and
                      the pigtail length against the pad distance.  A
                      malformed block is a FAIL.

A footprint property of the same name (`mating_direction`, `height_mm`,
`interface`, `access`) fills any key the PARTS row leaves unset.

The forked kicad-cli's `connector_edge` DRC and this contract read one
source: the footprint property `mating_direction` (+x -x +y -y +z -z in
footprint axes, rotated by the footprint, y mirrored on the back face, +z and
-z skipped).  The DRC message carries `body_to_edge_mm` and the angle to the
nearest edge normal.  Without the property the DRC falls back to the shortest
body to edge distance.  The old board-frame field `Mating_Direction` (N/S/E/W)
is no longer read (fork master, 2026-10-03).

A part with no declared height takes one from its STEP model
(`kicad_3d.model_extent`), and the record names which source fired.  A
back-face footprint's library-local axes are stored mirrored in y, so a
declared direction is mirrored the same way before the placement rotation;
this was checked against a back-face MSK12C02 whose pads sit at local
y -1.95 in the library and +1.95 in the board file.

Schema, version 1.  Stable: add keys, never rename or re-mean one.

    schema            "hw_forge.fit_contract"
    version           1
    source, design    the board and design.py paths it was built from
    units             "mm"
    frame             board coords: x east, y south, z up; z = 0 is the top
                      face, the bottom face is z = -thickness
    board
      thickness       mm, from the file's (general (thickness)), and
      thickness_source
      outline         {polygon: [[x, y], ...], bbox, area, closed}
      cutouts         [{polygon, bbox, area, owner}]: interior Edge.Cuts loops;
                      owner is a ref for a footprint-drawn window, else null
    mounting_holes    [{ref, x, y, diameter, plated, pad}]
    parts             one per footprint:
      ref value lib x y rotation side pad_side through_hole protrudes
      courtyard body_bbox      as in --json
      obstacle        {bbox, basis}: what stands on the board, plan view
      model_bbox      plan bbox of the part's STEP models, or null
      envelope        obstacle U body_bbox U model_bbox: the plan box of
                      the whole part (a module's courtyard can miss the USB
                      shell its model carries)
      bodies          [{source, bbox, z}]: one box per STEP model, or one
                      over the envelope for a declared height, plus a tail
                      box under the pads of a through-hole part; z in the
                      board frame.  The solid fit checks test these.
      z_band          [z_lo, z_hi] board frame, or null when unknown
      z_source        "design.py PARTS['J1'].height_mm" | "...z_band" |
                      "footprint field.height_mm" | "step: FILE[, FILE]" |
                      "none"
      role            "connector" | "user_facing" | null
      connector       true when the part is a connector by the rule above
      connector_basis why: "design.py role" | "interface" |
                      "mating_direction" | "prefix J" | "library Connector_..."
                      | null
      board_inherent  BOARD_INHERENT kind ("mounting_hole", ...) or null
      interface       PARTS interface string, or null
      access          "external" | "internal"
      mating          null, or
        direction_local   "+y"
        direction_board   [dx, dy, dz] unit vector, board frame
        kind              "edge" (in-plane) | "top" | "bottom" | "internal"
        face_body         {source, bbox, z}: the body the opening is for
        wall              edge name the face points through: "north", "south",
                          "east", "west", "edge@<deg>"; "top"/"bottom" for z
        body_to_edge_mm   along the mating direction, leading body face to the
                          edge it crosses; negative = the body overhangs
        nearest_edge      {wall, distance_mm, normal}: closest edge to the
                          body; at equal distance (a corner) the edge whose
                          outward normal best aligns with direction_board
        outboard          the face points out through the edge it crosses,
                          and sits within edge_max_mm of it
        edge_max_mm, edge_max_source
        opening           what the case must open: {wall, normal, plane_point,
                          span_points [[x, y], [x, y]], span_mm, z}, or for a
                          top/bottom face {face, bbox, z}
        verdict, reason   "PASS" | "FAIL" | "INFO"
    offboard          one per design.py PARTS row with an `offboard` block:
                      a part that lives off the board, on the enclosure (a
                      panel connector wired by a pigtail to solder pads, a
                      capsule on leads).  Its geometry is in the CASE frame,
                      because no board coordinate describes it:
      ref             the PARTS key
      pads            ref of the board pad set it is wired to (default ref)
      pads_xy         [x, y] board frame: centre of those pads, or null
      what            free text, e.g. "GX16-4 male panel socket"
      face            the enclosure face it mounts through, free text
                      ("tail wall"), used in messages only
      axis            outward normal of that face, case frame: [dx, dy, dz]
      up              case-frame vector across the axis that a box
                      segment's h runs along: [dx, dy, dz]
      datum           name of a case datum (`datums=` in case_verify), or null
      at              [X, Y, Z] mounting point, the centre of the opening on
                      the face's outer surface; case frame, or an offset from
                      the datum
      segments        [{name, z: [lo, hi], d | w and h, mated}]: the body as
                      coaxial pieces along the axis, z = 0 on the outer
                      surface and positive outward.  A round piece has a
                      diameter d, a rectangular one w by h.  `mated` marks
                      the mating plug's envelope beyond the face.  A piece
                      with z lo < 0 <= z hi crosses the wall: the opening
                      must clear it.
      margin_mm       clearance per side the opening must leave
      pigtail         {length_mm, slack_mm, to_z} or null: the wire must
                      reach from pads_xy to the axis point at z = to_z
                      (default: the innermost segment end) with slack_mm to
                      spare
      source          "design.py PARTS['J1'].offboard"
    z_sources         {declared, step, none}: counts over non-inherent parts
    findings          [{severity, ref, message}], severity "FAIL" | "WARN"
"""

import argparse
import json
import math
import os
import re
import sys

# Footprint properties the fit contract reads when design.py's PARTS table
# does not state them.  The forked kicad-cli's `connector_edge` DRC reads the
# same `mating_direction` property (fork master, 2026-10-03).
FIT_FIELDS = ("mating_direction", "height_mm", "interface", "access")

# Board-level graphic items that can carry the outline.
GRAPHIC_ITEMS = ("gr_rect", "gr_line", "gr_arc", "gr_circle", "gr_poly")
FP_GRAPHIC_ITEMS = ("fp_rect", "fp_line", "fp_arc", "fp_circle", "fp_poly")
OUTLINE_LAYER = "Edge.Cuts"
COURTYARD_LAYERS = ("F.CrtYd", "B.CrtYd")
# The Fab layers carry the part's own body outline (and often its actuator),
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


ARC_SEGMENTS = 16          # chords per arc or circle when an outline is
                           # polygonised; a 0.5 mm radius corner then deviates
                           # from its chord by under 0.003 mm


def _arc_points(start, mid, end, segments=ARC_SEGMENTS):
    """Points along the circular arc through start, mid and end."""
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    det = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(det) < 1e-12:
        return [start, end]                          # collinear: a line
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    cx = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / det
    cy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / det
    r = math.hypot(x1 - cx, y1 - cy)
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    a3 = math.atan2(y3 - cy, x3 - cx)

    def ccw(a, b):                                   # sweep a -> b, [0, 2pi)
        return (b - a) % (2.0 * math.pi)
    sweep = ccw(a1, a3)
    if ccw(a1, a2) > sweep:                          # mid is on the other way
        sweep -= 2.0 * math.pi
    return [(cx + r * math.cos(a1 + sweep * i / segments),
             cy + r * math.sin(a1 + sweep * i / segments))
            for i in range(segments + 1)]


def _item_paths(node, head):
    """[(points, closed)] for one graphic item, in its own frame."""
    def pt(tag):
        got = kid(node, tag)
        vals = nums(got, 2) if got else []
        return tuple(vals) if len(vals) == 2 else None
    if head in ("gr_line", "fp_line"):
        a, b = pt("start"), pt("end")
        return [([a, b], False)] if a and b else []
    if head in ("gr_rect", "fp_rect"):
        a, b = pt("start"), pt("end")
        if not (a and b):
            return []
        return [([a, (b[0], a[1]), b, (a[0], b[1])], True)]
    if head in ("gr_arc", "fp_arc"):
        a, m, b = pt("start"), pt("mid"), pt("end")
        return [(_arc_points(a, m, b), False)] if a and m and b else []
    if head in ("gr_circle", "fp_circle"):
        c, e = pt("center"), pt("end")
        if not (c and e):
            return []
        r = math.hypot(e[0] - c[0], e[1] - c[1])
        n = 2 * ARC_SEGMENTS
        return [([(c[0] + r * math.cos(2 * math.pi * i / n),
                   c[1] + r * math.sin(2 * math.pi * i / n))
                  for i in range(n)], True)]
    if head in ("gr_poly", "fp_poly"):
        poly = kid(node, "pts")
        pts = [tuple(nums(p, 2)) for p in kids(poly, "xy")] if poly else []
        return [(pts, True)] if len(pts) >= 3 else []
    return []


def _outline_item(node, head, owner, origin, angle):
    """One Edge.Cuts graphic, in board coordinates."""
    ox, oy = origin
    pts = []
    for px, py in _bbox_points(node, head):
        rx, ry = rotate(px, py, angle) if owner else (px, py)
        pts.append((round(rx + ox, 4), round(ry + oy, 4)))
    if not pts:
        return None
    paths = []
    for path, closed in _item_paths(node, head):
        placed = []
        for px, py in path:
            rx, ry = rotate(px, py, angle) if owner else (px, py)
            placed.append((round(rx + ox, 4), round(ry + oy, 4)))
        paths.append({"points": placed, "closed": closed})
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return {"kind": head, "owner": owner, "points": pts, "paths": paths,
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


# A reference designator is a prefix plus digits, and the prefixes are not a
# prefix-free code (`D`/`DISP`, `R`/`RN`, `C`/`CN`, `J`/`JP`), so the split has
# to be parsed rather than guessed with startswith().
_DESIGNATOR = re.compile(r"^([A-Za-z_]+?)(\d+)$")


def designator(ref):
    """{'prefix': 'DISP', 'index': 1}, with index None for an unparseable ref.

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
    """({bbox, basis, courtyard_dropped}): what physically stands on a face.

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
    # body only where its own pads also do.  Then the excess is flat copper and
    # silk, nothing that stands above the board.  Both conditions are needed:
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
    fields = {}
    for prop in kids(node, "property"):
        names = atoms(prop)
        if len(names) >= 3 and names[1] == "Reference":
            ref = names[2]
        elif len(names) >= 3 and names[1] == "Value":
            value = names[2]
        elif len(names) >= 3 and names[1] in FIT_FIELDS:
            fields[names[1]] = names[2]

    fp = {"ref": ref, "value": value, "lib": lib, "x": round(x, 4),
          "y": round(y, 4), "rotation": rot, "side": side, "layer": layer,
          "designator": designator(ref), "fields": fields}

    holes = []
    pad_boxes, pad_layer_names, through = [], set(), False
    for pad in kids(node, "pad"):
        hole = _pad_hole(pad, ref or lib, (x, y), rot)
        if hole:
            holes.append(hole)
        pad_type = atoms(pad)[2] if len(atoms(pad)) > 2 else ""
        if pad_type == "thru_hole":
            through = True
        if pad_type != "np_thru_hole":               # non-plated: no copper
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

    # 3D model links, with the transform the 3D viewer and STEP exporter apply.
    models = []
    for model in kids(node, "model"):
        names = atoms(model)
        if len(names) < 2:
            continue
        xform = {}
        for key, default in (("offset", 0.0), ("scale", 1.0),
                             ("rotate", 0.0)):
            got = kid(model, key)
            xyz = kid(got, "xyz") if got else None
            vals = nums(xyz) if xyz else []
            xform[key] = (vals + [default] * 3)[:3]
        hide = kid(model, "hide")
        models.append({"path": names[1], "offset": xform["offset"],
                       "scale": xform["scale"], "rotate": xform["rotate"],
                       "hidden": bool(hide) and "no" not in atoms(hide)})

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
               "models": models,
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
    return _read(path)[0]


def _read(path):
    """(board summary, every Edge.Cuts item with its polygon paths)."""
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

    # Vias are drilled and plated, so a fab's plated-through-hole tool list
    # includes them.
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
    general = kid(root, "general")
    thick = kid(general, "thickness") if general else None
    thickness = nums(thick)[0] if thick and nums(thick) else None
    return {"source": path,
            "units": "mm",
            "coordinate_frame": "KiCad board coords: x east, y south",
            "thickness": thickness,
            "outline": _outline_summary(outline, board_rects),
            "holes": sorted(holes, key=lambda h: (h["diameter"], h["y"], h["x"])),
            "footprints": sorted(footprints,
                                 key=lambda f: (f["ref"] or f["lib"]))}, outline


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
    figures.  A hole coordinate that reads 47.62 when the board says 47.625 is
    the kind of quiet rounding the enclosure phase must never inherit from this
    tool.
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
        print("\n%d footprint(s) whose BODY overhangs their own COURTYARD: "
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
              "their own pad row:\n`obstacle_above`/`obstacle_below` are the "
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
              "other: their\nhardware is NOT where `side` says. Build "
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
            print("\n%d footprint(s) with no %s geometry (%s), %s:"
                  % (len(missing), key, where, consequence))
            print("  %s" % ", ".join(sorted(f["ref"] or f["lib"]
                                            for f in missing)))


# ------------------------------------------------------------ the fit contract

CONTRACT_SCHEMA = "hw_forge.fit_contract"
CONTRACT_VERSION = 1

# How far inboard of its edge a mating face may sit when design.py states no
# `edge_max_mm`.  A stated policy number, not a derived one: set the real value
# per part from the connector datasheet and the case wall it has to reach
# through.
EDGE_MAX_INSET_MM = 1.0
# Far-face extent given to a through-hole part whose height source says
# nothing about its tails: a clipped and soldered lead, the figure
# references/mechanical.md §4 measured for a display's header tails.
THT_TAIL_MM = 1.50
# A mating face "points out through" an edge when its direction is within 45
# degrees of that edge's outward normal.
OUTBOARD_COS = math.cos(math.radians(45.0))
DEFAULT_THICKNESS = 1.60          # KiCad's own default board thickness
DIRECTIONS = {"+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0),
              "+y": (0.0, 1.0, 0.0), "-y": (0.0, -1.0, 0.0),
              "+z": (0.0, 0.0, 1.0), "-z": (0.0, 0.0, -1.0)}
LOOP_TOL = 0.01                   # endpoint match when chaining Edge.Cuts
# Reference prefixes and footprint library prefix that make a part a
# connector without any design.py declaration (module docstring).
CONNECTOR_PREFIXES = ("J", "P", "USB", "CN", "X")
CONNECTOR_LIB_PREFIX = "Connector"


def connector_basis(fp, entry, kind):
    """Why a part is a connector, or None when it is not one."""
    if kind:                      # a hole, fiducial or test point
        return None
    for key in ("role", "interface", "mating_direction"):
        if entry.get(key):
            return "design.py %s" % key
    prefix = fp["designator"]["prefix"]
    if prefix in CONNECTOR_PREFIXES:
        return "prefix %s" % prefix
    if (fp.get("lib") or "").startswith(CONNECTOR_LIB_PREFIX):
        return "library %s" % fp["lib"].split(":")[0]
    return None


def load_design_tables(path, names=("PARTS", "BOARD_INHERENT")):
    """{name: dict} imported from a design.py; empty dicts when no path.

    The same mechanism kicad_fpcheck.py and kicad_bom.py use: design.py is
    pure stdlib by hw_forge doctrine, so importing it under any python3 is
    safe.  Bytecode is suppressed so a reader leaves nothing in the project.
    """
    if not path:
        return dict((n, {}) for n in names)
    import importlib.util
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("hwforge_design_contract",
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict((n, getattr(module, n, {}) or {}) for n in names)


_AXES = {"+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0),
         "+y": (0.0, 1.0, 0.0), "-y": (0.0, -1.0, 0.0),
         "+z": (0.0, 0.0, 1.0), "-z": (0.0, 0.0, -1.0)}


def _vector(value):
    """A unit 3-vector from "+x" style text or a list, or None."""
    if isinstance(value, str):
        return _AXES.get(value.strip().lower())
    try:
        v = [float(c) for c in value]
    except (TypeError, ValueError):
        return None
    if len(v) != 3:
        return None
    n = math.sqrt(sum(c * c for c in v))
    return tuple(round(c / n, 6) for c in v) if n > 1e-9 else None


def offboard_pads(key, spec, by_ref, footprints):
    """The footprints an offboard block's pads are on: `pads` (else the
    PARTS key) as a reference, else every footprint whose value is that
    name, the same ref-then-value order kicad_bom.kind_of uses."""
    want = spec.get("pads") or key
    if want in by_ref:
        return [by_ref[want]]
    return sorted((f for f in footprints if f.get("value") == want),
                  key=lambda f: f["ref"])


def offboard_record(key, spec, by_ref, footprints=()):
    """([records], [problems]) for one PARTS[key]["offboard"] block: one
    record per footprint it resolves to (by ref, then by value)."""
    problems = []
    source = "design.py PARTS[%r].offboard" % key
    if not isinstance(spec, dict):
        return [], ["%s must be a dict" % source]
    axis = _vector(spec.get("axis"))
    if axis is None:
        problems.append("%s: axis %r is not +x -x +y -y +z -z or a "
                        "3-vector" % (source, spec.get("axis")))
    up = _vector(spec.get("up")) if spec.get("up") else None
    if up is None and axis is not None:
        up = (0.0, 1.0, 0.0) if abs(axis[2]) > 0.9 else (0.0, 0.0, 1.0)
    at = spec.get("at")
    try:
        at = [float(c) for c in at]
        if len(at) != 3:
            raise ValueError
    except (TypeError, ValueError):
        problems.append("%s: at %r is not [X, Y, Z]" % (source, at))
        at = None
    segments = []
    raw = spec.get("segments") or []
    if not isinstance(raw, (list, tuple)):
        problems.append("%s: segments must be a list" % source)
        raw = []
    for i, seg in enumerate(raw):
        name = "segment %d" % i
        try:
            name = seg.get("name") or name
            z = [float(seg["z"][0]), float(seg["z"][1])]
            if z[1] <= z[0]:
                raise ValueError
            rec = {"name": name, "z": z, "mated": bool(seg.get("mated"))}
            if seg.get("d") is not None:
                rec["d"] = float(seg["d"])
            else:
                rec["w"], rec["h"] = float(seg["w"]), float(seg["h"])
        except (KeyError, TypeError, ValueError, IndexError,
                AttributeError):
            problems.append("%s: segment %r needs z [lo, hi] with lo < hi "
                            "and d, or w and h" % (source, name))
            continue
        segments.append(rec)
    if not segments:
        problems.append("%s: no usable segments: the body envelope is what "
                        "the opening check tests" % source)
    pads = spec.get("pads") or key
    fps = offboard_pads(key, spec, by_ref, footprints)
    if not fps:
        problems.append("%s: pads %r is neither a reference nor a value of "
                        "a footprint on this board" % (source, pads))
    pig = spec.get("pigtail")
    if pig is not None:
        try:
            body = [s for s in segments if not s["mated"]]
            pig = {"length_mm": float(pig["length_mm"]),
                   "slack_mm": float(pig.get("slack_mm", 0.0)),
                   "to_z": float(pig["to_z"]) if pig.get("to_z") is not None
                   else min(s["z"][0] for s in body) if body else 0.0}
        except (KeyError, TypeError, ValueError):
            problems.append("%s: pigtail needs length_mm (and optional "
                            "slack_mm, to_z)" % source)
            pig = None
    try:
        margin = float(spec.get("margin_mm", 0.30))
    except (TypeError, ValueError):
        problems.append("%s: margin_mm %r is not a number"
                        % (source, spec.get("margin_mm")))
        margin = 0.30
    records = []
    for fp in fps or [None]:
        box = fp and (fp.get("pads_bbox") or fp.get("body_bbox"))
        pads_xy = ([round((box[0] + box[2]) / 2.0, 4),
                    round((box[1] + box[3]) / 2.0, 4)] if box
                   else [fp["x"], fp["y"]] if fp else None)
        records.append({
            "ref": fp["ref"] if fp else key,
            "pads": fp["ref"] if fp else pads, "pads_xy": pads_xy,
            "what": spec.get("what"), "face": spec.get("face"),
            "axis": list(axis) if axis else None,
            "up": list(up) if up else None,
            "datum": spec.get("datum"), "at": at, "segments": segments,
            "margin_mm": margin, "pigtail": pig, "source": source})
    return records, problems


def part_entry(parts, ref, value):
    """The PARTS row for a part: by reference first, then by value."""
    if ref in parts:
        return parts[ref], "PARTS[%r]" % ref
    if value in parts:
        return parts[value], "PARTS[%r]" % value
    return {}, None


def _area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                     - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def _close(a, b, tol=LOOP_TOL):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def edge_loops(items):
    """Chain Edge.Cuts paths into loops: [{polygon, owner, closed}].

    Lines and arcs are open paths and are joined end to end; rects, circles
    and polygons arrive closed.  A chain that never closes is returned with
    `closed: False`, which a fab would reject and the contract reports.
    """
    loops, open_paths = [], []
    for item in items:
        for path in item.get("paths") or []:
            pts = [tuple(p) for p in path["points"]]
            if path["closed"]:
                loops.append({"polygon": pts, "owner": item["owner"],
                              "closed": True})
            elif len(pts) >= 2:
                open_paths.append((pts, item["owner"]))
    while open_paths:
        chain, owner = open_paths.pop(0)
        grown = True
        while grown and not (len(chain) > 2 and _close(chain[0], chain[-1])):
            grown = False
            for i, (pts, own) in enumerate(open_paths):
                if own != owner:
                    continue
                if _close(chain[-1], pts[0]):
                    chain += pts[1:]
                elif _close(chain[-1], pts[-1]):
                    chain += pts[::-1][1:]
                elif _close(chain[0], pts[-1]):
                    chain = pts[:-1] + chain
                elif _close(chain[0], pts[0]):
                    chain = pts[::-1][:-1] + chain
                else:
                    continue
                open_paths.pop(i)
                grown = True
                break
        closed = len(chain) > 2 and _close(chain[0], chain[-1])
        if closed:
            chain = chain[:-1]
        loops.append({"polygon": chain, "owner": owner, "closed": closed})
    for loop in loops:
        poly = loop["polygon"]
        loop["area"] = round(abs(_area(poly)), 4) if len(poly) >= 3 else 0.0
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        loop["bbox"] = [round(min(xs), 4), round(min(ys), 4),
                        round(max(xs), 4), round(max(ys), 4)]
        loop["polygon"] = [[round(p[0], 4), round(p[1], 4)] for p in poly]
    return loops


def _segments(poly):
    """[(a, b, outward_normal)] for a polygon, whichever way it winds."""
    sign = 1.0 if _area(poly) > 0 else -1.0
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        out.append((a, b, (sign * dy / length, -sign * dx / length)))
    return out


def point_in_polygon(x, y, poly):
    inside = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def _point_seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    t = 0.0 if den == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx
                                                + (p[1] - a[1]) * dy) / den))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _box_seg_dist(box, a, b):
    """Distance from an axis-aligned box to a segment; 0 when they touch."""
    x0, y0, x1, y1 = box
    for p in (a, b):
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            return 0.0
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for i in range(4):
        if _ray_seg(corners[i], (corners[(i + 1) % 4][0] - corners[i][0],
                                 corners[(i + 1) % 4][1] - corners[i][1]),
                    a, b, limit=1.0) is not None:
            return 0.0
    return min([_point_seg_dist(c, a, b) for c in corners]
               + [math.hypot(max(x0 - p[0], 0, p[0] - x1),
                             max(y0 - p[1], 0, p[1] - y1)) for p in (a, b)])


def _ray_seg(p, d, a, b, limit=None):
    """t where p + t*d meets segment ab (t >= 0, and <= limit), else None."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    den = d[0] * ey - d[1] * ex
    if abs(den) < 1e-12:
        return None
    wx, wy = a[0] - p[0], a[1] - p[1]
    t = (wx * ey - wy * ex) / den
    s = (wx * d[1] - wy * d[0]) / den
    if t < -1e-9 or s < -1e-9 or s > 1.0 + 1e-9:
        return None
    if limit is not None and t > limit + 1e-9:
        return None
    return t


def wall_name(normal):
    """'east' / 'south' / 'west' / 'north' for an axis-aligned outward
    normal in board coords (y south), else 'edge@<deg>'."""
    deg = math.degrees(math.atan2(normal[1], normal[0])) % 360.0
    for name, at in (("east", 0.0), ("south", 90.0), ("west", 180.0),
                     ("north", 270.0), ("east", 360.0)):
        if abs(deg - at) < 1.0:
            return name
    return "edge@%d" % round(deg)


def resolve_model_path(link, board_path):
    """A STEP file for one footprint model link, or None.

    `${KIPRJMOD}` is the board's own directory, the KiCad model variables
    resolve against the installed library (preflight.model_roots), and a
    `.wrl` link is tried as `.step`/`.stp` first, because only STEP carries
    the solid geometry a height can be read from.
    """
    path = link.strip().replace("\\", "/")
    board_dir = os.path.dirname(os.path.abspath(board_path))
    for anchor in ("${KIPRJMOD}", "$(KIPRJMOD)"):
        path = path.replace(anchor, board_dir)
    candidates = [path]
    if "${" in path or "$(" in path:
        try:
            from preflight import model_roots
            roots = model_roots()
        except ImportError:                          # pragma: no cover
            roots = []
        var = re.search(r"\$[{(]([A-Z0-9_]+)[})]", path)
        candidates = [path.replace(var.group(0), root) for root in roots] \
            if var else []
    out = []
    for cand in candidates:
        stem, ext = os.path.splitext(cand)
        out += [stem + e for e in (".step", ".stp", ".STEP", ".STP")]
        out.append(cand)
    for cand in out:
        if not os.path.isabs(cand):
            cand = os.path.join(board_dir, cand)
        if os.path.isfile(cand) and cand.lower().endswith((".step", ".stp")):
            return os.path.normpath(cand)
    return None


def _model_info(fp, board_path):
    """(local z band, [file names], plan bbox in board coords, per-model
    [{file, z_local, bbox}]) of a part's visible STEP models, unioned;
    (None, [], None, []) when none resolves.

    A module footprint often links its body and its connector shell as two
    models, and the shell is what overhangs the board edge, so both count.
    The plan box maps the model's y-north frame into the footprint's y-south
    one, and is skipped for a model turned about x or y.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import kicad_3d
    local, names, corners, per_model = None, [], [], []
    for model in fp.get("models") or []:
        if model.get("hidden"):
            continue
        step = resolve_model_path(model["path"], board_path)
        if not step:
            continue
        extent, _why = kicad_3d.model_extent(step)
        if extent is None:
            continue
        band = kicad_3d.placed_z_band(extent, model["offset"],
                                      model["scale"], model["rotate"])
        local = band if local is None else [min(local[0], band[0]),
                                            max(local[1], band[1])]
        names.append(os.path.basename(step) + (
            "" if kicad_3d.rotation_is_sign_proof(model["rotate"])
            else " (x/y rotation not a multiple of 180)"))
        rx, ry, rz = model["rotate"]
        mine = []
        per_model.append({"file": names[-1], "z_local": band, "corners": mine})
        if abs(rx) > 1e-9 or abs(ry) > 1e-9:
            continue
        a = math.radians(-rz)
        for mx in (extent["min"][0], extent["max"][0]):
            for my in (extent["min"][1], extent["max"][1]):
                x1, y1 = mx * model["scale"][0], my * model["scale"][1]
                x2 = x1 * math.cos(a) - y1 * math.sin(a) + model["offset"][0]
                y2 = x1 * math.sin(a) + y1 * math.cos(a) + model["offset"][1]
                lx, ly = x2, -y2                    # model y north -> local
                if fp["side"] == "bottom":
                    ly = -ly                        # stored frame is mirrored
                bx, by = rotate(lx, ly, fp["rotation"])
                corners.append((bx + fp["x"], by + fp["y"]))
                mine.append((bx + fp["x"], by + fp["y"]))
    def box(pts):
        return [round(min(c[0] for c in pts), 4), round(min(c[1] for c in pts), 4),
                round(max(c[0] for c in pts), 4),
                round(max(c[1] for c in pts), 4)] if pts else None
    for rec in per_model:
        rec["bbox"] = box(rec.pop("corners"))
    return local, names, box(corners), per_model


def _board_z(local, side, thickness):
    """A band above the mounting face -> the board frame (z = 0 top face)."""
    lo, hi = local
    band = [lo, hi] if side == "top" else [-thickness - hi, -thickness - lo]
    return [round(band[0], 4), round(band[1], 4)]


def _bodies(fp, entry, entry_key, thickness, model, envelope):
    """([{source, bbox, z}], union z band or None, source label).

    A declared height is one body over the plan envelope.  Otherwise each
    STEP model is its own body, so a module's USB shell and its board are
    two boxes rather than one box round both.  A through-hole part adds a
    tail body under its pads on the far face.
    """
    bodies, source = [], "none"
    declared = None
    if entry.get("z_band") is not None:
        declared = [float(v) for v in entry["z_band"]]
        source = "%s.z_band" % entry_key
    elif entry.get("height_mm") is not None:
        declared = [0.0, float(entry["height_mm"])]
        source = "%s.height_mm" % entry_key
    if declared is not None:
        bodies.append({"source": source, "bbox": envelope,
                       "z": _board_z(declared, fp["side"], thickness)})
    elif model[0] is not None:
        source = "step: " + ", ".join(model[1])
        for m in model[3]:
            bodies.append({"source": "step: " + m["file"],
                           "bbox": m["bbox"] or envelope,
                           "z": _board_z(m["z_local"], fp["side"], thickness)})
    if not bodies:
        return [], None, source
    if fp["through_hole"]:
        tail = [-thickness - THT_TAIL_MM, -thickness]
        bodies.append({"source": "through-hole tails, THT_TAIL_MM %.2f"
                                 % THT_TAIL_MM,
                       "bbox": fp.get("pads_bbox") or envelope,
                       "z": _board_z(tail, fp["side"], thickness)})
    z = [round(min(b["z"][0] for b in bodies), 4),
         round(max(b["z"][1] for b in bodies), 4)]
    return bodies, z, source


def _face_body(fp, entry, bodies, d, thickness):
    """The body a mating face belongs to: design.py `mating_body` (library
    footprint-local [x0, y0, x1, y1], with optional `mating_z`), else the
    body reaching furthest in the mating direction."""
    raw = entry.get("mating_body")
    if raw:
        x0, y0, x1, y1 = [float(v) for v in raw]
        pts = []
        for lx in (x0, x1):
            for ly in (y0, y1):
                if fp["side"] == "bottom":
                    ly = -ly
                bx, by = rotate(lx, ly, fp["rotation"])
                pts.append((bx + fp["x"], by + fp["y"]))
        bbox = [round(min(p[0] for p in pts), 4), round(min(p[1] for p in pts), 4),
                round(max(p[0] for p in pts), 4), round(max(p[1] for p in pts), 4)]
        z = (_board_z([float(v) for v in entry["mating_z"]], fp["side"],
                      thickness) if entry.get("mating_z") is not None
             else None)
        return {"source": "design.py mating_body", "bbox": bbox, "z": z}
    real = [b for b in bodies if not b["source"].startswith("through-hole")]
    if not real:
        return None
    if d[2]:
        return max(real, key=lambda b: b["z"][1] * d[2])
    return max(real, key=lambda b: max(
        x * d[0] + y * d[1] for x in (b["bbox"][0], b["bbox"][2])
        for y in (b["bbox"][1], b["bbox"][3])))


def _mating(fp, entry, entry_key, outline, z_band, box, bodies=(),
            thickness=DEFAULT_THICKNESS):
    """The mating record for one part, or None when none is declared."""
    raw = entry.get("mating_direction")
    if not raw:
        return None
    key = str(raw).strip().lower()
    if key in ("x", "y", "z"):
        key = "+" + key
    if key not in DIRECTIONS:
        return {"direction_local": raw, "verdict": "FAIL",
                "reason": "mating_direction %r is not one of %s"
                          % (raw, ", ".join(sorted(DIRECTIONS)))}
    vx, vy, vz = DIRECTIONS[key]
    internal = str(entry.get("access") or "external").lower() == "internal"
    bottom = fp["side"] == "bottom"
    if bottom:                    # the stored local frame is mirrored in y
        vy, vz = -vy, -vz
    dx, dy = rotate(vx, vy, fp["rotation"])
    rec = {"direction_local": key,
           "direction_board": [round(dx, 6), round(dy, 6), vz]}
    face = _face_body(fp, entry, bodies, (dx, dy, vz), thickness)
    if face:
        box = face["bbox"] or box
        z_band = face["z"] or z_band
        rec["face_body"] = face
    if internal:
        rec.update({"kind": "internal", "wall": None, "verdict": "INFO",
                    "reason": "access internal: mates inside the enclosure, "
                              "no edge or opening required"})
        return rec
    if vz:
        face = "top" if vz > 0 else "bottom"
        rec.update({"kind": face, "wall": face,
                    "opening": {"face": face, "bbox": box, "z": z_band},
                    "verdict": "INFO",
                    "reason": "mates through the %s face; the case opens "
                              "over it" % face})
        return rec
    if not box or not outline:
        rec.update({"kind": "edge", "verdict": "FAIL",
                    "reason": "no body geometry or no closed board outline "
                              "to test the mating face against"})
        return rec
    segs = _segments(outline)
    d = (dx, dy)
    # The ray starts at the footprint origin, which is on the board even when
    # the mating body (a knob, a shell) already overhangs the edge.
    cx, cy = fp["x"], fp["y"]
    if not point_in_polygon(cx, cy, outline):
        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    lead = max((x - cx) * dx + (y - cy) * dy
               for x in (box[0], box[2]) for y in (box[1], box[3]))
    hits = [(t, a, b, n) for a, b, n in segs
            for t in [_ray_seg((cx, cy), d, a, b)] if t is not None]
    # At equal distance (a body in a corner touches two edges at 0 mm) the
    # tie goes to the edge whose outward normal best aligns with the mating
    # direction, so the reported nearest edge does not depend on the order
    # the outline was drawn in.
    near = min(((_box_seg_dist(box, a, b), n) for a, b, n in segs),
               key=lambda r: (round(r[0], 6),
                              -(r[1][0] * dx + r[1][1] * dy)))
    max_inset = entry.get("edge_max_mm")
    max_source = ("%s.edge_max_mm" % entry_key
                  if max_inset is not None
                  else "kicad_geom.EDGE_MAX_INSET_MM default")
    max_inset = EDGE_MAX_INSET_MM if max_inset is None else float(max_inset)
    near_aligned = near[1][0] * dx + near[1][1] * dy >= OUTBOARD_COS
    rec.update({"kind": "edge",
                "nearest_edge": {"wall": wall_name(near[1]),
                                 "distance_mm": round(near[0], 4),
                                 "normal": [round(near[1][0], 6),
                                            round(near[1][1], 6)]},
                "outboard": False, "edge_max_mm": max_inset,
                "edge_max_source": max_source})
    if not hits:
        rec.update({"verdict": "FAIL", "wall": None,
                    "reason": "the mating direction crosses no board edge"})
        return rec
    t, a, b, n = min(hits, key=lambda h: h[0])
    inset = t - lead
    # Outboard is judged on the edge the direction crosses, not the nearest
    # edge: a part 15 mm from the edge it faces, with edge_max_mm 100, passes
    # even when another edge is 5 mm away.  edge_max_mm is the whole policy.
    aligned = n[0] * dx + n[1] * dy >= OUTBOARD_COS
    outboard = aligned and inset <= max_inset + 1e-6
    rec["outboard"] = outboard
    hx, hy = cx + t * dx, cy + t * dy
    tangent = (-n[1], n[0])
    spans = [(x - hx) * tangent[0] + (y - hy) * tangent[1]
             for x in (box[0], box[2]) for y in (box[1], box[3])]
    s0, s1 = min(spans), max(spans)
    rec.update({"wall": wall_name(n),
                "body_to_edge_mm": round(t - lead, 4),
                "opening": {"wall": wall_name(n),
                            "normal": [round(n[0], 6), round(n[1], 6), 0.0],
                            "plane_point": [round(hx, 4), round(hy, 4)],
                            "span_points": [[round(hx + s0 * tangent[0], 4),
                                             round(hy + s0 * tangent[1], 4)],
                                            [round(hx + s1 * tangent[0], 4),
                                             round(hy + s1 * tangent[1], 4)]],
                            "span_mm": round(s1 - s0, 4),
                            "z": z_band}})
    if not aligned and n[0] * dx + n[1] * dy <= 0.0:
        rec.update({"verdict": "FAIL",
                    "reason": "mating face points %s, into the board across "
                              "the %s edge: the plug would enter from inboard"
                              % (wall_name(d), wall_name(n))})
    elif not aligned:
        rec.update({"verdict": "FAIL",
                    "reason": "mating face points %s, but crosses the %s "
                              "edge at more than 45 degrees to its normal"
                              % (wall_name(d), wall_name(n))})
    elif not outboard and near[0] <= max_inset + 1e-6 and not near_aligned:
        rec.update({"verdict": "FAIL",
                    "reason": "mating face points %s, but the part sits at "
                              "the %s edge (%.3f mm away): the plug would "
                              "enter from inboard"
                              % (wall_name(d), wall_name(near[1]), near[0])})
    elif not outboard and near[0] > max_inset + 1e-6:
        # Mid-board: no edge is within reach, so naming one would mislead.
        rec.update({"verdict": "FAIL",
                    "reason": "mating face points %s from %.3f mm inboard: "
                              "no board edge within %.3f mm (%s)"
                              % (wall_name(d), inset, max_inset,
                                 max_source)})
    elif not outboard:
        rec.update({"verdict": "FAIL",
                    "reason": "mating face sits %.3f mm inboard of the %s "
                              "edge (max %.3f, %s)"
                              % (inset, wall_name(n), max_inset,
                                 max_source)})
    else:
        rec.update({"verdict": "PASS",
                    "reason": "mating face points out through the %s edge, "
                              "%s %.3f mm" % (wall_name(n),
                                              "inboard" if t - lead >= 0
                                              else "overhanging",
                                              abs(t - lead))})
    return rec


def fit_contract(board_path, design_path=None, use_models=True):
    """Build the fit contract for one board.  See the module docstring."""
    board, items = _read(board_path)
    tables = load_design_tables(design_path)
    parts_table = tables["PARTS"]
    inherent = tables["BOARD_INHERENT"]
    findings = []
    thickness = board.get("thickness")
    thickness_source = "file (general (thickness))"
    if not thickness:
        thickness, thickness_source = DEFAULT_THICKNESS, "default (none in file)"

    loops = edge_loops(items)
    board_loops = [l for l in loops if l["owner"] is None and l["closed"]]
    outline = max(board_loops, key=lambda l: l["area"]) if board_loops else None
    for loop in loops:
        if not loop["closed"]:
            findings.append({"severity": "FAIL", "ref": loop["owner"],
                             "message": "Edge.Cuts chain from %s does not "
                                        "close: a fab cannot route it"
                                        % (loop["polygon"][0],)})
    if outline is None:
        findings.append({"severity": "FAIL", "ref": None,
                         "message": "no closed board outline on Edge.Cuts"})
    cutouts = [dict((k, l[k]) for k in ("polygon", "bbox", "area", "owner"))
               for l in loops if l is not outline and l["closed"]]

    by_ref = dict((f["ref"], f) for f in board["footprints"])

    def inherent_kind(fp):
        """design.py BOARD_INHERENT first, then kicad_bom.py's heuristic.
        `off_board` is a BOM kind, not board fabric: the pads stay a part."""
        kind = inherent.get(fp["ref"]) or inherent.get(fp["value"])
        if kind == "off_board":
            return None
        if kind:
            return kind
        for lib, k in (("MountingHole:", "mounting_hole"),
                       ("Fiducial:", "fiducial"), ("TestPoint:", "test_point")):
            if fp["lib"].startswith(lib):
                return k
        return {"H": "mounting_hole", "MH": "mounting_hole",
                "FID": "fiducial", "TP": "test_point",
                "LOGO": "logo"}.get(fp["designator"]["prefix"])

    def is_mount(owner):
        fp = by_ref.get(owner)
        return bool(fp) and inherent_kind(fp) == "mounting_hole"
    mounting = [{"ref": h["owner"], "x": h["x"], "y": h["y"],
                 "diameter": h["diameter"], "plated": h["plated"],
                 "pad": h["pad"]}
                for h in board["holes"] if is_mount(h["owner"])]

    poly = outline["polygon"] if outline else None
    parts, z_counts = [], {"declared": 0, "step": 0, "none": 0}
    for fp in board["footprints"]:
        entry, key = part_entry(parts_table, fp["ref"], fp["value"])
        key = "design.py " + key if key else None
        # design.py wins; a footprint field fills only what it leaves unset.
        extra = dict((k, v) for k, v in (fp.get("fields") or {}).items()
                     if entry.get(k) in (None, ""))
        if "height_mm" in extra:
            try:
                extra["height_mm"] = float(extra["height_mm"])
            except ValueError:
                del extra["height_mm"]
        if extra:
            entry = dict(entry, **extra)
            key = "%sfootprint field" % (key + " + " if key else "")
        model = (_model_info(fp, board_path) if use_models
                 else (None, [], None, []))
        obstacle = fp.get("obstacle_above") or fp.get("obstacle_below")
        envelope = _union([(obstacle or {}).get("bbox"), fp.get("body_bbox"),
                           model[2]]) or fp.get("pads_bbox")
        bodies, z_band, z_source = _bodies(fp, entry, key, thickness, model,
                                           envelope)
        kind = inherent_kind(fp)
        if not kind:            # a hole or a fiducial has no body to count
            z_counts["step" if z_source.startswith("step")
                     else "none" if z_source == "none"
                     else "declared"] += 1
        role = entry.get("role")
        if not role and entry.get("interface"):
            role = "connector"
        if not role and entry.get("mating_direction"):
            role = "user_facing"
        basis = connector_basis(fp, entry, kind)
        if basis and not role:
            role = "connector"
        rec = {k: fp[k] for k in ("ref", "value", "lib", "x", "y", "rotation",
                                  "side", "pad_side", "through_hole",
                                  "protrudes", "courtyard", "body_bbox")}
        rec.update({"obstacle": ({"bbox": obstacle["bbox"],
                                  "basis": obstacle["basis"]}
                                 if obstacle else None),
                    "model_bbox": model[2], "envelope": envelope,
                    "bodies": bodies,
                    "z_band": z_band, "z_source": z_source, "role": role,
                    "connector": bool(basis), "connector_basis": basis,
                    "board_inherent": kind,
                    "interface": entry.get("interface"),
                    "access": str(entry.get("access") or "external").lower(),
                    "mating": _mating(fp, entry, key, poly, z_band,
                                      envelope, bodies, thickness)})
        if basis and rec["mating"] is None:
            findings.append({"severity": "FAIL", "ref": fp["ref"],
                             "message": "undeclared mating_direction: a "
                                        "connector (%s) needs "
                                        "mating_direction in design.py PARTS "
                                        "or as a footprint field" % basis})
        if rec["mating"] and rec["mating"].get("verdict") == "FAIL":
            findings.append({"severity": "FAIL", "ref": fp["ref"],
                             "message": rec["mating"]["reason"]})
        # A model on the placement face of a part whose copper is all on the
        # other face is the hotswap-socket case kicad_geom's docstring names:
        # the STEP height is then on the wrong side of the board.
        if (z_band and z_source.startswith("step")
                and fp["pad_side"] in ("top", "bottom")
                and fp["pad_side"] != fp["side"]
                and ((fp["side"] == "top" and z_band[0] >= 0.0)
                     or (fp["side"] == "bottom"
                         and z_band[1] <= -thickness))):
            findings.append({"severity": "WARN", "ref": fp["ref"],
                             "message": "placed %s with every pad on the %s, "
                                        "and its STEP model sits wholly on "
                                        "the %s: declare z_band in design.py "
                                        "or fix the model link"
                                        % (fp["side"], fp["pad_side"],
                                           fp["side"])})
        if role and z_band is None:
            findings.append({"severity": "WARN", "ref": fp["ref"],
                             "message": "%s has no height: declare height_mm "
                                        "in design.py PARTS or link a STEP "
                                        "model" % role})
        parts.append(rec)
    offboard = []
    for key, entry in sorted(parts_table.items()):
        if not isinstance(entry, dict) or not entry.get("offboard"):
            continue
        try:
            recs, problems = offboard_record(key, entry["offboard"], by_ref,
                                             board["footprints"])
        except Exception as exc:                 # a malformed block fails
            recs, problems = [], ["design.py PARTS[%r].offboard: %s: %s"
                                  % (key, type(exc).__name__, exc)]
        for msg in problems:
            findings.append({"severity": "FAIL", "ref": key, "message": msg})
        offboard.extend(recs)
    if z_counts["none"]:
        findings.append({"severity": "WARN", "ref": None,
                         "message": "%d of %d part(s) have no height source "
                                    "(design.py height_mm/z_band or a STEP "
                                    "model): %s"
                                    % (z_counts["none"], sum(z_counts.values()),
                                       ", ".join(p["ref"] for p in parts
                                                 if p["z_band"] is None
                                                 and not p["board_inherent"]
                                                 )[:200])})
    return {"schema": CONTRACT_SCHEMA, "version": CONTRACT_VERSION,
            "source": board_path, "design": design_path, "units": "mm",
            "frame": "board coords: x east, y south, z up; z = 0 is the top "
                     "face, the bottom face is z = -thickness",
            "board": {"thickness": thickness,
                      "thickness_source": thickness_source,
                      "outline": (dict((k, outline[k]) for k in
                                       ("polygon", "bbox", "area", "closed"))
                                  if outline else None),
                      "cutouts": cutouts},
            "mounting_holes": mounting,
            "parts": parts,
            "offboard": offboard,
            "z_sources": z_counts,
            "findings": findings}


def print_contract(contract, out_path):
    b = contract["board"]
    print("--- fit contract: %s -> %s ---" % (contract["source"], out_path))
    if b["outline"]:
        ob = b["outline"]["bbox"]
        print("  outline   %d-point polygon, %s x %s mm, %d cutout(s), "
              "thickness %s (%s)"
              % (len(b["outline"]["polygon"]), fmt(ob[2] - ob[0]),
                 fmt(ob[3] - ob[1]), len(b["cutouts"]), fmt(b["thickness"]),
                 b["thickness_source"]))
    print("  holes     %d mounting hole(s)" % len(contract["mounting_holes"]))
    z = contract["z_sources"]
    print("  heights   %d declared (design.py or footprint field), %d from "
          "STEP models, %d unknown" % (z["declared"], z["step"], z["none"]))
    mating = [p for p in contract["parts"] if p["mating"]]
    for p in mating:
        m = p["mating"]
        print("  %-4s %-8s %-22s %s -> %-6s %s"
              % (m["verdict"], p["ref"], (p["interface"] or p["role"]
                                          or "-")[:22],
                 m["direction_local"], m.get("wall") or "-", m["reason"]))
    for o in contract.get("offboard") or []:
        print("  offboard %-6s %s through %s, axis %s, %d segment(s)%s%s"
              % (o["ref"], o.get("what") or "-", o.get("face") or "-",
                 o.get("axis"), len(o["segments"]),
                 ", datum %s" % o["datum"] if o.get("datum") else "",
                 ", pigtail %.1f mm" % o["pigtail"]["length_mm"]
                 if o.get("pigtail") else ""))
    connectors = [p for p in contract["parts"] if p.get("connector")]
    print("  connectors %d (%s)" % (len(connectors), ", ".join(
        p["ref"] for p in connectors)[:200] or "none on this board"))
    if not mating:
        print("  mating    no part declares a mating_direction (design.py "
              "PARTS)")
    for f in contract["findings"]:
        if f["severity"] == "FAIL" and f["ref"] and any(
                p["ref"] == f["ref"] and p["mating"]
                and p["mating"].get("verdict") == "FAIL"
                for p in contract["parts"]):
            continue                          # already printed above
        print("  %-4s %s%s" % (f["severity"],
                               "%s: " % f["ref"] if f["ref"] else "",
                               f["message"]))
    fails = sum(1 for f in contract["findings"] if f["severity"] == "FAIL")
    print("  verdict   %s" % ("FAIL (%d)" % fails if fails else "PASS"))
    return fails


# ------------------------------------------------------------------- the diff

# Below this, a placement "change" is the file's own 4-decimal rounding.
MOVE_TOL = 1e-4


def _turn(degrees):
    """A rotation delta as the smallest equivalent turn, in (-180, 180].

    Rotation is modular, so a bare subtraction can report a 270 degree change
    for a 90 degree turn.  The sign of a rotation delta is what tells you which
    way a two-terminal part's pads swapped.
    """
    turn = round(degrees, 4) % 360.0
    return round(turn - 360.0 if turn > 180.0 else turn, 4)


def diff_boards(old, new):
    """Placement differences between two parsed boards.

    Keyed on ref, because that is the only stable identity a footprint has
    across a hand edit and a regeneration.  Position is what changed, and the
    KIID (KiCad's per-item unique identifier) is minted fresh on every save;
    see kicad_digest.py.
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
    # component bound is invalidated by that component leaving the face.
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
                  "now merely conservative: the one failure\n              "
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
    print("\n# adopted from %s: %d footprint(s)" % (new["source"], len(rows)))
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
                    help="with --diff, exit 1 if the two boards differ; this "
                         "is the check that verifies a regeneration reproduced "
                         "the placements it adopted")
    ap.add_argument("--contract", metavar="OUT.json",
                    help="write the board-to-enclosure fit contract (schema "
                         "in the module docstring) and exit 1 if a "
                         "connector's mating face does not point out "
                         "through its nearest edge")
    ap.add_argument("--design", metavar="design.py",
                    help="with --contract, the design.py whose PARTS table "
                         "carries mating_direction, height_mm and interface")
    ap.add_argument("--no-models", action="store_true",
                    help="with --contract, do not read STEP models for part "
                         "heights")
    args = ap.parse_args()

    if args.contract:
        if len(args.board) != 1:
            ap.error("--contract takes one board file")
        contract = fit_contract(args.board[0], args.design,
                                use_models=not args.no_models)
        with open(args.contract, "w") as fh:
            json.dump(contract, fh, indent=2, sort_keys=True)
            fh.write("\n")
        if args.json:
            json.dump(contract, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            fails = sum(1 for f in contract["findings"]
                        if f["severity"] == "FAIL")
        else:
            fails = print_contract(contract, args.contract)
        sys.exit(1 if fails else 0)

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
