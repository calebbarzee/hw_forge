#!/usr/bin/env python3
"""Export and verify a populated 3D assembly for mechanical review.

The artifact a case engineer checks the enclosure against: the board plus every
component body, in the board's own coordinate frame.  This is not a fab output.
`kicad_fab.py` produces what a board house sees; nothing here reaches one.

Three subcommands:

  export   kicad-cli pcb export step, with the flags that matter chosen and
           explained rather than defaulted.
  verify   resolve the STEP assembly's occurrence transforms and report where
           every component is actually placed, optionally cross-checked against
           the board's own idea of which face each footprint is on.
  render   the transform-aware pictures.  Reach for these first.

Why `verify` exists
-------------------
A KiCad STEP export is an AP214 **assembly**.  Each unique model's geometry is
written once, in its own local frame; every footprint using it is an instance
carried by a transform chain:

    NEXT_ASSEMBLY_USAGE_OCCURRENCE
      -> PRODUCT_DEFINITION_SHAPE
      -> CONTEXT_DEPENDENT_SHAPE_REPRESENTATION
      -> ITEM_DEFINED_TRANSFORMATION
      -> AXIS2_PLACEMENT_3D

So a `grep CARTESIAN_POINT | min/max` sweep is a **valid** z-extent check for
the board slab and copper, which are baked in as absolute coordinates, and an
**invalid** one for components, which sit at their authoring coordinates until
the chain above places them.  One tool, two questions, one right answer and one
confidently wrong one, in the same file.

The failure signature is that every part appears to sit at z 0..h, on the wrong
face, intersecting the board.  Read that way once on the z_board fixture, it was
reported as a defect and an agent was dispatched to fix a bug that did not
exist.  This subcommand is what that round trip bought.

What `verify` does and does not cover
-------------------------------------
It resolves each occurrence's placement: its origin in board coordinates, its
Z-axis direction, and hence which face it is mounted on.  With `--board` it
cross-checks that face against the footprint's own `IsFlipped()`, which is the
check that catches a genuinely wrong-face model.

It does **not** map each model's local geometry through the transform to give a
placed bounding box.  That needs a per-product geometry walk this does not
attempt.  The renders cover it: a side profile shows a back-face part hanging
below the board immediately, and costs one command.

Python 3 stdlib only for the parsing half, so `verify` runs on a STEP file with
no KiCad present.  `--board` shells out to KiCad's bundled interpreter.
"""

import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _kicad_env import (cli_version, find_cli, find_python,  # noqa: E402
                        run, strip_wx_noise)

# Occurrence names KiCad writes for its own internal assembly bookkeeping
# rather than for a placed footprint.  They are not components and counting
# them inflates every total.
BOOKKEEPING = re.compile(r"^=>\[")

# The two flag sets, named so the choice is a decision and not a default.
#
# Copper costs roughly 6x the file size (27 MB against 4 MB on the z_board
# combo) and an enclosure check does not need it: the board slab and the
# component bodies are what a wall or a floor can foul.  Ask for it when the
# question is about the board itself.
COPPER_FLAGS = ["--include-tracks", "--include-pads", "--include-zones",
                "--include-inner-copper"]


# --------------------------------------------------------------- STEP parsing

def parse_entities(text):
    """`{id: (type, argstring)}` for every `#N = TYPE(...);` in a STEP file.

    Entity bodies wrap across lines freely, and a complex entity is a
    parenthesised run of several types, so this splits on the `;` terminator
    rather than on newlines.
    """
    body = text.split("DATA;", 1)[-1].split("ENDSEC;", 1)[0]
    out = {}
    for chunk in body.split(";"):
        chunk = chunk.strip()
        if not chunk.startswith("#"):
            continue
        head, _, rest = chunk.partition("=")
        try:
            ident = int(head.strip()[1:])
        except ValueError:
            continue
        rest = rest.strip()
        if rest.startswith("("):                 # complex entity
            out[ident] = ("_COMPLEX", rest)
            continue
        m = re.match(r"([A-Z_0-9]+)\s*\((.*)\)\s*$", rest, re.S)
        if m:
            out[ident] = (m.group(1), m.group(2))
    return out


def refs(argstring):
    """Every `#N` appearing in an argument string, in order."""
    return [int(x) for x in re.findall(r"#(\d+)", argstring)]


def strings(argstring):
    """Every single-quoted literal in an argument string, in order."""
    return re.findall(r"'((?:[^']|'')*)'", argstring)


def triple(entities, ident):
    """The three floats of a CARTESIAN_POINT or DIRECTION."""
    args = entities[ident][1]
    nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", args.split("(", 1)[-1])
    return tuple(float(n) for n in nums[:3])


# ------------------------------------------------------------- transform math

def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v) if n else v


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def placement_matrix(entities, ident):
    """AXIS2_PLACEMENT_3D -> (3x3 rotation as row tuples, origin).

    The entity gives an origin, a Z direction (`axis`) and an X direction
    (`ref_direction`).  X is orthogonalised against Z, and Y is their cross
    product, which is what makes a mirrored instance readable: KiCad flips a
    back-face part by pointing Z at -1, and the handedness follows.
    """
    args = entities[ident][1]
    r = refs(args)
    origin = triple(entities, r[0])
    z = _norm(triple(entities, r[1])) if len(r) > 1 else (0.0, 0.0, 1.0)
    x = _norm(triple(entities, r[2])) if len(r) > 2 else (1.0, 0.0, 0.0)
    d = sum(a * b for a, b in zip(x, z))
    x = _norm(tuple(xi - d * zi for xi, zi in zip(x, z)))
    y = _cross(z, x)
    # columns are the basis vectors, so rows are what a point multiplies through
    rot = ((x[0], y[0], z[0]),
           (x[1], y[1], z[1]),
           (x[2], y[2], z[2]))
    return rot, origin


def compose_inverse(rot_a, org_a, rot_b, org_b):
    """The rigid transform taking frame A onto frame B: B * A^-1.

    In practice KiCad makes A the identity placement at the origin and puts the
    whole placement in B, so this reduces to B.  Composing properly anyway costs
    nothing and means a file that does not follow that habit still reads right.
    """
    # A is orthonormal, so its inverse rotation is its transpose.
    inv_a = tuple(zip(*rot_a))
    inv_org = tuple(-sum(inv_a[i][k] * org_a[k] for k in range(3))
                    for i in range(3))
    rot = tuple(tuple(sum(rot_b[i][k] * inv_a[k][j] for k in range(3))
                      for j in range(3)) for i in range(3))
    org = tuple(sum(rot_b[i][k] * inv_org[k] for k in range(3)) + org_b[i]
                for i in range(3))
    return rot, org


# ---------------------------------------------------------------- occurrences

def occurrences(entities):
    """One record per placed component instance.

    Walks CONTEXT_DEPENDENT_SHAPE_REPRESENTATION, which is the only entity that
    ties a placement to the occurrence it belongs to.
    """
    # index the reverse links we need
    nauo_of_pds = {}
    for ident, (kind, args) in entities.items():
        if kind == "PRODUCT_DEFINITION_SHAPE":
            r = refs(args)
            if r:
                nauo_of_pds[ident] = r[0]

    out = []
    for ident, (kind, args) in entities.items():
        if kind != "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION":
            continue
        r = refs(args)
        if len(r) < 2:
            continue
        rr_id, pds_id = r[0], r[1]
        nauo_id = nauo_of_pds.get(pds_id)
        if nauo_id is None or entities.get(nauo_id, ("", ""))[0] != \
                "NEXT_ASSEMBLY_USAGE_OCCURRENCE":
            continue
        nauo_args = entities[nauo_id][1]
        names = strings(nauo_args)
        label = names[1] if len(names) > 1 else ""

        # the transform lives in the complex REPRESENTATION_RELATIONSHIP
        rr_args = entities.get(rr_id, ("", ""))[1]
        m = re.search(r"REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION\s*\(\s*#(\d+)",
                      rr_args)
        if not m:
            continue
        idt = int(m.group(1))
        ax = refs(entities[idt][1])
        if len(ax) < 2:
            continue
        rot_a, org_a = placement_matrix(entities, ax[0])
        rot_b, org_b = placement_matrix(entities, ax[1])
        rot, org = compose_inverse(rot_a, org_a, rot_b, org_b)

        # the product this instance is an instance OF
        child = refs(nauo_args)[-1] if refs(nauo_args) else None
        product = product_name(entities, child)

        out.append({
            "label": label,
            "product": product,
            "origin": [round(c, 4) for c in org],
            "z_axis": [round(rot[i][2], 6) for i in range(3)],
            "face": "back" if rot[2][2] < 0 else "front",
            "bookkeeping": bool(BOOKKEEPING.match(label)),
        })
    out.sort(key=lambda o: (o["bookkeeping"], o["label"]))
    return out


def product_name(entities, product_definition):
    """PRODUCT_DEFINITION -> PRODUCT_DEFINITION_FORMATION -> PRODUCT name."""
    try:
        pdf = refs(entities[product_definition][1])[0]
        prod = refs(entities[pdf][1])[0]
        return strings(entities[prod][1])[0]
    except (KeyError, IndexError):
        return ""


# --------------------------------------------------------- board-side lookup

FACE_PROBE = r"""
import json, sys, pcbnew
bd = pcbnew.LoadBoard(sys.argv[1])
out = {}
for f in bd.GetFootprints():
    out[f.GetReference()] = "back" if f.IsFlipped() else "front"
print(json.dumps(out))
"""


def board_faces(board, python):
    """`{reference: 'front'|'back'}` read from the board itself."""
    proc = run([python, "-c", FACE_PROBE, board])
    if proc.returncode != 0:
        raise SystemExit("error: could not read %s\n  %s"
                         % (board, (proc.stderr or "").strip().splitlines()[-1:]))
    for line in strip_wx_noise(proc.stdout).splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise SystemExit("error: face probe produced no output for %s" % board)


# ------------------------------------------------------------------ subcommands

def cmd_export(args):
    cli, how = require_cli()
    # KiCad 10.0.5's `pcb export step` has no origin option: it always writes
    # the board's own frame, negating y.  That is what an enclosure generator
    # keeping board x and negating y already agrees with, so x and y need no
    # adjustment downstream and only the z datum differs.  Checked against
    # `kicad-cli pcb export step --help`; do not add an origin flag on the
    # assumption that one exists.
    argv = [cli, "pcb", "export", "step", "-o", args.out]
    if args.with_copper:
        argv += COPPER_FLAGS
    argv += [args.board]
    proc = run(argv)
    missing = [l for l in strip_wx_noise(proc.stderr or "").splitlines()
               if "Could not add 3D model" in l or "File not found" in l]
    for line in (strip_wx_noise(proc.stdout) or "").splitlines():
        if line.strip():
            print("  " + line.strip())
    if proc.returncode != 0:
        print(strip_wx_noise(proc.stderr or ""), file=sys.stderr)
        raise SystemExit("error: export failed (kicad-cli via %s)" % how)
    size = os.path.getsize(args.out) if os.path.exists(args.out) else 0
    print("  wrote %s  %.1f MB  (%s)"
          % (args.out, size / 1e6,
             "with copper" if args.with_copper else "geometry only"))
    # A missing model is non-fatal to kicad-cli: the part simply exports with no
    # body, and the export otherwise looks complete.  Say so out loud.
    if missing:
        print("  %d footprint(s) exported with NO body:" % len(missing))
        for line in missing:
            print("     " + line.strip())
        print("  a missing model is a warning, not a failure. The assembly is "
              "incomplete where it matters mechanically.")
    return 0


def cmd_verify(args):
    entities = parse_entities(open(args.step, errors="replace").read())
    occ = [o for o in occurrences(entities) if not o["bookkeeping"]]
    skipped = sum(1 for o in occurrences(entities) if o["bookkeeping"])

    front = [o for o in occ if o["face"] == "front"]
    back = [o for o in occ if o["face"] == "back"]

    failures = []
    opposite = []
    if args.board:
        python, how = find_python()
        if not python:
            raise SystemExit("error: no python that can import pcbnew (%s)\n"
                             "  fix: python3 scripts/preflight.py" % how)
        faces = board_faces(args.board, python)
        # One footprint may legitimately carry several models, and one of them
        # may sit on the opposite face on purpose: a keyswitch inserted from the
        # far side into a socket soldered on this one is the standard case.  So
        # the failure condition is not "some model faces the other way", it is
        # "NO model for this footprint is on the face the board says".  Getting
        # that wrong turns 22 correct switches into 22 red lines.
        by_ref = {}
        for o in occ:
            want = faces.get(o["label"])
            if want is None:
                continue
            o["board_face"] = want
            by_ref.setdefault(o["label"], []).append(o)
        for _ref, group in sorted(by_ref.items()):
            want = group[0]["board_face"]
            if not any(o["face"] == want for o in group):
                failures.extend(group)
            else:
                for o in group:
                    if o["face"] != want:
                        opposite.append(o)

    if args.json:
        print(json.dumps({"occurrences": occ, "front": len(front),
                          "back": len(back), "mismatches": len(failures),
                          "opposite_face": len(opposite)}, indent=2))
    else:
        print("%s" % args.step)
        print("  occurrences   %d  (front %d, back %d)"
              % (len(occ), len(front), len(back)))
        if skipped:
            print("  bookkeeping   %d internal entries skipped" % skipped)
        for face, group in (("front", front), ("back", back)):
            if not group:
                continue
            zs = sorted({o["origin"][2] for o in group})
            print("  %-5s origin z  %s"
                  % (face, ", ".join("%.3f" % z for z in zs[:6])
                     + (" ..." if len(zs) > 6 else "")))
        if args.verbose:
            print("  %-10s %-28s %-26s %s"
                  % ("ref", "product", "origin", "face"))
            for o in occ:
                print("  %-10s %-28s (%8.3f, %8.3f, %7.3f)  %s"
                      % (o["label"][:10], o["product"][:28],
                         o["origin"][0], o["origin"][1], o["origin"][2],
                         o["face"]))
        if args.board:
            if opposite:
                refs_seen = sorted({o["label"] for o in opposite})
                print("  opposite-face models  %d on %d footprint(s): %s"
                      % (len(opposite), len(refs_seen),
                         ", ".join(refs_seen[:6])
                         + (" ..." if len(refs_seen) > 6 else "")))
                print("  that is the insert-from-the-far-side pattern, not a "
                      "fault. Each of these footprints also has a model on the "
                      "face the board says.")
            if failures:
                print("  FAIL: %d footprint(s) have NO model on the board's face"
                      % len({o["label"] for o in failures}))
                for o in failures:
                    print("     %-10s %-24s step says %-5s, board says %s"
                          % (o["label"], o["product"][:24], o["face"],
                             o["board_face"]))
            else:
                print("  face cross-check ok against %s"
                      % os.path.basename(args.board))
    return 1 if failures else 0


def cmd_render(args):
    cli, how = require_cli()
    os.makedirs(args.out, exist_ok=True)
    made = []
    for side in args.views.split(","):
        side = side.strip()
        if not side:
            continue
        path = os.path.join(args.out, "%s_%s.png"
                            % (os.path.splitext(os.path.basename(args.board))[0],
                               side))
        proc = run([cli, "pcb", "render", "-o", path, "--side", side,
                    "-w", str(args.width), "--height", str(args.height),
                    "--zoom", str(args.zoom), "--background", "opaque",
                    "--quality", args.quality, args.board])
        if proc.returncode != 0:
            print(strip_wx_noise(proc.stderr or ""), file=sys.stderr)
            raise SystemExit("error: render failed (kicad-cli via %s)" % how)
        made.append(path)
    for path in made:
        print("  %-52s %8d" % (path, os.path.getsize(path)))
    print("  a side view is the cheapest proof of placement: back-face parts "
          "hang below the board, front-face parts stand above it.")
    return 0


def require_cli():
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
    return cli, how


def main():
    ap = argparse.ArgumentParser(
        description="Export and verify a populated 3D assembly for "
                    "mechanical review.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="export a populated 3D assembly")
    e.add_argument("board")
    e.add_argument("-o", "--out", required=True, help="output .step path")
    e.add_argument("--with-copper", action="store_true",
                   help="include tracks, pads, zones and inner copper "
                        "(roughly 6x the file size; an enclosure check does "
                        "not need it)")
    e.set_defaults(func=cmd_export)

    v = sub.add_parser("verify", help="resolve occurrence transforms")
    v.add_argument("step")
    v.add_argument("--board", help="cross-check each occurrence's face "
                                   "against this .kicad_pcb")
    v.add_argument("--verbose", action="store_true",
                   help="list every occurrence")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_verify)

    r = sub.add_parser("render", help="transform-aware views")
    r.add_argument("board")
    r.add_argument("-o", "--out", required=True, help="output directory")
    r.add_argument("--views", default="top,bottom,left",
                   help="comma list of kicad-cli --side values "
                        "(default: top,bottom,left)")
    r.add_argument("--width", type=int, default=1600)
    r.add_argument("--height", type=int, default=1200)
    r.add_argument("--zoom", type=float, default=1.4)
    r.add_argument("--quality", default="high")
    r.set_defaults(func=cmd_render)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
