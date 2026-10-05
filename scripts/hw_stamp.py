#!/usr/bin/env python3
"""Stamp a generated KiCad file with the hash of the design.py it came from.

A board and a schematic are outputs of `design.py`.  Nothing in either file
says which revision of `design.py` produced it, so a gate that passes on a
board tells you nothing about the design source beside it.  Measured
(hypercardiod_mic, 2026-10-03): `design.py` said BOARD_L_MM = 68.0, edited at
08:17, while the board file was 24 x 60 mm, saved at 07:49.  Every gate ran
against the older board and nothing reported it.

So each generator stamps its output, and `hw_review.py` compares the stamp
with the current `design.py` (its `fresh` row, first in the table).

The stamp is a title-block comment, slot 9:

    (title_block
        (comment 9 "hw_forge design-sha1: 3f2a9c0d41e7b5a6")
    )

Chosen because both file types carry a title block, `pcbnew.SaveBoard()` and
KiCad's editors write it back unchanged, and `kicad-cli` only reads it.  A
board property or a text item would also survive, but would show on the
drawing or need a layer.  The stamp is read from comment 9 only, and a
comment 9 that holds anything else is never overwritten (exit 2, quoting it).

What is hashed.  By default only design.py: SHA-1 of its bytes with line
endings normalised to LF, first STAMP_LEN hex digits.  An edit to gen_sch.py
or gen_pcb.py alone does not change that hash.  `--also FILE` (repeatable)
folds more files into it; their paths, relative to design.py's directory,
are written into the stamp, so a check re-hashes the same files without
being told:

    (comment 9 "hw_forge design-sha1: 9b0e... also=gen_pcb.py,gen_sch.py")

The template Makefile's generation rule ends with that step, passing
gen_sch.py and gen_pcb.py.  A generator may also stamp its own output (the
snippet is in templates/design.py, "Generated-file stamp"):

    hw_stamp.stamp_file(out_path, os.path.join(HERE, "design.py"))

A pcbnew generator may instead call `stamp_board(board, design_path)` before
`pcbnew.SaveBoard()`; the result in the file is the same line.

    python3 scripts/hw_stamp.py FILE --design design.py           # check
    python3 scripts/hw_stamp.py FILE --design design.py --write \
        [--also gen_sch.py --also gen_pcb.py]                      # stamp

Exit 0 when every FILE carries the current hash, 1 otherwise, 2 when a
comment 9 holds something other than a stamp.  Runs under any python3 (3.6
and up), stdlib only, so the system python, KiCad's bundled python and a
generator can all import it.
"""

import argparse
import hashlib
import os
import re
import sys

sys.dont_write_bytecode = True

STAMP_KEY = "hw_forge design-sha1"
STAMP_SLOT = 9                       # KiCad title blocks have comments 1 to 9
STAMP_LEN = 16
_STAMP = re.compile(r"^%s:\s*([0-9a-fA-F]{6,40})(?:\s+also=(\S+))?\s*$"
                    % re.escape(STAMP_KEY))
_SLOT = re.compile(r'\(comment\s+%d\s+"((?:[^"\\]|\\.)*)"\)' % STAMP_SLOT)


class StampConflict(ValueError):
    """Comment 9 holds text that is not a stamp; it is never overwritten."""


def _bytes(path):
    with open(path, "rb") as fh:
        return fh.read().replace(b"\r\n", b"\n")


def also_names(design_path, also):
    """`also` paths relative to design.py's directory, '/'-separated and
    sorted, as they are written into the stamp."""
    base = os.path.dirname(os.path.abspath(design_path))
    return sorted(set(os.path.relpath(os.path.abspath(p), base).replace(
        os.sep, "/") for p in also or ()))


def design_hash(design_path, length=STAMP_LEN, also=()):
    """SHA-1 of design.py with CRLF folded to LF, first `length` hex digits.
    Each `also` file (a path relative to design.py's directory, as
    also_names() gives) is folded in after it, with its name."""
    h = hashlib.sha1(_bytes(design_path))
    base = os.path.dirname(os.path.abspath(design_path))
    for name in also or ():
        h.update(b"\0" + name.encode("utf-8") + b"\0")
        h.update(_bytes(os.path.join(base, name)))
    return h.hexdigest()[:length]


def stamp_line(sha, also=()):
    line = "%s: %s" % (STAMP_KEY, sha)
    return line + (" also=%s" % ",".join(also) if also else "")


def parse_stamp(text):
    """(hash, [also names]) from comment 9's text, or None if not a stamp."""
    found = _STAMP.match((text or "").strip())
    if not found:
        return None
    return (found.group(1).lower(),
            found.group(2).split(",") if found.group(2) else [])


def _comment9(text):
    """Comment 9's text in the title block, unescaped, or None."""
    span = _title_block_span(text)
    if span is None:
        return None
    found = _SLOT.search(text, span[0], span[1])
    if not found:
        return None
    return re.sub(r"\\(.)", r"\1", found.group(1))


def read_stamp_full(path):
    """(hash, [also names]) stamped in comment 9 of a .kicad_pcb or
    .kicad_sch, or None."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_stamp(_comment9(fh.read()))


def read_stamp(path):
    """The hash stamped in comment 9 of a .kicad_pcb or .kicad_sch, or
    None."""
    got = read_stamp_full(path)
    return got[0] if got else None


def _close_paren(text, start):
    """Index just past the parenthesis that closes the one at `start`."""
    depth, i, n, quoted = 0, start, len(text), False
    while i < n:
        c = text[i]
        if quoted:
            if c == "\\":
                i += 1
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced parentheses after offset %d" % start)


def _title_block_span(text):
    """(start, end) of the top-level (title_block ...), or None."""
    found = re.search(r"^[ \t]*\(title_block\b", text, re.M)
    if not found:
        return None
    start = text.index("(", found.start())
    return start, _close_paren(text, start)


def stamp_text(text, sha, also=()):
    """`text` with the stamp written into its title block (created after the
    (paper ...) line when the file has none).  StampConflict when comment 9
    holds anything but an earlier stamp or nothing."""
    current = _comment9(text)
    if current and parse_stamp(current) is None:
        raise StampConflict("title-block comment %d holds %r, not a `%s:` "
                            "stamp; move that text to another comment"
                            % (STAMP_SLOT, current, STAMP_KEY))
    line = '(comment %d "%s")' % (STAMP_SLOT, stamp_line(sha, also))
    span = _title_block_span(text)
    if span is None:
        paper = re.search(r"^([ \t]*)\(paper\b[^\n]*\n", text, re.M)
        if not paper:
            raise ValueError("no (paper ...) line to anchor a title block")
        ind = paper.group(1)
        block = "%s(title_block\n%s%s%s\n%s)\n" % (
            ind, ind, "\t" if ind.startswith("\t") or not ind else "  ",
            line, ind)
        return text[:paper.end()] + block + text[paper.end():]
    start, end = span
    body = text[start:end]
    if _SLOT.search(body):
        body = _SLOT.sub(line.replace("\\", "\\\\"), body, count=1)
    else:
        close = body.rstrip().rfind(")")
        head = body[:close].rstrip()
        lead = re.match(r"[ \t]*", text[text.rfind("\n", 0, start) + 1:]
                        ).group(0)
        inner = lead + ("\t" if lead.startswith("\t") or not lead else "  ")
        body = "%s\n%s%s\n%s)" % (head, inner, line, lead)
    return text[:start] + body + text[end:]


def stamp_file(path, design_path, also=()):
    """Write the current hash of design.py (and the `also` files) into
    `path`.  Returns the hash.  StampConflict when comment 9 is taken."""
    names = also_names(design_path, also)
    sha = design_hash(design_path, also=names)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    new = stamp_text(text, sha, names)
    if new != text:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
    return sha


def stamp_board(board, design_path, also=()):
    """pcbnew form: set the title-block comment before SaveBoard()."""
    names = also_names(design_path, also)
    sha = design_hash(design_path, also=names)
    block = board.GetTitleBlock()
    current = block.GetComment(STAMP_SLOT - 1)           # 0-based in pcbnew
    if current and parse_stamp(current) is None:
        raise StampConflict("title-block comment %d holds %r, not a `%s:` "
                            "stamp" % (STAMP_SLOT, current, STAMP_KEY))
    block.SetComment(STAMP_SLOT - 1, stamp_line(sha, names))
    board.SetTitleBlock(block)
    return sha


def check(path, design_path):
    """(state, detail): state is 'ok', 'stale', 'unstamped' or 'missing'.
    The files a stamp names with also= are re-hashed with design.py."""
    if not os.path.exists(path):
        return "missing", "no such file: %s" % path
    stamp = read_stamp_full(path)
    if stamp is None:
        return "unstamped", ("%s carries no `%s:` stamp in comment %d"
                             % (os.path.basename(path), STAMP_KEY,
                                STAMP_SLOT))
    got, also = stamp
    base = os.path.dirname(os.path.abspath(design_path))
    gone = [n for n in also if not os.path.isfile(os.path.join(base, n))]
    what = os.path.basename(design_path) + (
        " + " + ", ".join(also) if also else "")
    if gone:
        return "stale", ("%s stamp %s covers %s, but %s no longer exist(s)"
                         % (os.path.basename(path), got, what,
                            ", ".join(gone)))
    want = design_hash(design_path, also=also)
    if want.startswith(got) or got.startswith(want):
        return "ok", "%s stamp %s matches %s" % (
            os.path.basename(path), got, what)
    return "stale", ("%s stamp %s, but %s is now %s"
                     % (os.path.basename(path), got, what, want))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", help=".kicad_pcb / .kicad_sch")
    ap.add_argument("--design", required=True, help="the design.py")
    ap.add_argument("--write", action="store_true",
                    help="write the current hash instead of checking it")
    ap.add_argument("--also", action="append", default=[], metavar="FILE",
                    help="with --write: fold this file (a generator) into "
                         "the hash; repeatable.  A check reads the list "
                         "from the stamp")
    args = ap.parse_args()
    if args.also and not args.write:
        ap.error("--also is for --write; a check reads the list from the "
                 "stamp")
    bad = 0
    for path in args.files:
        if args.write:
            try:
                sha = stamp_file(path, args.design, args.also)
            except StampConflict as exc:
                sys.stderr.write("error: %s: %s\n" % (path, exc))
                sys.exit(2)
            print("  stamped   %s %s" % (path, sha))
            continue
        state, detail = check(path, args.design)
        print("  %-9s %s" % (state, detail))
        bad += state != "ok"
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
