---
domain: keyboards/display
tags: [nice-view, sharp-memory-lcd, ls011b7dh03, spi, spi0, display, nice-nano, zmk-display, macro-pad, hexpad, dry-run, mounting, stack-height, mechanical, enclosure, display-bay, usb-c-clearance, header-offset, rev-3, rev-3.1, 3d-model, no-model-found, regression-note]
source: hexpad resource-scout run, 2026-08-22 — nicekeyboards.com/docs/nice-view, zmkfirmware/zmk (app/boards/shields/nice_view*), ceoloide/ergogen-footprints (commit 48935f54), HookyQR/nice_view_pcb (commit f09725d5), this machine's nice-nano-v2.md and zmk-electrical.md cards; follow-up run, 2026-08-22 — Nice-Keyboards/nicekeyboards.com raw mdx source, typeractive.xyz (nice-view product page + no-solder-spring-headers), github.com/joric/nrfmicro wiki; hexpad phase-6 case run (case/hexpad_case.py, 239-check verify() pass (board rev 2)) — see 2a; hexpad phase-7 harvest (§3.6 re-scoped); rev-3 research pass, 2026-08-23 — re-confirmed no Nice-Keyboards hardware/mechanical repo exists, re-applied the existing two-source header offset to the corrected L4 geometry, confirmed no STEP/WRL model exists for nice!view (only an unusable Printables STL); hexpad rev-3.1 phase-6 case run, 2026-08-23 (case/hexpad_case.py, 416-check verify() pass against board rev 3.1) — see 2a-R, which REGRESSES 2a's display-beside-the-connector win
date: 2026-08-23
confidence: researched
---

# nice!view display

Researched for the **hexpad dry-run project (6-key macro pad, nice!view on a nice!nano
v2)** — see `hexpad/RESOURCES.md` for the full citation table and
`hexpad/lib/gen_nice_view.py` for the generated symbol/footprint. §3's checklist is
answered below; items still open are marked `(needs-verification)` inline. A follow-up
pass (§2's "Mechanical" paragraph) closed the mounting-stack-height question as far as
it can be closed with text sources — the honest answer is "no authoritative figure
exists," not a number. Raise this card to `verified-in-cad` once a board carrying
`DISP_nice_view` passes ERC/DRC/parity, and to `verified-in-hardware` once a populated
hexpad unit's display actually lights up **and** its measured stack height is recorded
here to replace the inference below.

## 1. What I can state with reasonable confidence

- nice!view is a **Sharp memory-in-pixel LCD** ("memory LCD") module from Nice Keyboards,
  sold as a low-power alternative to the 128×32 I²C OLED used on nice!nano keyboards.
- **Interface is SPI and write-only.** A memory LCD holds its image with essentially no
  refresh current, which is why it is the low-power choice: static power is orders of
  magnitude below an OLED, and there is no I²C bus to share.
- Being SPI, it needs a **chip-select pin**, so it requires **one more pin than the 4-pin
  I²C OLED header** on standard nice!nano keyboards. This is the reason ZMK ships an
  *adapter* shield alongside the display shield — the adapter remaps the existing OLED
  header pins into the SPI roles and picks up the extra CS line.
- It is **socketed on top of the nice!nano** (pin header / socket strip), in the same
  position the nice!oled occupies, so it stacks above the module and adds to the module's
  z-stack (see `nice-nano-v2.md`: socket 1.90 + module PCB 1.20 already reaches 3.10 mm
  before the display).
- **ZMK supports it as a shield**, combined with the keyboard shield on the build command
  line, and requires the display subsystem enabled (`CONFIG_ZMK_DISPLAY=y`). ZMK draws its
  own nice!view widget (battery, output/BLE status, layer, and an art panel); it is not a
  generic framebuffer you can draw to without writing code.
- Consequences that are **already actionable for hardware design**, independent of the
  exact pinout:
  - it is an **SPI peripheral**, so the same rule as any other SPI device applies — pick a
    dedicated SPI instance in a board overlay and check the default pinmux of every other
    SPI/UART instance against the matrix (`zmk-electrical.md`).
  - a display sharing the SPI bus with an LED chain needs either distinct instances or
    proper CS discipline; on a 6-key pad there are plenty of free GPIOs, so **use a
    separate instance**.
  - the display sits **above** the MCU module, so the enclosure's z-budget is
    `socket + module PCB + display stack`, and a plate/deck cannot pass over it — the same
    open-window conclusion as a socketed nice!nano (`mx-switch-geometry.md`).
  - low static current means the display is **not** a candidate for `ext_power` gating on
    power grounds; check whether ZMK gates it anyway.

## 2. Verified facts

**Module pin order (its own 5-pin, 2.54mm-pitch header, single row):**
`1=MOSI 2=SCK 3=VCC 4=GND 5=CS`. Two independently-authored KiCad assets agree exactly:
`ceoloide/ergogen-footprints` `display_nice_view.js` (commit `48935f54`) and
`HookyQR/nice_view_pcb` `nice_view.kicad_mod`/`.kicad_sym` (commit `f09725d5`). **Caveat
(needs-verification):** both ultimately cite the same nicekeyboards.com pinout *image* as
their datasheet reference, and that image could not be read directly (text-only fetch
tooling cannot OCR it) — so this is two independently-authored transcriptions agreeing,
not confirmation against the primary image itself or a third, unrelated lineage. Treat as
strong but not airtight.

**Signal → nice!nano v2 default GPIO** (this is the fact that matters for firmware/pin-map
work, and it *is* airtight — three-way agreement): CS = D1/**P0.06**, MOSI = D2/**P0.17**,
SCK = D3/**P0.20**. Sources: `nicekeyboards.com/docs/nice-view/pinout-schematic/` (vendor
docs) + `zmkfirmware/zmk` `app/boards/shields/nice_view_adapter/boards/
nice_nano_nrf52840_zmk.overlay` (`cs-gpios = <&pro_micro 1 ...>`,
`NRF_PSEL(SPIM_MOSI, 0, 17)`, `NRF_PSEL(SPIM_SCK, 0, 20)`) — cross-checked a third time
against this project's own `nice-nano-v2.md` D-label→port table. A fourth psel,
`NRF_PSEL(SPIM_MISO, 0, 25)`, is asserted by the same overlay, but **P0.25 has no D-label**
in the verified nice!nano v2 pin map — almost certainly a required-but-unconnected pin for
the Zephyr SPIM driver binding (the display is write-only), but this was not independently
confirmed **(needs-verification)**.

**SPI instance**: `spi0` (SPIM0), `spi-max-frequency = <1000000>` (1MHz). Source: ZMK's
`nice_view.overlay`. Uses `pinctrl-1 = <&spi0_sleep>` with `low-power-enable` — worth
copying into any board overlay that reuses this SPI instance elsewhere.

**Mechanical**: PCB outline **36 × 14 × 2.9mm**. Three-way agreement: vendor listing text
(splitkb/mechboards/keeb.supply, consistent) + both vendored footprints' outline geometry
(36×14mm each, independently). Header sits **~1.3mm from one short edge** (ceoloide:
1.3mm; HookyQR: 1.27mm — agree to within 0.03mm), i.e. near one end, not centred. The
2.9mm figure is read as the module's own body thickness (PCB + panel + conformal coat),
**excluding** its mounting standoff below it — a reasoned inference, not confirmed by
any source; no footprint carries Z data to cross-check it **(needs-verification)**.

**Mounting stack height — the hexpad follow-up (still unresolved as a number, but now
fully researched rather than merely "not found"):**
  - The **standard kit hardware** is a plain 5-pin, 2.54mm-pitch solder header+socket
    pair (confirmed by reading the *raw `.mdx` source* behind
    `nicekeyboards.com/docs/nice-view/getting-started` and `.../pinout-schematic` in
    `Nice-Keyboards/nicekeyboards.com` on GitHub — not just the rendered page). **No
    part number or height figure exists anywhere in the official text source**; the only
    place any dimension appears is three PNGs with zero accompanying alt text in the
    markdown — confirmed image-only, not a fetch-tool artifact.
  - **Real-world evidence says do not assume it clears a stacked arrangement**: a named
    reviewer (Yash Savani) on Typeractive's nice!view product page reports, verbatim,
    "it has to be fit press and still doesn't fit on top of the nice!nano v2s. Feels
    like there needs to be more clearance." `researched` confidence that a genuine fit
    problem exists in this exact scenario; not a measured shortfall.
  - **One purpose-built aftermarket answer exists**: Typeractive's "No-Solder Spring
    Headers," sold in two packs — "(2x) 12pin header, 5mm height, good for one
    nice!nano" and **"(1x) 5pin header, 7mm height, good for one nice!view,"** the
    latter marketed explicitly to "fit it right above the nice!nano without any
    soldering." 7mm clears hexpad's required 6.30mm (1.90 socket + 1.20 nice!nano PCB +
    3.20 USB-C shell, per this card's own verified stack figures) by 0.70mm.
  - **That number conflicts with a second, independent source**: the
    `github.com/joric/nrfmicro` wiki "Sockets" page describes what reads as the same
    Typeractive product family as **5.0mm**, "short enough for the nice!view to sit
    atop." Not resolved — may reflect a different product revision, a looser
    paraphrase, or a different mounting topology (nice!view resting on the elevated
    MCU's own top face rather than plugging into its own independent socket row, which
    is hexpad's actual arrangement). **Stated as a genuine conflict, not adjudicated.**
  - **Working assumption for a case generator**: make stack height a named parameter,
    not a constant. Default **7.0mm** (the one purpose-built, dimensioned part), design
    the keep-out to tolerate **6.3–8.5mm** without a hard collision, and re-measure
    whatever part is actually purchased before trusting either cited number precisely.
  - Separately, hexpad's own PCB phase confirmed the display's envelope sits *directly
    over* the nice!nano (compounding z-stack at one location), closing the other half of
    the previously-open "stacked vs. co-located" question for this project — that
    resolution is project-specific, not a general nice!view fact, so it is not stated as
    settled for every board using this display.

## 1b. Rev-3 correction: header-to-body offset for a west-of-MCU mount (hexpad L4)

**hexpad's SPEC.md L4 was corrected by the user in rev 3.** The header does not sit inside
the nice!nano's pad corridor (rev 1/2's assumption, which §2a below was written against);
it sits **west of the nice!nano's pin rows, outside the MCU socket entirely**, with the
display body then resting on top of the module, extending east over it. This card already
had the fact needed to place it correctly — it just hadn't been asked for in these terms
yet.

**Header-to-body offset, in display-local coordinates** (origin at the display PCB's own
centre, module 36mm long × 14mm wide): the 5-pin header sits on the centreline (x = 0,
spanning the full 14mm width is irrelevant here — the header row is short and centred in
x), at **y ≈ +16.5 to +16.7mm**, i.e. **~1.3mm in from one short edge**. The body's other
36 − 1.3 ≈ **34.7mm extends away from the header** in the −y direction. This was already
two-source verified in §"Mechanical" above (ceoloide `display_nice_view.js`: header at
local y=16.7 within a ±18mm outline, 1.3mm from the near edge; HookyQR's footprint: header
at y=16.51 within a 17.78/−18.22mm outline, 1.27mm from the near edge — the two agree to
0.03mm). **Nothing new was found from a nicekeyboards-owned hardware/mechanical repo** —
confirmed (again, for this pass) that `Nice-Keyboards`'s GitHub org has no PCB-design or
mechanical-drawing repo for nice!view (only `nicekeyboards.com` the website, `nice60-zmk-config`,
and `nice-keyboards-docs`, none of which carry nice!view hardware source). The two vendored
community footprints remain the best two sources for this fact.

**What this means for placement**: put the header socket west of (outside) the nice!nano's
pad columns — do not try to route it through the 15.24mm inter-column corridor. Then the
display body, whose long axis runs away from the header by ~34.7mm, extends *east*, laid
so its far end lands over the nice!nano's own pad footprint — "the glass lands centered
over the module" is achieved by choosing the header's exact (x,y) west-of-the-MCU so that
the body's 34.7mm extent, minus the ~1.3mm header margin already spent at the near end,
centers the remaining ~33.4mm of body length over the nice!nano's own ~33mm outline
(`nice-nano-v2.md`: nice!nano v2 is 33.0 × 17.78mm) — a coincidence of scale worth noting:
the display body (minus its header margin) and the nice!nano module are almost the same
length, which is presumably *why* this stacking convention exists at all.

**3D model**: none was found for the nice!view module itself, in any format usable by
KiCad. The only hit was a Printables **STL** ("nice!view OLED" by spamwax) — STL is a mesh
format KiCad's 3D viewer does not consume as a footprint-linked model (KiCad wants STEP or
WRL) and it was not vendored for that reason, not for a license reason. **No STEP/WRL exists
that this run could find.** Per L11's own fallback allowance, use a **placeholder box**
sized to the verified envelope: 36 × 14 × 2.9mm body, positioned per the header offset
above, seated at whatever mounting-standoff height the case phase's named parameter
resolves to (§"Mounting stack height," 7.0mm nominal). This is an honest placeholder, not a
found model — say so wherever it's linked.

**This invalidates the specific numbers in §2a below** (the 18.88×36.85mm window, the
7.00mm/0.25mm setback figures) — those were computed for the rev-1/2 "header in the pad
corridor, display centred lengthwise over the MCU" geometry. The *method* in §2a (union of
plan envelopes, display-underside-vs-USB-shell as the load-bearing check, stack height as a
named parameter) still applies; only the specific coordinates need re-deriving against the
corrected header offset above. **Not re-derived in this pass** — that is case-phase work,
not resource-scout's, and is flagged in `hexpad/GAPS.md`.

## 2a-R. REGRESSION NOTE — hexpad rev 3/3.1 gave the §2a win back, by locked-decision collision

**Convention**: `hexpad/GAPS.md` #78 asks that when a card records a design *win*
and a later revision gives it up, the card is amended rather than the loss living
only in that revision's report. This is that amendment. Read it before §2a's "the
layout that removes the clearance entirely", which is still correct advice and was
still overridden.

| | |
|---|---|
| **Property lost** | the display sitting *beside* the USB-C receptacle, which converted a knife-edge **z** clearance into a **plan** check that no header height can fail (§2a's closing recommendation, and rev 2's measured 7.00 mm set-back). |
| **Decisions that collided** | **L4** (rev 3, user-corrected): the 5-pin header sits *west* of the nice!nano's pin rows, outside the socket, body cantilevering east. **L10**: an EC11 encoder in the same north strip. Each satisfiable alone; jointly they are not — a header 1.3 mm from the body's west short edge with 34.7 mm of body east of it cannot both start west of the pin rows and stop west of a 7.35 mm-deep receptacle, and pulling it far enough west takes the whole strip the encoder needs. |
| **The number** | display body east end **x 52.225** on a board whose east edge is 51.625: the glass covers the receptacle (x 44.875…52.225) entirely in plan and hangs **0.600 mm** past the board edge, *exactly* flush with the USB-C shell's outer face. So display-underside-vs-shell-top is load-bearing again: **+0.70 mm** at the 7.00 mm default, **0.00 mm — touching** at the 6.30 mm band floor, +2.20 at 8.50. Identical to rev 1's numbers. The honest usable band is **6.60–8.50** for a 0.30 keepout. |
| **What would get it back** | only L4 moving. `DISP_HX ≤ 10.175` clears the receptacle and puts the header ~11 mm west of the pin rows — which is the encoder's strip. So: give up the encoder, or accept a z clearance that goes to zero on the low cited header height. |

**What this means for a reader of §2a.** The set-back rule
(`display_setback > receptacle_depth − shell_overhang`) is still right and still
the thing to design for on a *new* board. What rev 3 proves is that it is only
available if nothing else claims the strip on the other side of the module — so
**check the set-back against the rest of the north-strip budget before treating it
as free.** §2a calls the cost "nothing"; on a board with an encoder it is the
encoder.

Three consequences that appear only in the over-the-receptacle arrangement, all
measured on hexpad rev 3.1:

- **The case cannot help.** The deck is an open window, so nothing the enclosure
  does changes a board-part-to-board-part clearance. The case's whole contribution
  is to *assert* the number at the band floor, the default and the ceiling, so a
  wrong header fails a check instead of failing at assembly.
- **A plug's overmold butts against the shell's outer face at x 52.225 — exactly
  where the glass ends.** Zero plan overlap and zero margin: the plug's moulding
  sits flush against the display's edge. It inserts; it looks like an
  interference and is not. Worth asserting at 0.000 mm rather than eyeballing.
- **The enclosure's east wall needs no notch for the cantilever.** With a 5.00 mm
  plate top the glass at 7.00 mm flies over the wall with 2.00 mm to spare (1.30
  at the band floor) — so the third feature on that wall is an *assertion*, not an
  opening. It does overhang 0.300 mm of the wall's footprint in plan, and stops
  2.200 mm inside the case's outer face, so a knock lands on plastic.

Worked, `verify()`-passing at 416 checks: `hexpad/case/hexpad_case.py`
(`display_stack_h`, `display_band`, `display_band_safe`).

## 2a. The enclosure consequence, worked (hexpad phase 6, `verify()`-passing) — rev-2 geometry, superseded by §1b above and REGRESSED by §2a-R

The stack height stays unresolved as a *number*, but its consequences are now fully
quantified, and the important finding is that **the case does not care and the board
does**.

**Design it as an open bay whose window rim is the bezel.** The display cannot be roofed
(a 1.5 mm MX plate leaves 3.50 mm; the display's underside is at 6.3–8.5 mm) and a raised
shroud stands proud of the print's plate-down reference face, which
`references/mechanical.md` §5 forbids. So the deck gets one open window sized on the
**union** of the nice!nano's and the nice!view's plan envelopes (each unioned with its own
courtyard — see `nice-nano-v2.md` on courtyards being the *smaller* rect), and the display
stands proud of the plate. On hexpad: window **18.88 × 36.85 mm**, its width set by the
*module* underneath, not the 14 mm display, so ~2.4 mm of nice!nano shows along each long
side. That is the look; there is no printable alternative.

**The load-bearing clearance is display-underside vs the nice!nano's USB-C shell** (6.30 mm
above the host PCB) — *whenever the display's plan envelope covers the receptacle*, which
depends on the layout and is the single most useful thing to check early (see "layout that
removes it" below):

| stack height | display body | proud of a 5.00 mm plate top | clear of the USB-C shell |
|---|---|---|---|
| 6.30 (low end of the cited range) | 6.30 – 9.20 | +4.20 mm | **0.00 mm — touching** |
| **7.00 (Typeractive figure)** | 7.00 – 9.90 | +4.90 mm | **+0.70 mm** |
| 8.50 (tallest generic socket cited) | 8.50 – 11.40 | +6.40 mm | +2.20 mm |

So the honest band is **6.60 – 8.50 mm** if you want a 0.30 mm keepout, and the 5 mm
citation would be an outright collision. This is consistent with — and arguably explains —
the named first-hand report that the standard kit hardware "doesn't fit on top of the
nice!nano v2s": the standard 2.54 mm solder header/socket pair is nowhere near 7 mm.

**Two more consequences worth knowing before laying a board out this way:**
- With the display's short edge flush to the board's own edge, its north face ends up
  **directly above the USB-C receptacle mouth**, separated only by the shell's ~0.6 mm
  overhang. A plug inserts, but its overmold sits visually flush against the display's
  edge. Setting the display back 2–3 mm from the board edge costs nothing and removes it.
- The display standing 4.90 mm proud of the plate is *below* typical 1u keycap height
  (~9.5–11 mm above the plate), so **the keycaps are the display's protection**. On a
  keyless corner of a board it would be fully exposed.

Make the stack a named parameter, keep the case clear of the display entirely, and assert
the display-vs-USB-shell clearance — that assertion is the one that fails when the wrong
header arrives. Worked example: `hexpad/case/hexpad_case.py` (`display_stack_h`,
`display_band`).

### The layout that removes the clearance entirely (hexpad rev 2)

**Rotate the module so USB exits a SIDE edge, lay the display along the module's long axis,
and set the display back from that edge by more than the receptacle's depth.** The display
then sits *beside* the receptacle instead of over it, and the whole z problem above
disappears — the stack height stops being a collision risk and becomes a cosmetic
ride-height choice.

hexpad rev 2, measured: module at rot −90 with USB east, receptacle shell
x 44.875 … 52.225 (7.35 mm deep including its 0.60 mm overhang), display body
x 8.625 … 44.625 — i.e. **set back 7.00 mm from the board's east edge and stopping 0.25 mm
short of the shell.** Consequences:

| | display over the receptacle (rev 1) | display beside it (rev 2) |
|---|---|---|
| clearance that governs | display underside vs 6.30 mm shell top | display underside vs the module's own top-side parts (~4.30 mm) |
| at the band floor (6.30) | **0.00 mm — touching** | **+2.00 mm** |
| at 7.00 default | +0.70 mm | +2.70 mm |
| plug overmold | 0.60 mm from the display's edge | 7.60 mm of horizontal clearance |
| the assertion | a **z** check that fails on the wrong header | a **plan** check that cannot fail on a header at all |

**Set-back rule**: `display_setback > receptacle_depth − shell_overhang` (7.00 > 6.75 here).
Cost: nothing — the display is 36 mm long on a 65 mm board either way. So on any new board,
**place the display beside the connector, not over it**; the 0.00 mm case above is a layout
choice, not a fact about the part.

The keycap observation survives the rotation: 4.90 mm proud of the plate is below typical 1u
keycap height (~9.5–11 mm), so the caps still shield the display — but only if there are
keys around it.

**Electrical**: 3.3V, <10µA typical static current (memory-in-pixel technology), 3-wire
SPI, Sharp LS011B7DH03 panel, 160×68px, 1.08" diagonal, ~30Hz refresh (`serial-vcom-interval
= <33>` in the ZMK overlay ≈ 30.3Hz — numerically consistent with the vendor-stated 30Hz).

**ZMK shield config**: shields are `nice_view` (the display, requires feature
`nice_view_header`) and `nice_view_adapter` (bridges an *existing* 4-pin I2C-OLED header to
a 5-pin `nice_view_header`, requires feature `i2c_oled`, exposes `nice_view_header`; bodges
CS to `&pro_micro 1`/P0.06 by default — override `cs-gpios` on `&nice_view_spi` if that pin
is taken). `CONFIG_ZMK_DISPLAY=y` is pulled in automatically by `nice_view.conf`; opting
out of the shield's own custom status widget additionally needs
`CONFIG_ZMK_DISPLAY_STATUS_SCREEN_BUILT_IN=y` + two `LV_FONT`/`LV_Z_FONT` keys. Build
incantation: `-DSHIELD="<kb> nice_view"` if `<kb>` exposes `nice_view_header` natively, or
`-DSHIELD="<kb> nice_view_adapter nice_view"` (adapter **first**) if `<kb>` only exposes an
OLED-compatible `i2c_oled` header. **No upstream example of a shield that exposes
`nice_view_header` directly (i.e. a genuine native 5-pin design with no adapter) was found**
in `zmkfirmware/zmk` at time of writing — every worked example goes through the adapter.
A board wiring nice!view to its own dedicated SPI0 pins from scratch (not retrofitting an
OLED header) should define `&nice_view_spi` directly in its own board overlay the same way
`nice_view_adapter`'s board-overlay does internally, without including the adapter shield
at all — this is a reasoned inference from the verified facts above, **not itself confirmed
against a working native example (needs-verification)**.

**Footprint/symbol**: no nice!view footprint exists in the three local vendor libraries
surveyed by `local-libraries.md` (foostan `kbd.pretty`, ScottoKeebs `ScottoKicad`,
`keyswitches.pretty`). A workable KiCad-native pair was generated from the verified pin
table above (not adopted from either vendored reference) — see `hexpad/lib/gen_nice_view.py`
and `hexpad/RESOURCES.md` §2. Pad style (1.7mm/1.0mm drill, 2.54mm pitch, pad-1 rect) matches
the nice!nano socket footprint family already proven in `nice-nano-v2.md`.

## 3. Checklist status (was §3, now closed out)

1. **Pinout** — done, two-source (with the caveat above). ✅
2. **Mechanical** — outline/header-position done, three-source; the *enclosure consequences* of the
   unresolved stack height are now fully quantified in 2a (open-bay pattern, and the
   display-vs-USB-C-shell clearance table that makes 6.30mm a touching fit and any 5mm
   claim a collision). Socket/mounting-standoff
   height above the nice!view PCB was researched exhaustively in a follow-up pass and
   **has no authoritative answer** — two community sources conflict (7mm vs. 5mm) and
   the official kit gives no figure at all, with a named real-world report that it does
   not reliably clear this exact stacking arrangement. This is now a closed research
   question with an honest "unresolved, use a parameter" answer, not an open one. The
   stacking-vs-adjacent question was resolved *for hexpad specifically* (compounds, per
   its own PCB layout) but remains open as a general nice!view fact for other boards. ⚠️
3. **ZMK config** — done, read from the ZMK tree (a fresh fetch + this machine's own older
   `keyboard/zmk` checkout, which agreed except for two VCOM lines added upstream since that
   checkout's pinned commit). Native-vs-adapter choice for a from-scratch board is inferred,
   not confirmed against a working example. ⚠️
4. **Electrical** — done. ✅
5. **Footprint/symbol** — done: generated, not adopted, from the verified table. ✅
6. **Pin-map interaction** — done as far as phase 1 can take it, and **the collision check
   is owned by the schematic phase (phase 3), not by this checklist.** Phase 1's deliverable
   is the *list*: the display claims `spi0` at CS P0.06 (D1) / MOSI P0.17 (D2) / SCK P0.20
   (D3) per §2, an addressable-LED chain claims its own `&spi3` (`zmk-electrical.md`), and
   the module's default peripheral pinmux — `uart0`, `i2c0`, `spi1`, blue LED, ext-power,
   plus the NFC pads and the fact that `spi0`/`spi2`/`spi3` start unclaimed — is tabled in
   `nice-nano-v2.md`, "Default peripheral pinmux — the enumeration, done once". **Hand that
   list to the schematic phase.** Checking it against the chosen key GPIOs is phase 3's job
   because at phase 1 the key GPIOs do not exist yet: GPIO assignment *is* a schematic
   decision. The original item asked phase 1 to "check them against the macro pad's key
   GPIOs before locking the map" — a check against pins nobody has chosen, logged as
   mis-scoped in this run's gap log (`hexpad/GAPS.md`). ✅ (enumerate + hand off);
   the collision check itself belongs to phase 3.
