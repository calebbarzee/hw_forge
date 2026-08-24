#!/usr/bin/env python3
"""Geometry-normalized comparison of two fab-output directories.

Answers one question: did the plotted geometry change? A plain text diff
cannot answer it. Gerber files renumber aperture D-codes and reorder draw
commands between otherwise-identical plots, because footprint emission order
and UUIDs differ on every regeneration. Both gerber and excellon also carry
timestamps in their headers.

Normalization: resolve every D-code to its aperture shape signature and
every excellon tool number to its diameter, drop headers and comments, then
compare the sorted multiset of draw operations. Identical multisets mean
identical geometry, so the files are interchangeable at the fab.

Usage:
    gerber_diff.py OLD_DIR NEW_DIR

Compares every *.gbr and *.drl present in OLD_DIR against its same-named
counterpart in NEW_DIR. Exits 0 if all pairs match and 1 otherwise, so a
script can use it to gate "the old upload zip is still valid".
"""
import glob
import os
import re
import sys

DRILL_NOISE = {"M48", "%", "M30", "M95", "G90", "G05", "FMAT,2",
               "METRIC", "METRIC,TZ", "METRIC,LZ", "INCH,TZ", "INCH,LZ"}


def norm_gerber(path):
    apertures, out, cur = {}, [], None
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("G04") or "%TF" in line or line == "M02*":
            continue
        m = re.match(r"%ADD(\d+)(.*?)\*%$", line)
        if m:
            apertures["D" + m.group(1)] = m.group(2)
            continue
        m = re.match(r"D(\d+)\*$", line)
        if m:
            cur = apertures.get("D" + m.group(1), "D" + m.group(1))
            continue
        if line[0] in "XYI":
            out.append(f"{cur}|{line}")
        else:
            out.append(f"CMD|{line}")
    return sorted(out)


def norm_drill(path):
    tools, out, cur = {}, [], None
    for line in open(path):
        line = line.strip()
        if not line or line.startswith(";") or line in DRILL_NOISE:
            continue
        m = re.match(r"T(\d+)C([\d.]+)", line)
        if m:
            tools["T" + m.group(1)] = m.group(2)
            continue
        m = re.match(r"T(\d+)$", line)
        if m:
            cur = tools.get("T" + m.group(1), "T" + m.group(1))
            continue
        out.append(f"{cur}|{line}")
    return sorted(out)


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: gerber_diff.py OLD_DIR NEW_DIR")
    old_dir, new_dir = sys.argv[1], sys.argv[2]
    files = sorted(glob.glob(os.path.join(old_dir, "*.gbr"))) + \
        sorted(glob.glob(os.path.join(old_dir, "*.drl")))
    if not files:
        sys.exit(f"no *.gbr / *.drl in {old_dir}")
    failed = 0
    for old in files:
        base = os.path.basename(old)
        new = os.path.join(new_dir, base)
        if not os.path.exists(new):
            print(f"  MISSING    {base} (not in {new_dir})")
            failed += 1
            continue
        norm = norm_drill if old.endswith(".drl") else norm_gerber
        a, b = norm(old), norm(new)
        if a == b:
            print(f"  identical  {base} ({len(a)} draw ops)")
        else:
            failed += 1
            only_old, only_new = set(a) - set(b), set(b) - set(a)
            print(f"  DIFFERS    {base}: {len(only_old)} ops only-old, "
                  f"{len(only_new)} only-new")
            for x in sorted(only_old)[:3]:
                print(f"    old: {x[:100]}")
            for x in sorted(only_new)[:3]:
                print(f"    new: {x[:100]}")
    n = len(files)
    print(f"\n{n - failed}/{n} identical" + ("" if not failed else f", {failed} differ"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
