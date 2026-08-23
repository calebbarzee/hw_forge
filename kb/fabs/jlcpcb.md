---
domain: fabs/jlcpcb
tags: [jlcpcb, drc, design-rules, capability, 4-layer, 2-layer, hole-to-hole, annular-ring,
       kicad-dru, npth, pth, clearance]
source: jlcpcb.com/capabilities/pcb-capabilities (read 2026-08-22) + z_board combo DRC alignment run
date: 2026-08-22
confidence: researched
---

# JLCPCB rigid-PCB capability floors, and how they map onto KiCad DRC

Numbers read off JLCPCB's capability page on 2026-08-22 — **re-read the page before a new
order; fabs revise these.** Values are the *capability minimum*, not the no-extra-cost
tier; very small vias (<0.3 mm drill) and tight geometry can carry a price adder even when
buildable.

## The numbers (1 oz outer copper)

| Spec | 2-layer | 4-layer (multilayer) | KiCad default | Who is stricter |
|---|---|---|---|---|
| Min track width / spacing | 0.10 / 0.10 mm | 0.09 / 0.09 mm | 0.2 track, **no clearance floor** | mixed — see below |
| Min via drill / diameter | 0.3 / 0.5 typical | 0.15 / 0.25 mm | 0.3 / 0.5 | KiCad |
| Via annular ring | 0.15 mm abs. min (0.2 recommended) | same | **0.10 mm** | **JLC** |
| Via-to-via hole spacing | 0.2 mm | 0.2 mm | 0.25 | KiCad |
| PTH-pad hole-to-hole (drill web) | 0.45 mm | 0.45 mm | **0.25** | **JLC** |
| PTH drill to track | 0.28 mm | 0.28 mm | **0.25** | **JLC** |
| NPTH to track | 0.2 mm | 0.2 mm | 0.25 | KiCad |
| Copper to routed board edge | 0.2 mm | 0.2 mm | 0.5 | KiCad |
| Min NPTH hole | 0.5 mm | 0.5 mm | — | — |
| Min plated slot width | 0.5 mm | 0.35 mm | — | — |
| Min non-plated slot width | 1.0 mm | 1.0 mm | — | — |
| Silkscreen line / text height | 0.15 / 1.0 mm | same | 0.15 thick / 0.8 high text | mixed |
| Solder mask bridge | 0.10 mm | 0.10 mm | — | — |
| Outline tolerance | ±0.2 mm | ±0.2 mm | — | — |

The three **bold** rows are where KiCad's stock DRC is *looser than what the fab can
build* — a board can pass a default-settings DRC and still be rejected or mis-built at
order time. Those three are the whole point of the alignment pass.

## How to encode them (the z_board combo pattern)

Rule: **DRC floor = max(your design floor, fab floor)** — tighten where the fab is
stricter, never loosen your own floors down to fab minimums.

- Global, unconditional floors → project `board.design_settings.rules`
  (`min_clearance: 0.09`, `min_via_annular_width: 0.15`). Applied by the generator's
  `patch_project()` because `SaveBoard()` rewrites the `.kicad_pro`.
- Anything that differs by pad type → conditioned rules in the generated `.kicad_dru`,
  because **the project `min_hole_clearance` knob is hole-blind**: it cannot tell a
  plated hole (0.28 at JLC) from an unplated one (0.2 at JLC). Verified the hard way on
  z_board: setting the knob to 0.28 produced **148 false violations**, every one an NPTH
  socket slot legitimately sitting at 0.2505 mm from zone fill.

```
(rule "jlc_pth_hole_to_hole"
    (constraint hole_to_hole (min 0.45mm))
    (condition "A.Pad_Type == 'Through-hole' && B.Pad_Type == 'Through-hole'"))

(rule "jlc_pth_hole_to_copper"
    (constraint hole_clearance (min 0.28mm))
    (condition "A.Pad_Type == 'Through-hole' || B.Pad_Type == 'Through-hole'"))
```

Vias carry no `Pad_Type` property, so these conditions exclude them — via pairs stay on
the project's 0.25 knob, which already beats JLC's 0.2. That selectivity is exactly what
the knob can't do.

## Related JLC facts

- Overlapping drills are a fab reject; two holes closer than the drill web minimum must
  become **one routed slot** (z_board: two 3 mm contact holes 2.84 mm apart → one oval).
- NPTH-to-copper 0.2 mm is what makes z_board's 0.3 mm `npth_to_copper` edge-clearance
  relaxation safe (KiCad treats an unplated hole wall as board edge at 0.5 mm otherwise).
- Standard 4-layer stackup is JLC04161H-7628; inner copper 0.5 oz.
