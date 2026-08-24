#!/usr/bin/env python3
"""Summarise a kicad-cli DRC/ERC JSON report as one line per category.

Reads either report shape and prints one padded line per category: `ok`,
`warn` when only warnings are present, or `FAIL` with a count per violation
type.  An electrical rule check (ERC) report nests violations under `sheets`;
a design rule check (DRC) report carries `violations`, `schematic_parity` and
`unconnected_items` at the top level.

    python3 scripts/report.py build/left/drc.json
    python3 scripts/report.py build/left/drc-all.json --by-owner
    python3 scripts/report.py drc-all.json --by-owner --baseline old-all.json

`--by-owner` groups findings by the footprint refs their items name, which is
the check a severity demotion has to keep passing.  A demotion is per rule, so
it switches that rule off board-wide, and the only thing that makes it
defensible is proving the whole finding set has the sanctioned cause, as in
"24/24 name DISP1+MCU1" (see references/kicad-api.md §4).

That claim has to be re-proved every revision, and counting by type never
names the owners, so every project ends up writing the same little grouper by
hand.

`--baseline FILE` compares finding classes against an earlier report of the
same board, one class per `(type, owner-set)` pair.  It answers the question a
second revision asks: did I introduce a finding class that was not there
before?

Errors are gated and warnings are not, so a new warning class otherwise
arrives in silence.  Measured: a revision's first green build carried 8
silkscreen findings the previous revision did not have, and finding that out
meant `git show HEAD:drc-all.json` and a hand-written grouper.  With
`--strict`, a new class exits 1, which makes "no new warning classes this rev"
a build gate rather than a habit.

Run both against a `--severity-all` report, not the gate's error-only one:
warnings are the whole point.

Exit status is 0 unless --strict is given.  Under --strict, any error-severity
violation exits 1, as does any new finding class when --baseline is given.
The default status is silent by design: the gate script already owns the exit
code, and this is its printer.
"""

import argparse
import collections
import json
import re
import sys

# DRC report keys, in the order they are printed.
DRC_SECTIONS = (("violations", "DRC"),
                ("schematic_parity", "parity"),
                ("unconnected_items", "unconnected"))


def load(path):
    with open(path) as fh:
        return json.load(fh)


def sections(doc):
    """[(label, [violation, ...]), ...] for either report shape."""
    if "sheets" in doc:                        # ERC
        items = [v for sheet in doc["sheets"] for v in sheet.get("violations", [])]
        return [("ERC", items)]
    return [(label, doc.get(key) or []) for key, label in DRC_SECTIONS]


def show(label, items, indent="  "):
    """Print one line; return the number of error-severity violations."""
    errs = [v for v in items if v.get("severity") == "error"]
    if not items:
        print("%s%-11s ok" % (indent, label))
        return 0
    counts = collections.Counter(v.get("type", "?") for v in items)
    print("%s%-11s %s  %s" % (indent, label, "FAIL" if errs else "warn",
                              ", ".join("%s x%d" % (t, n)
                                        for t, n in counts.most_common())))
    return len(errs)


def summarise(path, indent="  "):
    """Print every section of one report; return total error-severity count."""
    doc = load(path)
    return sum(show(label, items, indent) for label, items in sections(doc))


# ------------------------------------------------------------------ by owner
#
# Item descriptions look like: "Footprint DISP1", "Footprint text of MCU1 (D0)",
# "PTH pad 21 [VCC] of MCU1" for a plated through-hole pad, and "NPTH pad of
# SW7" for a non-plated one.  So the owner is either the whole description
# after "Footprint ", or whatever follows the last " of ".
# Bracketed net names are stripped first, because a net can carry a refdes
# inside it ("unconnected-(MCU1-D8-Pad11)") and that is not an owner.

NET_BRACKET = re.compile(r"\[[^\]]*\]")
REF = r"[A-Za-z][A-Za-z_]*\d+"
OWNER_PATTERNS = (re.compile(r"\bof (%s)\b" % REF),
                  re.compile(r"^(?:Footprint|Pad|Zone|Track|Via|Symbol) (%s)$"
                             % REF))


def owners_of(item):
    """The refdes(es) one violation item names, as a sorted list."""
    text = NET_BRACKET.sub("", item.get("description") or "").strip()
    found = []
    for pattern in OWNER_PATTERNS:
        found += pattern.findall(text)
    return sorted(set(found))


def classes(doc):
    """{(label, type, owner_set): [severity, ...]}, one key per finding class.

    The owner set is the key, not each owner separately: a clearance-style
    violation is a statement about a pair, and "every finding is DISP1 against
    MCU1" is the claim a demotion rests on.
    """
    out = collections.OrderedDict()
    for label, items in sections(doc):
        for violation in items:
            refs = sorted({ref for item in violation.get("items", [])
                           for ref in owners_of(item)})
            key = (label, violation.get("type", "?"),
                   "+".join(refs) or "(no ref named)")
            out.setdefault(key, []).append(violation.get("severity", "?"))
    return out


def show_by_owner(doc, indent="  "):
    """Print one line per finding class. Returns the class dict."""
    found = classes(doc)
    if not found:
        print("%sno findings in any section" % indent)
        return found
    width = max(len(k[1]) for k in found)
    for (label, vtype, owners), sevs in sorted(found.items()):
        worst = "error" if "error" in sevs else sorted(set(sevs))[0]
        print("%s%-11s %-*s x%-4d %-7s %s"
              % (indent, label, width, vtype, len(sevs), worst, owners))
    return found


def compare_classes(new, old, indent="  "):
    """Print added/gone classes. Returns the number of new classes."""
    added = [k for k in new if k not in old]
    gone = [k for k in old if k not in new]
    same = [k for k in new if k in old and len(new[k]) != len(old[k])]
    for key in sorted(added):
        print("%s+ NEW CLASS  %-11s %-24s %s  x%d"
              % (indent, key[0], key[1], key[2], len(new[key])))
    for key in sorted(gone):
        print("%s- gone       %-11s %-24s %s  (was x%d)"
              % (indent, key[0], key[1], key[2], len(old[key])))
    for key in sorted(same):
        print("%s~ count      %-11s %-24s %s  %d -> %d"
              % (indent, key[0], key[1], key[2], len(old[key]),
                 len(new[key])))
    if not (added or gone or same):
        print("%sno change: same finding classes at the same counts" % indent)
    return len(added)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report", help="a kicad-cli erc/drc JSON report")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any error-severity violation is present, "
                         "or (with --baseline) if any finding class is new")
    ap.add_argument("--by-owner", action="store_true",
                    help="group findings by the footprint refs they name; "
                         "this is the demotion-family check")
    ap.add_argument("--baseline", metavar="FILE",
                    help="an earlier report of the same board; report finding "
                         "classes added, gone, or changed in count")
    ap.add_argument("--indent", default="  ")
    args = ap.parse_args()

    if args.by_owner or args.baseline:
        doc = load(args.report)
        new = classes(doc)
        if args.by_owner:
            print("--- findings by owner: %s ---" % args.report)
            show_by_owner(doc, args.indent)
        added = 0
        if args.baseline:
            print("--- vs baseline: %s ---" % args.baseline)
            added = compare_classes(new, classes(load(args.baseline)),
                                    args.indent)
        if args.strict and added:
            print("%d new finding class(es)" % added, file=sys.stderr)
            sys.exit(1)
        return

    errors = summarise(args.report, args.indent)
    if args.strict and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
