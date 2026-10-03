---
domain: interfaces/i2c
tags: [qwiic, stemma-qt, i2c, jst-sh, 4-pin, sda, scl, 3v3, daisy-chain]
source: [SparkFun Qwiic page sparkfun.com/qwiic (read), Adafruit Learn "What is STEMMA QT" (read), JST eSH.pdf (read)]
date: 2026-10-03
confidence: researched
---

# Qwiic and STEMMA QT: JST SH 4-pin I2C

A vendor convention, not a standard. The connector is the 4-position JST SH
(`jst-sh.md`). SparkFun names the board connector `SM04B-SRSS-TB(LF)(SN)` and the cable
connector `SHR-04V-S`.

| Pin | Signal | Wire colour |
|---|---|---|
| 1 | GND | black |
| 2 | 3.3 V | red |
| 3 | SDA | blue |
| 4 | SCL | yellow |

- Qwiic is 3.3 V only (SparkFun). STEMMA QT devices keep their regulator and level
  shifting on the device, so one runs on a 3 to 5 V controller (Adafruit). The two
  ecosystems are cross compatible.
- One set of pullups per bus. Several boards that each carry pullups put them in
  parallel. The SparkFun page gives no pullup value.
- About 1 m of standard cable is the stated reliable length.

## Footprint and mating direction

Stock footprint for the SparkFun style board connector:
`Connector_JST.pretty/JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal.kicad_mod`,
packages.json key `JST-SH-4`, 6 pads (4 signal, 2 `MP`), outer span 6.8 x 5.55 mm.
`mating_direction` `+y` (needs-verification, see `jst-sh.md`). The top-entry
`..BM04B..Vertical` also mates the same cable, `mating_direction` `+z`.

## Mated plug envelope

SHR-04V-S housing: 5.0 mm wide, 2.8 mm deep, 5 mm tall (JST eSH.pdf). Side-entry mated
length 6.25 mm.

## Traps

- A board that exposes this connector on a non-3.3 V rail is not Qwiic, and a 5 V
  Qwiic peripheral on a 3.3 V host works only if it is STEMMA QT.
- Cables and boards must agree on pin 3 SDA and pin 4 SCL. A swapped bus hangs.

## What a research pass must confirm

1. Pullup values and bus limits in the SparkFun Qwiic hardware specification.
