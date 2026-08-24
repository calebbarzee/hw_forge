---
domain: keyboards/libraries
tags: [kicad-libraries, footprints, symbols, corne, foostan, scottokeebs, keyswitches-pretty, ergogen, ceoloide, nice-view, zmk-source, gitlink, vendoring, provenance]
source: local filesystem survey, 2026-08-22; z_board v0.4 (CLEANUP.md, kicad/NOTES.md); hexpad resource-scout run, 2026-08-22
date: 2026-08-22
confidence: verified-in-cad
---

# Proven local keyboard part libraries

Three vendor libraries on this machine cover almost every keyboard part KiCad does not
ship. Check these before authoring geometry.

## 1. foostan `kbd` (the corne libraries)

`/Users/calebbarzee/1_projects/dev/keyboard/kbd/`
- `kicad-footprints/kbd.pretty/` · `kicad-symbols/kbd.kicad_sym` · `kicad-packages3D/kbd.3dshapes`

The upstream corne library. Proves out, among others:
- `YS-SK6812MINI-E.kicad_mod`, the reverse-mount `-E` LED; pads at ±2.80/±0.70, 1.7 × 0.825.
  Its light window is the wide (3.6 mm) ceoloide-lineage one; narrow it (see
  `sk6812mini-e.md`).
- `LED_WS2812B-PLCC4`
- `keyswitch_cherrymx_hotswap_1u` / `_1.5u` / `_rotary_encoder_ec12`, `keyswitch_cherrymx_alps_choc12_*`, `keyswitch_choc12_hotswap_*`, `keyswitch_gateron_low_profile_hotswap_1u`, `keyswitch_hole`
- `ProMicro`, `OLED`, `Pico-EZmate_PCB_Header`, `TYPE-C-31-M-13C`, `MJ-4PP-9`,
  `PJ-398A-5A_PJ-399B-6A` (a tip-ring-ring-sleeve, or TRRS, jack), `ResetSW`,
  `TS-1088R-02026`, `Breakaway_Tabs`, corne logo/silk/mask artwork.

## 2. ScottoKeebs `ScottoKicad`

`/Users/calebbarzee/1_projects/dev/keyboard/scottokeebs/Extras/ScottoKicad/`
- `footprints/`, 13 `.pretty` libs: `ScottoKeebs_MCU`, `_Components`, `_MX`, `_Choc`,
  `_Hotswap`, `_Alps`, `_Hybrid`, `_KH`, `_NB`, `_Stabilizer`, `_Cutout`, `_CAD`,
  `_Miscellaneous`
- `symbols/ScottoKeebs.kicad_sym` · `3dmodels/*.3dshapes`

Highest-value contents:
- `ScottoKeebs_MCU.pretty`: `Nice_Nano_V2` and `Nice_Nano_V2_Flipped`, plus
  `Arduino_Pro_Micro(_Flipped)`, `RP2040_Pro_Micro`, `RP2040_Zero`, `RP2040_Stamp`,
  `Raspberry_Pi_Pico(_Flipped)`, `Adafruit_KB2040`, `Seeed_XIAO_RP2040`, `Adafruit_QTPY_2040`.
  The nice!nano footprint here is the cross-check reference for a generated one.
- `ScottoKeebs_Components.pretty`: `Switch_MSK12C02` (a single-pole double-throw, or
  SPDT, slide power switch), `Switch_K3-1204D`, `Switch_SSAL220100`, `LED_SK6812MINI`,
  `LED_WS2812B`, `Connector_1x02_JST-PH`, `Diode_SOD-123`, `ESD_SOT-23-6`, `Fuse_0603`,
  `Voltage_SOT-23`, `OLED_128x32` / `128x64`, `USB_C_HRO_TYPE-C-31-M-12/-14`,
  `Battery_Holder_2032`, `TRRS_PJ-320A`, 0402/0603/0805/1206 passives.
- `ScottoKeebs_Miscellaneous.pretty`: `Mouse_Bites_5/7/9`, `Hub_2_Port`, `Hub_4_Port`.

## 3. `keyswitches.pretty` (Kailh hotswap sockets)

`/Users/calebbarzee/1_projects/dev/keyboard/keyswitches.pretty/`

The hotswap library. KiCad ships no hotswap socket footprint at all.
- `Kailh_socket_MX`, `_optional`, `_platemount`, `_optional_platemount`
- `Kailh_socket_MX_reversible`, `_reversible_platemount`, `_optional_reversible`
- `Kailh_socket_PG1350` (Choc) + `_optional` / `_reversible` variants
- `SW_MX`, `SW_MX_reversible`, `SW_MX_reversible_minimal`, `SW_PG1350*`,
  `Stabilizer_MX_2u`

Caveat on the reversible variants: `Kailh_socket_MX_reversible` mirrors in y, which
turns the MX switch 180° between faces and takes its light aperture with it. For an
x-mirror reversible cell, generate your own; see `mx-switch-geometry.md`.

## 4. Ergogen footprint repos: a fourth location this card previously missed

This section corrects a gap. The three libraries above are all KiCad-native vendor
libraries, and they are not the only place keyboard footprints live on this machine.

`z_board/ergogen/footprints/` is a checkout of `github.com/ceoloide/ergogen-footprints`
(pinned commit `48935f54`). It contains, among others, `display_nice_view.js`: a
parameterized, actively-maintained nice!view footprint generator (reversible,
3D-model-aware, with trace generation) that a prior pass of this card asserted did not
exist locally anywhere. It was found only because a hexpad resource-scout run grepped the
whole `keyboard/` tree for `*nice*view*` instead of trusting this card's prior negative.

Lesson: when a card records "not found locally," it must name what was searched
(paths, patterns) so a future search can tell whether the negative still holds. A bare
"no footprint was observed" invites re-trusting a search that was narrower than it looked.

Ergogen `.pretty`-equivalent repos (`ergogen/footprints/`, or a project's own
`ergogen/output/footprints/`) are a fourth location to check, alongside the three
KiCad-native libraries above, whenever surveying for a display/connector/exotic part.

Trap: a bare gitlink with no `.gitmodules`. `z_board/ergogen/footprints` is a git submodule
entry (`git ls-files -s` shows mode `160000`) with no `.gitmodules` file in the parent
repo, and `z_board/CLEANUP.md` already flagged this as unresolved ("UNSURE... kept in
place").

This is the "asset already lost to everyone but this machine" trap: on a fresh
clone of `z_board`, `ergogen/footprints/` is an empty directory. It only works on
the original machine because it was cloned by hand and never committed as a proper
submodule. Vendor the specific files you need out of it (copy, do not re-link) the
moment you use anything from there; a hexpad run copied `display_nice_view.js` into
`hexpad/lib/reference/` for this reason. Do not assume this gitlink will resolve
for anyone else, including a future session on a fresh checkout of z_board itself.

License note: `display_nice_view.js` is CC-BY-NC-SA-4.0 (Marco Massarelli, with
ceoloide/nidhishs improvements), so non-commercial and share-alike. A project vendoring it
verbatim as a reference/evidence file is fine; adopting its generated geometry as
production output on a board sold commercially is not, without checking the license again.

## 5. A local ZMK firmware checkout also lives on this machine

`/Users/calebbarzee/1_projects/dev/keyboard/zmk/` is a full checkout of ZMK (git remote
`https://github.com/calebbarzee/zmk`, a fork) with a real commit checked out, not a
bare gitlink. It contains the same `app/boards/shields/nice_view*` trees documented in
`nice-view-display.md`, and per this project's own "local machine first, always" doctrine,
this should be searched before any GitHub fetch for ZMK shield/devicetree/Kconfig
facts.

A hexpad run fetched from `github.com/zmkfirmware/zmk` first and only found this
local checkout afterward. The checkout was slightly behind upstream (missing two lines
added to `nice_view.overlay` since its pinned commit), which is itself a useful data point:
pin the exact commit checked, and re-diff against upstream when trusting an old local
clone for anything that changes over time, such as display timing parameters.

## Doctrine: vendor into the project library, then upgrade

1. Search all four locations before authoring anything: the three KiCad-native
   libraries above, and any local ergogen footprint checkout (§4) and firmware source
   checkout (§5), which cover display/connector/exotic parts and devicetree facts the
   KiCad libraries never will. Hand-authored geometry is the most expensive and least
   trustworthy artifact in the pipeline; the phase-1 exit gate is "every part resolves,
   zero hand-authored geometry".
2. Copy the part into a project-local library (`lib/<project>.kicad_sym`,
   `lib/<project>_kbd.pretty/`) rather than referencing the vendor path. Project
   `sym-lib-table` / `fp-lib-table` point at `${KIPRJMOD}/../lib/`, so a project resolves
   without touching the user's global KiCad config and without a vendor checkout.
3. Upgrade the vendored files (`kicad-cli fp upgrade`, `sym upgrade`). Vendor libs are
   often KiCad 5–8 format; upgrade is one-way, so copy first, and diff a render afterwards
   because custom-primitive pads are the usual casualty.
4. Record provenance, meaning which library and which upstream commit, in the project
   library's descr field or a manifest. A bare gitlink with no `.gitmodules` means a fresh
   clone gets an empty directory and the parts are effectively lost to everyone but the
   original machine (an actual z_board finding). Vendor the files rather than linking to
   another repo.
5. Prefer stock KiCad where it ships the part: `Device:D` + `Diode_SMD:D_SOD-123`,
   `Switch:SW_Push` + `Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2`, `Switch:SW_SPDT` +
   `Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02`, `Connector_Molex:...Pico-EZmate...`,
   `Capacitor_SMD:C_0603_1608Metric`, `MountingHole:MountingHole_2.2mm_M2`. Only three
   z_board parts had to be project-local: the Kailh socket, the SK6812MINI-E, and the
   generated nice!nano.
6. Where a footprint's symbol partner is ambiguous, or the vendor ships variants with
   different pin order, generate both from one pin table. Do not pair a stock symbol
   with a vendor footprint. See `references/kicad-api.md` §8.
