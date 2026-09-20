#!/usr/bin/env python3
"""Fork a stock footprint into a project library, and edit the fork.

A datasheet check or a physical measurement (`kicad_fpcheck.py`) produces a
fact about a footprint's geometry. A knowledge-base card can record that fact,
but a card changes nothing about what gets fabbed. This script is the other
half: the mechanism that moves a finding into the file KiCad actually builds
from, the same way a resolved 3D model moves into `kicad/lib/3dmodels/` and a
footprint's `(model ...)` line rather than staying a note. See
`kb/README.md`'s "where a fact lives" table for the full doctrine.

    python3 scripts/kicad_fplib.py fork Diode_SMD:D_SOD-123 \\
        --into kicad/lib/myproj.pretty --as D_SOD-123_myproj
    python3 scripts/kicad_fplib.py set-pads kicad/lib/myproj.pretty/D_SOD-123_myproj.kicad_mod \\
        --size 0.70x1.00 --all
    python3 scripts/kicad_fplib.py set-model FP.kicad_mod \\
        --model '${KIPRJMOD}/../lib/3dmodels/part.step' --rotate 0,0,-90
    python3 scripts/kicad_fplib.py annotate FP.kicad_mod \\
        --source https://example.com/datasheet.pdf --note "pads shrunk 0.20mm/side, gap was tight against body"
    python3 scripts/kicad_fplib.py diff OLD.kicad_mod NEW.kicad_mod
    python3 scripts/kicad_fplib.py provenance-row FP.kicad_mod

Five subcommands: `fork` copies a stock footprint into a project `.pretty`
directory; `set-pads` and `set-model` apply the change a check called for;
`annotate` records the source and the change in the footprint's own fields,
so the footprint is self-documenting even if `lib/PROVENANCE.md` is lost;
`diff` and `provenance-row` are read-only reporting.

Runs under system python3, stdlib only. Imports `kicad_geom.py`'s
s-expression parser and `kicad_fpcheck.py`'s pad-measurement functions
(same directory) rather than re-implementing either.

Why every mutation is a text substitution, not a re-serialise
---------------------------------------------------------------
A generic s-expression serialiser was considered and rejected. KiCad writes
`.kicad_mod` files with tab indentation and a specific key order that this
script has no reason to reproduce byte-for-byte, and a footprint that has
round-tripped through a generic serialiser is a bigger diff for a human or
`git blame` to read than the two-line change that actually happened.

So every write here is a *targeted* substitution on one balanced
s-expression block, never a blind regex over the whole file:

  1. parse the file (`kicad_geom.parse`) to decide WHICH block to touch: the
     third pad, the `(model ...)` block, `(descr ...)`, `(tags ...)`;
  2. re-locate that same block's exact character span in the RAW text, by
     scanning for a balanced-parens block starting at the matching
     `(head ...` token, in file order. Pads never nest inside pads, and a
     model never nests inside a model, so this is exact, not a heuristic;
  3. splice in new text for that span only, re-parse the RESULT to prove it
     is still a valid, well-formed footprint, and only then write it.

Every mutating command re-parses its own output afterwards and runs the same
pad extraction `kicad_fpcheck.py` uses (`footprint_pads` / `measure`),
printing the before and after numbers. A `set-model` or `annotate` call
whose "before" and "after" pad numbers differ is a bug in this script, not an
intended effect, and the printed line is what would catch it.

What this script does not do
-----------------------------
It does not decide whether a footprint is wrong. That is `kicad_fpcheck.py`
and a human reading a datasheet. This script is the write path once a
decision is made: fork, edit, prove the edit did what it says, record why.
"""

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_geom      # noqa: E402  s-expression parser, reused, never redone
import kicad_fpcheck    # noqa: E402  pad extraction / measurement, reused
import _kicad_env       # noqa: E402  KiCad install discovery, same as preflight.py

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACKAGES = os.path.join(HERE, "packages.json")


# --------------------------------------------------------------- text editing

def read_text(path):
    with open(path) as fh:
        return fh.read()


def write_text(path, text):
    with open(path, "w") as fh:
        fh.write(text)


def block_span(text, start):
    """(start, end) of the balanced-parens block beginning at text[start].

    Mirrors kicad_geom.tokenize's own quoting rules (a quoted string's own
    parens do not count, and a backslash escapes the next character) so a
    `)` or `(` inside a quoted path or note is never mistaken for structure.
    """
    if text[start] != "(":
        raise ValueError("block_span must start on '(' (got %r)" % text[start])
    depth, i, n, in_str = 0, start, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return start, i + 1
        i += 1
    raise ValueError("unbalanced parens from offset %d" % start)


def find_blocks(text, head, region=None):
    """[(start, end), ...] for every top-level "(head ..." block, in order.

    A sequential scan that jumps to the end of each match before searching
    for the next. Exact rather than a heuristic, because none of the heads
    this script looks for (pad, model, descr, tags) ever nest inside a block
    with the same head.
    """
    lo, hi = region or (0, len(text))
    pattern = re.compile(r"\(%s(?=[\s)])" % re.escape(head))
    spans, cursor = [], lo
    while True:
        m = pattern.search(text, cursor, hi)
        if not m:
            break
        span = block_span(text, m.start())
        spans.append(span)
        cursor = span[1]
    return spans


def root_span(text):
    """The whole file's outermost block."""
    return block_span(text, text.index("("))


def replace_span(text, span, new_block):
    return text[:span[0]] + new_block + text[span[1]:]


def insert_before_root_close(text, block_text):
    """Splice `block_text` in as the last child of the file's root block."""
    _, end = root_span(text)
    insert_pos = end - 1                       # the root's own closing ')'
    return text[:insert_pos] + block_text + "\n" + text[insert_pos:]


def detect_indent(text):
    """The whitespace this file uses for one nesting level.

    Read off the first indented line rather than assumed: a hand-edited or
    foreign-tool-written footprint may use spaces instead of KiCad's tabs.
    """
    m = re.search(r"\n([ \t]+)\(", text)
    return m.group(1) if m else "\t"


def fnum(v):
    """A float formatted the way KiCad writes one: trimmed, never '-0'."""
    text = ("%.4f" % v).rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def verify_and_write(path, new_text):
    """Re-parse `new_text` as a footprint before writing it; refuse if not."""
    try:
        root = kicad_geom.parse(new_text)
    except Exception as exc:
        raise SystemExit("error: this edit produced invalid s-expression "
                         "syntax, nothing was written: %s" % exc)
    if not root or root[0] != "footprint":
        raise SystemExit("error: this edit corrupted the footprint root, "
                         "nothing was written (root is %r)"
                         % (root[0] if root else None))
    write_text(path, new_text)


# ------------------------------------------------------------------ measuring

def measure_text(text):
    """The same {pad_count, span_long, span_short, pitch, gap} kicad_fpcheck
    prints, computed by calling its own footprint_pads()/measure(), never a
    re-derivation."""
    root = kicad_geom.parse(text)
    pads = kicad_fpcheck.footprint_pads(root)
    if not pads:
        return None
    lead_pads, _ep = kicad_fpcheck.exclude_exposed_pad(pads)
    return kicad_fpcheck.measure(lead_pads) if lead_pads else None


def fmt_measure(m):
    if not m:
        return "no copper pads"
    return ("pads=%d span=%s/%s pitch=%s gap=%s"
           % (m["pad_count"], m["span_long"], m["span_short"],
              m["pitch"] if m["pitch"] is not None else "-",
              m["gap"] if m["gap"] is not None else "-"))


def report_before_after(old_text, new_text):
    before, after = measure_text(old_text), measure_text(new_text)
    print("  before  %s" % fmt_measure(before))
    print("  after   %s" % fmt_measure(after))


# ------------------------------------------------------------- stock library

def footprint_roots():
    """Directories holding *.pretty libraries, KiCad's own install first.

    Same discovery `preflight.py`'s `model_roots()` uses for the 3D-model
    tree, generalised to footprints: KICAD_ROOT if set, then the platform's
    default install root, checked against both the macOS SharedSupport
    layout and the Linux share/kicad layout.
    """
    roots = []
    env_root = os.environ.get("KICAD_ROOT")
    bases = [env_root] if env_root else []
    bases += list(_kicad_env.default_roots())
    for base in bases:
        for rel in (os.path.join("SharedSupport", "footprints"),
                    os.path.join("share", "kicad", "footprints")):
            path = os.path.join(base, rel)
            if os.path.isdir(path):
                roots.append(path)
    return roots


def split_libname(spec):
    if ":" not in spec:
        raise SystemExit("error: expected LIB:NAME (e.g. "
                         "Diode_SMD:D_SOD-123), got %r" % spec)
    lib, name = spec.split(":", 1)
    return lib, name


def resolve_stock_footprint(lib, name):
    for root in footprint_roots():
        candidate = os.path.join(root, lib + ".pretty", name + ".kicad_mod")
        if os.path.exists(candidate):
            return candidate
    return None


# --------------------------------------------------------------------- fork

def cmd_fork(args):
    lib, name = split_libname(args.libname)
    src = resolve_stock_footprint(lib, name)
    if not src:
        roots = footprint_roots()
        raise SystemExit(
            "error: %s:%s not found under any discovered KiCad footprint "
            "root (%s). Set KICAD_ROOT, or vendor the stock .pretty "
            "directory yourself and pass its path."
            % (lib, name, "; ".join(roots) if roots else "none found"))

    newname = args.as_name or name
    os.makedirs(args.into, exist_ok=True)
    dest = os.path.join(args.into, newname + ".kicad_mod")
    if os.path.exists(dest) and not args.force:
        raise SystemExit("error: %s already exists (--force to overwrite)"
                         % dest)

    src_text = read_text(src)
    new_text = src_text
    if args.as_name and args.as_name != name:
        # Rename ONLY the footprint's own declared name -- the header's
        # first quoted string -- never every occurrence of the old name in
        # the file, which would also hit unrelated text that happens to
        # share it (a Value property, a datasheet URL).
        m = re.match(r'(\(footprint\s+)"%s"' % re.escape(name), new_text)
        if not m:
            raise SystemExit(
                "error: could not find the header (footprint \"%s\" ...) "
                "to rename -- inspect %s by hand" % (name, src))
        new_text = new_text[:m.end(1)] + '"%s"' % newname + new_text[m.end():]

    verify_and_write(dest, new_text)
    print("forked %s:%s -> %s" % (lib, name, dest))
    report_before_after(src_text, new_text)


# ----------------------------------------------------------------- set-pads

def parse_wh(spec):
    m = re.match(r"^\s*([-\d.]+)\s*x\s*([-\d.]+)\s*$", spec, re.I)
    if not m:
        raise SystemExit("error: --size wants WxH in mm, e.g. 0.70x1.00, "
                         "got %r" % spec)
    return float(m.group(1)), float(m.group(2))


def parse_at_args(items):
    out = {}
    for item in items or ():
        m = re.match(r"^\s*([^=]+?)\s*=\s*([-\d.]+)\s*,\s*([-\d.]+)\s*$", item)
        if not m:
            raise SystemExit("error: --at wants PADNUM=X,Y, got %r" % item)
        out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return out


def pad_number_of(block_text):
    node = kicad_geom.parse(block_text)
    atoms = kicad_geom.atoms(node)
    return atoms[1] if len(atoms) > 1 else None


def cmd_set_pads(args):
    old_text = read_text(args.footprint)
    at_targets = parse_at_args(args.at)
    size = parse_wh(args.size) if args.size else None
    if size and not args.all and not at_targets:
        raise SystemExit(
            "error: --size needs --all (every pad) or --at PADNUM=X,Y "
            "(named pads) to say which pads it applies to")
    size_targets = "all" if (size and args.all) else \
        (set(at_targets) if size else None)

    spans = find_blocks(old_text, "pad")
    if not spans:
        raise SystemExit("error: no (pad ...) blocks found in %s"
                         % args.footprint)

    seen, edits = set(), []
    for start, end in spans:
        block = old_text[start:end]
        number = pad_number_of(block)
        seen.add(number)
        changed = block
        if number in at_targets:
            x, y = at_targets[number]
            new_block = re.sub(
                r"\(at\s+[-\d.]+\s+[-\d.]+((?:\s+[-\d.]+)?)\)",
                lambda m: "(at %s %s%s)" % (fnum(x), fnum(y), m.group(1)),
                changed, count=1)
            if new_block == changed:
                raise SystemExit("error: pad %r has no (at ...) to rewrite "
                                 "in %s" % (number, args.footprint))
            changed = new_block
        if size_targets == "all" or (isinstance(size_targets, set)
                                     and number in size_targets):
            w, h = size
            new_block = re.sub(
                r"\(size\s+[-\d.]+\s+[-\d.]+\)",
                "(size %s %s)" % (fnum(w), fnum(h)), changed, count=1)
            if new_block == changed:
                raise SystemExit("error: pad %r has no (size ...) to "
                                 "rewrite in %s" % (number, args.footprint))
            changed = new_block
        if changed != block:
            edits.append((start, end, changed))

    missing_at = set(at_targets) - seen
    if missing_at:
        raise SystemExit("error: --at names pad(s) not in %s: %s"
                         % (args.footprint, sorted(missing_at)))
    if isinstance(size_targets, set):
        missing_size = size_targets - seen
        if missing_size:
            raise SystemExit("error: --size --at names pad(s) not in %s: %s"
                             % (args.footprint, sorted(missing_size)))

    new_text = old_text
    for start, end, changed in sorted(edits, key=lambda e: -e[0]):
        new_text = new_text[:start] + changed + new_text[end:]

    verify_and_write(args.footprint, new_text)
    print("%s: %d pad(s) edited" % (args.footprint, len(edits)))
    report_before_after(old_text, new_text)


# ---------------------------------------------------------------- set-model

def parse_xyz(spec):
    parts = spec.split(",")
    if len(parts) != 3:
        raise SystemExit("error: expected x,y,z, got %r" % spec)
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        raise SystemExit("error: x,y,z must be numbers, got %r" % spec)


def build_model_block(indent_unit, level, model_path, offset, rotate):
    """A `(model ...)` block matching KiCad's own indentation and field
    order, ${KIPRJMOD}-anchored path convention as read (see
    references/kicad-api.md §9 for the offset/rotate sign conventions --
    this script does not guess a sign, it only writes the numbers given).

    Returned WITHOUT leading indentation on its own opening line: a replace
    splices this in right after the ORIGINAL block's own leading whitespace
    (untouched text, not part of the matched span), so a block meant for
    that use must not add a second copy of it. `level` still controls every
    inner line and the closing paren. Callers inserting a brand new block
    (no existing one to replace) must prepend their own `indent_unit *
    level` before this string.
    """
    p1, p2 = indent_unit * (level + 1), indent_unit * (level + 2)
    p0 = indent_unit * level

    def xyz(name, v):
        return ("%s(%s\n%s(xyz %s %s %s)\n%s)\n"
               % (p1, name, p2, fnum(v[0]), fnum(v[1]), fnum(v[2]), p1))

    return ('(model "%s"\n' % model_path
           + xyz("offset", offset)
           + xyz("scale", (1.0, 1.0, 1.0))
           + xyz("rotate", rotate)
           + p0 + ")")


def cmd_set_model(args):
    old_text = read_text(args.footprint)
    indent = detect_indent(old_text)
    offset = parse_xyz(args.offset) if args.offset else (0.0, 0.0, 0.0)
    rotate = parse_xyz(args.rotate) if args.rotate else (0.0, 0.0, 0.0)
    body = build_model_block(indent, 1, args.model, offset, rotate)

    spans = find_blocks(old_text, "model")
    if spans:
        if len(spans) > 1:
            print("warning: %d (model ...) blocks found; replacing only the "
                  "first. A footprint may deliberately carry more than one "
                  "(an opposite-face model, kicad-api.md sec 9) -- check the "
                  "rest by hand." % len(spans), file=sys.stderr)
        new_text = replace_span(old_text, spans[0], body)
        action = "replaced"
    else:
        new_text = insert_before_root_close(old_text, indent + body)
        action = "attached"

    verify_and_write(args.footprint, new_text)
    print("%s: (model ...) %s -> %s" % (args.footprint, action, args.model))
    report_before_after(old_text, new_text)


# ----------------------------------------------------------------- annotate

def string_value_of(text, span):
    node = kicad_geom.parse(text[span[0]:span[1]])
    atoms = kicad_geom.atoms(node)
    return atoms[1] if len(atoms) > 1 else ""


def rebuild_string_field(head, value):
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '(%s "%s")' % (head, escaped)


def cmd_annotate(args):
    old_text = read_text(args.footprint)
    today = datetime.date.today().isoformat()

    descr_spans = find_blocks(old_text, "descr")
    tags_spans = find_blocks(old_text, "tags")
    if not descr_spans or not tags_spans:
        raise SystemExit(
            "error: %s has no (descr ...) / (tags ...) field to annotate -- "
            "this only edits a stock KiCad-format footprint" % args.footprint)

    old_descr = string_value_of(old_text, descr_spans[0])
    old_tags = string_value_of(old_text, tags_spans[0])

    stamp = ("hw_forge fork: %s (source: %s, %s)"
            % (args.note, args.source, today))
    new_descr = ("%s -- %s" % (old_descr, stamp)) if old_descr else stamp
    tag_word = "hw_forge-fork"
    new_tags = old_tags if tag_word in old_tags.split() else \
        ("%s %s" % (old_tags, tag_word)).strip()

    edits = [(descr_spans[0], rebuild_string_field("descr", new_descr)),
            (tags_spans[0], rebuild_string_field("tags", new_tags))]
    new_text = old_text
    for span, block in sorted(edits, key=lambda e: -e[0][0]):
        new_text = new_text[:span[0]] + block + new_text[span[1]:]

    verify_and_write(args.footprint, new_text)
    print("%s: annotated" % args.footprint)
    print("  descr  %r" % new_descr)
    print("  tags   %r" % new_tags)
    report_before_after(old_text, new_text)


# --------------------------------------------------------------------- diff

def cmd_diff(args):
    root_a, root_b = kicad_geom.parse_file(args.a), kicad_geom.parse_file(args.b)
    for path, root in ((args.a, root_a), (args.b, root_b)):
        if not root or root[0] != "footprint":
            raise SystemExit("error: %s is not a single .kicad_mod (root "
                             "is %r)" % (path, root[0] if root else None))

    pads_a = {p["number"]: p for p in kicad_fpcheck.footprint_pads(root_a)}
    pads_b = {p["number"]: p for p in kicad_fpcheck.footprint_pads(root_b)}

    print("--- pad diff: %s -> %s ---" % (args.a, args.b))
    numbers = sorted(set(pads_a) | set(pads_b),
                     key=lambda n: (len(n or ""), n or ""))
    changed = 0
    for number in numbers:
        a, b = pads_a.get(number), pads_b.get(number)
        if a is None:
            print("  + pad %-4s added    bbox=%s" % (number, b["bbox"]))
            changed += 1
            continue
        if b is None:
            print("  - pad %-4s removed  bbox=%s" % (number, a["bbox"]))
            changed += 1
            continue
        if a["bbox"] == b["bbox"]:
            continue
        wa, ha = a["bbox"][2] - a["bbox"][0], a["bbox"][3] - a["bbox"][1]
        wb, hb = b["bbox"][2] - b["bbox"][0], b["bbox"][3] - b["bbox"][1]
        print("  ~ pad %-4s size %.4gx%.4g -> %.4gx%.4g  (%+.4g, %+.4g)"
              % (number, wa, ha, wb, hb, wb - wa, hb - ha))
        changed += 1

    lead_a, _ = kicad_fpcheck.exclude_exposed_pad(list(pads_a.values()))
    lead_b, _ = kicad_fpcheck.exclude_exposed_pad(list(pads_b.values()))
    ma = kicad_fpcheck.measure(lead_a) if lead_a else None
    mb = kicad_fpcheck.measure(lead_b) if lead_b else None
    print("  summary  %s -> %s" % (fmt_measure(ma), fmt_measure(mb)))
    if not changed:
        print("  no pad differences (%d pads)" % len(pads_a))


# ------------------------------------------------------------ provenance-row

_STAMP_RE = re.compile(
    r"hw_forge fork: (?P<note>.*?) \(source: (?P<source>.*?), "
    r"(?P<date>\d{4}-\d{2}-\d{2})\)")


def cmd_provenance_row(args):
    text = read_text(args.footprint)
    root = kicad_geom.parse(text)
    if not root or root[0] != "footprint":
        raise SystemExit("error: %s is not a single .kicad_mod"
                         % args.footprint)
    atoms = kicad_geom.atoms(root)
    fp_name = atoms[1] if len(atoms) > 1 else "?"

    descr_spans = find_blocks(text, "descr")
    descr = string_value_of(text, descr_spans[0]) if descr_spans else ""

    m = _STAMP_RE.search(descr)
    note = m.group("note") if m else "(not annotated -- run `annotate` first)"
    source = m.group("source") if m else "?"
    date = m.group("date") if m else "?"

    pads = kicad_fpcheck.footprint_pads(root)
    lead_pads, _ep = kicad_fpcheck.exclude_exposed_pad(pads)
    meas = kicad_fpcheck.measure(lead_pads) if lead_pads else None

    table = kicad_fpcheck.load_packages(args.packages)
    family = kicad_fpcheck.heuristic_family(fp_name, table)
    entry = table.get(family) if family else None

    dims = "-"
    if meas:
        if entry and entry.get("gap_check"):
            dims = ("pad outer span %s/%s mm, pad inner gap %s mm"
                    % (meas["span_long"], meas["span_short"], meas["gap"]))
        else:
            dims = ("pad outer span %s/%s mm, pad pitch %s mm"
                    % (meas["span_long"], meas["span_short"], meas["pitch"]))

    print("| Asset | Source | Version | License | Date | Verified against | "
         "Modifications |")
    print("|---|---|---|---|---|---|---|")
    print("| `%s` (footprint `%s`) | %s | fork of a stock KiCad footprint | "
         "TODO: license, same as the stock library's unless stated "
         "otherwise | %s | `kicad_fpcheck.py`: %s -- family %s, %s | %s |"
         % (os.path.basename(args.footprint), fp_name, source, date,
            fmt_measure(meas), family or "unresolved (add a packages.json "
            "alias)", dims, note))


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="Fork a stock footprint into a project library, and "
                    "edit the fork -- the path from a kicad_fpcheck.py "
                    "finding to a fabbed change.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fork", help="copy a stock footprint into a project "
                                    ".pretty library")
    p.add_argument("libname", metavar="LIB:NAME")
    p.add_argument("--into", required=True, metavar="DIR",
                   help="destination .pretty directory (created if needed)")
    p.add_argument("--as", dest="as_name", metavar="NEWNAME",
                   help="rename the forked footprint (default: keep NAME)")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing file at the destination")
    p.set_defaults(func=cmd_fork)

    p = sub.add_parser("set-pads", help="resize or reposition named pads")
    p.add_argument("footprint")
    p.add_argument("--size", metavar="WxH", help="new pad size in mm")
    p.add_argument("--at", action="append", default=[], metavar="PADNUM=X,Y",
                   help="reposition one pad's local (at x y); repeatable")
    p.add_argument("--all", action="store_true",
                   help="apply --size to every pad")
    p.set_defaults(func=cmd_set_pads)

    p = sub.add_parser("set-model", help="attach or replace the "
                                         "(model ...) 3D link")
    p.add_argument("footprint")
    p.add_argument("--model", required=True, metavar="PATH",
                   help="e.g. '${KIPRJMOD}/../lib/3dmodels/part.step'")
    p.add_argument("--offset", metavar="x,y,z", help="mm, default 0,0,0")
    p.add_argument("--rotate", metavar="x,y,z", help="degrees, default 0,0,0")
    p.set_defaults(func=cmd_set_model)

    p = sub.add_parser("annotate", help="record the source and the change "
                                        "in (descr) and (tags)")
    p.add_argument("footprint")
    p.add_argument("--source", required=True, metavar="URL")
    p.add_argument("--note", required=True, metavar="TEXT")
    p.set_defaults(func=cmd_annotate)

    p = sub.add_parser("diff", help="pad-by-pad geometric difference "
                                    "between two footprints")
    p.add_argument("a", metavar="A.kicad_mod")
    p.add_argument("b", metavar="B.kicad_mod")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("provenance-row", help="print the lib/PROVENANCE.md "
                                              "row for a forked footprint")
    p.add_argument("footprint")
    p.add_argument("--packages", default=DEFAULT_PACKAGES,
                   help="packages.json (default: beside this script)")
    p.set_defaults(func=cmd_provenance_row)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
