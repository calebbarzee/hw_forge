---
domain: keyboards/display
tags: [nice-view, sharp-memory-lcd, spi, display, nice-nano, zmk-display, macro-pad, dry-run]
source: general knowledge, no vendor doc consulted; staged for the hw_forge dry-run project
date: 2026-08-22
confidence: needs-verification
---

# nice!view display — staging card

Written from general knowledge for the **dry-run project (6-key macro pad, nice!view on a
nice!nano)**. **No web/vendor source was consulted.** Everything below is a starting
hypothesis; the research pass in §3 must run before any of it is used to place a footprint
or write a devicetree.

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

## 2. Explicitly NOT known

- Pin count, pin order, and pin names — including **which pin is CS** and whether the
  header is 4 or 5 positions.
- Physical dimensions (PCB outline, display active area, total height above the nice!nano),
  and the socket/header pitch and position relative to the module's own pads.
- Resolution. A figure around 160 × 68 is in my memory but is **not** to be relied on.
- Whether the ZMK shield names are `nice_view` + `nice_view_adapter`, the exact build
  incantation, and which `CONFIG_*` keys beyond `CONFIG_ZMK_DISPLAY` are required.
- Which SPI instance ZMK's shield binds by default, and its pin assignments.
- Operating voltage / current, and whether a 3.3 V rail is the only option.
- Whether a KiCad footprint exists in any local library (see `local-libraries.md` — the
  foostan `kbd.pretty` has an `OLED` footprint and ScottoKeebs has `OLED_128x32`/`128x64`;
  **no nice!view footprint was observed in either**).

## 3. What a research pass must confirm — checklist

1. **Pinout**: full pin list in physical order, with CS identified, from the vendor pinout
   page **and** a second independent source (a shipping board's schematic or a community
   library footprint). Two-source verification, per the resource-acquisition doctrine.
2. **Mechanical**: PCB outline dimensions, header position/pitch, and total stack height
   above the nice!nano's top face. Needed for the case z-budget and the deck window.
3. **ZMK config**: exact shield names, the adapter's role, the full build command, required
   `CONFIG_*` keys, and the SPI instance + pinctrl the shield expects. Read them out of the
   ZMK tree, not from a blog post.
4. **Electrical**: supply voltage, active and static current, and whether any series or
   pull resistors are expected on the SPI lines.
5. **Footprint/symbol**: find an existing footprint or generate symbol + footprint from the
   confirmed pin table (one table, two emitters). Do **not** reuse an OLED footprint.
6. **Pin-map interaction**: list the default pinmux of every SPI and UART instance on
   nice!nano v2 and check them against the macro pad's key GPIOs before locking the map.

Raise `confidence` to `researched` once §3.1–§3.4 are done from primary sources, and to
`verified-in-cad` once a board with the footprint passes ERC/DRC/parity.
