---
description: Run the hardware gate on a KiCad project: ERC, DRC with schematic parity, and unconnected nets. Then summarize and triage failures.
argument-hint: "<project-dir> [--name NAME]"
---

# /hw-validate

Run the gate. This is the pipeline's definition of "does this board pass" and it
is the same check every phase-4 exit uses.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kicad_gate.py" $ARGUMENTS
```

With no argument, find the project(s) yourself: look for `*.kicad_pro` /
`*.kicad_pcb` under the working tree (commonly `kicad/<variant>/`) and run the
gate on each. If a project's schematic and board share a directory but not a base
name, pass `--name NAME`.

The script writes its JSON reports beside the project, prints a per-check
summary, and exits nonzero if anything failed. `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/report.py" FILE.json` gives a one-line summary of
any individual report if you want to re-read one.

## What passing means

**Precondition: zones filled.** An unfilled pour reports its nets as
unconnected, so fill before gating. If VCC or GND read as unconnected, suspect
the fill before you suspect the routing.

The four numbers, per project:

- **ERC 0** (electrical rules check) at error severity.
- **DRC 0** (design rules check) at error severity.
- **Schematic parity 0.** Parity is not optional. A board can be geometrically
  perfect and wired to a netlist that is not the schematic's.
- **0 unconnected** nets.

Report each project on its own line with the four numbers, and say explicitly
whether the gate passed or failed. Do not soften a failure into a caveat.

## On failure: triage

Read the violation **records**, not just the count. Each one names a location, a
layer, and the two items involved. That is what separates one systematic error
from many independent ones. Large counts usually collapse to a single cause.

Order of investigation:

1. **Group the violations.** By type, then by location. All in one block? One
   cause. Spread evenly across every instance of a repeated cell? A cell-level
   error, so fix the cell and regenerate. Do not fix instances.
2. **Check for the toolchain signature.** If the *committed* board still passes
   while a *fresh regeneration* fails, the fault is in generation or the
   toolchain, not in the design rules or the project settings.
   `references/kicad-api.md` lists the known API changes that produce exactly
   this, including the flip-direction argument whose meaning changed between
   KiCad versions and silently rotates every back-face footprint.
3. **Consult the reference for the class of failure:**
   - clearance, zones, island removal, unconnected planes, severity settings,
     s-expression or CLI behaviour → `references/kicad-api.md`
   - net topology, layer assignment, mirroring, matrix and chain routing, power
     rails → `references/electronics.md`
   - and recall matching KB (knowledge base) cards by domain and tag before
     theorizing.
4. **Fix in the generator, never in the board file.** Move one named constant,
   regenerate, re-run the gate, compare counts. One hypothesis per pass.
5. **If the count does not move across two passes**, your model of the failure is
   wrong. Re-read the records. If what makes it immovable is a user-locked
   decision, stop and report it as a barrier (blocked / why / options /
   recommendation) rather than grinding.

If the project has no `Makefile` target for regeneration, say so. The nudge loop
is only cheap when regeneration and validation are each one command, and adding
those targets is worth doing before iterating.

## Beyond the gate: the semantic audit

The gate proves the design is **self-consistent**, not that it is **right**.

A schematic wired to the wrong pins, with a diode convention the firmware
default contradicts, passes ERC 0 / DRC 0 / parity 0 cleanly.

When the user asks to validate the *conceptual* build-out (pin definitions,
power delivery, chain order), run this second pass.

1. **Export the truth**: `kicad-cli sch export netlist --format kicadsexpr`
   gives what is actually connected, independent of how the schematic looks.
   Parse it with a small script; never audit by eyeballing the schematic.
2. **Three-way diff** every fact against the intent sources: the logical design
   file (pin tables, net lists, chain order) and the human docs. Code says X,
   docs say X, netlist says X. Any disagreement is a finding **even when the
   netlist is right**, because a stale doc causes the next bug. Say which source
   is wrong.
3. **Check by category, scripted:**

   | Category | What to compare | Pass condition |
   |---|---|---|
   | Pin map | every MCU (microcontroller) pad against the expected net | every pad is on its expected net |
   | Power | every power-type pin against its intended rail | on the intended rail, and no power pins on signal nets |
   | Chains | the node count of each intermediate link net | exactly 2 nodes (zero fan-out) |
   | Matrix | the expected key→row/col table, regenerated from the design file, against the netlist | no differences |
   | Polarity | diode/cap pin-1-vs-pin-2 across all instances | the same convention on every instance |
   | No-connects | spare pins and named nets | spares explicitly NC'd, and no single-node named nets |
   | Package | every footprint's pad geometry against its declared package (`kicad_fpcheck.py BOARD --design design.py`) | PASS, or an explained WARN or FAIL naming the rule that fired; footprints checked only against their own name are named as such |
   | Schematic rules | decoupling on every IC power pin, bulk capacitance per rail, series resistor on the first addressable LED, pull-ups on I2C and reset nets, protection on connector power inputs (`kicad_schrules.py SCHEMATIC.kicad_sch`) | exit 0, meaning no error-severity finding; each warning and each waiver is listed with its reason. Connectivity only: placement distance is a board check |

4. **Symbol pin semantics vs footprint pad numbering**, for every non-stock
   part. It is the one error class that passes ERC, DRC, *and* parity while
   swapping power and data (the SK6812MINI vs -E hazard).
5. **Audit the firmware handoff**: anything copper fixes that a firmware
   default could silently contradict. Examples: diode direction vs the kscan
   binding's default, peripheral default pinmuxes vs the matrix, moved pin maps
   needing their own devicetree (the firmware's hardware-description source).

Report as a table of check → PASS/FAIL → one-line evidence. "All correct" is
only a result when each row shows what was compared.
