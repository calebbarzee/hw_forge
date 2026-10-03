# Interfaces: what each standard connector requires

Generic rules. One section per standardized interface: the governing standard, the
connector families and their stock KiCad footprints, the pinout, the circuit the
standard requires, polarity and keying, mating geometry, panel opening, retention, and
the failure modes with the check that catches each. Part numbers, measured
footprint numbers and project incidents live in `kb/interfaces/`. Cross-domain rules
for ESD and cabling are in section 0.4 here and in `domains.md` section 9.

Every number carries a source tag such as `[S3]`, defined in appendix B. A number with
no reachable source is marked `(NV)`, short for needs-verification, and is listed in
appendix C. Treat an NV number as a prompt to read the named document, not as a design
input.

## 0. How to read this file

### 0.1 Definitions

| Term | Meaning here |
|---|---|
| Receptacle | The fixed connector soldered to the board. Also called the header, jack, or socket. |
| Plug | The mating part on the cable. Its housing, boot, or overmold is the mated-plug envelope. |
| `mating_direction` | The outward normal of the receptacle's mating face, stated in the footprint's own local axes as `+x`, `-x`, `+y`, `-y`, `+z`, or `-z`. It is the direction from the receptacle toward the plug, and the direction a straight cable leaves. KiCad footprints are y-south: `+y` points toward the bottom of the footprint editor, `+z` points out of the component face. The field is required by `kb/README.md`, and `mechanical.md` section 7 turns it into board and case axes. |
| Mated-plug envelope | The bounding box of the plug as it sits mated: housing, latch, overmold, boot, and the first bend of the cable. The receptacle's own outline understates it. |
| Panel opening | The hole or slot in a wall that the receptacle's mating face, or the plug, must pass through. |
| Rule ID | A short name for one checkable rule, such as `UC-DEV-01`. A checker implements a rule and reports its ID. |
| Check class | How a rule is established: `netlist` (nets and parts in `design.py` or the schematic), `pads` (a footprint's pad geometry), `placement` (a part's position against the board outline), `case` (the enclosure `verify()`), `manual` (a human or agent review step with no script). |

### 0.2 What the generic gates see

ERC, DRC with schematic parity, the unconnected count, and `kicad_fpcheck.py` see
nets, copper, and pad geometry against a declared package. They do not see any of the
following, and each is a rule in this file:

- A required pulldown, pullup, fuse, or TVS that was never drawn. ERC passes a USB-C
  device with no CC resistor.
- A receptacle that faces the wrong way, or sits 3 mm inboard of the board edge behind a
  wall too thick for the plug.
- A panel opening cut for the receptacle's shell when the plug's overmold is larger.
- A shield pad left floating, or a pin 1 that a footprint puts at the other end from the
  cable's pin 1.
- Two connector families with near-identical names and different pitches. JST PH (2.0
  mm) and XH (2.5 mm) differ by 0.5 mm per pin and look alike. `kicad_fpcheck.py` catches
  this when the design declares the package (section 4 and `packages.json`).

### 0.3 Rule table format

Each interface section ends with a table of rules:

```
ID | Rule | Check | Class
```

The Rule column is a sentence a checker can implement, such as `CC1 and CC2 each carry
a 5.1 kΩ ±10 % resistor to GND on a device port`. The Check column names the evidence:
the nets and parts to query, or the coordinates to compare. Severity is FAIL unless the
rule says WARN. The tables are written so they can be transcribed into the format
`scripts/interfaces.schema.json` defines, which `kicad_ifcheck.py` loads from
`scripts/interfaces/*.json` and from `kb/interfaces/` cards. The tables here are the
human-readable source; a definition file carries the same rule ids.

### 0.4 Cross-cutting rules (apply to every external connector)

These are stated once and referenced from each section.

| ID | Rule | Check | Class |
|---|---|---|---|
| `X-ESD-01` | Every signal pin of a connector that a user can touch has an ESD clamp, or a written reason it does not (an internal-only connector, or a pin that already has a stated protection path). | Query the nets on each external connector pin for a TVS or varistor part between the net and GND, or a design-record exemption. | netlist |
| `X-ESD-02` | A TVS sits within 5 mm of the connector pad it protects, with its ground return through a via or pour directly under or beside it. (NV: the 5 mm figure is a common vendor layout rule, not from one standard.) | Measure TVS pad to connector pad distance on the board. | placement |
| `X-SHD-01` | Every shield pad of a connector is tied to a stated net. The net is GND, or chassis through a stated network (for example 1 MΩ in parallel with 4.7 nF, NV). A shield pad on an unnamed net is a FAIL. | List pads with names `SH`, `S`, `MP`, or a repeated mounting number, and their nets. | netlist |
| `X-ORI-01` | The connector's `mating_direction`, rotated by its placement angle and face, points outboard (toward a board edge or a wall opening) or toward a stated internal mate. | Rotate the card's `mating_direction` through the part's rotation and flip, as in `kicad-api.md` section 4, and compare to the nearest outline edge. | placement |
| `X-EDGE-01` | A receptacle whose mating face is meant to be reached from outside has that face flush with the board edge, overhanging it by at most 0.5 mm, or inset from it by at most 0.5 mm, unless the case provides a captured opening sized to the plug envelope (see `kb/keyboards/usb-c-port-opening.md`). | Distance from the receptacle's front outline to the board edge. | placement |
| `X-PAD-01` | The footprint's pad geometry matches the declared package (`kicad_fpcheck.py` with a `PACKAGES` entry from `packages.json`). | Run `kicad_fpcheck.py --design`. | pads |
| `X-1ST-01` | Pin 1 of the footprint is pin 1 of the connector, and the schematic symbol's pin 1 net is the net the pinout table below assigns. | Compare symbol pin to net against the section's pinout. | netlist |

---

## 1. USB Type-C (receptacle, USB 2.0 16-pin and full-featured 24-pin)

### 1.1 Standard

USB Type-C Cable and Connector Specification, USB Implementers Forum (USB-IF). Release
1.0 (2014-08-11) chapter 4 was read for the CC, Rp, Rd, and Ra values `[S2]`. The current
release is 2.3, published as IEC 62680-1-3:2024 `[S2]`. USB 2.0 data signalling is the
USB 2.0 specification. Power above 5 V and 3 A is USB Power Delivery (USB PD).

Mechanical numbers for one 16-pin receptacle are from the GCT USB4105 drawing, read in
full `[S1]`. The receptacle shell length of 6.20 ±0.02 mm is a reference dimension per
the Type-C ECN "Receptacle shell length" `[S2b]`.

### 1.2 Families and stock KiCad footprints

| Family | Contacts | Stock footprint (KiCad 10 `Connector_USB.pretty`) | packages.json key |
|---|---|---|---|
| USB 2.0 16-pin top mount | 16 contact pads (power and ground pads of the A and B rows share positions) plus 4 shield pads | `USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal` | `USB-C-16P-GCT-USB4105` |
| USB 2.0 16-pin SMT | same | `USB_C_Receptacle_HRO_TYPE-C-31-M-12` | `USB-C-16P-HRO-TYPE-C-31-M-12` |
| Full-featured 24-pin | 24 contact pads plus 4 shield pads | `USB_C_Receptacle_Amphenol_12401610E4-2A` | `USB-C-24P-Amphenol-12401610E4` |

Other stock footprints exist (JAE DX07, GCT USB4110, USB4085, Molex 105450). Pad
lengths, shield-tail layout, and row spacing differ per vendor, so a footprint from one
vendor is not interchangeable with another's part. Declare the exact part.

Pad geometry read from the library with `kicad_fpcheck.py -v` `[S11]`:

| Footprint | Pads counted | Outer span (long x short) | Contact pitch |
|---|---|---|---|
| GCT USB4105 16P | 20 | 9.64 x 6.23 mm | 0.50 mm (0.30 mm wide pads, 1.15 mm long) |
| HRO TYPE-C-31-M-12 | 20 | 9.64 x 6.62 mm | 0.50 mm (1.45 mm long pads) |
| Amphenol 12401610E4-2A | 28 | 9.78 x 8.91 mm | 0.50 mm (0.30 x 0.70 mm pads) |

### 1.3 Pinout

16-pin USB 2.0 receptacle, from the GCT drawing `[S1]`:

| Pin | Signal | Pin | Signal |
|---|---|---|---|
| A1 | GND | B12 | GND |
| A4 | VBUS | B9 | VBUS |
| A5 | CC1 | B8 | SBU2 |
| A6 | Dp1 (D+) | B7 | Dn2 (D-) |
| A7 | Dn1 (D-) | B6 | Dp2 (D+) |
| A8 | SBU1 | B5 | CC2 |
| A9 | VBUS | B4 | VBUS |
| A12 | GND | B1 | GND |

Shell: tied to GND (the GCT drawing lists SHELL as GND) `[S1]`. On the GCT footprint the
power and ground pads of the two rows (A1 and B12, A4 and B9, A9 and B4, A12 and B1)
sit at the same x position, so each coordinate carries two pad numbers. The signal pads
interleave at 0.5 mm pitch: A5 at x = -1.25, B8 at -1.75, B7 at -0.75, A6 at -0.25, A7 at
+0.25, B6 at +0.75, A8 at +1.25, B5 at +1.75 mm `[S11]`. The 16-pin parts therefore show
16 contact positions as 12 distinct coordinates.
Pin names A2, A3, A10,
A11, B2, B3, B10, B11 are the SuperSpeed lanes, present only on 24-pin parts:
A2 SSTXp1, A3 SSTXn1, A10 SSRXn2, A11 SSRXp2, B2 SSTXp2, B3 SSTXn2, B10 SSRXn1, B11
SSRXp1 (NV: pin numbers not read in this session, taken from the Type-C specification
as commonly reproduced; Table 4-1 in `[S2]` lists the signals without pin numbers).

On a 16-pin receptacle, join Dp1 to Dp2 and Dn1 to Dn2 on the board with the shortest
possible stub, because the plug orientation decides which pair is live. Leave SBU1 and
SBU2 unconnected unless an alternate mode uses them. A floating SBU appears open
(at least 950 kΩ per Table 4-17 `[S2]`).

### 1.4 Device port (UFP, sink: the board takes power from the cable)

Per Table 4-14 `[S2]`, a sink port presents Rd, a resistor to GND, on each CC pin.

| Rd implementation | Nominal | Can detect advertised current | Max CC voltage |
|---|---|---|---|
| Resistor to GND, ±20 % | 5.1 kΩ | no | 2.18 V |
| Resistor to GND, ±10 % | 5.1 kΩ | yes | 2.04 V |
| Voltage clamp, ±20 % | 1.1 V | no | 1.32 V |

Requirements stated as rules:

- CC1 and CC2 each have their own 5.1 kΩ resistor to GND. They are not shared, and not
  tied to one resistor. A single resistor on CC1 only makes a plug fit in one orientation.
- Use ±1 % or ±5 % parts so the ±10 % window holds across temperature, when the product
  must detect 1.5 A or 3 A advertisements.
- A device with no data connection to the host (a power-only gadget) still needs both Rd
  resistors. Without them a Type-C to Type-C cable from a compliant source supplies no
  VBUS. A Type-A to Type-C cable has Rp built into its plug, so a bench test with that
  cable passes while the product fails with a C-to-C charger. This is the commonest
  failure and the reason the rule exists.
- VBUS: bulk capacitance at a cold attach is limited by the source. USB 2.0 limits the
  capacitance a device may present at hot attach to 10 µF without inrush limiting (NV:
  USB 2.0 specification section 7.2.4.1, not read). Add a load switch or soft start if
  the bulk exceeds that.
- VBUS reverse protection: not required by the standard. A sink that also has a battery
  charger needs a path that blocks battery current into VBUS when VBUS is absent
  (`domains.md` section 8).
- D+ and D-: no series resistor is required by the USB 2.0 specification. Some MCUs
  specify 22 Ω series resistors for full speed (NV: per MCU datasheet). Keep the pair
  length matched and the 90 Ω differential impedance (`domains.md` section 3).
- Source of more than 5 V: a PD sink controller negotiates it. CC pins of PD devices must
  tolerate VBUS shorted to CC. Select a CC-protected PD controller or add clamps (NV: the
  20 V CC tolerance requirement is stated by several vendors for PD sinks; confirm in the
  chosen controller's datasheet).

Protection that the standard strongly recommends (NV: ESD levels are IEC 61000-4-2 by
convention, not a Type-C normative requirement):

- A TVS on VBUS whose standoff voltage is at least the highest negotiated voltage.
- A low-capacitance ESD array on D+ and D- (a few pF at most; check the part's
  datasheet capacitance against the USB 2.0 high-speed budget).
- ESD on CC1 and CC2. These lines connect to user-reachable pins.
- A fuse or resettable fuse is optional on a sink. The source limits current.

### 1.5 Host port (DFP, source: the board supplies VBUS)

Per Table 4-13 `[S2]`, a source presents Rp, a pullup, on each CC pin. The Rp value
advertises the current the source can supply.

| Advertised current | Resistor to 4.75 to 5.5 V | Resistor to 3.3 V ±5 % | Current source to 1.7 to 5.5 V |
|---|---|---|---|
| Default USB power | 56 kΩ ±20 % | 36 kΩ ±20 % | 80 µA ±20 % |
| 1.5 A at 5 V | 22 kΩ ±5 % | 12 kΩ ±5 % | 180 µA ±8 % |
| 3.0 A at 5 V | 10 kΩ ±5 % | 4.7 kΩ ±5 % | 330 µA ±8 % |

Note 1 of Table 4-13 `[S2]`: a Rp placed in a Type-C to Type-A or Micro-B cable plug, or
on a captive cable, is 56 kΩ ±5 %.

Requirements stated as rules:

- Rp on both CC1 and CC2, one resistor each. Each CC pin's pullup reference is the rail
  named in the table row used.
- The advertised current is no more than the current limit the VBUS switch enforces. A
  3 A Rp behind a 1 A limiter is a defective port.
- VBUS is switched through a current-limited load switch. VBUS is off until a sink
  attaches. When VBUS is not sourced, impedance from VBUS to GND is at least 72.4 kΩ
  (Table 4-2 `[S2]`).
- VCONN: needed only when the port must power an electronically marked cable. A basic
  host with no SuperSpeed lanes need not source VCONN (section 4.4.3 `[S2]`).
- Add a fuse or a current-limit switch with a fault output. Add VBUS discharge so the
  rail falls to near 0 V after detach (tVBUSOFF is at most 650 ms, Table 4-18 `[S2]`).

### 1.6 Mating geometry, panel opening, retention

| Item | Value | Source |
|---|---|---|
| Receptacle opening (plug shell goes inside) | 8.34 +0.06/-0.02 x 2.56 ±0.04 mm | `[S1]` |
| Plug shell (the metal part) | about 8.25 x 2.40 mm | (NV: from vendor plug drawings quoted in search results; confirm in the Type-C specification chapter 3) |
| Receptacle body (GCT USB4105) | 8.94 x 7.35 mm, 3.31 mm tall | `[S1]` |
| Plug overmold maximum | 12.35 x 6.50 mm | `kb/keyboards/usb-c-port-opening.md` citing the Type-C plug mechanical limit; 6.5 mm height also on `[S1]` |
| Receptacle shell length | 6.20 ±0.02 mm, reference | `[S2b]` |
| Mating force, unmating force | 5 to 20 N, 6 to 20 N after test | `[S1]` |
| Durability | 20 000 cycles (GCT part) | `[S1]` |
| Current rating (GCT USB4105) | 5.00 A on all VBUS pins together, 1.25 A on CC, 0.25 A per other pin | `[S1]` |

`mating_direction` for the stock footprints, in footprint-local axes:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| GCT USB4105 16P top mount | `+y` | Its `Dwgs.User` line at y = +3.675 is labelled `PCB Edge`; the fab outline runs y -3.675 to +3.675 with contact tails at y = -3.68 `[S11]` |
| HRO TYPE-C-31-M-12 | `+y` (inferred) | Same body shape and tail position; the footprint has no edge marker. Needs one more source |
| Amphenol 12401610E4-2A | `+y` (inferred) | Contact pads at y = -5.02 and -3.32, fab outline y -5.22 to +5.23; no edge marker |

Panel opening rules:

- A closed window with real wall in front of the receptacle must admit the overmold
  (12.35 x 6.50 mm), not the shell. With the 0.5 mm per side clearance used in the
  knowledge base, the minimum is 13.35 x 7.50 mm, derived. The knowledge base rounds the
  width up to 13.50 mm (`kb/keyboards/usb-c-port-opening.md`).
- Past about 0.5 mm of recess between the wall's outer face and the mated shell, a
  closed window sized for the shell alone stops being sufficient. Use a notch open
  toward a board face, or a window sized for the overmold plus the recess depth (that
  card gives the measured case: a 2.625 mm recess blocked mating).
- A window sized for the receptacle's own shell opening plus 0.2 mm per side (8.74 x
  2.96 mm, derived) is acceptable only when the receptacle's front face is flush with
  the outer wall face, so the overmold butts against the wall.

Retention and strain: surface-mount signal pads alone do not carry the plug's lateral
load. Solder all shield tails. The stock footprints give the 4 shield tails
plated through-hole or large pads. A wall that supports the plug's boot reduces the
moment on the tails.

### 1.7 Failure modes and checks

| ID | Rule | Check | Class |
|---|---|---|---|
| `UC-DEV-01` | CC1 and CC2 each carry a 5.1 kΩ ±10 % pulldown to GND on a device port, as two separate resistors. | Find the nets on pads A5 and B5. Each has exactly one resistor to GND of 4.59 to 5.61 kΩ. A resistor shared between both CC nets, or a missing resistor, FAILs. | netlist |
| `UC-DEV-02` | A device port shows no resistance to VBUS on CC. | Nets on A5 and B5 have no pullup part. | netlist |
| `UC-HOST-01` | CC1 and CC2 each carry an Rp from Table 4-13 to a rail within its stated range, one resistor each. | Find resistor value and the rail it ties to. Value in the row's tolerance band. | netlist |
| `UC-HOST-02` | The advertised current in Rp is at most the load-switch current limit on VBUS. | Compare Rp row to the switch part's limit in `design.py`. | netlist |
| `UC-ALL-01` | All VBUS pads (A4, A9, B4, B9) share one net, and all GND pads (A1, A12, B1, B12) share one net. | Connectivity of those pads. | netlist |
| `UC-ALL-02` | On a 16-pin part, Dp1 and Dp2 are joined, and Dn1 and Dn2 are joined, within 5 mm of the pads (NV: layout heuristic). SBU1 and SBU2 are on no net, or unused-pin nets. | Net membership and track length. | netlist |
| `UC-ALL-03` | Every shield pad is on GND or a stated chassis network. All four shield tails exist as pads. | Pads `SH` per `X-SHD-01`. | netlist |
| `UC-ALL-04` | A TVS or ESD array covers VBUS, D+ and D-, and CC1 and CC2, within 5 mm of the receptacle, or the exemption is recorded. | `X-ESD-01` and `X-ESD-02`. | netlist |
| `UC-ALL-05` | The receptacle's `mating_direction`, after the part's rotation and flip, points outboard, and the front outline is flush with the board edge, overhangs it by at most 0.5 mm, or is inset from it by at most 0.5 mm (`X-EDGE-01`). | `X-ORI-01` and `X-EDGE-01` against the outline. | placement |
| `UC-ALL-06` | The case opening admits the 12.35 x 6.50 mm overmold plus 0.5 mm per side, or is a notch open to a board face. | `verify()` in the case generator: opening width at least 13.35 mm and height at least 7.50 mm. | case |
| `UC-ALL-07` | Footprint matches the declared vendor part. | `X-PAD-01` with the key in section 1.2. | pads |

---

## 2. USB 2.0 Micro-B (device receptacle)

### 2.1 Standard

Universal Serial Bus Micro-USB Cables and Connectors Specification, Revision 1.01
(2007-04-04), with the USB 2.0 specification for signalling `[S16]`. The specification PDF was located but not
loaded, so mechanical figures below are NV unless tagged.

### 2.2 Families and stock footprints

| Family | Stock footprint (`Connector_USB.pretty`) |
|---|---|
| Micro-B SMD with through-hole shell tabs | `USB_Micro-B_Molex-105017-0001`, `USB_Micro-B_Amphenol_10118194-0001LF_Horizontal`, `USB_Micro-B_GCT_USB3076-30-A` |

Geometry read from the library `[S11]`: Molex 105017-0001 has 5 signal pads 0.40 x 1.35
mm at a 0.65 mm pitch (x = -1.3 to +1.3), outer copper span 8.20 x 4.375 mm, with two
through-hole shield pads and four SMD shield pads. Amphenol 10118194-0001LF is the same
pitch (x = -1.3 to +1.3) with outer span 7.89 x 4.15 mm.

### 2.3 Pinout

| Pin | Signal | Notes |
|---|---|---|
| 1 | VBUS | 5 V from the host |
| 2 | D- | |
| 3 | D+ | |
| 4 | ID | Floating on a device (B plug). Tied to GND at an A-plug in an OTG adapter. |
| 5 | GND | |
| Shell | GND or chassis | `X-SHD-01` |

(NV: pin names are the standard Micro-B assignment, from the Micro-USB specification
`[S16]`, not re-read here.)

### 2.4 Required circuit

- A device port presents no CC. VBUS is received on pin 1. Leave ID unconnected on a
  device-only product. A product that supports OTG reads ID with a pullup.
- A full-speed device presents a 1.5 kΩ ±5 % pullup from D+ to a 3.3 V source (NV: USB
  2.0 specification section 7.1.5, not read this session). Many MCUs integrate it.
- ESD clamp on D+, D-, VBUS, and ID (`X-ESD-01`).
- Fuse or current limit: optional on a device.

### 2.5 Mating geometry, panel opening, retention

| Item | Value | Source |
|---|---|---|
| Receptacle opening | about 6.85 x 1.80 mm | (NV: Micro-USB specification) |
| Plug overmold maximum | about 10.6 x 8.5 mm | (NV: widely quoted, not read) |
| Orientation | Asymmetric shell: the plug cannot be inserted upside down | `[S16]` (NV) |
| Rated durability | 10 000 cycles | (NV) |

`mating_direction`:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| Molex 105017-0001 | `+y` | `PCB Edge` text on `Dwgs.User` at y = +2.6875 `[S11]` |
| Amphenol 10118194-0001LF | `+y` | `Dwgs.User` line `PCB Edge` at y = +2.75 `[S11]` |

Retention: Micro-B signal pads are fine pitch (0.65 mm) and break off under side load.
Use a receptacle with through-hole or large-pad shell tabs and solder all of them.

### 2.6 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `UM-01` | Pin 1 is VBUS, pin 2 D-, pin 3 D+, pin 4 ID, pin 5 GND, per the table above. | Net of each pad in the footprint. | netlist |
| `UM-02` | Pin 4 (ID) is unconnected or has a stated pull on a device-only port. | Net of pad 4. | netlist |
| `UM-03` | ESD protection on VBUS, D+, D-. | `X-ESD-01`. | netlist |
| `UM-04` | All shell pads are tied to GND or chassis. | `X-SHD-01`. | netlist |
| `UM-05` | The receptacle front face points to the board edge and is flush or within 0.5 mm. | `X-ORI-01`, `X-EDGE-01`. | placement |

---

## 3. USB 2.0 Type-A (receptacle, host port)

### 3.1 Standard

USB 2.0 specification, Chapter 6 (mechanical) and Chapter 7 (electrical) `[S15]` (NV:
document not read this session; values below are the standard's well-known figures and
need a page-level check).

### 3.2 Stock footprints

| Footprint (`Connector_USB.pretty`) | Style | Note |
|---|---|---|
| `USB_A_Molex_67643_Horizontal` | Through hole, horizontal receptacle | Pads: 4 signal (1.6 mm round, 0.95 mm drill) at 2.5 mm pitch, 2 shell pads 3.0 mm, drill 2.3 mm, `[S11]` |
| `USB_A_Receptacle_GCT_USB1046`, `USB_A_Connfly_DS1095`, `USB_A_Wuerth_614004134726_Horizontal` | Other receptacles | |

Trap: `USB_A_CNCTech_1001-011-01101_Horizontal` is described by its own `descr` as a
USB type A **plug** (a PCB-edge dongle), not a receptacle. Its fab outline is 21.3 mm
long. Do not use it for a host port `[S11]`.

### 3.3 Pinout

| Pin | Signal |
|---|---|
| 1 | VBUS |
| 2 | D- |
| 3 | D+ |
| 4 | GND |
| Shell | GND or chassis |

(NV: standard pin names.)

### 3.4 Required circuit (host port)

- D+ and D- each have a 15 kΩ ±5 % pulldown to GND at a host (NV: USB 2.0 section 7.1.5).
- VBUS is switched through a power switch with overcurrent detection. A downstream port
  has at least 120 µF of bulk capacitance, and no more than the figure needed so the
  switch current limit is not tripped by inrush (NV: USB 2.0 section 7.2.4.1).
- ESD clamp on D+, D-, VBUS (`X-ESD-01`).
- A device-side Type-A is a plug, not a receptacle. This section covers receptacles.
- Overcurrent: 500 mA per port at USB 2.0 (5 unit loads of 100 mA) (NV).

### 3.4a Mating geometry

| Item | Value | Source |
|---|---|---|
| Standard-A plug shell | about 12.0 x 4.5 mm | (NV) |
| Receptacle opening | about 12.5 x 5.0 mm | (NV) |
| Plug overmold | about 15 to 17 mm wide in common cables | (NV) |

`mating_direction`:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| Molex 67643 horizontal | `+y` (inferred) | Pad row at y = 0, fab outline to y = +12.99 `[S11]`; no edge marker |

### 3.5 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `UA-01` | A host port has a 15 kΩ ±5 % pulldown from each of D+ and D- to GND. | Nets on pads 2 and 3. | netlist |
| `UA-02` | VBUS passes through a current-limited switch, and the switch's fault output is wired to something. | Part on VBUS net and its fault net. | netlist |
| `UA-03` | At least 120 µF of capacitance on a downstream VBUS (NV), and its inrush does not trip the limiter. | Sum of capacitors on the VBUS net. | netlist |
| `UA-04` | The footprint is a receptacle, not a plug. | `descr` string and `kb/interfaces/usb-a.md`. | pads |
| `UA-05` | Shell pads on GND or chassis. | `X-SHD-01`. | netlist |
| `UA-06` | Mating face flush with the board edge or within 0.5 mm. | `X-ORI-01`, `X-EDGE-01`. | placement |

---

## 4. JST PH (2.0 mm pitch, wire to board)

### 4.1 Standard

Vendor catalogue, not an industry standard: JST PH connector, `ePH.pdf` (JST Mfg.),
read in full `[S3]`. Ratings, wire range, and dimensions below are from it. The same
four JST families (PH, XH, SH, GH) share the structure of sections 4 to 7.

### 4.2 Families and stock footprints

| Part | Style | Stock footprint (`Connector_JST.pretty`) | packages.json key |
|---|---|---|---|
| `B<n>B-PH-K-S` | Through hole, top entry | `JST_PH_B<n>B-PH-K_1x0<n>_P2.00mm_Vertical` | `JST-PH-<n>`, n = 2 to 6 |
| `S<n>B-PH-K-S` | Through hole, side entry | `JST_PH_S<n>B-PH-K_1x0<n>_P2.00mm_Horizontal` | same key |
| `B<n>B-PH-SM4-TB`, `S<n>B-PH-SM4-TB` | SMT | `JST_PH_B<n>B-PH-SM4-TB_*`, `JST_PH_S<n>B-PH-SM4-TB_*` | not covered |

Mating housing: `PHR-<n>`. Crimp contact: `SPH-002T-P0.5S` (AWG 30 to 24) `[S3]`.

Measured from the library, 4-position `B4B-PH-K` `[S11]`: pads 1.20 x 1.75 mm, drill
0.75 mm, pitch 2.00 mm, outer copper span 7.20 x 1.75 mm. The through-hole `B` and `S`
footprints share one pad pattern. The catalogue's recommended hole is 0.7 +0.1/0 mm `[S3]`.

### 4.3 Pinout and polarity

The standard assigns no signal to a pin. Pin 1 is the position JST marks `No. 1
circuit` (the left end viewed from the mounting side in the catalogue). The mating
housing is polarized by its shape. Polarity of a battery or supply pigtail is set by
whoever wired the cable, and differs between vendors with identical-looking plugs
(`batteries.md` section 5). The board's `design.py` states which pin carries which net,
and the silkscreen marks pin 1 and the positive pin.

### 4.4 Ratings

| Item | Value | Source |
|---|---|---|
| Current | 2 A AC or DC with AWG 24 wire | `[S3]` |
| Voltage | 100 V AC or DC | `[S3]` |
| Wire | AWG 32 to 24, insulation 0.5 to 1.5 mm diameter | `[S3]` |
| Contact resistance | 10 mΩ initial, 20 mΩ after test, maximum | `[S3]` |
| Temperature | -40 to +105 °C | `[S3]` |
| PCB thickness | 0.8 to 1.6 mm | `[S3]` |

### 4.5 Mating geometry

| Item | Value | Source |
|---|---|---|
| Header, top entry (`B<n>B-PH-K-S`) | width B = 2.0 x (n-1) + 3.9 mm, 4.5 mm deep, 6.0 mm above the board | `[S3]` |
| Mated height above board, top entry | 8 mm | `[S3]` (the catalogue gives "mounting height of 8 mm") |
| Header, side entry | 4.8 mm tall, 7.6 mm long body; mated length 9.6 mm | `[S3]` |
| Plug housing `PHR-<n>` | width B = 2.0 x (n-1) + 3.8 mm, 4.5 mm deep, 6.85 mm tall | `[S3]` |
| Mating lock | none stated on the catalogue pages read (friction retention) | (NV: confirm in the PH product page) |

`mating_direction`:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| `JST_PH_B<n>B-PH-K_*_Vertical` | `+z` | Top entry per `[S3]`; vertical footprint |
| `JST_PH_S<n>B-PH-K_*_Horizontal` | `+y` (inferred) | Pad row at y = 0, fab outline y -1.35 to +6.25 `[S11]`; catalogue side-entry drawing places the housing on one side of the pad row. Needs a second source: a mated photograph or the 3D model |

Strain relief: a crimp housing holds the wire. The plug leaves its cable along the
mating axis. Reserve at least the plug height plus about 5 times the cable diameter
(NV: a bend-radius rule of thumb) beyond the header in the mating direction.

### 4.6 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `PH-01` | The footprint is a 2.0 mm pitch PH footprint of the right pin count (not a 2.5 mm XH or 1.25 mm GH). | `X-PAD-01` with a `JST-PH-<n>` entry: pitch 2.00 mm. The XH footprint declared as PH fails on pitch, span, and family name (shown in the repository's verification run). | pads |
| `PH-02` | Pin 1 net and the polarity of the supply pins match the documented pigtail, and the polarity is silkscreened. | Pad nets against the `design.py` connector table. | netlist |
| `PH-03` | Current per pin is at most 2 A, and less for wire thinner than AWG 24. | Sum of the load current routed to the pins from the power budget. | netlist |
| `PH-04` | The header's `mating_direction` points outboard or to a stated internal path with 8 mm of free height (top entry) or 9.6 mm of length (side entry). | `X-ORI-01` and the case census. | placement |
| `PH-05` | A battery connector has either a keyed, polarized shroud and a documented pigtail check, or a reverse-polarity element; the choice is recorded. | `electronics.md` section 6. | manual |
| `P2-01` | Both pins of a 2-pin power or battery connector are wired to another part. | Each pin's net has a node of another reference (`scripts/interfaces/power-2pin.json`). | netlist |
| `P2-02` | The two pins are on different nets: the connector does not short its supply. | Pin nets differ. | netlist |

---

## 5. JST XH (2.5 mm pitch)

### 5.1 Standard

JST XH connector, `eXH.pdf`, read in full `[S4]`.

### 5.2 Families and stock footprints

| Part | Style | Stock footprint | packages.json key |
|---|---|---|---|
| `B<n>B-XH-A` | Through hole, top entry | `JST_XH_B<n>B-XH-A_1x0<n>_P2.50mm_Vertical` | `JST-XH-<n>`, n = 2 to 6 |
| `S<n>B-XH-A` | Through hole, side entry, C = 9.2 mm | `JST_XH_S<n>B-XH-A_1x0<n>_P2.50mm_Horizontal` | same key |
| `S<n>B-XH-A-1` | Side entry, C = 7.6 mm | `..._S<n>B-XH-A-1_...` | not covered |
| `B<n>B-XH-AM` | With boss | `..._B<n>B-XH-AM_...` | not covered |

Mating housing `XHP-<n>`. Measured `B4B-XH-A` `[S11]`: pads 1.70 x 1.95 mm, drill
0.95 mm, pitch 2.50 mm, outer span 9.20 x 1.95 mm. Catalogue hole 0.9 +0.1/0 mm `[S4]`.

### 5.3 Ratings and geometry

| Item | Value | Source |
|---|---|---|
| Current, voltage | 3 A AC or DC (AWG 22), 250 V | `[S4]` |
| Wire | AWG 30 to 22, insulation 0.9 to 1.9 mm | `[S4]` |
| Withstanding voltage | 1 000 V AC for one minute | `[S4]` |
| PCB thickness | 1.6 mm | `[S4]` |
| Header, top entry | width B = 2.5 x (n-1) + 4.9 mm, 5.75 mm deep, 7.0 mm above board | `[S4]` |
| Assembled height above board, top entry | 9.8 mm | `[S4]` |
| Plug housing `XHP-<n>` | width B = 2.5 x (n-1) + 4.8 mm, 5.7 mm deep, 7.5 mm tall | `[S4]` |
| Side entry mated length | 14.3 mm, 6.1 mm tall (C = 9.2 mm type) | `[S4]` |
| Lock | The housing carries a lock ramp (NV: the catalogue pages read do not state it) | |

The pin 1 mark is `No. 1 circuit`. The 4-pin XH conforms to JEMA home-automation
terminal standards `[S4]`, which fixes housing shape, not signal assignment.

`mating_direction`:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| `JST_XH_B<n>B-XH-A_*_Vertical` | `+z` | Top entry `[S4]` |
| `JST_XH_S<n>B-XH-A_*_Horizontal` | `+y` (inferred) | Pad row at y = 0, fab outline y -2.30 to +9.20, matching the 9.2 mm C dimension `[S4][S11]` |

### 5.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `XH-01` | The footprint is a 2.50 mm pitch XH footprint of the right pin count. | `X-PAD-01`, key `JST-XH-<n>`. | pads |
| `XH-02` | Pin 1 net, polarity, silkscreen mark as `PH-02`. | As `PH-02`. | netlist |
| `XH-03` | Current per pin at most 3 A with AWG 22 wire. | Power budget. | netlist |
| `XH-04` | Free height of 9.8 mm above the board for a top-entry mated pair, or 14.3 mm of length for side entry. | Case census. | case |
| `XH-05` | `mating_direction` outboard or to a stated internal path. | `X-ORI-01`. | placement |

---

## 6. JST SH (1.0 mm pitch)

### 6.1 Standard

JST SH connector, `eSH.pdf`, read in full `[S5]`. The SH header is socket compatible
with the SR series IDC style `[S5]`.

### 6.2 Families and stock footprints

| Part | Style | Stock footprint | packages.json key |
|---|---|---|---|
| `BM<nn>B-SRSS-TB` | SMT, top entry | `JST_SH_BM<nn>B-SRSS-TB_1x<nn>-1MP_P1.00mm_Vertical` | `JST-SH-<n>`, n = 2 to 6 |
| `SM<nn>B-SRSS-TB` | SMT, side entry | `JST_SH_SM<nn>B-SRSS-TB_1x<nn>-1MP_P1.00mm_Horizontal` | same key (`JST-SH-2` and `JST-SH-2-SM` are split) |

Mating housing `SHR-<nn>V-S` or `SHR-<nn>V-S-B` (with protrusions). Measured `BM04B`
`[S11]`: signal pads 0.60 x 1.55 mm at 1.00 mm pitch, two mounting-tab pads (`MP`) 1.2 x
1.8 mm at x = ±2.8 mm, outer span 6.80 x 4.20 mm. The footprint counts the `MP` pads, so
a 4-circuit part reads as 6 pads.

### 6.3 Ratings and geometry

| Item | Value | Source |
|---|---|---|
| Current, voltage | 1.0 A AC or DC (AWG 28), 50 V | `[S5]` |
| Wire | AWG 32 to 28, insulation 0.4 to 0.8 mm | `[S5]` |
| Contact resistance | 20 mΩ initial, 40 mΩ after test, maximum | `[S5]` |
| Header, top entry | width B = 1.0 x (n-1) + 3.0 mm, 2.9 mm deep, 4.25 mm above board | `[S5]` |
| Mated height above board, top entry | 6.3 mm | `[S5]` |
| Side entry | mated length 6.25 mm, 2.95 mm tall | `[S5]` |
| Plug housing `SHR-<nn>V-S` | width B = 1.0 x (n-1) + 2.0 mm (+ 4.0 mm for `-B` with protrusions), 2.8 mm deep, 5 mm tall | `[S5]` |
| Mating lock | none stated on the pages read; `SHR-..-B` has protrusions (NV: whether they act as retention) | |

`mating_direction`:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| `JST_SH_BM<nn>B-SRSS-TB_*_Vertical` | `+z` | Top entry `[S5]` |
| `JST_SH_SM<nn>B-SRSS-TB_*_Horizontal` | `+y` (inferred) | Signal pads at y = -2.0, `MP` pads at y = +1.875, fab outline y -1.68 to +2.58 `[S11]`; side-entry layout in `[S5]` |

Retention: the signal contacts are tiny, so the header is held by the `MP` tabs. They
must be soldered to copper and tied to a stated net (`X-SHD-01`).

### 6.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `SH-01` | The footprint is a 1.00 mm pitch SH footprint with the right number of positions. | `X-PAD-01`, key `JST-SH-<n>`. | pads |
| `SH-02` | Both `MP` mounting pads exist, are on a net (GND or NC with copper), and are not left unnamed. | `X-SHD-01` for pads named `MP`. | netlist |
| `SH-03` | Current at most 1 A per pin with AWG 28 wire, and the rail is not a hundreds-of-milliamps battery (`batteries.md` section 5). | Power budget. | netlist |
| `SH-04` | Pin 1 net and mate with the cable. | As `PH-02`. | netlist |
| `SH-05` | `mating_direction` outboard or to a stated internal path. | `X-ORI-01`. | placement |

---

## 7. JST GH (1.25 mm pitch, locking)

### 7.1 Standard

JST GH connector, `eGH.pdf`, read in full `[S6]`.

### 7.2 Families and stock footprints

| Part | Style | Stock footprint | packages.json key |
|---|---|---|---|
| `BM<nn>B-GHS-TBT` | SMT, top entry | `JST_GH_BM<nn>B-GHS-TBT_1x<nn>-1MP_P1.25mm_Vertical` | `JST-GH-<n>`, n = 2 to 6 |
| `SM<nn>B-GHS-TB` | SMT, side entry | `JST_GH_SM<nn>B-GHS-TB_1x<nn>-1MP_P1.25mm_Horizontal` | same key |
| `BM<nn>B-GHP-A-TBT` | Keying pattern A | not in the stock set read | not covered |

Mating housing `GHR-<nn>V-S`; keying pattern A housings are `GHR-<nn>V-2P`, purple
`[S6]`. Measured `BM04B` `[S11]`: signal pads 0.6 x 1.7 mm at 1.25 mm pitch, `MP` pads
1.0 x 2.8 mm at x = ±3.725 mm, outer span 8.45 x 5.60 mm (counts as 6 pads).

### 7.3 Ratings and geometry

| Item | Value | Source |
|---|---|---|
| Current, voltage | 1.0 A AC or DC (AWG 26), 50 V | `[S6]` |
| Wire | AWG 30 to 26, insulation 0.76 to 1.0 mm | `[S6]` |
| Contact resistance | 30 mΩ initial, 50 mΩ after test, maximum | `[S6]` |
| Header, top entry | width B = 1.25 x (n-1) + 4.5 mm, 4.25 mm deep, 4.05 mm above board | `[S6]` |
| Mated height above board, top entry | 7.3 mm | `[S6]` |
| Side entry | mated length 7.15 mm, 4.35 mm tall | `[S6]` |
| Plug housing `GHR-<nn>V-S` | width B = 1.25 x (n-1) + 2.5 mm, 4.15 mm deep, 5.7 mm tall | `[S6]` |
| Lock | Positive latch: the catalogue lists "secure lock mechanism" and "large outer latch" | `[S6]` |
| Keying | Keying pattern A housings and headers (2, 4 and 5 positions) prevent mating with standard GH | `[S6]` |

`mating_direction`:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| `JST_GH_BM<nn>B-GHS-TBT_*_Vertical` | `+z` | Top entry `[S6]` |
| `JST_GH_SM<nn>B-GHS-TB_*_Horizontal` | `+y` (inferred) | Signal pads at y = -1.85, `MP` pads at y = +1.35, fab outline y -1.60 to +2.45 `[S11]` |

### 7.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `GH-01` | The footprint is a 1.25 mm pitch GH footprint with the right number of positions. | `X-PAD-01`, key `JST-GH-<n>`. | pads |
| `GH-02` | Both `MP` pads are on a stated net. | `X-SHD-01`. | netlist |
| `GH-03` | Current at most 1 A per pin with AWG 26 wire. | Power budget. | netlist |
| `GH-04` | The plug latch has clearance: at least the mated height 7.3 mm above the board for top entry. | Case census. | case |
| `GH-05` | `mating_direction` outboard or to a stated internal path. | `X-ORI-01`. | placement |

---

## 8. Qwiic and STEMMA QT (I2C on JST SH, 4 pins)

### 8.1 Standard

A vendor convention, not an industry standard: SparkFun Qwiic Connect System, with
Adafruit STEMMA QT cross-compatible `[S7]`. Both use the 4-position, 1.0 mm JST SH
connector of section 6. SparkFun names the board connector `SM04B-SRSS-TB(LF)(SN)` and
the cable connector `SHR-04V-S` `[S7]`.

### 8.2 Pinout and electrical

| Pin | Signal | Wire colour |
|---|---|---|
| 1 | GND | Black |
| 2 | 3.3 V | Red |
| 3 | SDA | Blue |
| 4 | SCL | Yellow |

Source: SparkFun `[S7]`. Qwiic is 3.3 V only `[S7]`. STEMMA QT keeps its own regulator
and level shifting on the device board, so a STEMMA QT peripheral may run from a 3 V to
5 V controller (Adafruit, from the learn guide `[S7b]`). The Qwiic page states no
pullup value (NV: SparkFun boards carry a pullup jumper; confirm per board).

Rules from the I2C specification (UM10204, see `domains.md` section 3 for the sizing
arithmetic): one set of pullups per bus. Daisy-chained boards each carrying pullups put
them in parallel, so the total resistance falls with every board added.

Cable: standard cables are good for roughly 1 m (about 4 ft) of I2C `[S7]`.

### 8.3 Geometry and `mating_direction`

Section 6 applies, because the connector is a JST SH. SparkFun's board connector is the
side-entry `SM04B-SRSS-TB`, so the stock footprint is
`JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal`, `mating_direction` `+y` (inferred),
packages.json key `JST-SH-4`. A top-entry `BM04B` also works mechanically.

### 8.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `QW-01` | Pin 1 GND, pin 2 supply, pin 3 SDA, pin 4 SCL. | Pad nets. | netlist |
| `QW-02` | A Qwiic-labelled port is on a 3.3 V rail. A port on another rail is labelled STEMMA QT only if every peripheral has its own level shifting. | Supply net voltage in `design.py`. | netlist |
| `QW-03` | Exactly one device on the bus carries pullups, or the parallel pullup value stays within the I2C bounds for the bus capacitance. | Sum pullup conductance per net against `domains.md` bounds. | netlist |
| `QW-04` | The JST SH rules `SH-01` to `SH-05` hold. | As section 6. | pads |

---

## 9. 2.54 mm (0.1 in) pin headers: SWD, UART, I2C conventions

### 9.1 Standard

There is no standard for the 2.54 mm single-row header's signal assignment. The
mechanical size (2.54 mm pitch, 0.64 mm square pin) is a de facto industry convention
(NV: no single manufacturer drawing was read). The conventions below are common
practice and are marked as such. Debug-port signal meanings come from the Arm debug
specifications (section 10).

### 9.2 Stock footprints

| Style | Stock footprint (`Connector_PinHeader_2.54mm.pretty`) | packages.json key |
|---|---|---|
| Through hole, straight | `PinHeader_1x0<n>_P2.54mm_Vertical` | `PinHeader-1x0<n>-2.54`, n = 2 to 6 |
| Through hole, right angle | `PinHeader_1x0<n>_P2.54mm_Horizontal` | same key |
| SMD, pin 1 left or right | `PinHeader_1x0<n>_P2.54mm_Vertical_SMD_Pin1Left` and `..._Pin1Right` | `PinHeader-SMD-1x0<n>-2.54` |

Measured `PinHeader_1x04_P2.54mm_Vertical` `[S11]`: pad 1 square 1.7 mm, others round
1.7 mm, drill 1.0 mm, pitch 2.54 mm, outer span 9.32 x 1.70 mm. Pin 1 is the square pad
at the origin and numbering runs along +y.

`mating_direction`:

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| `..._Vertical` | `+z` | Straight pins point out of the component face |
| `..._Horizontal` | `+x` | The fab outline runs x -0.32 to +10.04 mm while the pads sit at x = 0, so the long pin extends to +x `[S11]` |
| `..._Vertical_SMD_*` | `+z` | Straight pins out of the component face |

### 9.3 Conventions

The conventions below are widespread but not standardised. Mark each one in the
silkscreen, because two vendors can order the same four pins differently.

| Use | Pins | Convention |
|---|---|---|
| SWD, 4 pin | 3V3 or VTref, SWDIO, SWCLK, GND | Order varies by programmer. State the order on the silkscreen and in `design.py`. (NV) |
| SWD, 5 pin | as above plus nRESET | (NV) |
| UART, 6 pin (FTDI cable style) | 1 GND, 2 CTS, 3 VCC, 4 TXD, 5 RXD, 6 RTS or DTR | The cable's TXD drives the target's RXD. Label the header from the header's own side and say so. (NV: FTDI cable datasheet not read) |
| I2C, 4 pin | GND, VCC, SDA, SCL | Order varies. Use the Qwiic order (section 8) for any new board that wants Qwiic cables to fit. |

The single-row header is not keyed. A plug can go on backwards or offset by one pin. The
failure is power on a signal pin. Rules:

- Put GND on both end pins, or place a shrouded keyed header, when a reversed plug
  could drive a rail into a signal pin.
- Label pin 1 and the supply pin in silkscreen (`silkscreen.md`).

Current: a 2.54 mm header pin carries about 3 A on a short contact (NV: typical
manufacturer figure, not from a named datasheet).

### 9.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `H25-01` | The footprint is a 2.54 mm pitch header of the right pin count and style (through hole, SMD). | `X-PAD-01`, key `PinHeader-1x0<n>-2.54`. | pads |
| `H25-02` | A debug or UART header's pins are named on the silkscreen from the header's own perspective, with TX or RX stated. | `kicad_silkcheck.py` required-label rule plus the `design.py` pin table. | manual |
| `H25-03` | A header carrying a supply and a signal has a reversed-plug mitigation: GND on both ends, a shroud, or a documented risk. | Pin table: first and last pins are GND, or an exemption in the design record. | netlist |
| `H25-04` | Header's `mating_direction` clears the case and the plug's cable. | `X-ORI-01` and case census. | placement |
| `H25-05` | An SWD header's SWDIO, SWCLK, GND and VTref pins are each wired to another part, on four different nets, with GND on the ground net and VTref on a rail. | Pin nets by symbol pin name or `design.py` `pin_map` (`scripts/interfaces/header-2.54-swd.json`). | netlist |
| `H25-06` | When an SWD header brings out nRESET, it has a pull-up to the target rail, or the MCU's own pull-up is documented (`H12-03`). WARN. | A resistor between the nRESET net and the VTref net. | netlist |

---

## 10. 1.27 mm (0.05 in) pin headers: the Arm Cortex debug connector

### 10.1 Standard

The Arm Cortex debug connector, 10 pin, 2 x 5, 1.27 mm. The pin assignment is
reproduced by Microchip's documentation and by a working-engineer article, which agree
with each other `[S14]`. The Arm source (the Cortex-M System Design Kit and CoreSight
documentation) was not retrieved (NV). A matching shrouded, keyed part is a 2 x 5
1.27 mm box header.

### 10.2 Pinout

| Pin | Signal | Note |
|---|---|---|
| 1 | VTref | Target voltage reference. A sense input for the probe, not a supply (NV: some probes can supply 3.3 V; check the probe). |
| 2 | SWDIO / TMS | Bidirectional data. |
| 3 | GND | |
| 4 | SWCLK / TCK | Probe output. |
| 5 | GND | |
| 6 | SWO / TDO | Optional. On a Cortex-M3 or M4, serial wire output. On an M0 or M0+, usable as a spare UART TX. `[S14]` |
| 7 | KEY | No pin. Leave unconnected. |
| 8 | NC / TDI | Optional. Usable as a UART RX for a console. `[S14]` |
| 9 | GNDDetect | Leave unconnected unless the target reads probe presence. `[S14]` |
| 10 | nRESET | Target reset. Pullup of 10 to 100 kΩ to VDD `[S14]`. |

Wiring guidance from `[S14]` (a single author's recommendation, not a standard text):
SWCLK has a 10 to 100 kΩ pulldown to GND, and SWDIO normally needs none (check the MCU
datasheet). Mark these NV against the Arm Debug Interface Architecture Specification.

### 10.3 Stock footprints

| Style | Stock footprint (`Connector_PinHeader_1.27mm.pretty`) | packages.json key |
|---|---|---|
| 2 x 5 through hole | `PinHeader_2x05_P1.27mm_Vertical` | `PinHeader-2x05-1.27` |
| 2 x 5 SMD | `PinHeader_2x05_P1.27mm_Vertical_SMD` | `PinHeader-2x05-1.27-SMD` |
| 1 x N through hole, N = 4 to 6 | `PinHeader_1x0<n>_P1.27mm_Vertical` or `_Horizontal` | `PinHeader-1x0<n>-1.27` |
| Tag-Connect, no header | `Connector.pretty/Tag-Connect_TC2050-IDC-*` | not covered |

Measured `PinHeader_2x05_P1.27mm_Vertical` `[S11]`: pad 1 square 1.0 mm, round pads 1.0
mm, drill 0.65 mm, pitch 1.27 mm, outer span 6.08 x 2.27 mm. Numbering runs across the
rows: pad 2 sits 1.27 mm from pad 1 in x, pad 3 is 1.27 mm from pad 1 in y (the usual
IDC convention, and the Arm connector's). A shrouded header's keying notch must be on
the side the Arm numbering expects, so the footprint's pin 1 and the part's pin 1 agree.

`mating_direction`: `+z` for the vertical footprints. For `..._Horizontal` single-row
1.27 mm headers, `+x` (inferred by the same reasoning as section 9).

### 10.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `H12-01` | On a 10-pin Cortex debug header: pin 2 SWDIO, pin 4 SWCLK, pins 3 and 5 GND, pin 1 VTref (target rail), pin 10 nRESET. | Pad nets against the table. | netlist |
| `H12-02` | Pin 7 (KEY) has no net. Pin 9 is unconnected unless detect is used. | Pad nets. | netlist |
| `H12-03` | nRESET has a 10 to 100 kΩ pullup to VDD, or the MCU's own pullup is documented. | Resistor on the nRESET net. | netlist |
| `H12-04` | VTref is connected to the target rail, not to an unrelated rail. | Net of pad 1 against the MCU VDD net. | netlist |
| `H12-05` | The keyed shroud's notch matches the pin numbering of the footprint. | Part number and footprint 3D check (manual). | manual |
| `H12-06` | The footprint is a 1.27 mm pitch header of the right layout. | `X-PAD-01`. | pads |

---

## 11. GX12 and GX16 aviation connectors (panel mount, solder cup)

### 11.1 Standard

No international standard defines the "GX" aviation connector. The names mean a
12 mm or 16 mm panel thread class, and vendors differ in detail. Numbers for the GX16
are from the Handson Technology GX16 datasheet, as read and recorded in
`~/1_projects/dev/hypercardiod_mic/docs/research.md` section 3 `[S10]`. No GX12 drawing
was read: every GX12 number is NV.

### 11.2 Families and stock footprints

There is no stock KiCad footprint for the panel connector, because it is an off-board
part: the user solders wires to its solder cups, and the board never sees the
connector. `packages.json` carries `GX12-offboard` and `GX16-offboard` entries with
`pad_count` 0 for that reason. A board that terminates the connector's pigtail uses
wire-solder pads from `Connector_Wire.pretty` (`SolderWire-*`), which is a different
part. The mic buffer project uses `SolderWire-0.5sqmm_1x04_P4.6mm_D0.9mm_OD2.1mm` for a
GX16-4 pigtail.

### 11.3 Pinout

Pin numbers are stamped by the manufacturer on the solder cups, and count differs by
shell (GX16 from 2 to 8 pins typical, NV). The board's `design.py` states which cup
carries which net and records the vendor's numbering as read from the stamp, not from
the product photo. The common failure is a mirrored view: pin numbers read from the
solder side are mirrored relative to the mating face.

### 11.4 Mechanical (GX16)

| Item | Value | Source |
|---|---|---|
| Panel thread | M16 x 1 | `[S10]` |
| Panel nut | Hexagon, 19 mm across flats | `[S10]` |
| Coupling ring thread | M16 x 0.75 | `[S10]` |
| Male connector length | 35.5 mm total | `[S10]` |
| Maximum body diameter | 18.3 mm | `[S10]` |
| Solder cup | 0.8 mm aperture, cable up to 5.0 mm diameter | `[S10]` |
| Rating | 7 A at 125 V (4 pin) | `[S10]` |
| Panel hole | not stated by the vendor; the project banded it 16.2 to 17.0 mm and used 16.5 mm | project report, NV |
| Anti-rotation flat | none on the drawing read; some vendors cut flats on the thread | `[S10]` (NV for other vendors) |

GX12: thread M12 x 1 by class name (NV), nut size, length, and rating all NV.

`mating_direction`: the panel axis. Off-board, so no footprint axis exists. Record the
case wall it passes through, as in `kb/interfaces/gx12-gx16.md`.

Retention: the panel nut is the only retention. The thread engages the wall only if the
wall is thick enough (for printed walls, at least 2 to 3 mm, NV). A round hole in
plastic lets the connector spin when the coupling ring is turned, which twists the
cable inside. Use a flat or a D-profile in the hole if the thread has a flat, or print
an anti-rotation key.

Plug envelope: the mated pair is about 35.5 mm long behind the panel plus the mating
half (NV: only the male connector length was read). Reserve the coupling ring's
swing diameter, larger than the 18.3 mm body, for the hand.

### 11.5 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `GX-01` | A GX connector is declared as an off-board part with no board pads. A footprint with pads on a `GX*-offboard` declaration is an error. | `X-PAD-01` with `GX16-offboard` (pad count 0). | pads |
| `GX-02` | The pigtail wire pads match the wire gauge (drill at least wire diameter plus 0.2 mm, NV) and the cable's conductors are labelled in `design.py` in the vendor's numbering. | Pad drill and the `design.py` cup-to-net table. | manual |
| `GX-03` | The case wall opening is at least the thread major diameter plus 0.2 mm and not more than 1.0 mm over it, with an anti-rotation feature if the part has a flat. | Case `verify()`. | case |
| `GX-04` | The case leaves the connector's rear length (35.5 mm for GX16) free inside the shell, or the cable is a pigtail that does not. | Case census. | case |
| `GX-05` | The solder-side wire has strain relief inside the shell (a clamp or a zip tie post). | Case feature check. | manual |

---

## 12. SMA (RF coaxial, 50 Ω)

### 12.1 Standard

SMA is defined by MIL-PRF-39012 and IEC 61169-15 (NV: not read this session). It is a
50 Ω, threaded connector for DC to 18 GHz in common grades, 1/4-36 UNS thread (NV). Nut
torque is set in the vendor's datasheet.

### 12.2 Families and stock footprints

| Style | Stock footprint (`Connector_Coaxial.pretty`) | `mating_direction` |
|---|---|---|
| Vertical through hole | `SMA_Amphenol_132134_Vertical` | `+z` |
| Edge mount, Amphenol | `SMA_Amphenol_132289_EdgeMount` | `+x` (the body, fab x -1.91 to +13.97, extends away from the launch pads in +x) |
| Edge mount, Molex | `SMA_Molex_73251-1153_EdgeMount_Horizontal` | `-x` (fab x -13.79 to +2.50) |

The two edge-mount parts face opposite ways in their local frames. A copy-and-adapt of
one for the other mirrors the part. Geometry `[S11]`: the Amphenol 132134 centre pad is
2.05 mm with a 1.5 mm drill, four ground legs at (±2.54, ±2.54) mm, 2.25 mm pads, 1.7 mm
drill, outer span 7.33 mm square. Amphenol 132289 has a 1.5 mm wide centre pad and
signal and ground pads 5.08 mm long along the mating axis, outer span 13.58 x 1.5 mm
(counting the repeated ground pads).

### 12.3 Required circuit and layout

- The launch is a 50 Ω transition. Its pad width and clearance depend on board
  thickness, copper weight, and dielectric. Use the vendor's footprint for the vendor's
  stated board thickness (NV: confirm per part), then verify the stackup in
  `domains.md` section 4.
- Ground stitching vias around the launch, spaced under one twentieth of a wavelength
  (`domains.md` section 4).
- A DC block or ESD element between the connector and the RF input only if the circuit
  needs it, since both change the transition.
- The connector's ground legs tie to the plane under the whole footprint.

### 12.4 Mating geometry, panel opening

| Item | Value | Source |
|---|---|---|
| Thread | 1/4-36 UNS | (NV) |
| Bulkhead panel hole | about 6.4 mm, with a flat on some jacks | (NV) |
| Mating torque | per vendor datasheet | (NV) |

A threaded plug adds a hex nut larger than the receptacle's thread (NV: about 8 mm
across flats on common SMA). Reserve wrench or finger room around the face.

### 12.5 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `SMA-01` | The launch footprint is the vendor's footprint for this part and board thickness. | `X-PAD-01` plus the stackup in `design.py`. | pads |
| `SMA-02` | An edge-mount SMA's `mating_direction`, after rotation, points off the board, and its footprint front reaches the edge. | `X-ORI-01`, `X-EDGE-01`. | placement |
| `SMA-03` | Ground vias around the launch at spacing under lambda/20 at the highest frequency. | Via coordinates against `domains.md` section 4 arithmetic. | placement |
| `SMA-04` | The signal pad has no stub, and the 50 Ω line starts at the launch. | Track width at the pad against the stackup. | placement |

---

## 13. U.FL (Hirose, ultraminiature RF)

### 13.1 Standard

A vendor interface: Hirose U.FL series, receptacle `U.FL-R-SMT-1`, mated with
`U.FL-LP-*` plugs on a 0.81 mm or 1.13 mm coaxial cable (NV: figures from general
knowledge; the Hirose drawing returned HTTP 403). The footprint's `descr` cites
Hirose's drawing.

### 13.2 Stock footprints

| Footprint | `mating_direction` | Geometry `[S11]` |
|---|---|---|
| `Connector_Coaxial.pretty/U.FL_Hirose_U.FL-R-SMT-1_Vertical` | `+z` | Centre pad 1.05 x 1.0 mm at x = -1.525; two ground pads 2.2 x 1.05 mm at y = ±1.475; outer span 3.15 x 4.0 mm |
| `U.FL_Molex_MCRF_73412-0110_Vertical` | `+z` | not measured here |

### 13.3 Ratings and mechanics (NV)

| Item | Value |
|---|---|
| Impedance | 50 Ω |
| Frequency | DC to 6 GHz |
| Mated height | about 2.5 mm |
| Durability | about 30 mating cycles |

The low durability means the connector is for assembly, not for a user. Mating is a
straight push along `+z` and unmating needs a pull tool: a plug pulled by its cable
lifts the receptacle's pads. Keep the mated cable from side loads (a clip, or
adhesive) and keep the cable's first bend away from the plug.

Families with similar size are not compatible: U.FL, W.FL, MHF4, and IPEX variants
differ by fractions of a millimetre (NV). Declare the exact receptacle and plug in the
BOM.

### 13.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `UFL-01` | The BOM names the exact plug series that mates with the receptacle. | BOM text against the receptacle's series. | manual |
| `UFL-02` | The receptacle has at least 2.5 mm of free height above it for the plug and cable (NV), with a retention feature for the cable. | Case census. | case |
| `UFL-03` | The 50 Ω line starts at the receptacle pad, with a ground reference under it. | As `SMA-04`. | placement |
| `UFL-04` | The mating count over the product's life is under the connector's rating. | Assembly and service plan. | manual |

---

## 14. 3.5 mm audio jacks: TRS and TRRS

### 14.1 Standard

The 3.5 mm plug is defined by IEC 60603-11 (NV: not read). TRRS wiring has two
competing conventions (NV: general knowledge): CTIA (also AHJ) is tip left, ring 1
right, ring 2 ground, sleeve microphone; OMTP is tip left, ring 1 right, ring 2
microphone, sleeve ground. They are not compatible. A headset with the wrong
convention has no microphone, or shorts the microphone to ground.

### 14.2 Stock footprints

| Part | Stock footprint (`Connector_Audio.pretty`) | Pads | `mating_direction` |
|---|---|---|---|
| CUI SJ1-3535NG, TRS with switch | `Jack_3.5mm_CUI_SJ1-3535NG_Horizontal` | `T`, `R`, `S`, plus switch contacts `TN` and `RN` (5) | `-y` |
| QingPu PJ320E, TRRS headset | `Jack_3.5mm_PJ320E_Horizontal` | `T`, `R1`, `R2`, `S` plus one unnamed plated pad at (5.5, -7.0) | `-y` |

`mating_direction` evidence `[S11]`: both fab outlines show a narrow nose, the part that
goes through the panel, at the negative-y end (SJ1: nose 6.0 mm wide, 4.0 mm deep, y
-5.2 to -1.2; PJ320E: nose 5.6 mm wide, 2.8 mm deep, y -12.0 to -9.2).

Trap: the PJ320E stock footprint has one plated pad with an empty number. It carries
no net, so it floats. It is probably a second sleeve or a mechanical pad. Read the
manufacturer drawing and name it `S` or leave a documented no-connect (NV).

packages.json keys: `Jack-3.5mm-CUI-SJ1-3535NG`, `Jack-3.5mm-PJ320E`.

### 14.3 Required circuit

- A headphone or line output sees a plug inserted live. Use DC blocking capacitors on
  the outputs (`domains.md` section 1) and an ESD clamp on every tip, ring, and
  sleeve pin (`X-ESD-01`).
- The sleeve is ground. A TRRS microphone pin needs a bias source of about 2 to 3 V
  through about 2.2 kΩ (NV: common headset practice; check the headset's datasheet).
- The jack's switch contacts (`TN`, `RN` normally closed to the tip and ring) open on
  insertion. Their use is optional and they float when unused. Check the contact
  polarity against the part drawing.
- A 3.5 mm panel jack's retention is the threaded bushing and nut (NV: size, commonly
  M6 x 0.5 or similar), not the PCB pins. SMD jacks without a bushing rely on solder
  pads and fail under plug side load.

Mated plug: the plug body is about 3.5 mm in diameter with an overmold or strain relief
commonly 6 to 8 mm in diameter and up to 40 mm long (NV). Reserve a larger opening or
recess if the jack is recessed in a wall.

### 14.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `TRS-01` | A TRRS jack documents CTIA or OMTP in `design.py`, and the pad-to-net map follows the stated convention. | `design.py` connector table field. | manual |
| `TRS-02` | Every plated pad of the footprint has a name and a net or a stated no-connect. | Pad numbering and nets of the footprint. | netlist |
| `TRS-03` | An ESD clamp on tip, ring, and mic pins, or the exemption is recorded. | `X-ESD-01`. | netlist |
| `TRS-04` | The jack's `mating_direction` points outboard and the nose's outer face is within 0.5 mm of the wall plane. | `X-ORI-01`, `X-EDGE-01`, case census. | placement |
| `TRS-05` | An output has DC blocking when the load can be a grounded sleeve plug. | Series capacitor on each output net. | netlist |

---

## 15. DC barrel jacks (2.1 mm and 2.5 mm center pin)

### 15.1 Standard

Industry convention. The size is named outer diameter by inner diameter: 5.5 mm x 2.1 mm
and 5.5 mm x 2.5 mm are the common plugs. Dimensions for plugs are in EIAJ RC-5320A
(NV: not read). Polarity is by convention center positive, and it is not universal.

### 15.2 Families and stock footprints

| Part | Stock footprint (`Connector_BarrelJack.pretty`) | Pin | packages.json key |
|---|---|---|---|
| CUI PJ-102AH, through hole | `BarrelJack_CUI_PJ-102AH_Horizontal` | 2.1 mm plug | `BarrelJack-2.1-CUI-PJ-102AH` |
| Wuerth 694108106102, SMD | `BarrelJack_Wuerth_694108106102_2.5x5.5mm` | 2.5 mm plug | `BarrelJack-2.5-Wuerth-694108106102` |

Facts read from the CUI PJ-102AH drawing `[S9]`: body 11.0 mm wide, 9.0 mm tall, 14.4 mm
long; centre pin 2.0 mm diameter; bore 6.5 mm; rating 24 V DC and 5 A; contact
resistance 50 mΩ maximum; insulation resistance 50 MΩ minimum at 100 V DC; 500 V AC
withstand; 5 000 cycles; -25 to +85 °C. Pad geometry `[S11]`: three through-hole pads
2.6 mm with 1.6 mm drills at (0, 0), (0, 6.0), (4.7, 3.0), outer span 8.6 x 7.3 mm.

A 2.0 mm pin accepts a 2.1 mm plug by spring contact. A 2.5 mm plug does not fit it.
A 2.1 mm plug in a 2.5 mm jack fits loosely and disconnects with vibration (NV).

`mating_direction` `+y` for the PJ-102AH. The fab outline runs y -0.7 to +13.7 mm and
steps in at y = +10.2 to a 3.5 mm long front section, consistent with the drawing's
3.5 mm dimension `[S9][S11]`. Wuerth 694108106102: not established; the footprint
outline has no nose or edge marker (NV).

### 15.3 Required circuit

- Reverse-polarity protection for any input that a user can connect to an unknown
  supply: a series Schottky (cheap, drops 0.3 to 0.5 V), a P-FET (low loss), or an
  ideal-diode controller (`domains.md` section 2).
- TVS on the input, rated above the largest supply voltage and below the downstream
  absolute maximum (`domains.md` section 2).
- A fuse or PTC when the source can deliver more than the rating of the traces or
  downstream parts.
- Hot-plugging a supply with a long cable onto a ceramic-capacitor input rings above
  twice the supply voltage (NV, `domains.md` section 2). Add bulk capacitance with
  ESR or a TVS.
- Silkscreen the polarity and the voltage next to the jack (`silkscreen.md`).

Mated plug: the overmold of a typical supply plug is wider than 5.5 mm. A panel opening
at the jack's face must be at least the bore (6.5 mm for the PJ-102AH `[S9]`) plus
clearance, and large enough for the plug's barrel body (NV: commonly 10 to 12 mm
diameter on molded plugs). Size the hole to the plug the user will have, and record it.

### 15.4 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `BJ-01` | The BOM and the silkscreen state center pin diameter (2.1 or 2.5 mm), outer diameter, voltage, and polarity. | Silkscreen text and the `design.py` connector table. | manual |
| `BJ-02` | The input has reverse-polarity protection, or the design record states why it is not needed. | A series diode, P-FET, or ideal-diode part between the jack pin and the first load. | netlist |
| `BJ-03` | A TVS or clamp covers the input rail. | `X-ESD-01` for the power pin, with working voltage above supply. | netlist |
| `BJ-04` | The jack's rated current (5 A for the PJ-102AH) exceeds the load, and traces are sized per `domains.md` section 2. | Power budget. | netlist |
| `BJ-05` | All three terminals' nets are named (center, sleeve, switch). An unused switch terminal has a stated no-connect. | Pad nets. | netlist |
| `BJ-06` | The jack's `mating_direction` points outboard and the front is flush or within 0.5 mm of the wall plane, with the opening sized to the plug's barrel. | `X-ORI-01`, `X-EDGE-01`, case `verify()`. | placement |

---

## 16. RJ45 (8P8C Ethernet), with and without magnetics

### 16.1 Standard

Ethernet over twisted pair: IEEE 802.3 clause 14 (10BASE-T), clause 25 (100BASE-TX),
and clause 40 (1000BASE-T) (NV: clause numbers from general knowledge, not read). The
connector is the TIA-568 8P8C modular jack. Datasheet facts below are from the Wuerth
WE-RJ45LAN 7499010001A datasheet `[S8]`, read in full.

### 16.2 Families and stock footprints

| Part | Magnetics | Stock footprint (`Connector_RJ.pretty`) | `mating_direction` |
|---|---|---|---|
| Wuerth 7499010001A | Yes, 10/100, integrated | `RJ45_Wuerth_7499010001A_Horizontal` | `-x` |
| HALO HFJ11-x2450ERL | Yes, shielded | `RJ45_HALO_HFJ11-x2450ERL_Horizontal` | `-y` (inferred) |
| Amphenol 54602-x08 | No (jack only) | `RJ45_Amphenol_54602-x08_Horizontal` | `-y` (inferred) |

Pad geometry `[S11]`: Wuerth 7499010001A has 8 signal pads 1.6 mm on a 2.54 mm pitch in
two columns offset by 1.27 mm, two shield pads 2.2 mm (drill 1.6 mm), two 3.25 mm
non-plated locating holes, and a fab body 25.3 x 16.2 mm. The footprint's x axis runs
along the connector's length. Pins sit 5.6 mm from the -x end of the body and 19.7 mm
from the +x end.

`mating_direction` `-x` for the Wuerth part: the datasheet's recommended panel cutout
drawing shows the jack's face and the PCB pins at the same end, with the longer body
behind, which is the -x side of the footprint (the pins are near the -x end) `[S8][S11]`.
The HALO and Amphenol footprints put pads within about 4 mm of the -y end and the body
extends +y; the jack face is at the pin end (NV: inferred from the same layout, no drawing
read).

### 16.3 Pinout and magnetics

T568 pair order (NV): pair 1 on pins 4 and 5, pair 2 on pins 1 and 2, pair 3 on pins 3
and 6, pair 4 on pins 7 and 8. 10BASE-T and 100BASE-TX use pins 1 and 2 (transmit) and
3 and 6 (receive). 1000BASE-T uses all four pairs, bidirectionally.

The Wuerth part's schematic `[S8]`: pins 1, 2, 3 are TD+, centre tap, TD-; pins 4, 5, 6
are RD+, centre tap, RD-; two 75 Ω resistors per pair join the unused pairs; the common
node returns through a 1 nF, 2 kV capacitor to pin 8, which is the chassis tie. The
transformer turns ratio is 1:1 ±2 %, inductance 350 µH minimum, insulation test 2 250 V
DC, return loss better than 18 dB from 1 to 30 MHz, 750 mating cycles, rated to
IEEE 802.3u.

Rules:

- 10/100 over a non-magnetic jack needs magnetics on the board, or the transceiver
  integrates them. A bare PHY pin pair wired to a bare jack has no galvanic isolation.
  IEEE 802.3 requires 1 500 V rms isolation (NV: clause not read), which the Wuerth
  magnetics' 2 250 V DC test exceeds `[S8]`.
- The centre taps (pins 2 and 5 of the Wuerth part) are connected as the PHY datasheet
  states. Many PHYs want 3.3 V on them through a bypass (NV: PHY-specific).
- The Bob Smith termination (75 Ω resistors and a high-voltage capacitor) is inside
  the Wuerth part. A jack without it needs it on the board. Its return is the chassis
  net, not signal ground.
- Place the magnetics, if separate, within about 25 mm of the jack and keep the plane
  clear of the isolation barrier (NV: layout guidance, the part datasheet governs).
- Shield pads are tied to chassis ground through a stated network, not left floating.

### 16.4 Panel opening and retention

| Item | Value | Source |
|---|---|---|
| Panel cutout | 16.6 x 14.05 mm, flange 2.03 mm | `[S8]` |
| Body | 16.1 mm wide, 13.55 mm tall, 25.4 mm long | `[S8]` |
| Recommended holes | 8 x 0.90 mm pins, 2 x 1.6 mm shield, 2 x 3.25 mm locating | `[S8]` |
| Plug latch | A flexible tab on the plug. It needs clear space above the jack, about 1 mm beyond the cutout's top edge (NV). | |

The two locating holes are non-plated posts that keep the part from rotating. Do not
leave them out. The shield tabs and posts carry the retention load.

### 16.5 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `RJ-01` | A 10/100/1000 port has magnetics: either a MagJack part or a transformer on the board with isolation of at least 1 500 V rms. | Part table: the RJ45 part's description or a transformer on the TD and RD nets. | netlist |
| `RJ-02` | The centre tap nets follow the PHY datasheet, and the Bob Smith network is either inside the jack or present on the board with its return to chassis. | Net of the centre-tap pins and the 75 Ω network. | netlist |
| `RJ-03` | The shield pads and the capacitor return are tied to chassis through a stated network. | `X-SHD-01`. | netlist |
| `RJ-04` | Pins 1, 2 and 3, 6 map to TX and RX per the PHY and the jack's own pin table. | Pad nets against the PHY pin table. | netlist |
| `RJ-05` | The footprint's two locating holes exist and are in `Edge`-clear positions. | Footprint NPTH count equals the part drawing. | pads |
| `RJ-06` | The case cutout is at least 16.6 x 14.05 mm for the Wuerth 7499010001A, and the jack's front face is within 0.5 mm of the cutout plane. | Case `verify()`, `X-EDGE-01`. | case |
| `RJ-07` | A differential pair of 100 Ω runs from the PHY to the jack with length matching per `domains.md` section 3. | Pair length and impedance. | manual |

---

## 17. XLR and TRS balanced audio

### 17.1 Standards

- XLR3 pin assignment: pin 1 shield (ground), pin 2 hot (in phase, positive), pin 3
  cold. IEC 60268-12 and AES14 (NV: neither read; the assignment is universal in
  professional audio).
- TRS balanced: tip hot, ring cold, sleeve shield (IEC 60268-11, NV).
- Phantom power: P48 supplies 48 V ±4 V through two 6.81 kΩ resistors, one per signal
  leg, return on pin 1, up to 10 mA total, in IEC 61938 (a secondary source `[S13]`;
  the standard was not read). The P12 and P24 variants use 680 Ω and 1.2 kΩ (NV).
- Neutrik NC3FAH: 6 A per contact, below 50 V, insertion and withdrawal force at most
  20 N, 23 mm centre spacing `[S17]`.

### 17.2 Families and stock footprints

| Part | Stock footprint (`Connector_Audio.pretty`) | `mating_direction` |
|---|---|---|
| Neutrik NC3FAH, female XLR, horizontal, no shell contact | `Jack_XLR_Neutrik_NC3FAH_Horizontal` | `+x` |
| Neutrik NC3MAH, male XLR, horizontal, shell contact | `Jack_XLR_Neutrik_NC3MAH_Horizontal` | `+y` |
| Neutrik NC3FAV, female XLR, vertical | `Jack_XLR_Neutrik_NC3FAV_Vertical` | (NV: vertical, likely `+z`) |
| Neutrik NRJ6HF, 6.35 mm stereo jack | `Jack_6.35mm_Neutrik_NRJ6HF_Horizontal` | (NV) |

Evidence `[S11]`: both horizontal XLR footprints draw a `Dwgs.User` line at the
panel plane. For NC3FAH it is the line x = 12.7 mm, with the fab outline stepping out
to x = 15.4 mm beyond it (the barrel protruding through the panel). For NC3MAH it is
the line y = 17.78 mm. Pads for NC3FAH `[S11]`: pins 1 and 2 are 3.4 mm pads with 1.6 mm
drills, pin 3 is a 2.9 mm pad with a 1.2 mm drill, and two 1.6 mm non-plated holes
position the part. The NC3MAH adds a `G` pad, the separate ground contact to the mating
connector's shell.

### 17.3 Required circuit

- A microphone input: DC blocking capacitors in series with each of pins 2 and 3,
  rated at least 63 V because phantom power puts 48 V behind them (NV), with the
  phantom resistors matched. A mismatch converts the common-mode phantom voltage into
  a differential signal. P48 is optional on the board, but its pops on hot-plug need
  a clamp or a switching-pop mitigation.
- A line input or output: shield on pin 1 goes to chassis through a stated network. A
  direct tie at the connector to signal ground can create a ground loop (the "pin 1
  problem"), and a floating shield lets noise in. State the choice. (NV: AES48 covers
  shield termination.)
- ESD: clamp pins 2 and 3 to GND with low-capacitance diodes or accept the input stage's
  ESD rating; XLR is reached by users.
- Output drive of a balanced line: an impedance-balanced driver on each of pins 2 and 3,
  with matched series resistors (for the arithmetic see `domains.md` section 1).

### 17.4 Panel opening and retention

The XLR "D" mounting pattern (a Ø24 mm hole and two M3 holes at 19 mm centres, NV:
Neutrik drawing not read) is the usual panel cutout. The Neutrik product page lists
DXF and STEP drawings, which give the figure (`[S17]`). Latch: the female has a locking
latch with a release button on the shell. Retention is by the panel screws and PCB
pins together. A panel-mounted XLR carries the cable's pull through the panel, so the
PCB must not be the only support.

### 17.5 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `XLR-01` | Pin 1 is shield or ground, pin 2 hot, pin 3 cold. | Pad nets of the footprint. | netlist |
| `XLR-02` | A phantom-powered input has matched 6.81 kΩ ±1 % resistors (or tighter) feeding pins 2 and 3 from a 48 V source, blocking capacitors of at least 63 V in series with the signal, and total current at most 10 mA (NV on the standard's text). | Resistor values and capacitor voltage ratings on the pin 2 and 3 nets. | netlist |
| `XLR-03` | The shield termination (pin 1 and the shell) is a stated choice: direct to chassis, to chassis through a network, or to signal ground. The case with a shell contact (`G` pad) is handled explicitly. | `X-SHD-01` and the `G` pad net. | netlist |
| `XLR-04` | Pins 2 and 3 have ESD clamps or a stated exemption. | `X-ESD-01`. | netlist |
| `XLR-05` | Both non-plated positioning holes of the footprint exist. | Footprint NPTH count. | pads |
| `XLR-06` | The panel cutout matches the vendor's drawing for the mounting series (D series), and the panel plane equals the footprint's `Dwgs.User` panel line. | Case `verify()`. | case |
| `XLR-07` | A TRS balanced jack's tip, ring, and sleeve map to hot, cold, and shield. | Pad nets. | netlist |

---

## 18. Screw terminals and pluggable terminal blocks

### 18.1 Standard

No signal standard. Electrical clearance for the pins follows the insulation
coordination rules: IEC 60664-1 (NV), and for a board, IPC-2221B Table 6-1 (NV: values
below are recalled, not re-read). Ratings are vendor ratings per part.

### 18.2 Families and stock footprints

| Family | Stock footprint | Rating | Source |
|---|---|---|---|
| Phoenix MSTBA 2,5/4-G-5,08, angled pluggable header, 5.08 mm | `Connector_Phoenix_MSTB.pretty/PhoenixContact_MSTBA_2,5_4-G-5,08_1x04_P5.08mm_Horizontal` | 12 A, 320 V (overvoltage category III, pollution degree 2) | `[S12]`, and the footprint's `descr` |
| Phoenix MSTBVA 2,5/4-G-5,08, vertical | `PhoenixContact_MSTBVA_2,5_4-G-5,08_1x04_P5.08mm_Vertical` | 12 A | footprint `descr` `[S11]` |
| Phoenix MC 1,5/4-G-3.5, 3.5 mm | `Connector_Phoenix_MC.pretty/PhoenixContact_MC_1,5_4-G-3.5_1x04_P3.50mm_Horizontal` | 8 A, 160 V | footprint `descr` `[S11]` |
| Phoenix MKDS 1,5/2, 5.0 mm screw terminal | `TerminalBlock_Phoenix.pretty/TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal` | (NV) | |

Geometry `[S11]`: MSTBA 5.08 mm, pads 2.08 x 3.6 mm, drill 1.4 mm, four pins span 17.32
x 3.6 mm, body 22.32 x 12.0 mm. MC 3.5 mm, pads 1.8 x 3.6 mm, drill 1.2 mm, body 15.4 x
9.2 mm. The conductor range of the MSTB 2,5 family is 0.2 to 2.5 mm² (NV, the RS result
`[S12]` states the 2.5 mm² nominal cross section).

`mating_direction` (the plug entry axis; wire entry axis for a screw terminal):

| Footprint | `mating_direction` | Evidence |
|---|---|---|
| MSTBA angled header | `+y` (inferred) | Pad row at y = 0, fab outline y -2.0 to +10.0 `[S11]` |
| MC 1,5 angled header | `+y` (inferred) | Fab outline y -1.2 to +8.0 `[S11]` |
| MSTBVA vertical header | `+z` | Vertical per its name |
| MKDS 1,5 screw terminal | needs-verification: the wire opening is along y, but the footprint shows no marker for which end | |

Clearance: for the pins' pad-to-pad gap (pitch minus pad width: 3.0 mm for MSTBA, 1.7
mm for MC 3.5), compare to the IPC-2221B Table 6-1 spacing for the working voltage
(NV: external conductors, uncoated, sea level, are 0.1 mm to 15 V and to 30 V, 0.6 mm
to 100 V and to 150 V, 1.25 mm to 170 V and to 250 V, 2.5 mm to 500 V). A 320 V rating
at 3.0 mm gap is within 2.5 mm; 160 V at 1.7 mm is within 0.6 mm.

Retention and strain: a pluggable header with a threaded flange (the `GF` footprints)
screws the plug to the header. A screw terminal clamps the wire and relies on the
conductor not being pulled. Reserve the plug's width: MSTB 5.08 mm plugs stand well
above the header (NV: depends on `ST` or `GST` plug type), and the wire leaves
in a direction set by the plug type.

### 18.3 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `TB-01` | Pad-to-pad gap (pitch minus pad width) is at least the IPC-2221B spacing for the working voltage. | Pad coordinates from the board plus working voltage in `design.py`. | pads |
| `TB-02` | The rated current of the part exceeds the load, and traces to the pads are sized per `domains.md` section 2. | Power budget. | netlist |
| `TB-03` | The footprint's drill and pad match the declared part (5.08, 5.00, 3.81, 3.50 mm pitches are all common and not interchangeable). | `X-PAD-01` (not in `packages.json` yet). | pads |
| `TB-04` | A mains or high-voltage terminal has a cover or case feature that prevents touch; creepage to adjacent pads is documented. | Case census. | manual |
| `TB-05` | The wire-entry side points outboard or toward a free cable path. | `X-ORI-01`. | placement |

---

## 19. Card edge connectors: PCIe and M.2

### 19.1 Standard

PCI Express Card Electromechanical Specification (PCI-SIG), and the PCI Express M.2
Specification (PCI-SIG), cited by the stock footprints' own `descr` strings. Neither
was read (NV). The facts below come from the stock footprints `[S11]` and general
knowledge marked NV.

### 19.2 Stock footprints

| Interface | Stock footprint (`Connector_PCBEdge.pretty`) | Geometry read `[S11]` |
|---|---|---|
| PCIe x1 | `BUS_PCIexpress_x1` | 36 contact fingers (2 rows of 18) at a 1.0 mm pitch, finger 0.7 mm wide by 3.2 mm (short) or 4.3 mm (long) tall, board thickness note 1.57 mm, key notch from x = 10.55 to x = 12.45 mm |
| PCIe x4, x8, x16 | `BUS_PCIexpress_x4` and others | not measured |
| M.2 key M, 2280 | `M.2_2280-xx-M` | 67 fingers of 0.35 mm width at 0.5 mm pitch, 20 degree 0.3 mm chamfer, board thickness note 0.8 mm, key M notch 1.2 mm wide |
| M.2 other keys | `M.2_2230-xx-A`, `-B`, `-E`, `M.2_2280-xx-B` and others | not measured |

The edge footprints carry `exclude_from_bom` and `exclude_from_pos_files`: the finger
set is part of the board's own outline, not a component. The footprints' `Edge.Cuts`
geometry contains the card outline and the key notch.

### 19.3 Keys and thickness

M.2 keys are positions of a notch in the module edge, which prevent mating with the
wrong socket: key A occupies pins 8 to 15, key B pins 12 to 19, key E pins 24 to 31,
and key M pins 59 to 66 (NV: from the M.2 specification as commonly quoted). The key
decides the interface the module offers: key M is PCIe x4 and SATA, key B is PCIe x2
and SATA, key A and E are PCIe x2 and USB 2.0 for wireless modules (NV).

Board thickness: PCIe card edge is 1.57 mm (the footprint note, matching 0.062 in);
M.2 is 0.8 mm `[S11]`. A board ordered at 1.6 mm cannot be an M.2 module.

### 19.4 Fabrication requirements for fingers (NV)

- Hard gold plating on fingers, with a stated thickness of at least 0.76 µm (30 µin) or
  the socket vendor's figure.
- A bevel at the leading edge, 20 degrees with a 0.3 mm chamfer on M.2 `[S11]`.
- No copper, vias, or mask openings beyond the finger pads in the insertion region
  stated by the socket vendor.

### 19.5 `mating_direction`

For a card edge the footprint is the board's own edge, so the direction is the
insertion direction of the card: `+y` for the M.2 footprint (fingers at y = +1.5 to
+3.5 mm, `Edge.Cuts` at y = +4.0) and `+y` for the PCIe x1 footprint (`Edge.Cuts` at y =
+3.45) `[S11]`.

### 19.6 Rules

| ID | Rule | Check | Class |
|---|---|---|---|
| `CE-01` | The board's thickness equals the interface's (0.8 mm for M.2, 1.57 mm for PCIe) in the stackup of `design.py` and the fab order. | Stackup thickness field. | netlist |
| `CE-02` | The key notch matches the intended M.2 key, and the footprint named in `design.py` has the same key letter as the product's interface. | Footprint name key letter against the declared interface. | netlist |
| `CE-03` | Fingers have a stated finish (hard gold) and bevel in the fab notes. | Fab notes in `kicad_fab.py` output or the BOM notes. | manual |
| `CE-04` | No component, via, or mask opening within the socket's keepout of the finger area. | Geometry against the vendor keepout. | placement |
| `CE-05` | Differential pairs (PCIe TX, RX, REFCLK) are controlled impedance with AC coupling capacitors on the transmit pairs per the specification (NV). | `domains.md` section 3. | manual |

---

## Appendix A: terms

| Term | Meaning |
|---|---|
| AHJ | Another name for the CTIA TRRS wiring order. |
| AWG | American wire gauge. A larger number is a thinner wire. |
| CC | Configuration channel. The USB Type-C pin pair used to detect attachment and orientation. |
| CTIA, OMTP | Two TRRS headset wiring conventions. They differ in which ring carries the microphone. |
| DFP | Downstream-facing port. A USB Type-C source, which supplies VBUS. |
| ESD | Electrostatic discharge. |
| IDC | Insulation-displacement connector. A ribbon-cable style connector, source of the 2-row numbering used by 1.27 mm debug headers. |
| IPC | The standards body for printed boards (formerly the Institute for Printed Circuits). IPC-2221B is its generic design standard. |
| NPTH | Non-plated through hole. |
| NV | Needs-verification. A number or claim with no source read in this work. |
| P48 | The 48 V phantom power standard in IEC 61938. |
| PD | USB Power Delivery. |
| PHY | The Ethernet physical-layer transceiver chip. |
| Rd, Rp, Ra | Type-C CC resistors: Rd pulldown on a sink, Rp pullup on a source, Ra on the VCONN pin of a powered cable. |
| TRS, TRRS | Tip-ring-sleeve and tip-ring-ring-sleeve audio plugs. |
| TVS | Transient voltage suppressor. |
| UFP | Upstream-facing port. A USB Type-C sink. |
| VBUS | The USB 5 V (or higher with PD) power pin. |
| VCONN | Power supplied by a Type-C source to a cable's electronics, on the CC pin not used for signalling. |

## Appendix B: sources

Tags marked read were opened and read in this work. Tags marked NV have no reachable
source read.

| Tag | Document | Status |
|---|---|---|
| `[S1]` | GCT, USB4105 drawing (`https://gct.co/files/drawings/usb4105.pdf`), rev B4, 2019-10-04 | Read in full |
| `[S2]` | USB-IF, USB Type-C Cable and Connector Specification, Release 1.0 (2014-08-11), chapter 4, as the 1.9 MB excerpt "USB Type-C Specification State Machine" (`xdevs.com` mirror) | Read: Tables 4-1, 4-2, 4-13 to 4-18 and the signal text. Chapters 3 and 5 not in the excerpt |
| `[S2b]` | USB-IF, "USB Type-C ECN for receptacle shell length" (Form 20140811-ECN) | Read |
| `[S3]` | JST, PH connector catalogue `ePH.pdf` | Read, pages 1 to 3 |
| `[S4]` | JST, XH connector catalogue `eXH.pdf` | Read, pages 1 to 6 |
| `[S5]` | JST, SH connector catalogue `eSH.pdf` | Read, pages 1 to 4 |
| `[S6]` | JST, GH connector catalogue `eGH.pdf` | Read, pages 1 to 4 |
| `[S7]` | SparkFun, Qwiic Connect System page (`sparkfun.com/qwiic`) | Read |
| `[S7b]` | Adafruit Learn, "What is STEMMA QT" | Read |
| `[S8]` | Wuerth Elektronik, WE-RJ45LAN 7499010001A datasheet, rev 004.001, 2024-07-26 | Read, pages 1 to 3 |
| `[S9]` | CUI Inc, PJ-102AH drawing, rev A, 2005-11-17 | Read |
| `[S10]` | Handson Technology, GX16 datasheet, as recorded in the hypercardiod_mic `docs/research.md` section 3 | Secondary (the project's record of a primary read) |
| `[S11]` | KiCad 10 stock footprint libraries, `SharedSupport/footprints/`, read with `kicad_fpcheck.py -v` and a pad dump | Read directly out of the library files |
| `[S12]` | Phoenix Contact MSTBA 2,5/4-G-5,08 (order 1757268), RS Components listing | Secondary (search result summary) |
| `[S13]` | Phantom power: IEC 61938 summarised by Wikipedia and sound-au.com | Secondary |
| `[S14]` | Arm Cortex debug connector pinout, Microchip documentation and myelin.nz "Serial Wire Debug" article | Secondary, two sources agree |
| `[S15]` | USB-IF, USB 2.0 Specification, chapters 6 and 7 | NV, not read |
| `[S16]` | USB-IF, Micro-USB Cables and Connectors Specification Rev 1.01 (2007-04-04) | NV, located but the file did not load |
| `[S17]` | Neutrik, NC3FAH product page | Read, text only; the DXF and STEP drawings were not read |

## Appendix C: needs-verification list

Each item is a number or claim above that has no source read. A research pass must
read the named document and replace the NV tag.

1. USB-C SuperSpeed pin numbers (section 1.3), plug shell 8.25 x 2.40 mm, the plug
   overmold limit 12.35 x 6.50 mm against Type-C chapter 3, and the CC overvoltage
   requirement for PD sinks. Document: USB Type-C Specification current release,
   chapters 3 and 4.
2. USB 2.0 hot-attach capacitance (10 µF), host pulldowns (15 kΩ), device pullup
   (1.5 kΩ), downstream bulk (120 µF), unit load (sections 1.4, 2.4, 3.4). Document:
   USB 2.0 specification sections 7.1.5 and 7.2.4.1.
3. Micro-B opening 6.85 x 1.80 mm, plug overmold 10.6 x 8.5 mm, 10 000 cycles. Document:
   Micro-USB specification Rev 1.01.
4. USB-A shell and receptacle opening dimensions. Document: USB 2.0 chapter 6.
5. JST PH, SH: absence of a mating latch (sections 4.5 and 6.3). Document: the JST
   product pages.
6. JST XH latch (section 5.3).
7. All `+y` and `-y` `mating_direction` values marked inferred: the horizontal JST
   footprints, HRO and Amphenol USB-C, USB-A Molex, HALO and Amphenol RJ45, terminal
   blocks, SMA edge mounts. Second source: the vendor's mated view or the footprint's
   3D model.
8. 2.54 mm header pin size and current; SWD and UART header orders (section 9).
9. Arm debug pull recommendations (section 10.2): Arm Debug Interface Architecture
   Specification.
10. GX12 every number; GX16 panel hole; GX16 key flat; wall thickness for thread
    engagement (section 11).
11. SMA thread, panel hole, torque; U.FL ratings and mated height; U.FL family
    compatibility (sections 12 and 13).
12. TRRS conventions and mic bias; 3.5 mm panel bushing; PJ320E unnamed pad
    (section 14).
13. EIAJ RC-5320A plug dimensions; plug overmold diameter; hot-plug ringing (section
    15).
14. IEEE 802.3 clause numbers and the 1 500 V rms isolation requirement; T568 pair
    order; centre tap bias (section 16).
15. XLR panel cutout and D-series holes; IEC 60268-11 and 12; AES14 and AES48;
    P12 and P24 resistor values (section 17).
16. IPC-2221B Table 6-1 spacing values; MKDS ratings; MSTB conductor range
    (section 18).
17. PCIe and M.2 key pin ranges; finger plating; device roles of each key
    (section 19).
18. The 5 mm TVS-to-pad and stub-length layout heuristics (`X-ESD-02`, `UC-ALL-02`).
