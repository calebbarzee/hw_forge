---
domain: keyboards/libraries
tags: [kicad-libraries, footprints, symbols, corne, foostan, scottokeebs, keyswitches-pretty, vendoring, provenance]
source: local filesystem survey, 2026-08-22; z_board v0.4 (CLEANUP.md, kicad/NOTES.md)
date: 2026-08-22
confidence: verified-in-cad
---

# Proven local keyboard part libraries

Three vendor libraries on this machine cover almost every keyboard part KiCad does not
ship. **Check these before authoring geometry.**

## 1. foostan `kbd` (the corne libraries)

`/Users/calebbarzee/1_projects/dev/keyboard/kbd/`
- `kicad-footprints/kbd.pretty/` · `kicad-symbols/kbd.kicad_sym` · `kicad-packages3D/kbd.3dshapes`

The upstream corne library. Proves out, among others:
- **`YS-SK6812MINI-E.kicad_mod`** — reverse-mount `-E` LED; pads at ±2.80/±0.70, 1.7 × 0.825.
  Its light window is the wide (3.6 mm) ceoloide-lineage one; narrow it (see
  `sk6812mini-e.md`).
- `LED_WS2812B-PLCC4`
- `keyswitch_cherrymx_hotswap_1u` / `_1.5u` / `_rotary_encoder_ec12`, `keyswitch_cherrymx_alps_choc12_*`, `keyswitch_choc12_hotswap_*`, `keyswitch_gateron_low_profile_hotswap_1u`, `keyswitch_hole`
- `ProMicro`, `OLED`, `Pico-EZmate_PCB_Header`, `TYPE-C-31-M-13C`, `MJ-4PP-9`,
  `PJ-398A-5A_PJ-399B-6A` (TRRS), `ResetSW`, `TS-1088R-02026`, `Breakaway_Tabs`,
  corne logo/silk/mask artwork.

## 2. ScottoKeebs `ScottoKicad`

`/Users/calebbarzee/1_projects/dev/keyboard/scottokeebs/Extras/ScottoKicad/`
- `footprints/` — 13 `.pretty` libs: `ScottoKeebs_MCU`, `_Components`, `_MX`, `_Choc`,
  `_Hotswap`, `_Alps`, `_Hybrid`, `_KH`, `_NB`, `_Stabilizer`, `_Cutout`, `_CAD`,
  `_Miscellaneous`
- `symbols/ScottoKeebs.kicad_sym` · `3dmodels/*.3dshapes`

Highest-value contents:
- **`ScottoKeebs_MCU.pretty`** — `Nice_Nano_V2` and `Nice_Nano_V2_Flipped`, plus
  `Arduino_Pro_Micro(_Flipped)`, `RP2040_Pro_Micro`, `RP2040_Zero`, `RP2040_Stamp`,
  `Raspberry_Pi_Pico(_Flipped)`, `Adafruit_KB2040`, `Seeed_XIAO_RP2040`, `Adafruit_QTPY_2040`.
  The nice!nano footprint here is the **cross-check reference** for a generated one.
- **`ScottoKeebs_Components.pretty`** — **`Switch_MSK12C02`** (SPDT slide power switch),
  `Switch_K3-1204D`, `Switch_SSAL220100`, `LED_SK6812MINI`, `LED_WS2812B`,
  `Connector_1x02_JST-PH`, `Diode_SOD-123`, `ESD_SOT-23-6`, `Fuse_0603`,
  `Voltage_SOT-23`, `OLED_128x32` / `128x64`, `USB_C_HRO_TYPE-C-31-M-12/-14`,
  `Battery_Holder_2032`, `TRRS_PJ-320A`, 0402/0603/0805/1206 passives.
- `ScottoKeebs_Miscellaneous.pretty` — `Mouse_Bites_5/7/9`, `Hub_2_Port`, `Hub_4_Port`.

## 3. `keyswitches.pretty` (Kailh hotswap sockets)

`/Users/calebbarzee/1_projects/dev/keyboard/keyswitches.pretty/`

The hotswap library — **KiCad ships no hotswap socket footprint at all**.
- `Kailh_socket_MX`, `_optional`, `_platemount`, `_optional_platemount`
- `Kailh_socket_MX_reversible`, `_reversible_platemount`, `_optional_reversible`
- `Kailh_socket_PG1350` (Choc) + `_optional` / `_reversible` variants
- `SW_MX`, `SW_MX_reversible`, `SW_MX_reversible_minimal`, `SW_PG1350*`,
  `Stabilizer_MX_2u`

**Caveat on the reversible variants**: `Kailh_socket_MX_reversible` mirrors in **y**, which
turns the MX switch 180° between faces and takes its light aperture with it. For an
x-mirror reversible cell, generate your own — see `mx-switch-geometry.md`.

## Doctrine: vendor into the project library, then upgrade

1. **Search all three libraries before authoring anything.** Hand-authored geometry is the
   most expensive and least trustworthy artifact in the pipeline; the phase-1 exit gate is
   *every part resolves, zero hand-authored geometry*.
2. **Copy the part into a project-local library** (`lib/<project>.kicad_sym`,
   `lib/<project>_kbd.pretty/`) rather than referencing the vendor path. Project
   `sym-lib-table` / `fp-lib-table` point at `${KIPRJMOD}/../lib/`, so a project resolves
   without touching the user's global KiCad config and without a vendor checkout.
3. **Upgrade the vendored files** (`kicad-cli fp upgrade`, `sym upgrade`). Vendor libs are
   often KiCad 5–8 format; upgrade is one-way, so copy first, and diff a render afterwards
   because custom-primitive pads are the usual casualty.
4. **Record provenance** — which library, which upstream commit — in the project library's
   descr field or a manifest. A bare gitlink with no `.gitmodules` means a fresh clone gets
   an empty directory and the parts are effectively lost to everyone but the original
   machine (an actual z_board finding). Vendor the files; don't submodule the world.
5. Prefer **stock KiCad** where it ships the part: `Device:D` + `Diode_SMD:D_SOD-123`,
   `Switch:SW_Push` + `Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2`, `Switch:SW_SPDT` +
   `Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02`, `Connector_Molex:...Pico-EZmate...`,
   `Capacitor_SMD:C_0603_1608Metric`, `MountingHole:MountingHole_2.2mm_M2`. Only three
   z_board parts had to be project-local: the Kailh socket, the SK6812MINI-E, and the
   generated nice!nano.
6. **Where a footprint's symbol partner is ambiguous or the vendor ships variants with
   different pin order, generate both from one pin table** — do not pair a stock symbol
   with a vendor footprint. See `references/kicad-api.md` §8.
