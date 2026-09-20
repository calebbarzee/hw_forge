#!/usr/bin/env python3
"""Bridge a board to an external Specctra autorouter, and adopt its result.

Why this exists.  `gen_pcb.py` routing-as-code (named-constant lanes and
corridors, see `references/electronics.md` §7) is the right tool for a
regular, repeated topology: a keyboard matrix, an LED chain, anything where
one cell's routing generalises to N cells by arithmetic.  It stops scaling
once placement is irregular and net count is high: an agent-designed RP2350
board with 65 footprints and 54 nets is the worked case in
`references/autorouting.md`, and hand-deriving lane order for that class of
board is the wrong use of a session.

That class of board is still gated the same way as any other: DRC 0 with
schematic parity, 0 unconnected, zones filled headlessly.  What changes is
who proposes the copper.  This script is the bridge to a Specctra-speaking
autorouter (Freerouting, or anything that reads a `.dsn` and writes a
`.ses`), and the adoption step that turns a one-time external routing pass
into a deterministic, checked-in python data file, the same generate-only
doctrine every other phase already follows, applied to routing instead of
placement.

    python3 scripts/kicad_route.py export-dsn BOARD.kicad_pcb [-o OUT.dsn]
    python3 scripts/kicad_route.py route OUT.dsn [-o OUT.ses] [--passes N] \\
        [--jar PATH]
    python3 scripts/kicad_route.py import-ses BOARD.kicad_pcb OUT.ses \\
        [-o ROUTED.kicad_pcb]
    python3 scripts/kicad_route.py adopt ROUTED.kicad_pcb [-o kicad/routing.py]

`export-dsn` and `import-ses` touch `pcbnew` and must run under KiCad's
bundled interpreter, exactly like `kicad_zonefill.py`; run either under the
system python and this script prints the exact re-run command instead of an
ImportError traceback.  `route` and `adopt` are plain subprocess/text-parsing
and run under any python3.

## A second backend: KiCadRoutingTools

KiCadRoutingTools (`references/autorouting.md` §6, `references/kicad-
ecosystem.md` §3) reads and writes a `.kicad_pcb` directly with its own
parser, no DSN/SES, no `pcbnew`, no `kipy`, so it has no export/import split:
one subcommand routes the board and refills zones in the same step.

    python3 scripts/kicad_route.py route-krt BOARD.kicad_pcb [-o ROUTED.kicad_pcb] \\
        [--power-nets GND VCC ...]

`route-krt` DOES need KiCad's bundled interpreter, unlike `route`/`adopt`
above: KiCadRoutingTools' own routing pass is a pure subprocess step, but the
zone refill after it (required, see `route_krt`'s docstring) calls
`kicad_zonefill.py`, which imports `pcbnew`.

**`adopt` is identical for both backends.** It reads tracks/vias/arcs out of
a `.kicad_pcb` with the same `kicad_geom`-based text parser regardless of
which tool produced them, so the same `python3 scripts/kicad_route.py adopt
ROUTED.kicad_pcb -o kicad/routing.py` command closes either flow.

## Why this goes through `pcbnew`, not `kicad-cli`

Checked directly against this machine's KiCad 10.0.5: `kicad-cli pcb export
--help` lists 3dpdf, brep, drill, dxf, gencad, gerbers, glb, hpgl, ipc2581,
ipcd356, odb, pdf, ply, pos, ps, stats, step, stl, stpz, svg, u3d, vrml, xao.
No `dsn`.  `kicad-cli pcb import --help` imports *other* CAD tools' PCB
files into KiCad format (pads, altium, eagle, cadstar, fabmaster, pcad,
solidworks), it does not read a Specctra session.  Neither the KiCad 10 IPC
API (`kicad-python` / `kipy`) documentation nor its `Board` class exposes
Specctra DSN/SES or track/via creation as of this writing (docs.kicad.org,
kicad-python-main).

So the only interface that does this in KiCad 10 is the same SWIG `pcbnew`
module `kicad_zonefill.py` already depends on:

    pcbnew.ExportSpecctraDSN(board, filename) -> bool
    pcbnew.ImportSpecctraSES(board, filename) -> bool

Both confirmed present by introspecting the bundled interpreter
(`dir(pcbnew)`) and both exercised end to end below. `references/kicad-api.md`
§10 has the full trap list; the two load-bearing ones are repeated here
because a caller of this script has to act on them, not just know them.

## Trap: locking is the only protection a wire gets, and it is opt-in

`ExportSpecctraDSN` writes a wire's `(type ...)` field from the track's own
`Locked` state, nothing else.  Verified by a controlled export: with five
tracks marked `SetLocked(True)` and 190 left alone, the DSN carried exactly
five `(type fix)` wires and zero on every other wire (no `(type ...)` suffix
at all is the unlocked default).  Freerouting's own docs describe a locked
wire as reserved rather than ripped up during autorouting.

The consequence for the hybrid flow in `references/autorouting.md`: whatever
the generator routes itself, power, differential pairs, the crystal, USB,
must call `track.SetLocked(True)` / `via.SetLocked(True)` **before the
board is saved**, in `gen_pcb.py`, before this script ever runs. This script
does not add locks on your behalf; it only reports how many `(type fix)`
wires came out, so a generator that forgot to lock anything finds out at
export time instead of after the autorouter has already rerouted a
protected net.

## Trap: `ImportSpecctraSES` replaces the routing, it does not patch it

Measured on a copy of a fully-routed 150-track/45-via test board: importing
a hand-built session naming a single wire on a single net left the board
with **one track and zero vias**, every other net's copper was gone. The
two copper pours were untouched, because Specctra has no zone concept at
all; only tracks and vias are replaced.

So a session file is not a diff. It is asserted as the board's *entire*
routing solution. This is safe when you import the autorouter's own output
SES against the DSN it just routed, because a real router's session
enumerates the whole net set it read, including the wires it left alone
because they were locked. It is not safe to hand-edit, truncate, or replay
an old session against a board that has since changed nets, and it is not
safe to assume a partially-successful router run (see the two-of-49 case in
`references/autorouting.md`) wrote out the untouched nets at all, check its
own log, and always diff track/via counts per net before trusting the
result. `import-ses` below does that diff for you and warns on any net that
went from populated to empty.

## Interaction with the determinism gate (`kicad_digest.py`)

`kicad_digest.py`'s canonical digest is the pipeline's proof that a
wipe-and-rebuild reproduces the same board. That proof depends on
`gen_pcb.py` being a pure function of `design.py` plus its own named
constants, nothing it calls may be nondeterministic, and an autorouter
plainly is: two runs of Freerouting against the same DSN are not guaranteed
to produce byte-identical, or even topologically identical, wiring.

So the autorouter cannot be inside the generator's hot path. `adopt` is what
keeps the contract intact: it runs once, outside `gen_pcb.py`, against a
board that has already passed the gate by hand-verification, and it freezes
that result into a plain python data module, `ROUTES` and `VIAS`, plain
tuples, committed to the repository exactly like any other named constant
table `design.py` or `gen_pcb.py` already carries. `gen_pcb.py` then imports
that module and replays it. A wipe-and-rebuild after that point is
deterministic for the same reason any other constant-driven geometry is:
`gen_pcb.py` never calls the router again, it only replays what `adopt`
recorded.

## Staleness rule: what a placement change invalidates

`adopt`'s output is copper positioned against the pad positions the board
had at adoption time. A track's endpoint has no idea which pad it used to
touch; it is just a coordinate pair. If any footprint moves, rotates, or
changes face after adoption, every adopted track or via that used to land on
one of its pads now lands on empty board, silently, because nothing about
the coordinate itself is invalid, it is just no longer connected to
anything.  DRC will eventually notice as an unconnected net or a dangling
track end, but only after a rebuild that looked clean at the generation
step.

There is no cheap way to prove which adopted routes were *not* touched by a
placement change short of cross-referencing every moved footprint's pads
against every route endpoint, which is exactly the kind of arithmetic
`references/electronics.md`'s "nudge, do not prove" rule exists to avoid
doing by hand. So the rule is the conservative one: **any placement change
to any footprint on the board makes the whole `routing.py` stale.**
Re-export, re-route, re-import, re-adopt. The full round trip costs minutes
against an irregular board with many nets; treating a stale routing file as
still valid costs a silent short or an open circuit that the next DRC run
reports as a mystery.

## CLI flags and traps for the router step itself

Verified from the Freerouting project's own docs
(github.com/freerouting/freerouting, `docs/command_line_arguments.md`, and
the v2.4.1 release notes/API, fetched during this work, not run against a
live install on this machine; see below):

    java -jar freerouting.jar -de BOARD.dsn -do BOARD.ses -mp PASSES \\
         -dct 0 --gui.enabled=false

`-de` loads the design, `-do` writes the session when routing finishes,
`-mp` caps the pass count, `-dct 0` disables the interactive confirmation
dialog's timeout wait, and `--gui.enabled=false` is what makes v2.x run
without a window. Freerouting issue #376 documents that v2.0.1's CLI mode
did not respect `-mp` in headless mode; fixed by v2.1 per the issue tracker.
Current stable is v2.4.1 (GitHub API, published 2026-09-03), whose release
notes state a move to a Java 25 baseline, this machine carries OpenJDK
21.0.2, so v2.4.1 may not run here unmodified; this is stated, not verified,
because installing a jar or a JRE is outside what this session may do
unattended. See `references/autorouting.md` for the comparison table and
every claim's verification status.

**Pre-v2 jars predate `--gui.enabled`, and this matters operationally, not
just historically.** A v1.9.0 jar found on this machine (built 2023-10-30,
`Main-Class: app.freerouting.gui.MainApplication`) was invoked with an
unrecognised flag during this work and did not exit: it neither errored nor
produced output, consistent with the Swing entry point waiting on a display
this machine genuinely has, rather than failing fast the way a true headless
environment would. The process had to be left running because there was no
safe way to confirm killing it would not also affect something else the
user was doing. **Do not invoke a Freerouting jar older than v2.1 through
this script, or through any other unattended path, without first confirming
`--gui.enabled=false` is recognised** (run it once, by hand, watching for a
window). `route()` below passes the flag unconditionally and lets an old
jar's own argument parser reject it, which is a fast, visible failure
instead of a silent hang, but only if that jar's parser actually rejects
unknown flags rather than falling through to the GUI, which was not true for
the one tested here.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True      # never leave __pycache__ in a project tree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kicad_digest
import kicad_geom
from _kicad_env import require_pcbnew, strip_wx_noise

# kicad_zonefill imports pcbnew at module scope (by the same design as this
# script's own export_dsn/import_ses), so it is imported lazily inside
# import_ses() below rather than at the top of this file. `route` and
# `adopt` must import and run cleanly under the plain system python3 with
# no KiCad interpreter anywhere on the machine; a top-level import here
# would silently take that away from them.

# Default candidate paths for a Freerouting jar, checked in order after
# --jar and FREEROUTING_JAR.  None of these are written by this script; a
# missing jar always prints the download command instead of fetching it.
JAR_CANDIDATES = (
    os.path.expanduser("~/.freerouting/freerouting.jar"),
    "/usr/local/share/freerouting/freerouting.jar",
    "/opt/freerouting/freerouting.jar",
)

FREEROUTING_RELEASES = "https://github.com/freerouting/freerouting/releases"
# The version this docstring's flag table and the install command below were
# verified against (GitHub releases API, see references/autorouting.md).
FREEROUTING_CURRENT = "2.4.1"

DEFAULT_PASSES = 20
# Freerouting can legitimately run for minutes on a dense board (the
# reference case in references/autorouting.md took ~2 minutes for 17
# passes); this is a safety ceiling against a genuinely hung process, not a
# tuning knob. Override with --timeout.
DEFAULT_TIMEOUT_S = 1200


# ------------------------------------------------------------- discovery

# Default candidate paths for a `java` binary, checked when neither --java
# nor JAVA_BIN is given. macOS carries two independent JREs that are NOT
# interchangeable for this jar: verified 2026-09-20, /usr/bin/java is OpenJDK
# 21.0.2 and loads freerouting-2.4.1.jar far enough to print
# `UnsupportedClassVersionError: ... class file version 69.0, this version of
# the Java Runtime only recognizes ... up to 65.0` (exit 0, no routing done);
# /opt/homebrew/opt/openjdk/bin/java is OpenJDK 25.0.2 (Homebrew) and runs the
# same jar cleanly. The jar's own minimum keeps climbing between releases, so
# `find_java` does not hardcode "prefer homebrew": it probes every candidate's
# own `java -version` and prefers the highest major version found, which is a
# proxy for "can run the jar", not a guarantee for jar versions not yet
# measured. `hw_install.py --check` runs the real headless smoke test.
JAVA_CANDIDATES = (
    "/opt/homebrew/opt/openjdk/bin/java",   # Homebrew, Apple Silicon
    "/usr/local/opt/openjdk/bin/java",      # Homebrew, Intel
    "/usr/bin/java",                        # macOS system java
)


def _java_major_version(path):
    """Major version integer from `java -version`, or None if unparseable."""
    try:
        proc = subprocess.run([path, "-version"], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              universal_newlines=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r'version "(\d+)(?:\.(\d+))?', proc.stdout or "")
    if not m:
        return None
    major = int(m.group(1))
    # Old-style version strings ("1.8.0_412") report major=1; the real major
    # version is the next dotted field.
    return int(m.group(2)) if major == 1 and m.group(2) else major


def find_java(explicit=None):
    """(path, how) for a `java` binary, or (None, reason).

    Among the unforced candidates (not --java, not JAVA_BIN), picks the one
    reporting the highest major version, not the first one on the list: see
    JAVA_CANDIDATES's comment for why path order alone is not safe here.
    """
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return explicit, "--java=%s" % explicit
        return None, "--java=%s (not an executable file)" % explicit
    env = os.environ.get("JAVA_BIN")
    if env:
        if os.path.isfile(env) and os.access(env, os.X_OK):
            return env, "JAVA_BIN=%s" % env
        return None, "JAVA_BIN=%s (not an executable file)" % env

    found = [(c, "default path %s" % c) for c in JAVA_CANDIDATES
             if os.path.isfile(c) and os.access(c, os.X_OK)]
    which = shutil.which("java")
    if which and which not in (c for c, _how in found):
        found.append((which, "PATH"))
    if not found:
        return None, ("not found (checked JAVA_BIN, %s, PATH)"
                      % ", ".join(JAVA_CANDIDATES))

    versioned = [(path, how, _java_major_version(path)) for path, how in found]
    versioned.sort(key=lambda t: (t[2] is None, -(t[2] or 0)))
    path, how, version = versioned[0]
    return path, ("%s (java %d)" % (how, version) if version else how)


def find_freerouting_jar(explicit=None):
    """(path, how) for a Freerouting jar, or (None, reason)."""
    if explicit:
        if os.path.isfile(explicit):
            return explicit, "--jar=%s" % explicit
        return None, "--jar=%s (no such file)" % explicit
    env = os.environ.get("FREEROUTING_JAR")
    if env:
        if os.path.isfile(env):
            return env, "FREEROUTING_JAR=%s" % env
        return None, "FREEROUTING_JAR=%s (no such file)" % env
    for cand in JAR_CANDIDATES:
        if os.path.isfile(cand):
            return cand, "default path %s" % cand
    return None, ("not found (checked --jar, FREEROUTING_JAR, %s)"
                  % ", ".join(JAR_CANDIDATES))


def jar_install_hint():
    return (
        "  fix: python3 scripts/hw_install.py --router\n"
        "       (downloads the pinned v%s jar to %s, verifies its SHA-256, "
        "and runs a\n"
        "       headless smoke test; see scripts/hw_install.py --check to "
        "report status\n"
        "       without downloading anything)\n"
        "       manual install: mkdir -p ~/.freerouting && curl -L -o "
        "~/.freerouting/freerouting.jar \\\n"
        "           %s/download/v%s/freerouting-%s.jar\n"
        "       or point at an existing copy: --jar PATH, or "
        "FREEROUTING_JAR=/path/to/freerouting.jar"
        % (FREEROUTING_CURRENT, JAR_CANDIDATES[0], FREEROUTING_RELEASES,
           FREEROUTING_CURRENT, FREEROUTING_CURRENT))


def java_install_hint():
    return (
        "  fix: install a JRE capable of running Freerouting v%s (its "
        "release notes\n"
        "       target Java 25). Verified 2026-09-20: macOS's own "
        "/usr/bin/java (OpenJDK 21)\n"
        "       loads the jar far enough to print "
        "UnsupportedClassVersionError and exit 0\n"
        "       with no routing done; `brew install openjdk` (OpenJDK 25 "
        "at\n"
        "       /opt/homebrew/opt/openjdk/bin/java on Apple Silicon) runs "
        "it cleanly.\n"
        "       `find_java` already checks that path automatically; if "
        "your JRE lives\n"
        "       somewhere else, put it on PATH or set "
        "JAVA_BIN=/path/to/java.\n"
        "       macOS: brew install openjdk    "
        "or: https://adoptium.net/temurin/releases/"
        % FREEROUTING_CURRENT)


# ---------------------------------------------------------------- export-dsn

def export_dsn(board_path, out_path):
    """Export a board to Specctra DSN. Returns (n_wires, n_fixed)."""
    pcbnew = require_pcbnew(__file__)
    if not os.path.exists(board_path):
        raise SystemExit("error: no such board: %s" % board_path)
    board = pcbnew.LoadBoard(board_path)
    n_locked = sum(1 for t in board.GetTracks() if t.IsLocked())
    ok = pcbnew.ExportSpecctraDSN(board, out_path)
    if not ok or not os.path.exists(out_path):
        raise SystemExit("error: ExportSpecctraDSN reported failure for %s"
                         % board_path)
    n_wires = n_fixed = 0
    with open(out_path) as fh:
        for line in fh:
            if "(wire " in line or "(wire\n" in line:
                n_wires += 1
                if "(type fix)" in line or "(type protect)" in line:
                    n_fixed += 1
    return n_wires, n_fixed, n_locked


# --------------------------------------------------------------------- route

def route(dsn_path, out_path, passes=DEFAULT_PASSES, jar=None, java_bin=None,
          timeout=DEFAULT_TIMEOUT_S, extra_args=None):
    """Invoke Freerouting headlessly. Returns (returncode, elapsed_s, log)."""
    if not os.path.exists(dsn_path):
        raise SystemExit("error: no such DSN file: %s" % dsn_path)

    java, java_how = find_java(java_bin)
    if not java:
        raise SystemExit("error: java not found (%s)\n%s"
                         % (java_how, java_install_hint()))

    jar_path, jar_how = find_freerouting_jar(jar)
    if not jar_path:
        raise SystemExit("error: freerouting jar %s\n%s"
                         % (jar_how, jar_install_hint()))

    # Keep any log/config output the router writes (Freerouting writes
    # logs/freerouting.log relative to its working directory) next to the
    # output SES instead of wherever this script happened to be invoked
    # from, a stray `logs/` directory landing in an unrelated repository
    # is exactly the kind of side effect a generator-only pipeline cannot
    # tolerate silently.
    workdir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(workdir, exist_ok=True)

    argv = [java, "-jar", jar_path,
            "-de", os.path.abspath(dsn_path),
            "-do", os.path.abspath(out_path),
            "-mp", str(passes),
            "-dct", "0",
            "--gui.enabled=false"]
    argv += list(extra_args or ())

    print("--- route: %s (jar via %s, java via %s) ---"
          % (os.path.basename(dsn_path), jar_how, java_how))
    print("  %s" % " ".join(argv))
    start = time.time()
    try:
        proc = subprocess.run(argv, cwd=workdir, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              universal_newlines=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(
            "error: freerouting did not exit within %ds\n"
            "  this is the exact failure mode documented in this script's "
            "docstring for a\n"
            "  pre-v2.1 jar, or any jar whose --gui.enabled flag was not "
            "recognised:\n"
            "  it opens a window instead of running headless and never "
            "returns.\n"
            "  fix: confirm --gui.enabled=false by running the jar once "
            "by hand, watching\n"
            "       for a window; upgrade to v%s if it predates that flag; "
            "or raise\n"
            "       --timeout if this is a genuinely large board still "
            "making progress.\n"
            "  the process may still be running; find and end it yourself "
            "(ps + kill),\n"
            "  this script will not do that on your behalf."
            % (timeout, FREEROUTING_CURRENT))
    elapsed = time.time() - start
    log = strip_wx_noise(proc.stdout or "")
    if proc.returncode != 0:
        tail = "\n".join(log.strip().splitlines()[-15:])
        raise SystemExit("error: freerouting exited %d after %.1fs\n%s"
                         % (proc.returncode, elapsed, tail))
    if not os.path.exists(out_path):
        raise SystemExit(
            "error: freerouting exited 0 after %.1fs but wrote no %s\n"
            "  this usually means the flags were parsed but the GUI path "
            "was still taken\n"
            "  (pre-v2.1 jar) and the window was closed before routing "
            "finished." % (elapsed, out_path))
    return proc.returncode, elapsed, log


# ----------------------------------------------------------------- import-ses

def _net_track_via_counts(board, pcbnew):
    counts = {}
    for t in board.GetTracks():
        counts[t.GetNetname()] = counts.get(t.GetNetname(), 0) + 1
    return counts


def import_ses(board_path, ses_path, out_path):
    """Import a session, save, refill zones. Returns a report dict."""
    pcbnew = require_pcbnew(__file__)
    import kicad_zonefill              # module-scope pcbnew import: see top of file
    if not os.path.exists(board_path):
        raise SystemExit("error: no such board: %s" % board_path)
    if not os.path.exists(ses_path):
        raise SystemExit("error: no such session file: %s" % ses_path)

    board = pcbnew.LoadBoard(board_path)
    before = _net_track_via_counts(board, pcbnew)
    n_tracks_before = sum(1 for t in board.GetTracks()
                          if t.Type() == pcbnew.PCB_TRACE_T
                          or t.Type() == pcbnew.PCB_ARC_T)
    n_vias_before = sum(1 for t in board.GetTracks()
                        if t.Type() == pcbnew.PCB_VIA_T)

    ok = pcbnew.ImportSpecctraSES(board, ses_path)
    if not ok:
        raise SystemExit("error: ImportSpecctraSES reported failure for %s"
                         % ses_path)
    pcbnew.SaveBoard(out_path, board)

    # ImportSpecctraSES replaces the whole routing solution (see the module
    # docstring's trap). Warn loudly on any net that had copper before and
    # has none after: that is the destructive case, not a design outcome.
    after = _net_track_via_counts(board, pcbnew)
    emptied = sorted(net for net, n in before.items()
                     if n and not after.get(net))

    # Zones are untouched by Specctra (it has no zone concept), so they must
    # be refilled against the newly-imported copper, exactly as any other
    # regeneration does. Reuse kicad_zonefill's own logic rather than
    # duplicating it.
    kicad_zonefill.fill(out_path, out_path, island_mode="area",
                        do_repatch=True, quiet=True)

    reloaded = pcbnew.LoadBoard(out_path)
    n_tracks_after = sum(1 for t in reloaded.GetTracks()
                         if t.Type() == pcbnew.PCB_TRACE_T
                         or t.Type() == pcbnew.PCB_ARC_T)
    n_vias_after = sum(1 for t in reloaded.GetTracks()
                       if t.Type() == pcbnew.PCB_VIA_T)

    return {
        "board_before": board_path, "session": ses_path, "board_after": out_path,
        "tracks_before": n_tracks_before, "vias_before": n_vias_before,
        "tracks_after": n_tracks_after, "vias_after": n_vias_after,
        "nets_emptied": emptied,
    }


# --------------------------------------------------------------- kicadroutingtools

# KiCadRoutingTools (github.com/drandyhaas/KiCadRoutingTools) reads and writes
# a `.kicad_pcb` directly with its own parser: no Specctra DSN/SES, no
# `pcbnew`, no `kipy`.  Measured on the hexpad board (`references/
# autorouting.md` §6, `kb/runs/hexpad-autoroute-2026-09-20.md`): 33/33
# single-ended nets and 63/63 multi-point pads routed, 0 failed, in 1.68s of
# its own reported routing time.

KRT_VENV_CANDIDATES = (os.path.expanduser("~/.hw_forge/venv"),)
KRT_ROOT_CANDIDATES = (os.path.expanduser("~/.hw_forge/KiCadRoutingTools"),)


def find_krt_root(explicit=None):
    """(path, how) for a KiCadRoutingTools checkout, or (None, reason)."""
    if explicit:
        if os.path.isdir(explicit):
            return explicit, "--krt-root=%s" % explicit
        return None, "--krt-root=%s (no such directory)" % explicit
    env = os.environ.get("KRT_ROOT")
    if env:
        if os.path.isdir(env):
            return env, "KRT_ROOT=%s" % env
        return None, "KRT_ROOT=%s (no such directory)" % env
    for cand in KRT_ROOT_CANDIDATES:
        if os.path.isfile(os.path.join(cand, "py_router", "route.py")):
            return cand, "default path %s" % cand
    return None, ("not found (checked --krt-root, KRT_ROOT, %s)"
                  % ", ".join(KRT_ROOT_CANDIDATES))


def find_krt_venv_python(explicit=None):
    """(path, how) for the venv python KiCadRoutingTools' own deps live in."""
    if explicit:
        if os.path.isfile(explicit) and os.access(explicit, os.X_OK):
            return explicit, "--krt-venv=%s" % explicit
        return None, "--krt-venv=%s (not an executable file)" % explicit
    env = os.environ.get("KRT_VENV")
    if env:
        py = os.path.join(env, "bin", "python3")
        if os.path.isfile(py) and os.access(py, os.X_OK):
            return py, "KRT_VENV=%s" % env
        return None, "KRT_VENV=%s (no bin/python3 under it)" % env
    for cand in KRT_VENV_CANDIDATES:
        py = os.path.join(cand, "bin", "python3")
        if os.path.isfile(py) and os.access(py, os.X_OK):
            return py, "default path %s" % cand
    return None, ("not found (checked --krt-venv, KRT_VENV, %s)"
                  % ", ".join(KRT_VENV_CANDIDATES))


def krt_install_hint():
    return (
        "  fix: python3 scripts/hw_install.py --routing-tools\n"
        "       or point at an existing checkout/venv: --krt-root PATH "
        "--krt-venv PATH,\n"
        "       or KRT_ROOT=/path/to/KiCadRoutingTools "
        "KRT_VENV=/path/to/venv\n"
        "       This script never downloads or clones anything itself; run "
        "the command yourself.")


def route_krt(board_path, out_path, power_nets=None, krt_root=None,
             venv_python=None, timeout=DEFAULT_TIMEOUT_S, extra_args=None):
    """Route a board with KiCadRoutingTools' `py_router/route.py`.

    Pure subprocess, no `pcbnew`: this call alone runs under any python3.

    It does NOT leave the board DRC-ready by itself.  KRT's own zone handling
    taps nets into a plane; it is not the same thing as refilling the
    `filled_polygon` cache `kicad-cli`'s DRC reads.  Measured: a KRT-routed
    hexpad board checked against `kicad_gate.py` before any refill reported
    251 `clearance` violations, all at `actual 0.0000 mm` against a stale
    zone fill (`references/autorouting.md` §6), the exact "zones carry a
    cached `filled_polygon`, stale the instant anything moves" trap
    `references/kicad-api.md` §4 already documents for scripted routing,
    reproduced here for an external router's output.  Call
    `refill_krt_output` (needs `pcbnew`) after this, or use the `route-krt`
    CLI subcommand below, which does both in one step, the same as
    `import-ses` does for the Freerouting flow.

    Three flags are always passed, because the router's defaults change what
    the gate measures:

    * `--no-fix-drc-settings`.  By default `route.py` rewrites the output's
      `.kicad_pro` Board Setup floors down to whatever it routed, so KiCad's
      DRC "only flags genuine problems".  Measured 2026-09-20: it lowered
      `min_hole_clearance` from 0.25 mm to 0.20 mm on the hexpad test board,
      and the gate then passed a board that carried 70 hole-clearance
      violations under the project's own rules.  That is a rule demotion the
      pipeline forbids (`references/kicad-api.md` §4), performed silently.
    * `--escalation board`.  The default, `fab`, lets a failing net retry at
      sizes below the board's own declared minimums.  `board` stops at the
      floors the project declares, which is what `kicad_gate.py` enforces.
    * `--strict-sizes`.  Exit 3 when any feature was delivered below its
      requested size, so a harness needs no grep of the log.

    Clearance: the router routes at the Default net class's copper clearance
    and has no separate copper-to-hole clearance.  When the project's
    `min_hole_clearance` is larger than its copper clearance (hexpad: 0.25 mm
    against 0.20 mm), this wrapper passes `--clearance` at the larger value
    so tracks keep the hole clearance too.  It over-constrains copper to
    copper by the difference, which is the honest price of a gate that holds.

    The sibling `.kicad_pro` and `.kicad_prl` of the input are copied beside
    the output before the zone refill, so the refill and the gate both read
    the project's real rules rather than whatever the router left there.
    """
    if not os.path.exists(board_path):
        raise SystemExit("error: no such board: %s" % board_path)
    root, root_how = find_krt_root(krt_root)
    if not root:
        raise SystemExit("error: KiCadRoutingTools %s\n%s"
                         % (root_how, krt_install_hint()))
    py, py_how = find_krt_venv_python(venv_python)
    if not py:
        raise SystemExit("error: KiCadRoutingTools venv %s\n%s"
                         % (py_how, krt_install_hint()))

    workdir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(workdir, exist_ok=True)
    argv = [py, os.path.join(root, "py_router", "route.py"),
            os.path.abspath(board_path), os.path.abspath(out_path),
            "--no-fix-drc-settings", "--escalation", "board", "--strict-sizes"]
    clearance = _route_clearance_for(board_path)
    if clearance is not None:
        argv += ["--clearance", "%.3f" % clearance]
    if power_nets:
        argv += ["--power-nets"] + list(power_nets)
    argv += list(extra_args or ())

    print("--- route-krt: %s (KRT via %s, venv via %s) ---"
          % (os.path.basename(board_path), root_how, py_how))
    print("  %s" % " ".join(argv))
    start = time.time()
    try:
        proc = subprocess.run(argv, cwd=workdir, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              universal_newlines=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit(
            "error: route.py did not exit within %ds\n"
            "  the process may still be running; find and end it yourself "
            "(ps + kill),\n"
            "  this script will not do that on your behalf." % timeout)
    elapsed = time.time() - start
    log = strip_wx_noise(proc.stdout or "")
    if proc.returncode == 3 and os.path.exists(out_path):
        # --strict-sizes: something was delivered below its REQUESTED size,
        # which with --escalation board is still at or above the project's
        # own floors.  Not a failure of the gate; say so and let the gate
        # decide.  Measured: 3 features on 1 net at 0.2044 mm against a
        # 0.20 mm floor and a wider requested width.
        for line in log.splitlines():
            if "delivered below the requested size" in line:
                print("  WARNING (router): %s" % line.strip())
                break
    elif proc.returncode != 0:
        tail = "\n".join(log.strip().splitlines()[-20:])
        raise SystemExit("error: route.py exited %d after %.1fs\n%s"
                         % (proc.returncode, elapsed, tail))
    if not os.path.exists(out_path):
        raise SystemExit(
            "error: route.py exited 0 after %.1fs but wrote no %s"
            % (elapsed, out_path))
    _copy_project_siblings(board_path, out_path)
    return proc.returncode, elapsed, log


def _project_rules(board_path):
    """The `rules` block of the board's sibling .kicad_pro, or {}."""
    pro = os.path.splitext(board_path)[0] + ".kicad_pro"
    try:
        with open(pro) as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return {}
    return (doc.get("board", {}).get("design_settings", {})
               .get("rules", {}) or {})


def _route_clearance_for(board_path):
    """Copper clearance to route at: the larger of the project's copper and
    hole clearance floors, or None to let the router read the Default class."""
    rules = _project_rules(board_path)
    copper = rules.get("min_clearance")
    hole = rules.get("min_hole_clearance")
    if copper is None and hole is None:
        return None
    values = [v for v in (copper, hole) if isinstance(v, (int, float))]
    chosen = max(values)
    if hole is not None and copper is not None and hole > copper:
        print("  note: routing at %.3f mm clearance (the project's hole "
              "clearance), above its %.3f mm copper clearance, because the "
              "router has no separate copper-to-hole rule" % (hole, copper))
    return chosen


def _copy_project_siblings(board_path, out_path):
    """Put the input's .kicad_pro and .kicad_prl beside the output, so the
    refill and the gate read the project's rules, not the router's."""
    src_base = os.path.splitext(board_path)[0]
    dst_base = os.path.splitext(out_path)[0]
    if os.path.abspath(src_base) == os.path.abspath(dst_base):
        return
    for ext in (".kicad_pro", ".kicad_prl"):
        src = src_base + ext
        if os.path.exists(src):
            shutil.copyfile(src, dst_base + ext)


def refill_krt_output(board_path, out_path=None):
    """Refill zones on a KRT-routed board (needs `pcbnew`).

    Mirrors `import_ses`'s own post-route step exactly, and for the same
    reason: whichever tool routed the board, `kicad-cli`'s DRC reads the
    zone's cached `filled_polygon`, and only a real fill after the new copper
    exists recomputes it.  Reports the same `nets_emptied`-shaped warning,
    because a net that had copper and has none after a refill is worth
    knowing about regardless of which backend produced the copper.
    """
    pcbnew = require_pcbnew(__file__)
    import kicad_zonefill              # module-scope pcbnew import: see top of file
    out_path = out_path or board_path
    if not os.path.exists(board_path):
        raise SystemExit("error: no such board: %s" % board_path)

    board = pcbnew.LoadBoard(board_path)
    before = _net_track_via_counts(board, pcbnew)
    kicad_zonefill.fill(board_path, out_path, island_mode="area",
                        do_repatch=True, quiet=True)

    reloaded = pcbnew.LoadBoard(out_path)
    after = _net_track_via_counts(reloaded, pcbnew)
    emptied = sorted(net for net, n in before.items()
                     if n and not after.get(net))
    n_tracks = sum(1 for t in reloaded.GetTracks()
                  if t.Type() == pcbnew.PCB_TRACE_T
                  or t.Type() == pcbnew.PCB_ARC_T)
    n_vias = sum(1 for t in reloaded.GetTracks()
                if t.Type() == pcbnew.PCB_VIA_T)
    return {"board": out_path, "tracks": n_tracks, "vias": n_vias,
           "nets_emptied": emptied}


# ---------------------------------------------------------------------- adopt

# Pure text parsing (via kicad_geom's s-expression reader), so adoption runs
# under any python3, no pcbnew, no bundled interpreter required.  Verified
# against KiCad 10.0.5's current board format (file `(version 20260206)`):
# segments, arcs and vias carry their net as a bare `(net "NAME")` string,
# no netcode table to resolve. A `(net CODE "NAME")` form, if a project's
# board format predates this, is handled the same way: the net name is
# whichever string atom is last inside the `(net ...)` node.


def _net_of(node):
    kids_ = kicad_geom.kid(node, "net")
    if kids_ is None:
        return ""
    strs = [a for a in kicad_geom.atoms(kids_)[1:]]
    return strs[-1] if strs else ""


def _extract_routes(path):
    root = kicad_geom.parse_file(path)
    if not root or root[0] != "kicad_pcb":
        raise SystemExit("error: %s is not a .kicad_pcb" % path)

    segments, arcs, vias = [], [], []
    for node in root:
        if not isinstance(node, list) or not node:
            continue
        head = node[0]
        if head == "segment":
            start, end = kicad_geom.kid(node, "start"), kicad_geom.kid(node, "end")
            width = kicad_geom.kid(node, "width")
            layer = kicad_geom.layer_of(node)
            if not (start and end and width):
                continue
            sx, sy = kicad_geom.nums(start, 2)
            ex, ey = kicad_geom.nums(end, 2)
            w = kicad_geom.nums(width, 1)[0]
            segments.append((_net_of(node), layer, round(sx, 4), round(sy, 4),
                             round(ex, 4), round(ey, 4), round(w, 4)))
        elif head == "arc":
            start = kicad_geom.kid(node, "start")
            mid = kicad_geom.kid(node, "mid")
            end = kicad_geom.kid(node, "end")
            width = kicad_geom.kid(node, "width")
            layer = kicad_geom.layer_of(node)
            if not (start and mid and end and width):
                continue
            sx, sy = kicad_geom.nums(start, 2)
            mx, my = kicad_geom.nums(mid, 2)
            ex, ey = kicad_geom.nums(end, 2)
            w = kicad_geom.nums(width, 1)[0]
            arcs.append((_net_of(node), layer, round(sx, 4), round(sy, 4),
                        round(mx, 4), round(my, 4), round(ex, 4), round(ey, 4),
                        round(w, 4)))
        elif head == "via":
            at = kicad_geom.kid(node, "at")
            size = kicad_geom.kid(node, "size")
            drill = kicad_geom.kid(node, "drill")
            layers = kicad_geom.kid(node, "layers")
            if not (at and size and drill and layers):
                continue
            vx, vy = kicad_geom.nums(at, 2)
            sz = kicad_geom.nums(size, 1)[0]
            dr = kicad_geom.nums(drill, 1)[0]
            lay = tuple(kicad_geom.atoms(layers)[1:])
            vias.append((_net_of(node), round(vx, 4), round(vy, 4),
                        round(sz, 4), round(dr, 4), lay))
    return segments, arcs, vias


ROUTING_TEMPLATE = '''\
"""Adopted routing, extracted from %(source)s by scripts/kicad_route.py adopt.

DO NOT HAND-EDIT.  Re-generate with:
    python3 scripts/kicad_route.py adopt %(source)s -o %(out)s

board-digest: %(digest)s

This file is a snapshot of copper positioned against the pad locations the
board had at adoption time.  ANY placement change to ANY footprint makes it
stale in full, see the staleness rule in scripts/kicad_route.py's module
docstring.  gen_pcb.py is expected to import SEGMENTS / ARCS / VIAS and
re-emit them as explicit tracks, so a wipe-and-rebuild replays this file
instead of invoking an autorouter, which is what keeps the regeneration
digest (kicad_digest.py) meaningful.
"""

# (net, layer, x0, y0, x1, y1, width), millimetres, board coordinates.
SEGMENTS = [
%(segments)s
]

# (net, layer, start_x, start_y, mid_x, mid_y, end_x, end_y, width)
ARCS = [
%(arcs)s
]

# (net, x, y, size, drill, (layer_a, layer_b))
VIAS = [
%(vias)s
]
'''


def adopt(board_path, out_path=None):
    segments, arcs, vias = _extract_routes(board_path)
    _n_lines, sha = kicad_digest.digest(board_path)

    def fmt_rows(rows):
        return "\n".join("    %r," % (row,) for row in rows) or "    # (none)"

    text = ROUTING_TEMPLATE % {
        "source": board_path,
        "out": out_path or "kicad/routing.py",
        "digest": sha,
        "segments": fmt_rows(segments),
        "arcs": fmt_rows(arcs),
        "vias": fmt_rows(vias),
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".",
                    exist_ok=True)
        with open(out_path, "w") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return {"segments": len(segments), "arcs": len(arcs), "vias": len(vias),
           "board_digest": sha, "out": out_path}


# ----------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export-dsn", help="board -> Specctra DSN (pcbnew)")
    p.add_argument("board")
    p.add_argument("-o", "--out", help="default: BOARD with .dsn extension")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("route", help="DSN -> SES via a headless Freerouting jar")
    p.add_argument("dsn")
    p.add_argument("-o", "--out", help="default: DSN with .ses extension")
    p.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    p.add_argument("--jar", help="path to freerouting.jar (else FREEROUTING_JAR, "
                                 "else %s" % ", ".join(JAR_CANDIDATES))
    p.add_argument("--java", help="path to a java binary (else JAVA_BIN, PATH)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                   help="seconds before giving up on a hung process "
                        "(default: %(default)ds)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("import-ses",
                       help="board + SES -> routed board (pcbnew), then "
                            "refill zones")
    p.add_argument("board")
    p.add_argument("ses")
    p.add_argument("-o", "--out", help="default: overwrite BOARD")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("route-krt",
                       help="board -> routed board via KiCadRoutingTools, "
                            "then refill zones (pcbnew); second autorouting "
                            "backend, same adopt step as the Freerouting flow")
    p.add_argument("board")
    p.add_argument("-o", "--out", help="default: BOARD with _krt_routed suffix")
    p.add_argument("--power-nets", nargs="+", metavar="NET",
                   help="glob patterns for power/plane nets, e.g. GND VCC")
    p.add_argument("--krt-root", help="path to a KiCadRoutingTools checkout "
                                      "(else KRT_ROOT, else "
                                      "~/.hw_forge/KiCadRoutingTools)")
    p.add_argument("--krt-venv", help="path to the venv holding its python "
                                      "deps (else KRT_VENV, else "
                                      "~/.hw_forge/venv)")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("adopt",
                       help="extract tracks/vias into a python data module")
    p.add_argument("board")
    p.add_argument("-o", "--out", help="default: print to stdout")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args()

    if args.cmd == "export-dsn":
        out = args.out or (os.path.splitext(args.board)[0] + ".dsn")
        n_wires, n_fixed, n_locked = export_dsn(args.board, out)
        if args.json:
            json.dump({"out": out, "wires": n_wires, "fixed_wires": n_fixed,
                      "locked_tracks_in_board": n_locked}, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print("  exported %s (%d wires, %d fixed/protected)"
                  % (out, n_wires, n_fixed))
            if n_locked and not n_fixed:
                print("  WARNING: %d track(s) are Locked in the board but 0 "
                      "wires came out `(type fix)`: the DSN export did not\n"
                      "           honour the lock. "
                      "Investigate before routing;\n"
                      "           an unprotected \"locked\" net will be "
                      "rerouted like any other." % n_locked)

    elif args.cmd == "route":
        out = args.out or (os.path.splitext(args.dsn)[0] + ".ses")
        rc, elapsed, log = route(args.dsn, out, passes=args.passes,
                                 jar=args.jar, java_bin=args.java,
                                 timeout=args.timeout)
        if args.json:
            json.dump({"out": out, "returncode": rc, "elapsed_s": round(elapsed, 1)},
                      sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print("  routed -> %s in %.1fs" % (out, elapsed))

    elif args.cmd == "import-ses":
        out = args.out or args.board
        report = import_ses(args.board, args.ses, out)
        if args.json:
            json.dump(report, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print("  %s + %s -> %s" % (args.board, args.ses, out))
            print("  tracks %d -> %d   vias %d -> %d"
                  % (report["tracks_before"], report["tracks_after"],
                     report["vias_before"], report["vias_after"]))
            if report["nets_emptied"]:
                print("  WARNING: %d net(s) had copper before and none after. "
                      "The session did\n"
                      "           not mention them, and ImportSpecctraSES "
                      "REPLACES routing rather\n"
                      "           than patching it (see this script's "
                      "docstring): %s"
                      % (len(report["nets_emptied"]),
                         ", ".join(report["nets_emptied"][:10])
                         + (" ..." if len(report["nets_emptied"]) > 10 else "")))
            print("  next: python3 scripts/kicad_gate.py <project_dir>")

    elif args.cmd == "route-krt":
        out = args.out or (os.path.splitext(args.board)[0] + "_krt_routed.kicad_pcb")
        rc, elapsed, log = route_krt(args.board, out, power_nets=args.power_nets,
                                     krt_root=args.krt_root,
                                     venv_python=args.krt_venv,
                                     timeout=args.timeout)
        report = refill_krt_output(out, out)
        if args.json:
            json.dump({"out": out, "elapsed_s": round(elapsed, 1), **report},
                      sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print("  routed -> %s in %.1fs" % (out, elapsed))
            print("  tracks %d   vias %d" % (report["tracks"], report["vias"]))
            if report["nets_emptied"]:
                print("  WARNING: %d net(s) had copper before the zone refill "
                      "and none after: %s"
                      % (len(report["nets_emptied"]),
                         ", ".join(report["nets_emptied"][:10])
                         + (" ..." if len(report["nets_emptied"]) > 10 else "")))
            print("  next: python3 scripts/kicad_gate.py <project_dir>")

    elif args.cmd == "adopt":
        report = adopt(args.board, args.out)
        if args.json:
            json.dump(report, sys.stdout, indent=2)
            sys.stdout.write("\n")
        elif args.out:
            print("  adopted %d segment(s), %d arc(s), %d via(s) -> %s"
                  % (report["segments"], report["arcs"], report["vias"],
                     args.out))
            print("  board-digest: %s" % report["board_digest"])


if __name__ == "__main__":
    main()
