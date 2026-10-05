#!/usr/bin/env python3
"""Fill a board's copper zones headlessly, then repair the project file.

Must run under KiCad's bundled python, the only interpreter that can import
pcbnew.  Run it under the system python and it tells you the exact command to
re-run instead of failing with an ImportError traceback.

    KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
    $KPY scripts/kicad_zonefill.py build/left/board.kicad_pcb
    $KPY scripts/kicad_zonefill.py build/left/board.kicad_pcb -o /tmp/filled.kicad_pcb

Why this is a separate tool: under KiCad 8 `ZONE_FILLER` needed the wx app
framework and aborted the interpreter with no display, so headless builds
shipped boards with unfilled zones. Those read as unconnected copper in the
design rule check (DRC).  Under KiCad 10 the filler runs headlessly, so
filling belongs in the build and `kicad_gate.py` needs no graphical pass.

Keep every net's connectivity in explicit copper anyway: treat zones as copper
balance and thermal relief, never as the only path a net has, so a filler
regression cannot silently break a board.

Two traps, both handled here:

  * `SaveBoard()` rewrites the sibling `.kicad_pro` from the board object's
    project settings, so a board built with `CreateEmptyBoard()` writes
    pcbnew's defaults over the project's DRC severity overrides and design
    rules.  This script loads an existing board, so it is not itself exposed.
    It calls `kicad_scaffold.repatch()` after saving anyway, because it is
    usually run right after a generator that is exposed.  Any generator that
    saves a from-scratch board owes the same call.
  * Zone island removal must be by area, not by connectivity, on any zone
    whose only connections are vias.  KiCad does not count via connectivity
    when deciding whether a filled island is connected, so the default mode
    deletes every island that lacks a pad.  That turns a full pour into a
    sliver around one pin and reports everything else unconnected.
    `--island-mode area` applies area-based removal to every zone before
    filling.
"""

import argparse
import os
import sys

sys.dont_write_bytecode = True      # never leave __pycache__ in a project tree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kicad_scaffold
from _kicad_env import require_pcbnew

pcbnew = require_pcbnew(__file__)

# Default minimum island area for --island-mode area, in mm per side.  Big
# enough to sweep up slivers, small enough to keep any pour worth having.
DEFAULT_MIN_ISLAND_MM = 3.0


def mm(value):
    return pcbnew.FromMM(value)


def set_island_mode_area(board, min_island_mm, quiet=False):
    """Switch every zone to area-based island removal.

    See the module docstring: connectivity-based removal (the KiCad default)
    does not count vias, so a via-fed plane loses its entire fill.
    """
    changed = 0
    area = int(mm(min_island_mm)) * int(mm(min_island_mm))
    for zone in board.Zones():
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_AREA)
        zone.SetMinIslandArea(area)
        changed += 1
    if changed and not quiet:
        print("  island removal: area mode, min %gmm^2, %d zone(s)"
              % (min_island_mm * min_island_mm, changed))
    return changed


def zone_report(board):
    """[(name, layer, filled_area_mm2), ...] for the printed summary."""
    out = []
    for zone in board.Zones():
        try:
            area = zone.GetFilledArea() / 1e12       # nm^2 -> mm^2
        except Exception:                            # pragma: no cover
            area = float("nan")
        out.append((zone.GetNetname() or "<no net>",
                    board.GetLayerName(zone.GetLayer()), area))
    return out


def fill(board_path, out_path=None, island_mode=None,
         min_island_mm=DEFAULT_MIN_ISLAND_MM, do_repatch=True, quiet=False):
    """Fill zones and save. Returns the number of zones filled."""
    if not os.path.exists(board_path):
        raise SystemExit("error: no such board: %s" % board_path)
    out_path = out_path or board_path

    board = pcbnew.LoadBoard(board_path)
    zones = board.Zones()
    if not len(zones):
        if not quiet:
            print("  no zones in %s: nothing to fill"
                  % os.path.basename(board_path))
        return 0

    if island_mode == "area":
        set_island_mode_area(board, min_island_mm, quiet)

    pcbnew.ZONE_FILLER(board).Fill(zones)
    pcbnew.SaveBoard(out_path, board)

    # SaveBoard just rewrote the sibling .kicad_pro from pcbnew's defaults.
    if do_repatch:
        touched = kicad_scaffold.repatch(os.path.dirname(os.path.abspath(out_path)))
        if touched and not quiet:
            print("  re-patched %d project file(s) after SaveBoard"
                  % len(touched))

    if not quiet:
        print("  filled %d zone(s) -> %s" % (len(zones), out_path))
        for net, layer, area in zone_report(board):
            print("    %-12s %-14s %10.1f mm^2" % (net, layer, area))
    return len(zones)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("board", help="a .kicad_pcb file")
    ap.add_argument("-o", "--out", help="write here instead of in place")
    ap.add_argument("--island-mode", choices=("area", "keep-default"),
                    default="keep-default",
                    help="'area' forces area-based island removal on every "
                         "zone, required for via-fed planes (see docstring)")
    ap.add_argument("--min-island", type=float, default=DEFAULT_MIN_ISLAND_MM,
                    metavar="MM",
                    help="island side length for --island-mode area "
                         "(default: %(default)g mm)")
    ap.add_argument("--no-repatch", action="store_true",
                    help="skip the post-SaveBoard project re-patch")
    args = ap.parse_args()

    print("--- zone fill: %s ---" % os.path.basename(args.board))
    fill(args.board, args.out,
         island_mode=None if args.island_mode == "keep-default" else "area",
         min_island_mm=args.min_island, do_repatch=not args.no_repatch)


if __name__ == "__main__":
    main()
