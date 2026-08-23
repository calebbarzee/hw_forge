#!/usr/bin/env python3
"""Canonical, KIID-free digest of a KiCad file — the determinism check.

    python3 scripts/kicad_digest.py board.kicad_pcb [more.kicad_pcb ...]
    python3 scripts/kicad_digest.py --expect 4f0c… board.kicad_pcb
    python3 scripts/kicad_digest.py --compare before.kicad_pcb after.kicad_pcb
    python3 scripts/kicad_digest.py --json board.kicad_pcb

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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", help="KiCad s-expression file(s)")
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
