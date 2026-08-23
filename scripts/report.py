#!/usr/bin/env python3
"""Summarise a kicad-cli DRC/ERC JSON report as one line per category.

Reads either report shape (ERC reports nest violations under `sheets`; DRC
reports carry `violations`, `schematic_parity` and `unconnected_items` at the
top level) and prints one padded line per category: `ok`, `warn` when only
warnings are present, or `FAIL` with a count per violation type.

    python3 scripts/report.py build/left/drc.json

Exit status is 0 unless --strict is given, in which case any error-severity
violation exits 1.  The default is silent-status-by-design: the gate script
already owns the exit code, and this is its printer.
"""

import argparse
import collections
import json
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report", help="a kicad-cli erc/drc JSON report")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any error-severity violation is present")
    ap.add_argument("--indent", default="  ")
    args = ap.parse_args()

    errors = summarise(args.report, args.indent)
    if args.strict and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
