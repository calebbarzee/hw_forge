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
