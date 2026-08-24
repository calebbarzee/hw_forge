---
domain: keyboards/zmk
tags: [zmk, ext-power, underglow, spi3, pinctrl, devicetree, overlay, brightness-cap, split-ble, nrf52840, diode-direction, col2row, kscan]
source: z_board v0.4 (kicad/POWER.md, kicad/NOTES.md, README.md) + ZMK hardware design guide; hexpad phase-7 harvest
date: 2026-08-22
confidence: researched
---

# ZMK electrical constraints that shape the PCB

Firmware facts that are hardware decisions in disguise. They must be settled during
the schematic phase, because they change the netlist.

## EXT_POWER: why switchable loads go on VCC, not RAW

On nice!nano v2, `ext-power` is `gpio0 13 GPIO_ACTIVE_HIGH`, and P0.13 is the enable pin
of the module's own 3.3 V low-dropout regulator (LDO), whose output is the VCC pad. So:

- A load on VCC is gated by ZMK's `ext_power` behavior for free: no external P-FET
  load switch, no extra GPIO, and the LDO's 800 mA limit becomes a hard ceiling.
- A load on RAW can never be switched off without adding a P-FET.
- 22 SK6812s idle at ~20 mA even with all pixels black → a 500 mAh cell flat in ~24 h. Any
  load in that class must be on the gated rail.
- A bare nRF chip (no module) would need the external switch; the module's own regulator is
  what makes this free. See `nice-nano-v2.md`.

Set `CONFIG_ZMK_RGB_UNDERGLOW_EXT_POWER=y` so toggling underglow also drops P0.13.

## The LED strip is a serial peripheral interface (SPI) device, so it belongs to a board, not a shield

An addressable strip is driven from the SPI master-out/slave-in (MOSI) line. SPI instances
are board resources, so the overlay goes in `boards/nice_nano_v2.overlay` inside the shield
directory, not in the shield's own `.overlay`.

- Give the chain its own `&spi3` with a pinctrl mapping MOSI to the data pin
  (z_board: P1.00, silkscreen D6).
- Avoid `spi1`'s defaults: its serial clock (SCK) is P1.13 (labeled D15), its
  master-in/slave-out (MISO) line is P1.11 (D14), and its MOSI is P0.10 (D16). P1.13 and
  P1.11 are matrix columns C4 and C5 on z_board's map. A default peripheral pinmux
  silently fighting the matrix is the failure mode.
- Likewise check `uart0`'s defaults against the matrix rows (they collided with R0/R1 on
  z_board's map).
- Rule: before locking a pin map, list every default peripheral pinmux on the target
  board and check it against the matrix and the chain. Free GPIOs are not the constraint;
  peripheral defaults are. For nice!nano v2 the enumeration is already done, so do not
  re-derive it from the firmware tree. See `nice-nano-v2.md`, "Default peripheral pinmux:
  the enumeration, done once", which tables `uart0`, `i2c0`, `spi1`, the blue LED and
  ext-power in port terms with the D labels derived, and records that `spi0`/`spi2`/`spi3`
  are unclaimed and that P0.29 (D20) has no default role.

## Brightness cap as a hardware requirement

22 LEDs at full white is 0.4–1.3 A (binning spread) against an 800 mA LDO. So:

```
CONFIG_ZMK_RGB_UNDERGLOW_BRT_MAX = ~25      # holds the rail near 300 mA worst-case
CONFIG_ZMK_RGB_UNDERGLOW_EXT_POWER = y
```
This is not a preference: without it the rail exceeds the regulator, and near
end-of-discharge the ME6217's dropout (Vin ≥ ~3.45 V at 300 mA) makes the LED rail sag
first. Measure one populated half before raising it. Record the key and value in the
power doc, not just in the firmware repo.

## Split Bluetooth Low Energy (BLE) architecture

- Two independent halves, each its own board and its own firmware image; one is the
  central and one the peripheral (`CONFIG_ZMK_SPLIT_BLE_ROLE_CENTRAL=y` on the
  central). A dongle setup makes both halves peripherals and the dongle central.
- Removing a wired tip-ring-ring-sleeve (TRRS) split removes the back-power hazard with
  it: a wired split can put battery voltage on the other half's rail through the
  interconnect. If the design is BLE-only, delete the connector rather than leaving it
  unpopulated.
- **The mirrored half's column order is reversed in the ZMK matrix transform, not in
  copper.** Both halves keep the same physical pin map. Do not mirror the pin assignment to
  "fix" the layout.
- Keep a `settings_reset` build target in the continuous integration (CI) matrix; clearing
  stale BLE pairings is otherwise unrecoverable without one.
- A build whose pin map differs (for example, a reversible board that had to move the row
  nets to different pads to clear a fastener) needs its own devicetree. Same nets and same
  count is not the same devicetree. Note it prominently in the assembly doc.
- Matrix wiring on nRF: per-key diodes plus ZMK's internal pulls mean no series resistors
  on rows/columns. GPIOs are drive-limited and the diodes block reverse paths.
- `diode-direction` must be stated explicitly, and the ZMK default is the unusual one.
  `zmk,kscan-gpio-matrix` defaults to `row2col`; the common keyboard wiring (column →
  switch → diode anode, cathode → row) is `col2row`. Omit the property on col2row
  hardware and the matrix scans nothing: no error, just a dead keyboard. The diode
  direction is fixed in copper during the schematic phase, so record the required
  devicetree value in the assembly doc at that point, not at firmware time (z_board
  combo audit, 2026-08-22: hardware unambiguously col2row, value stated nowhere).

## Needs verification

- Exact `CONFIG_ZMK_RGB_UNDERGLOW_BRT_MAX` scale semantics (percent vs 0–255) against the
  current ZMK release. The ~25 figure above was reasoned as "≈25 % duty", so confirm
  before trusting it as a literal.
- ZMK's own docs contain no electrical guidance on per-LED decoupling
  (`grep 100nF zmk/docs` → nothing); do not cite the guide for that decision.
