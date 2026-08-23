#!/usr/bin/env python3
"""Canonical, KIID-free digest of a KiCad file — the determinism check.

    python3 scripts/kicad_digest.py board.kicad_pcb [more.kicad_pcb ...]
    python3 scripts/kicad_digest.py --expect 4f0c… board.kicad_pcb
    python3 scripts/kicad_digest.py --compare before.kicad_pcb after.kicad_pcb
    python3 scripts/kicad_digest.py --json board.kicad_pcb
    python3 scripts/kicad_digest.py --stamp ASSEMBLY.md board.kicad_pcb

WHY THIS EXISTS.  "Regeneration from wiped outputs is deterministic" is part of
the PCB phase's contract, and the orchestrator's regression test — committed
artifact still passes, fresh regeneration does not — depends on being able to
say whether a rebuild changed anything.  But a generated board is **not
byte-stable and cannot be**: `pcbnew` mints a fresh random KIID for every item
it creates, and `SaveBoard()` writes footprints in its own internal order
rather than insertion order.  Two runs of an *unchanged* generator have been
measured differing in 5744 of 10488 lines while describing identical copper.

So `diff` and a plain checksum report a false failure every single time, and
without a canonical form there is no check that reports a true one.

The canonical form: drop every `uuid`/`tstamp`, sort the remaining lines, hash.
What survives is every coordinate, layer, net, width, drill, property and
filled-zone outline — i.e. everything a fab, a DRC or an enclosure generator
reads.  Equal digests across a wipe-and-rebuild is the strongest determinism
claim this toolchain supports, and a real regression (a moved lane, a changed
fill, a dropped footprint) changes the digest immediately.

What it deliberately does NOT prove: that two boards with equal digests are
byte-identical, or that item *order* is stable.  Nothing downstream reads
order, so nothing downstream should be gated on it.

Pure stdlib under any python3 — it must run without `pcbnew`, so it works in
the same shell as the rest of the gate.  Works on `.kicad_sch` and `.kicad_mod`
too: the canonicalisation is textual, not board-specific.

`--stamp DOC` — PROSE THAT OUTLIVED ITS BOARD.

An as-built document (an assembly doc, a fab handoff, a firmware pin list) is
correct for exactly one revision of the board it describes, and **no gate looks
at prose**.  Measured: a 284-line assembly document, entirely correct for rev 2,
became actively wrong the moment a direct-pin scan became a diode matrix — its
populate list had no diodes, its placement count was 33, its drill census was
stale, and its firmware section listed a `kscan-gpio-direct` map that would
have been copied into a real overlay.  Nothing detected that; it was caught by
someone happening to read the file for an unrelated number.  This is not the
stale-but-harmless kind of wrong, it is the kind that makes someone solder the
wrong board.

So stamp the document with the digest of what it describes, on one line, in a
comment or a footer:

    <!-- board-digest: 4f0c1e… -->        (markdown)
    # board-digest: 4f0c1e…               (anything hash-commented)

and put `--stamp` in `make check`.  The document then fails a check instead of
misleading a human, and re-stamping it is the one-line act of saying "I have
re-read this against the current board".  Any line matching
`board-digest:\s*<hex>` is found, wherever it lives in the file.

    kicad_digest.py --stamp ASSEMBLY.md board.kicad_pcb          # verify
    kicad_digest.py --stamp ASSEMBLY.md board.kicad_pcb --write  # re-stamp
"""

import argparse
import hashlib
import json
import os
import re
import sys

sys.dont_write_bytecode = True      # never leave __pycache__ in a project tree

# `(uuid "…")` appears both as a whole line and inline inside an item.
_UUID_LINE = ("(uuid", "(tstamp")
_UUID_INLINE = re.compile(r'\((?:uuid|tstamp) "?[^")]*"?\)')


def canon(path):
    """Sorted, identity-free lines of a KiCad s-expression file."""
    out = []
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if s.startswith(_UUID_LINE):
                continue
            s = _UUID_INLINE.sub("", s).strip()
            if s:
                out.append(s)
    return sorted(out)


def digest(path):
    """(line_count, sha1) of the canonical form."""
    lines = canon(path)
    return len(lines), hashlib.sha1("\n".join(lines).encode()).hexdigest()


def compare(a, b):
    """(same, detail) for two files' canonical forms."""
    ca, cb = canon(a), canon(b)
    if ca == cb:
        return True, "%d canonical lines identical" % len(ca)
    only_a = sorted(set(ca) - set(cb))
    only_b = sorted(set(cb) - set(ca))
    return False, ("%d line(s) only in %s, %d only in %s\n  - %s\n  + %s"
                   % (len(only_a), os.path.basename(a),
                      len(only_b), os.path.basename(b),
                      only_a[0][:100] if only_a else "",
                      only_b[0][:100] if only_b else ""))


_STAMP = re.compile(r"(board-digest:\s*)([0-9a-fA-F]{6,40})")


def stamp(doc_path, board_path, write=False):
    """Compare a document's `board-digest:` stamp against the board.

    Returns (state, detail): 'ok', 'stale', 'unstamped', or 'wrote'.  A partial
    digest is honoured as a prefix, so a document can carry a short readable
    stamp and still be checked.
    """
    _lines, sha = digest(board_path)
    try:
        with open(doc_path) as fh:
            text = fh.read()
    except OSError as exc:
        raise SystemExit("error: cannot read %s: %s" % (doc_path, exc))
    found = _STAMP.search(text)
    if found is None:
        if write:
            raise SystemExit(
                "error: %s carries no `board-digest:` line to re-stamp\n"
                "  fix: add one (a comment or a footer is fine):\n"
                "       <!-- board-digest: %s -->" % (doc_path, sha))
        return "unstamped", ("no `board-digest:` line — this document is not "
                            "tied to any board revision; the board is %s"
                            % sha[:12])
    stamped = found.group(2).lower()
    if sha.startswith(stamped):
        return "ok", "stamp %s matches %s" % (stamped,
                                              os.path.basename(board_path))
    if write:
        with open(doc_path, "w") as fh:
            fh.write(_STAMP.sub(lambda m: m.group(1) + sha[:len(stamped)],
                                text, count=1))
        return "wrote", "re-stamped %s -> %s" % (stamped, sha[:len(stamped)])
    return "stale", ("stamp %s but %s is %s — this document describes a board "
                     "that no longer\n              exists. RE-READ it against "
                     "the current board, then re-stamp with --write."
                     % (stamped, os.path.basename(board_path),
                        sha[:len(stamped)]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", help="KiCad s-expression file(s)")
    ap.add_argument("--stamp", metavar="DOC",
                    help="verify DOC's `board-digest:` line against the board "
                         "(a generated as-built document is correct for "
                         "exactly one revision)")
    ap.add_argument("--write", action="store_true",
                    help="with --stamp, rewrite the stamp — the one-line act "
                         "of saying the document has been re-read")
    ap.add_argument("--expect", metavar="SHA1",
                    help="assert the digest equals this (exit 1 if not); with "
                         "several files, every one must match")
    ap.add_argument("--compare", action="store_true",
                    help="treat the two files as before/after and report what "
                         "changed in the canonical form")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    for path in args.files:
        if not os.path.exists(path):
            raise SystemExit("error: no such file: %s" % path)

    if args.stamp:
        if len(args.files) != 1:
            ap.error("--stamp takes exactly one board file")
        state, detail = stamp(args.stamp, args.files[0], args.write)
        print("  %-11s %-9s %s" % (os.path.basename(args.stamp),
                                   state.upper() if state in ("stale",
                                                              "unstamped")
                                   else state, detail))
        sys.exit(1 if state in ("stale", "unstamped") else 0)

    if args.compare:
        if len(args.files) != 2:
            ap.error("--compare takes exactly two files")
        same, detail = compare(*args.files)
        print("%s  %s" % ("same    " if same else "DIFFERS ", detail))
        sys.exit(0 if same else 1)

    results = [(p,) + digest(p) for p in args.files]
    if args.json:
        json.dump([{"file": p, "lines": n, "sha1": h} for p, n, h in results],
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for path, lines, sha in results:
            print("%-44s lines=%-6d sha1=%s" % (path, lines, sha))

    if args.expect:
        bad = [p for p, _n, h in results if h != args.expect]
        if bad:
            print("error: digest does not match --expect %s: %s"
                  % (args.expect, ", ".join(bad)), file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
