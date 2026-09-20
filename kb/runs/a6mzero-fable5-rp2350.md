---
domain: runs/a6mzero-fable5-rp2350
tags: [rp2350, rp2350a, e-ink, gdey0154d67, jlcpcb, freerouting, kicadroutingtools,
       footprint-mismatch, package-mismatch, w25q128jvs, p25q64sh, qspi-flash,
       part-availability, kicad-mcp, agent-driven-design, drc]
source: https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/
date: 2026-09-20
confidence: researched
---

# A third party's RP2350A e-ink board, agent-designed with a "kicad mcp": what its gate list needed and did not have

Source: blog post by a6mzero, "This PCB is brought to you by Fable 5"
(a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/, read 2026-09-20). An
outside author had an AI agent ("Fable 5") design a board through a tool the
post calls "kicad mcp" without naming which one; several projects share that
name, see `skills/hw-design/references/kicad-ecosystem.md` for the candidates
and which is the likely match. The author then ordered assembled boards from
JLCPCB. None of this project used hw_forge. It is recorded here for the gaps it
exposes in any agent-driven KiCad pipeline, this one included.

## 1. The board

RP2350A microcontroller, a 1.54 inch e-ink display (GDEY0154D67-FL04), four
buttons (two left, two right, "watchy-style"), 8 MB QSPI flash, I2C and GPIO
broken out, 4 copper layers, 31.8 by 37.32 mm. JLCPCB quoted about 26 EUR per
board; five fully assembled boards came to about 130 EUR total.

## 2. 65 DRC errors, fixed from reports alone

The first-pass board reported 65 DRC violations. The author states the agent
fixed them by reading the violation reports, with no breakdown by rule class.
Consistent with hw_forge's own "generate, read report, nudge one constant,
regenerate" loop (`docs/ARCHITECTURE.md` §4). Useful as an outside data point:
a two-digit DRC violation count on a first pass is unremarkable for
agent-generated geometry, not evidence of something structurally wrong.

## 3. Two package mismatches, caught only at the JLCPCB upload, that no hw_forge gate today catches

Two parts had a footprint whose *drawn pads* did not match the part's *actual
physical package*. DRC on the board file did not flag either, because DRC
checks a footprint's pads against themselves and against other copper, never
against the ordering code of the part assigned to that footprint.

- **Flash**: W25Q128JVS was chosen in a SOIC-8 wide package, but the footprint
  drawn on the board had SOP-8 narrow pad spacing. Caught only when JLCPCB's
  assembly upload rejected it. Resolved by substituting P25Q64SH, a footprint
  match that also happened to dodge an availability problem (§4).
- **Boost-converter transistor**: its assigned package was too small for the
  pads already drawn for it. Same discovery point, same mechanism.

Neither is a rule ERC, DRC, unconnected-nets, or fab-export-assertion catches:
hw_forge's four existing gates (`README.md`, "Every phase ends at a
machine-checkable gate"). A DRC-clean, ERC-clean, fully-routed board can still
carry a part whose footprint is for the wrong package, silently, because
nothing in the geometry is locally wrong. The pads are internally consistent;
they are simply not for the part named in the BOM.

The gate that would catch it, run before DRC ever sees the board:
`scripts/kicad_fpcheck.py` (in progress in this repository as of 2026-09-20),
which checks a footprint's pad family and pitch against the package string
implied by the part's own ordering code, not against its own geometry alone.
This is a distinct check from DRC and from schematic parity; both of those
assume the footprint is honest about what it is.

## 4. Part availability was also caught only at the JLCPCB upload

Separately from the footprint mismatch, one or more chosen parts had stock or
availability problems that surfaced only when JLCPCB processed the assembly
order, requiring back-and-forth substitution. The post gives no part count or
identity beyond the flash swap in §3. No design-time check existed to catch
this before the order was placed.

The lesson: an assembly house's upload path is not a courtesy pre-check, it is
a real gate, just one that runs after every other gate in this pipeline, at
the point where a failure is most expensive to discover. A pre-upload
part-availability check, run against a live parts dataset close to order time
rather than once at design time, moves that failure back to where fixing it is
cheap. See `kb/fabs/jlcpcb.md` "pre-upload checks" and the LCSC dataset tools
in `skills/hw-design/references/kicad-ecosystem.md`.

## 5. Freerouting: 65 footprints, 54 nets, 118 unrouted connections, 17 passes in 2 minutes, 69 routed, 49 hand-routed

Freerouting's autorouter, run against the board (65 footprints, 54 nets, 118
unrouted connections going in), completed 17 passes in 2 minutes, routed 69 of
the 118 connections, and left 49 unrouted. The agent hand-routed the
remainder. That is 58% autorouted, 42% by hand, on a four-layer, 65-footprint
board.

The author later learned of KiCadRoutingTools
(github.com/drandyhaas/KiCadRoutingTools, MIT license, verified to exist and
under active development as of 2026-09-20; see
`skills/hw-design/references/kicad-ecosystem.md` and the deep dive in
`skills/hw-design/references/autorouting.md`) and reports it routing the same
class of problem in 1.25 seconds with nothing left unrouted. That run happened
after the board had already been ordered, against the same design but not as a
controlled before/after comparison logged with numbers, so treat the 1.25 s
figure as the author's own report rather than an independently reproduced
benchmark. Worth a trial run on hw_forge's own routing wrapper before
defaulting to Freerouting's stock settings on a board of comparable density.

## 6. Pre-power-on testing: a 3.3 V to ground short check, and nothing else

The only test the author describes before first power-up is a continuity check
for a short between the 3.3 V rail and ground. The board powered up and was
recognized on the first try.

This is far short of hw_forge's own phase-4 exit gate: DRC 0 at error severity
with schematic parity enforced, 0 unconnected nets (`docs/ARCHITECTURE.md`
§3). Recorded here as an outside data point, not a technique to adopt. A
minimal bench check plus a design that happened to be electrically sound was
enough in this one instance. That is not evidence the check generalizes; it
only shows a rail-to-rail short check is close to the floor any assembled
board should pass before power is ever applied.

## 7. What comes next, unverified

The author's stated next project is a Jetson Orin Nano tablet, again with an
agent operating under the same rule (the agent designs, the human does not
hand-edit) and again with KiCadRoutingTools in place of Freerouting. No result
to harvest yet; recorded only as a signal of where this class of workflow is
headed.
