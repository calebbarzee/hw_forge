---
domain: keyboards/mcu
tags: [nice-nano-v2, low-standoff, direct-solder, under-module-ledger, case-height, mcu-envelope-union, header-trim]
source: z_board combo re-spin and case rebuild, 2026-09-20 (kicad/combo/ASSEMBLY.md "Pass 3", design_combo.MCU_ENVELOPE_UNION; case/zboard_combo_case.py, case/README.md "Parametric switches")
date: 2026-09-20
confidence: verified-in-cad
---

# A low-standoff nice!nano mount needs an explicit under-module height ledger

`nice-nano-v2.md` documents the module's standard socketed stack: a
Mill-Max low-profile socket (1.90 mm) plus the module PCB (1.20 mm) plus the
USB-C shell (3.20 mm), 6.30 mm total above the board. That stack has enough
clearance under it that nothing normally needs to be checked for interference
a slide switch or connector nested between the module's two pad columns
sits well clear of a 1.90 mm standoff.

**Dropping the standoff removes that margin, and turns "nothing needs
checking" into "everything under the module needs checking."** A
direct-solder or trimmed-header mount can bring the standoff down to
roughly **1.00 mm** (header plastic removed), worth it for case height,
since 6.30 mm of stack drives an 0.90 mm taller case than a 5.40 mm stack
does, but every part whose footprint falls under the module's plan
envelope now has to clear that shorter standoff, not the original 1.90 mm.

## The check: recompute the ledger from the board, not from memory

z_board's combo re-spin needed this exactly once. The board's `SW_RST`
(reset button) pads overlapped the module's plan envelope
(`MCU_ENVELOPE_UNION`, the union of both hole grids' full PCB-body + USB-shell
rectangles, see `module-envelope-vs-case-wall.md`) by 0.84 mm in x. At the
originally-assumed 1.90 mm socket standoff this was harmless (DRC reported 0
errors either way, since DRC checks copper and hole clearance, not a plan-
view obstacle rectangle at a different Z). Once the case dropped the
standoff to ~1.00 mm, it was not: `SW_RST`'s own body height no longer had
1.90 mm of clearance to live inside.

The fix was two steps, both worth keeping as a pattern:

1. **Check every footprint's obstacle rectangle against the module's
   envelope, not just the one part expected to be a problem.** z_board
   checked every footprint's `pads_bbox` (no footprint on this board
   carries a courtyard, so pads bound the whole obstacle) against
   `MCU_ENVELOPE_UNION` for both hole grids. `SW_RST` was the only
   intersection on the entire board, worth confirming by enumeration, not
   assuming.
2. **Move the offending part, then re-verify the ledger is empty.**
   `RESET_C` moved +1.20 mm east; `SW_RST`'s pads now clear the envelope by
   0.36 mm. The ledger, one row per part that survives the check, height
   and clearance each asserted, reports **empty** when nothing intersects,
   which is itself the assertion that matters: an empty ledger at a known
   standoff height is the thing a case's `mcu_standoff` parameter needs to
   stay true against.

## The case-side assertion this feeds

z_board's case generator recomputes the same ledger from the board's own
obstacle rects on every run and asserts
`mcu_standoff >= tallest_under_module_part + 0.30`. With the ledger empty
(z_board's current state), *any* `mcu_standoff >= 0.30` passes this specific
check numerically, the 1.00 mm default is chosen for header-trim solder
clearance, not because the ledger demands a taller number. That distinction
is worth stating explicitly wherever this pattern is reused, so a future
reader does not mistake "the check passes" for "the check is the reason for
the chosen value."

## Numbers, for reuse

| Quantity | Value |
|---|---|
| Socketed standoff (documented default, `nice-nano-v2.md`) | 1.90 mm |
| Low/trimmed-header standoff (this pattern) | ~1.00 mm |
| Height budget a low standoff buys, stack-wide | ~0.90 mm (6.30 → 5.40 mm stack) |
| Case height at 1.00 mm standoff (z_board combo, direct-solder + 303450 cell) | 14.85 mm |
| Case height at 1.90 mm standoff (same board, socketed alternative) | ~15.75 mm |
| Margin an under-module part needs past the standoff | ≥0.30 mm (`mcu_standoff >= tallest part + 0.30`) |
