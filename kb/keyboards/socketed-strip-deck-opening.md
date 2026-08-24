---
domain: keyboards/enclosure
tags: [deck-opening, deck-window, open-bay, nice-nano-v2, nice-view, ec11, pico-ezmate, ck-kmr2, courtyard-vs-body, knob-disc, hexpad, build123d, case-verify, mx-plate]
source: hexpad case phase, board revs 2 / 3 / 3.1 (case/hexpad_case.py, 416-check case_verify pass against board rev 3.1, 2026-08-23); numbers read out of kicad/hexpad.kicad_pcb via scripts/kicad_geom.py
date: 2026-08-23
confidence: verified-in-cad
---

# The deck opening over a socketed nice!nano strip: rect, notch, disc

For a keyboard whose top shell is an integrated MX plate (plate top 5.00 mm
above the PCB, 1.5 mm thick → 3.50 mm of clearance under the deck) carrying a
socketed nice!nano v2 and the parts that share its strip.

Every named part here stands taller than 3.50 mm or must be reached from above,
so the deck gets an open window whose rim is the bezel. There is no printable
roofed variant: `references/mechanical.md` §5 forbids a raised bay outright in a
plate-down print. What this card adds is the shape of that window, which is not
one rectangle.

Sibling cards: `nice-nano-v2.md` (courtyards smaller than the module),
`nice-view-display.md` §2a-R (the display cantilever), `mx-switch-geometry.md`
(the 3.50 mm figure), `ec11-rotary-encoder.md` §5a (the knob disc).

## 1. The heights that force an open window

Measured/derived on hexpad, above the PCB's top face:

| part | top of it | vs the 3.50 mm deck underside |
|---|---|---|
| socketed nice!nano v2, module PCB | 3.10 (socket 1.90 + PCB 1.20) | clears, barely |
| its USB-C shell | 6.30 | +2.80 over |
| nice!view body | 7.00 … 9.90 (`display_stack_h`, band 6.30–8.50) | +6.40 over |
| Alps EC11 body | 7 or 11 (`needs-verification`, sources disagree) | over at either value |
| Molex Pico-EZmate vertical, mated + cable | ~3.00 + cable outer diameter (OD) | over |
| CK KMR2 pushbutton, body + plunger travel | 1.30 | clears by 2.20 |

The encoder's unresolved body height does not matter, and that is worth
knowing before anyone chases it: it is over the deck at both cited values, so
the window is open above it either way. Assert it at both rather than picking one.

## 2. The shape: one rect, plus a notch per outlier, plus a disc per knob

```
rect A   = union over the strip's parts of (their plan obstacle) + keepout
notch B  = one small local rect per part that sticks out of A's edge
disc C   = one circle per knob, centred on its shaft, r = knob_od/2 + keepout
```

Do not grow rect A to swallow an outlier. Rect A typically spans the full
board width to one wall, so pushing any of its edges outward moves that edge
across the whole width, and the things sitting near the far corners are
fastener seats. Both of hexpad's outliers were single parts a few mm across:

- a knob: a 10–15 mm cap reaches ~6.8–7.8 mm in every direction from its
  shaft. On rev 3, growing rect A to swallow a 15 mm knob put its north edge
  0.020 mm from a mounting hole's courtyard; the disc kept the same knob
  9 mm clear of the nearest boss.
- a vertical battery connector north of the module: J1's body reached
  0.305 mm past rect A's north edge. A single rect would therefore have set that
  edge 0.605 mm further north across the full width, eating 0.475 mm of the
  far corner's Ø5.60 boss seat. The connector itself is 4.2 mm wide and nowhere
  near a boss. A 4.8 × 0.605 mm notch cost nothing.

The general form: an edge of rect A is a global cost; a notch is a local one.
Any part that pokes past an edge by less than the seat margin at that edge's far
end gets a notch.

## 3. Size it on `courtyard ∪ body`, but per part, and know which is bigger

`references/mechanical.md` §4 has the rule. The per-part answers differ, and each
one has to be asserted so a footprint edit cannot silently swap them:

| part | which rect is larger | what to size the opening on |
|---|---|---|
| **nice!nano v2** | neither: the body overhangs the courtyard by 1.010 mm at each end (the courtyard is drawn round the pad grid), and the courtyard overhangs the body by 0.250 mm per side | the union |
| **nice!view** | the courtyard contains the body (drawn as the full envelope on purpose) | the courtyard |
| **Alps EC11** | the courtyard is larger, but the extra 1.3 mm is pads and silk | the body ∪ shaft |
| **CK KMR2** | pads reach outside the molded body in x (gull-wing leads) | the body ∪ plunger |
| **Pico-EZmate** | courtyard reaches 0.820 mm outside the body | the body (for the notch) |

The distinction that pays for itself is "is the extra margin flat copper?"
Where a courtyard's surplus is pads and silkscreen, a deck lip may lie over it,
because copper is 0 mm tall. Sizing an opening on those courtyards costs deck for
nothing, and on hexpad rev 3 it cost a fastener: the courtyard-sized rect ate a
boss seat that the body-sized one cleared.

On rev 3.1, after the encoder moved, the same substitution cost only 1.400 mm of
deck. The check stayed, its answer changed, and saying so is the point. Keep the
assertion and let it report the new number rather than deleting it because it
stopped being dramatic.

Corollary worth stating: use the part's envelope (`courtyard ∪ pads`), not
its courtyard, when you mean "everything the footprint claims". On the EC11 the
pads reached 0.100 mm further west than the courtyard did.

## 4. Deck-vs-standoff is not a keepout

The opening's edge and a fastener standoff below the deck are the same plastic
on the same printed part, so the 0.30 mm component keepout is the wrong rule
and applying it fails a correct design. What actually has to hold:

```
every standoff's TOP FACE stays wholly under deck        (worst: 0.130 mm)
every insert bore stays under solid deck, with margin    (worst: 1.330 mm, min 0.80)
```

The first is a cover rule, not a clearance one: the bore needs material all
round it and the post must not be half-cantilevered. 0.130 mm of cover is fine;
0.130 mm of ligament would not be. See `hexpad/GAPS.md` #89, which proposes a
`mechanical.md` §4a for the general form.

## 5. Reaching a top-face reset through the opening

When a reset button moves to the component face, the tray poke-hole is not
"moved", it is deleted: there is nothing under it. If the deck opening
already spans the plunger, the reset is free, but open is not the same as
reachable. The numbers to assert, from hexpad (CK KMR2, Ø1.600 plunger):

| number | value | rule |
|---|---|---|
| plunger center → nearest opening edge | 1.700 mm | ≥ 1.000 |
| nearest tall neighbor's edge, from the plunger | 4.225 mm (the nice!view body) | ≥ 2.000, or it shadows the approach |
| deck underside above the plunger crown | 2.200 mm | ≥ 1.000 for a probe |
| opening admits a Ø2.50 probe beside the plunger | 0.450 mm | ≥ 0 |

Keep a dedicated Ø2.2–2.5 deck hole modeled behind a parameter (default off)
for the day the opening is shrunk or gasketed, and check its geometry while it
is off so the flag cannot ship broken.

## 6. Verify the pieces on the solid, not from the parameters

A rect+notch+disc opening is three boolean unions, and every one of them can go
missing without failing a single parametric check: the parameters still compute,
the summary still prints, the shells are still valid solids. Probe the deck slab
instead:

- a small box inside the disc's reach but outside the rect must have
  zero intersection with the deck;
- a box just outside the disc must have a non-zero one (or the "disc" is
  really an over-wide rect);
- a box in the notch must be empty, and a box 1 mm to its side must not be (or
  the notch quietly became a full-width cut across a boss seat).

Three volumes, ~15 lines, and they are the only thing standing between a missing
`+ bdisc(...)` and a printed part with a knob that does not fit.
