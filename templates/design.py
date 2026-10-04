"""<PROJECT> logical design: the single source of truth for every emitter.

Copy this file into your project as `design.py` and replace every <ANGLE>
placeholder.  Delete the sections you do not need; keep the section order, so
that anyone who has read one project's design.py can read them all.

What this file is
-----------------
The netlist, the part list and the placement grid, expressed once, in pure
python.  The schematic emitter and the board emitter both import it, so they
cannot disagree about what the circuit is.  If a fact about the design lives
in two files, it will drift; if it lives here, it cannot.

The three rules
---------------
1. Pure python, no dependencies.  This module is imported by the schematic
   emitter under the system python3 and by the board emitter under KiCad's
   bundled python, the only one with `pcbnew`.  Import nothing that is not in
   the stdlib: not pcbnew, not build123d, not your computer-aided design
   library.  The preflight check `import design.py` catches a violation of
   this rule.

2. One table per fact.  Anything that appears in both a symbol and a
   footprint (pin numbers, pin names, pad order, electrical types) is written
   once, as a table here, and both the symbol generator and the footprint
   generator derive their geometry from it by index.

   A hand-drawn symbol and a hand-drawn footprint for the same part will
   eventually disagree about pin 1, and that bug is invisible until the board
   is assembled.  See MCU_HEADER / pad_local() below for the pattern.

3. Every placement number is a named constant.  The design loop is "generate,
   read the design rule check (DRC) or verify JSON, nudge one constant,
   regenerate", so every lane, corridor, offset and margin has a name and
   lives at module scope.  A literal buried in an emitter cannot be nudged; a
   named constant can be changed in one place and re-gated in seconds.

Coordinates
-----------
State the convention and never deviate from it inside this file.  The
suggested one, because it matches most PCB layout tools' native frame:

    design space: origin at <ORIGIN>, +x east, +y north

KiCad's board space is +y south.  Emitters convert at their own boundary: one
conversion, in one function, on the way out.  Do not mix frames here.
"""

# =========================================================================
# Placement grid: the geometry every emitter shares
# =========================================================================
# Named constants, module scope, one per number the nudge loop may touch.

PITCH = 19.05                     # <WHAT IT IS>, both axes
EDGE_MARGIN = 10.0                # outline to the outermost feature
TRACK_W = 0.25                    # default signal track width
VIA_D, VIA_DRILL = 0.6, 0.3       # default via geometry

# Per-cell component offsets, relative to the cell centre, in design space.
# These are the classic nudge targets: when the DRC reports a collision, one
# of these moves by a tenth of a millimetre and the board is regenerated.
OFF_<PART> = (0.0, 4.9)
ROT_<PART> = 180.0


# =========================================================================
# Topology: rows, columns, cells, chains
# =========================================================================

ROWS = ["<row0>", "<row1>"]                     # ordered, north -> south
COLS = list(range(<N>))

# Cells that actually exist. Derive it; never maintain a hand-written list
# alongside a rule that generates it.
ALL_CELLS = [(c, r) for r in ROWS for c in COLS]

# If anything is chained (LEDs, shift registers, a daisy-chained bus), define
# the order here and let the emitters follow it.  A serpentine order (run a
# row, then hop to the next in the margin) keeps every in-row link a short hop
# between neighbours, which is what makes a chain routable without an
# autorouter.
CHAIN_ROWS = [("<row0>", +1), ("<row1>", -1)]   # (row, +1 east / -1 west)


def _chain_order():
    out = []
    for row, direction in CHAIN_ROWS:
        cols = [c for c in COLS if (c, row) in ALL_CELLS]
        out += [(c, row) for c in (cols if direction > 0 else cols[::-1])]
    return out


CHAIN = _chain_order()
ROW_DIR = dict(CHAIN_ROWS)


def travels_east(row, mirror=False):
    """True when this row's chain runs toward +x on the finished board."""
    return (ROW_DIR[row] > 0) != bool(mirror)


def part_rotation(row, mirror=False):
    """Rotate a chained part so its output faces the way the chain travels.

    Without this, every reverse-direction link has to cross its own cell and
    collides with the next link's departure.  The alternating rotation in the
    placement file is intentional, so say so in the fab notes; otherwise an
    assembler will "fix" it.
    """
    return 0.0 if travels_east(row, mirror) else 180.0


# =========================================================================
# Nets
# =========================================================================
# Net names are computed, never typed twice.  A function per net family means
# the schematic and the board ask the same question and get the same answer.

def cell_id(c, r):
    return "c%d_%s" % (c, r)


def cell_nets(c, r):
    """(column net, per-cell net, row net) for one cell."""
    return ("C%d" % c, cell_id(c, r), "R%s" % ROWS.index(r))


def chain_nets(cells):
    """{cell: (in_net, out_net)} following CHAIN, skipping absent cells.

    Walking CHAIN rather than the cell list means omitting an optional cell
    leaves the chain intact instead of breaking it in the middle.
    """
    out, previous, i = {}, "<CHAIN_INPUT_NET>", 0
    for cell in CHAIN:
        if cell not in cells:
            continue
        i += 1
        out[cell] = (previous, "L%02d" % i)
        previous = "L%02d" % i
    return out


# =========================================================================
# Part tables: symbol, footprint and value, together
# =========================================================================
# One tuple per part: the symbol library reference, the footprint reference,
# and the value.  Keeping them adjacent is what stops a part being changed in
# the schematic and not on the board.  Mark project-library parts explicitly
# and say why a stock part would not do, so the next reader can answer "why is
# there a custom footprint here?".

SYM_<PART> = ("<SymbolLib>", "<SymbolName>")
FP_<PART> = "<FootprintLib>:<FootprintName>"
VAL_<PART> = "<value>"

# Support parts.  Record the reason for each, not just the value, so the
# choice can be reviewed later.
SYM_CAP = ("Device", "C")
FP_CAP = "Capacitor_SMD:C_0603_1608Metric"
DECOUPLE_VALUE = "100n"           # one per <PART>, at its supply pad, because
                                  # <REASON: datasheet requirement, etc.>
BULK_CAPS = [("10u", "Capacitor_SMD:C_0805_2012Metric")]

SYM_MH = ("Mechanical", "MountingHole")
FP_MH = "MountingHole:MountingHole_2.2mm_M2"

# Mounting holes: the enclosure and the board must agree on these exactly, so
# they are defined once, here, and the case reads them back out of the board
# file (see scripts/kicad_geom.py) rather than being handed a copy.
MOUNT_HOLE_XS = (<X0>, <X1>, <X2>)
MOUNT_HOLE_YS = (<Y0>, <Y1>)
MOUNT_HOLES = [(x, y) for y in MOUNT_HOLE_YS for x in MOUNT_HOLE_XS]


# =========================================================================
# Package declarations: what a part IS, independent of what footprint got
# laid down for it
# =========================================================================
# `scripts/kicad_fpcheck.py` verifies a footprint's pad geometry against the
# physical package a part is supposed to be.  Without this table it can only
# compare a footprint against ITS OWN name, which is a self-consistency
# check, not a real one.  This table is what makes the check independent:
# the design says what the part is; the footprint is checked against that,
# not against itself.
#
# One flat dict, keyed by reference first, then by value.  A key is a
# packages.json family id (see that file's own `_read_me` field for the
# format and the full package list): "SOD-123", "SOIC-8-N", "SOIC-8-W",
# "0603", and so on.
#
#   python3 scripts/kicad_fpcheck.py board.kicad_pcb --design design.py
#
# This is the check that would have caught a real incident: an agent-
# designed board specified a SOIC-8 wide (7.5 mm body) flash chip and laid
# down SOIC-8/SOP-8 narrow (3.9 mm body) pads for it.  Every design rule
# check passed, because DRC has no notion of a part's physical package; the
# mismatch was found only after the files reached a fab for assembly.  See
# `kb/parts/package-family-traps.md`.
PACKAGES = {
    # "<ref>": "<PackageFamilyId>",      # e.g. "U3": "SOIC-8-W"
    # "<value>": "<PackageFamilyId>",    # e.g. "W25Q128JVSIQ": "SOIC-8-W"
}


# =========================================================================
# Board-inherent kinds: geometry that is never a bill of materials (BOM) row
# =========================================================================
# A mounting hole is a property of the board, not a component someone
# sources and solders onto it.  A BOM lists what still has to be bought and
# assembled onto a bare board; a hole is neither.  Measured failure this
# table exists to prevent: exporting a real project's BOM listed its four
# mounting holes as line items to source, right alongside its capacitors and
# switches (hexpad, 2026-09-20).  `kicad_bom.py audit` now fails that case as
# rule BOARD_INHERENT_IN_BOM.
#
# Six kinds are declared board-inherent, and none of them is ever a sourced
# part:
#
#   mounting_hole   a hole that takes a fastener; nothing is placed there
#   cutout          a non-plated opening cut into the board (a USB notch, a
#                   speaker port) that mounts or solders no part.  Plain
#                   board-edge geometry with no footprint at all needs no
#                   entry here -- it was never a symbol and kicad-cli never
#                   sees it.  Only give a cutout an entry when a project
#                   represents it with an actual footprint (an NPTH ring, a
#                   keepout marker with a reference designator).
#   fiducial        an optical reference mark for pick-and-place alignment
#   test_point      a bare pad or via meant for a probe, not a part
#   logo            silkscreen or copper artwork with no function
#   net_tie         a zero-ohm copper bridge that is board fabric, not a
#                   discrete part
#   edge_connector  a card-edge connector formed by the board's own copper
#                   and gold fingers, with no separate part to source
#
# If a real component sits in one of these locations -- a mounting hole that
# also carries a press-fit standoff, a test point that is actually a
# populated pogo-pin header -- that location is a sourced part, not a
# board-inherent one, and belongs in PARTS below instead of here.
#
# Declare the kind per reference, falling back to value, same lookup order
# as PACKAGES.  `scripts/kicad_bom.py audit` also applies a reference-prefix
# and library-name heuristic (H*, FID*, TP*, LOGO*, MountingHole:*,
# Fiducial:*, TestPoint:*) so an undeclared board-inherent part is still
# caught, but an entry here always wins over the heuristic.
BOARD_INHERENT = {
    # "<ref>": "mounting_hole",        # e.g. "H1": "mounting_hole"
}

# How the schematic emitter and the board emitter each act on BOARD_INHERENT,
# stated once here because both halves have to agree or the BOM audit fails
# on a part nobody meant to exclude.
#
# Schematic side: `kicad-cli sch export bom` drops any symbol instance whose
# placement carries `(in_bom no)`.  This is a bare boolean directly on the
# symbol instance, not a named property, and it is set per-instance, not
# inherited from the library symbol's own default -- verified against a real
# project's placed symbols, where every instance carried `(in_bom yes)` even
# though the *library* copy of `Mechanical:MountingHole` in the same file's
# `lib_symbols` cache said `(in_bom no)`.  KiCad does not enforce the
# library's default at placement time; the emitter must set it explicitly:
#
#   (symbol
#       (lib_id "Mechanical:MountingHole")
#       (at 444.5 368.3 0)
#       (unit 1)
#       (exclude_from_sim no)
#       (in_bom no)              <- board-inherent: excluded here
#       (on_board yes)
#       (dnp no)
#       ...)
#
# Board side: the footprint's `(attr ...)` list carries `exclude_from_bom`,
# and, for a kind with no reason to appear in a placement file (a mounting
# hole, a test point), `exclude_from_pos_files` too.  Quoted directly from
# KiCad 10's own shipped footprint library, not from memory:
#
#   MountingHole_2.2mm_M2.kicad_mod:  (attr exclude_from_pos_files exclude_from_bom)
#   TestPoint_THTPad_D2.0mm...mod:    (attr exclude_from_pos_files exclude_from_bom)
#   Fiducial_1mm_Mask2mm.kicad_mod:   (attr smd exclude_from_bom)
#
# Note a fiducial keeps `exclude_from_pos_files` OFF: its position is
# exactly what the assembly line's optical alignment step needs from the
# placement file. Contrast an ordinary sourced footprint, which carries only
# its type token and nothing else, e.g. `(attr smd)` or `(attr through_hole)`.
#
# `scripts/kicad_bom.py audit --board BOARD.kicad_pcb` checks both halves
# together and fails on either one missing.


# =========================================================================
# Part fields: what a buyer needs to source and assemble this design
# =========================================================================
# Every SOURCED part -- anything a buyer must order and an assembler must
# place, which is everything NOT declared in BOARD_INHERENT above -- carries
# a full field set here, keyed the same way PACKAGES is: by reference first,
# falling back to value.
#
# This is a separate table from PACKAGES on purpose.  PACKAGES feeds
# `kicad_fpcheck.py`'s pad-geometry check and keeps its existing key
# convention untouched; PARTS feeds the bill of materials that leaves the
# building.  For a sourced part the two should agree on package family, and
# `scripts/kicad_bom.py audit` reports it as a note when they do not.
#
# Fill this as `resource-scout` resolves each part in phase 1, not as a
# phase-5 afterthought.  A description written after the part has already
# shipped is a description nobody could have bought from.
# `scripts/kicad_bom.py audit SCHEMATIC.kicad_sch [--board ...] [--assembly
# jlcpcb]` checks every sourced part's completeness before export, and
# `scripts/kicad_fab.py`'s BOM step fails the same way on an empty required
# cell.  See `commands/hw-bom.md` for the fill-in procedure and the
# description standard, with worked examples of both.
#
# Required fields, and what makes each one acceptable:
#
#   description   a sentence a buyer can act on: function, key rating(s),
#                 package.  Never just the value.  "100nF X7R ceramic
#                 decoupling capacitor, 0603" is a description; "100n" is a
#                 value repeated.  At least four words, and not the value
#                 restated.
#   manufacturer  the maker of the actual part, not the distributor.
#   mpn           the manufacturer's own part number.
#   package       a packages.json family id (see PACKAGES above).
#   datasheet     a URL to the manufacturer's own datasheet, not a
#                 distributor product page.
#   lcsc          the LCSC part number (e.g. "C1525").  Required whenever
#                 the assembly service is JLCPCB.  Property name "LCSC",
#                 chosen to match what `scripts/kicad_fpcheck.py` already
#                 reads and the first field name the locally installed
#                 Fabrication Toolkit plugin resolves (`kb/fabs/jlcpcb.md`,
#                 "Pre-upload checks"); a differently named field uploads a
#                 BOM that looks complete and is silently unsourceable.
#   distributors  optional dict of other distributor part numbers, keyed by
#                 distributor name, e.g. {"digikey": "...", "mouser": "..."}.
#
# Fit and interface fields.  Required on every connector and every
# user-facing part (a button, a switch, a display, an LED seen through the
# case, a knob); optional elsewhere.  The board file carries none of them, and
# without them nothing can check that a plug reaches its socket or that the
# board fits its case with the real part heights.  Read by
# `scripts/kicad_geom.py --contract`, `scripts/kicad_ifcheck.py` and
# `scripts/case_verify.py`; the method is in docs/QUALITY.md.
#
#   mating_direction  "+x" "-x" "+y" "-y" "+z" "-z", in the FOOTPRINT-LOCAL
#                 axes of the library footprint as drawn: x right, y down
#                 (KiCad footprints are y-south), z out of the face the part
#                 mounts on.  It names the outward normal of the mating face:
#                 the way a plug is pulled out, the way the cable leaves, the
#                 side a user reaches from.  `kb/README.md` requires it on
#                 every connector card and `kb/interfaces/` lists it for stock
#                 footprints.  The placement rotation and a back-face flip are
#                 applied by kicad_geom.py; never pre-rotate it here.
#   height_mm     body height above the mounting face, mm, from the datasheet.
#                 Without it the height comes from the part's STEP model, and
#                 the contract says which source it used.
#   z_band        [lo, hi] above the mounting face, instead of height_mm, for
#                 a part that also reaches below it (a reverse-mount LED
#                 [-0.84, 0.79]; a socket hanging under its footprint).
#   interface     the standard a connector follows, as kicad_ifcheck.py names
#                 it: "usb-c-device", "jst-ph-2:battery", "header-2.54:swd".
#                 `scripts/interfaces/` and `kb/interfaces/` hold the
#                 definitions; references/interfaces.md argues them.
#   pin_map       optional {role: [pin, ...]} for a connector whose pins the
#                 standard does not fix, e.g. a battery pigtail's polarity:
#                 {"POS": ["2"], "NEG": ["1"]}.
#   interface_wiring  "module" when the connector is part of a module (a
#                 nice!nano's USB-C): only its mating rules are checked.
#   access        "internal" for a connector that mates inside the enclosure
#                 (a battery lead); default "external", which needs an edge
#                 and an opening.
#   edge_max_mm   how far inboard of its edge the mating face may sit
#                 (default 1.0 mm in kicad_geom.py; an interface definition
#                 may set its own).
#   mating_body   optional [x0, y0, x1, y1], footprint-local: the part of the
#                 body an opening is for (a slide switch's knob), with
#                 optional mating_z [lo, hi].
#   ifcheck_exempt  optional {rule_id: reason} for an interface rule this
#                 design deliberately does not meet; printed with the reason.
#
# The emitters write mating_direction, height_mm, interface and access onto
# the footprint as properties of exactly those names as well.  The forked
# kicad-cli's `connector_edge` DRC reads the `mating_direction` property too
# (+x -x +y -y +z -z in footprint axes, rotated by the footprint, y mirrored
# on the back face, +z and -z skipped), so the board, the DRC and the fit
# contract (kicad_geom.py --contract) read one source.  Without the property
# the DRC falls back to the shortest body to edge distance.  The old
# board-frame field `Mating_Direction` (N/S/E/W) is no longer read (fork
# master, 2026-10-03).
#
# A part is a connector to the fit contract when this table gives it a role,
# an interface or a mating_direction, or its reference prefix is J, P, USB,
# CN or X, or its footprint library starts with Connector.  Every such part
# needs mating_direction, or the contract fails ("undeclared
# mating_direction").
#
# The schematic emitter writes every field present here into the schematic
# symbol as a property of the same, capitalised name: Description,
# Manufacturer, MPN, Package, Datasheet, LCSC.  Exactly the same mechanism
# every other symbol property already uses (Reference, Value, Footprint),
# quoted from a real project's placed symbol:
#
#   (property "Description" "100nF X7R ceramic capacitor, 0603"
#       (at 444.5 368.3 0)
#       (effects (font (size 1.27 1.27)) (hide yes)))
#
# A part with no entry here, or an entry missing a required field, is what
# `kicad_bom.py audit` reports as a FAIL, one rule per missing or
# insufficient field, naming the rule that fired.
PARTS = {
    # "<ref>": {                        # e.g. "C1"
    #     "description": "<sentence: function, rating(s), package>",
    #     "manufacturer": "<name>",
    #     "mpn": "<manufacturer part number>",
    #     "package": "<packages.json family id>",
    #     "datasheet": "<manufacturer datasheet URL>",
    #     "lcsc": "<LCSC part number>",
    #     "distributors": {"digikey": "<part number>"},
    # },
    # "<connector ref>": {               # e.g. "J1", a USB-C receptacle
    #     ...the sourcing fields above...,
    #     "interface": "usb-c-device",
    #     "mating_direction": "+y",      # GCT USB4105: kb/interfaces/
    #     "height_mm": 3.31,             # datasheet body height
    # },
}


# =========================================================================
# Pin-map table: the "one table, two emitters" doctrine
# =========================================================================
# The pattern that matters most in this file.
#
# List the part's pins once, in physical order, with their names and numbers.
# The symbol generator derives pin positions from the list index; the
# footprint generator derives pad positions from the same index via
# pad_local().  Neither has hand-authored geometry, so the symbol and the
# footprint cannot disagree about which pin is where.  That disagreement is
# invisible on screen and fatal on an assembled board.
#
# Order the list by physical position and say, in a comment, which physical
# position index 0 is.  Keep the manufacturer's own pin numbers as data, so
# the numbering can be non-sequential (as module pinouts usually are) without
# the geometry caring.
#
# Verify the pinout against two independent sources (datasheet plus a known-
# good reference design or library) and record both here.

# <PART> physical header, viewed from the component side with <REFERENCE
# FEATURE> at the top.  Source 1: <datasheet + page>.  Source 2: <reference>.
#   pads <a>..<b>  <first column, direction>
#   pads <c>..<d>  <second column, direction>
PIN_TABLE = [
    ("<num>", "<name>"),
    # ...
]

# Electrical type per pin, for the electrical rule check (ERC).  Getting these
# right is what makes ERC worth running: a supply pin typed as a passive input
# will never report the missing driver.  Note where a rail comes from: a
# module's regulator output is a power_out, and that fact often decides the
# whole power topology.
PIN_TYPE = {
    "<VCC>": "power_out",         # <e.g. module's own LDO, gated by <PIN>>
    "<GND>": "power_in",
    "<RST>": "input",
}

# Verified pin map: silkscreen/datasheet pin name -> net name.
PIN_NETS = {
    "<pin name>": "<net>",
}

ROW_PITCH = 2.54                  # pad-to-pad down one column
COL_SPACING = 15.24               # between the two columns


def pad_local(pad):
    """Pad position relative to the part centre, as (along, across).

    Derived from PIN_TABLE's index, so the symbol generator, the footprint
    generator and the board placement all read the same table.  Change the
    table and every emitter follows; there is no second copy to update.
    """
    names = [p for p, _ in PIN_TABLE]
    idx = names.index(pad)
    per_column = len(PIN_TABLE) // 2
    span = (per_column - 1) * ROW_PITCH / 2.0
    half = COL_SPACING / 2.0
    if idx < per_column:
        return (round(-span + idx * ROW_PITCH, 2), -half)
    return (round(span - (idx - per_column) * ROW_PITCH, 2), half)


def pad_for_net(net):
    """First pad carrying `net`, or None. Lets emitters ask by net, not by pin."""
    for pad, name in PIN_TABLE:
        if PIN_NETS.get(name) == net:
            return pad
    return None


# =========================================================================
# Downstream translations
# =========================================================================
# If a firmware or driver layer needs different names for the same pins, put
# the translation here rather than letting two vocabularies leak into other
# files.  Compatibility labels are usually not the underlying port names, and
# assuming they match is a classic error.

PORT_NAME = {
    "<board label>": "<real port>",
}


# =========================================================================
# Geometry helpers
# =========================================================================

def cell_pos(c, r):
    """Design-space centre of one cell, mm."""
    return (c * PITCH, ROWS[::-1].index(r) * PITCH)


if __name__ == "__main__":
    # A design module should be inspectable on its own: print the summary and
    # assert the invariants, so `python3 design.py` is a cheap sanity check
    # before either emitter runs.
    assert len(PIN_TABLE) == len(set(n for n, _ in PIN_TABLE)), \
        "duplicate pad numbers in PIN_TABLE"
    print("cells: %d, chain: %d, mounting holes: %d"
          % (len(ALL_CELLS), len(CHAIN), len(MOUNT_HOLES)))
