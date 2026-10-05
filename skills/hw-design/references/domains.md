# Domains: failure modes the generic gates cannot see

Generic rules. Part numbers, firmware symbols, and project geometry live in
`kb/`. Per-interface pinouts, protection parts, and mating geometry live in
`interfaces.md`.

ERC, DRC with schematic parity, the unconnected count, `kicad_fpcheck.py`, and
`kicad_silkcheck.py` prove a board is consistent with its schematic and that its
footprints and silkscreen are sane. None of them reads a voltage, a current, an
impedance, a temperature, or a datasheet. A board that passes all of them can
still sit outside a part's bias window, overheat a regulator, ring a switch
node, or fail an ESD test.

This file lists, per electrical domain, the properties those gates cannot see
and the check or review step that establishes each. It exists so that the
pipeline works for any kind of design, not only the one that produced the
examples.

## Terms used here

| Term | Meaning |
|---|---|
| ADC | Analog-to-digital converter. |
| AES | Audio Engineering Society. Publishes AES48 on cable shielding and grounding. |
| AGND, DGND, PGND | Analog, digital, and power ground. Separate names for return nets that may or may not be one plane. |
| CFR | Code of Federal Regulations. 47 CFR Part 15 holds the United States radio-frequency emission limits. |
| CISPR | International special committee on radio interference. Its publications set emission limits and methods. |
| CL | Crystal load capacitance, the capacitance the crystal sees across its two pins. |
| CMRR | Common-mode rejection ratio. |
| CPWG | Coplanar waveguide with ground. A trace with ground copper on both sides and a ground plane below. |
| DRC | Design rule check. |
| EIRP | Equivalent isotropically radiated power. |
| EMC | Electromagnetic compatibility. |
| EMIRR | Electromagnetic interference rejection ratio. An op-amp's immunity to radio-frequency interference. |
| ERC | Electrical rule check. |
| ESD | Electrostatic discharge. |
| ESR | Equivalent series resistance of a capacitor or crystal. |
| ETSI | European Telecommunications Standards Institute. |
| FCC | Federal Communications Commission, the United States radio regulator. |
| FET | Field-effect transistor. |
| FR-4 | The common glass-epoxy board laminate. |
| GBW | Gain-bandwidth product of an op-amp. |
| I2C | Inter-integrated circuit bus. A two-wire serial bus with open-drain lines and pull-up resistors. |
| IEC | International Electrotechnical Commission. |
| IEEE | Institute of Electrical and Electronics Engineers. |
| IPC | The association that publishes board design and assembly standards (IPC-2221, IPC-2152, IPC-2141). |
| ISO | International Organization for Standardization. |
| JEDEC | The standards body for solid-state devices. Publishes thermal test methods and, with IPC, moisture classification. |
| JEITA | Japan Electronics and Information Technology Industries Association. Its guideline sets temperature windows for lithium charging. |
| LDO | Low-dropout regulator. |
| LPDDR | Low-power double data rate memory. |
| LSB | Least significant bit. One code step of a converter. |
| MEMS | Micro-electro-mechanical system. A silicon sensor such as a microphone or accelerometer. |
| MSL | Moisture sensitivity level. How long a package may sit in air before reflow. |
| NTC | Negative temperature coefficient thermistor. |
| P48 | 48 V phantom power for microphones, defined in IEC 61938. |
| PCB | Printed circuit board. |
| PCM | Protection circuit module. The small board bonded to a lithium cell. |
| PHY | Physical-layer transceiver chip. |
| PSRR | Power supply rejection ratio. |
| RF | Radio frequency. |
| RMS | Root mean square. |
| SAR | Successive-approximation register, an ADC architecture. |
| SNR | Signal-to-noise ratio. |
| SoC | System on chip. |
| SPI | Serial peripheral interface bus. |
| SRF | Self-resonant frequency of a capacitor or inductor. |
| TVS | Transient voltage suppressor. A clamping diode for ESD and surges. |
| UI | Unit interval. The duration of one bit on a serial link. |
| USB | Universal Serial Bus. |
| UVLO | Undervoltage lockout. |
| VBUS | The USB power pin. |
| VNA | Vector network analyzer. |
| VSWR | Voltage standing wave ratio. A measure of mismatch at a port. |

## 0. How to use this file

**Declare the domains at spec lock.** Every design touches at least two of the
nine sections below. List them in the spec, with the reason, so that phase 3
knows which assertions to write and phase 4 knows which board checks to add.
Digital logic alone still touches sections 3 and 9.

**Assertions go in `design.py`, on import.** The model is
`hypercardiod_mic/kicad/design.py`. Its `_selfcheck()` runs when the file is
imported, so the schematic emitter, the board emitter, and any script all fail
before they emit anything. It is stdlib-only Python. It asserts the bias window
at both rail extremes (`_bias_arithmetic()`), every alternating-current corner
and the inter-unit phase spread (`signal_phase_spread_deg()`), the current
budget, a radio-frequency pole, and table hygiene. Each assertion uses named
constants and each constant's comment cites its source.

Build the same way for any domain:

1. Name every input as a constant with units in the name and a source in the
   comment.
2. Compute derived values in a function that returns a dict, so the power
   document and the assertions read the same numbers.
3. Evaluate every limit at both corners: the minimum supply with the worst
   tolerance against you, and the maximum supply with the worst tolerance the
   other way.
4. Put the numbers in the assertion message, so a failure states what to change.
5. Assign the result at module level (`_RESULT = _selfcheck()`), so import
   fails.

**Check classes.** Every rule states one.

| Class | Meaning | Runs today |
|---|---|---|
| automatic-in-design.py | An import-time assertion in the project's `design.py`. | Only if the project writes it. The pipeline ships no domain assertions. |
| automatic-in-board | Computable from the `.kicad_pcb`: a script reading it with the parser in `scripts/kicad_geom.py` (`parse_file`, `kids`), or a custom DRC rule in the generated `.kicad_dru` (`kicad-api.md` §4, "Custom rules"). | Shipped for a few properties: the baseline `.kicad_dru` (fab drill and annular floors, connector copper to edge), `kicad_fpcheck.py` (pad geometry), `kicad_silkcheck.py` (silk), and `kicad_geom.py --contract` (connector mating faces). No shipped check for the domain rules below that name this class; a project script or rule must be written. |
| manual-review | A reviewer reads a datasheet, runs a simulation, or measures a prototype. | Always manual. Record the outcome in the decision record. |

What the pipeline does run today: ERC, DRC at error severity with schematic
parity, the unconnected count, `kicad_fpcheck.py`, `kicad_silkcheck.py`,
`kicad_schrules.py`, `kicad_ifcheck.py`, the fit contract
(`kicad_geom.py --contract`), the case `verify()` for enclosures, and
whatever `design.py` asserts. The final
table (section 10) states which checks of this file fall in which class.

**Marker.** `(needs-verification)` means the number or document identifier was
not confirmed against the source text while writing this file. Confirm it
before relying on it, and remove the marker in the same commit.

## 1. Analog and audio

### 1.1 Bias windows at both rail extremes

- **Rule.** For every biased node (microphone bias, op-amp input bias, midrail
  reference), compute the node voltage at minimum and maximum supply, with
  resistor tolerance and device current spread both set against the window. Assert
  that the result lies inside the part's stated window at both extremes.
- **Gap.** ERC reads connectivity. No gate reads a resistor value. A divider
  centred for 12 V can sit outside the window at 9 V and at 15 V with no finding.
- **Check.** Evaluate the Thevenin equivalent of the divider and subtract the
  load drop. The minimum case takes minimum supply, maximum series drop,
  maximum load current, and resistors against you. The maximum case takes the
  reverse.
- **Class.** automatic-in-design.py.
- **Source.** `hypercardiod_mic/kicad/design.py`, `_bias_arithmetic()` and
  `_selfcheck()`: a capsule node held inside 1 to 10 V over a 9 to 15 V supply
  with 5 % resistors. The window comes from the part datasheet.

```python
VIN_MIN, VIN_MAX = 9.0, 15.0     # V, spec
R_TOL = 0.05                     # 5 % resistors assumed at every corner

def _node(vin, r_top, r_bot, i_load_a):
    v_th = vin * r_bot / (r_top + r_bot)          # Thevenin source
    r_th = r_top * r_bot / (r_top + r_bot)
    return v_th - i_load_a * r_th

node_min = _node(VIN_MIN - VF_MAX, R1 * (1 + R_TOL), R2 * (1 - R_TOL), I_LOAD_MAX_A)
node_max = _node(VIN_MAX - VF_MIN, R1 * (1 - R_TOL), R2 * (1 + R_TOL), I_LOAD_MIN_A)
assert NODE_WINDOW_MIN_V < node_min, "node %.2f V at VIN_MIN" % node_min
assert node_max < NODE_WINDOW_MAX_V, "node %.2f V at VIN_MAX" % node_max
```

### 1.2 Noise budget

- **Rule.** Sum the input-referred noise of every source over the stated
  bandwidth and assert the total against a budget derived from the required SNR.
  Sources: resistor thermal noise `sqrt(4·k·T·R·Δf)`, op-amp voltage noise `en`,
  op-amp current noise `in` times the source resistance, and later stages divided
  by the gain ahead of them. Use the parallel combination of the source
  resistance and any bias resistor that shunts the input.
- **Gap.** No gate knows the signal level, the bandwidth, or the target SNR.
- **Check.** At 300 K, a resistor produces `4.07 nV/√Hz` per `√kΩ`. Over a
  20 kHz audio bandwidth: 1 kΩ gives 0.58 µV rms, 10 kΩ gives 1.82 µV rms, and
  470 kΩ gives 12.5 µV rms. A large bias resistor matters only through its
  parallel combination with the source, so assert the combination, not each
  resistor alone. Add 1/f noise separately from the part's datasheet corner
  frequency.
- **Class.** automatic-in-design.py.
- **Source.** Johnson-Nyquist noise formula (any textbook, for example Horowitz
  and Hill, "The Art of Electronics"). Op-amp `en` and `in` from the datasheet
  table. Analog Devices MT-047 "Op Amp Noise" (needs-verification).

```python
K_B, T_K = 1.380649e-23, 300.0
def _en_r(r_ohm): return (4 * K_B * T_K * r_ohm) ** 0.5            # V/rtHz
def _par(a, b):   return a * b / (a + b)

r_src = _par(R_SOURCE, R_BIAS)
en_tot = (_en_r(r_src) ** 2 + EN_OPAMP ** 2 + (IN_OPAMP * r_src) ** 2) ** 0.5
vn_rms = en_tot * BW_HZ ** 0.5            # white-noise approximation
snr_db = 20 * math.log10(V_SIGNAL_MIN_RMS / vn_rms)
assert snr_db >= SNR_TARGET_DB + MARGIN_DB, "SNR %.1f dB" % snr_db
```

### 1.3 PSRR and supply filtering

- **Rule.** Compute the supply ripple that reaches the output at every
  frequency the rail carries: the upstream switching frequency and its
  harmonics, and mains-related 100 or 120 Hz. Rejection is the op-amp's PSRR at
  that frequency, read from the datasheet curve, plus the attenuation of any RC
  filter. Assert the result below the noise budget of 1.2.
- **Gap.** PSRR falls with frequency. A part quoted at 80 dB at DC may give 20 dB
  at a 500 kHz switcher's frequency. No gate sees the curve.
- **Check.** RC corner `fc = 1/(2π·R·C)`. Attenuation at `f` is
  `1/sqrt(1 + (f/fc)²)`. The design file `design.py` computes
  `CORNER_SUPPLY_HZ` for a 10 Ω and 100 µF filter as 159 Hz, giving 56 dB at
  100 kHz. The real value is lower because capacitor ESR bounds the attenuation
  at `ESR/(R + ESR)`. Enter the datasheet PSRR points as a table and assert the
  minimum over the ripple frequencies.
- **Class.** automatic-in-design.py for the arithmetic. The transcription of the
  datasheet curve is manual-review.
- **Source.** Op-amp datasheet PSRR curve. Analog Devices AN-202 (Brokaw), "An
  IC Amplifier User's Guide to Decoupling, Grounding, and Making Things Go Right
  for a Change", for decoupling method.

### 1.4 Coupling-capacitor corners and phase matching

- **Rule.** Every AC coupling stage has a high-pass corner `fc = 1/(2π·R·C)`
  computed with the loaded resistance and worst-case capacitance. Assert each
  corner below the band edge. Where several channels or units must stay in phase,
  assert the phase spread at the band edge.
- **Gap.** The nominal value passes review. Electrolytic capacitors carry ±20 %,
  and an X7R part loses capacitance under DC bias. A Y5V or Z5U part can lose
  most of it. No gate evaluates tolerance.
- **Check.** First-order high-pass phase at `f` is `atan(fc/f)`. For
  `fc = 1.5 Hz` at 80 Hz the phase is 1.07 degrees. With ±20 % on the capacitor
  the spread is `atan(1.8/80) − atan(1.2/80)` = 0.43 degrees per pole. Sum the
  spread over every pole in the path.
- **Class.** automatic-in-design.py.
- **Source.** `hypercardiod_mic/kicad/design.py`: `_hz()`, `_phase_deg()`,
  `signal_phase_spread_deg()`, and the assertion that spread stays under 2
  degrees at 80 Hz. DC-bias derating from the capacitor vendor's curve.

```python
def _hz(r, c):            return 1.0 / (2 * math.pi * r * c)
def _phase_deg(fc, f):    return math.degrees(math.atan2(fc, f))

def phase_spread_deg(corners_hz, f, tol):
    return sum(_phase_deg(fc * (1 + tol), f) - _phase_deg(fc * (1 - tol), f)
               for fc in corners_hz)

assert max(CORNERS_HZ) <= AC_CORNER_MAX_HZ
assert phase_spread_deg(CORNERS_HZ, BAND_LOW_HZ, CAP_TOL) < PHASE_SPREAD_MAX_DEG
```

### 1.5 Guard rings and leakage on high-impedance nodes

- **Rule.** Any node with a source resistance above about 1 MΩ (electrometer
  and photodiode amplifiers, pH, piezo and charge inputs) needs a guard trace
  at the node's own potential, surrounding the node on every layer it touches.
  State a leakage budget: `V_err = I_leak × R_source`.
- **Gap.** DRC checks air clearance, not surface insulation resistance. ERC does
  not know a node's impedance. Flux residue and humidity set the leakage.
- **Check.** Mark such nets in `design.py` as `HIGH_Z_NETS`, with a guard net
  for each. Assert the leakage budget: 100 pA across 10 MΩ is 1 mV. Surface
  leakage to a neighbouring 5 V trace through an assumed 1e11 Ω is 50 pA. A guard
  at the node's potential puts about 0 V across that path. On the board, assert
  guard copper exists within clearance on each side of every such pad and track.
  State the cleaning requirement in the assembly notes.
- **Class.** Budget: automatic-in-design.py. Guard continuity:
  automatic-in-board. Contamination and cleaning: manual-review.
- **Source.** Tektronix/Keithley "Low Level Measurements Handbook" (leakage and
  guarding). Analog Devices "Op Amp Applications Handbook" (Zumbahlen), board
  layout and guarding chapter (needs-verification of chapter).

### 1.6 Star ground and analog return separation

- **Rule.** The return current of a noisy or high-current load must not share
  copper with an analog reference before the single point where the grounds
  meet. State that point by net and location. Enumerate, per stage, the path its
  return current takes.
- **Gap.** DRC and parity see nets. One `GND` net hides a shared return segment.
- **Check.** Shared resistance converts load current to analog error. Sheet
  resistance of 1 oz copper is about 0.5 mΩ per square. A 20 mm long, 0.25 mm
  wide return segment is 80 squares, so 40 mΩ. A 20 mA digital return through it
  adds 0.8 mV into the analog reference. On a multilayer board with a continuous
  plane, use one solid ground and partition by placement (5.2). Separate return
  traces are for two-layer boards without a plane.
- **Class.** Return-path trace by reviewer: manual-review. If the project
  declares separate return nets joined by a net-tie footprint, assert exactly one
  tie: automatic-in-board.
- **Source.** Analog Devices AN-202. Ott, "Electromagnetic Compatibility
  Engineering", the grounding chapter.

### 1.7 Op-amp stability into capacitive load

- **Rule.** A capacitive load on an op-amp output (shielded cable at roughly
  100 pF per metre, an ADC input, a long trace) needs an isolation resistor or
  the datasheet's compensation. Check the datasheet capacitive-load curve for the
  load actually driven.
- **Gap.** ERC and DRC cannot see a pole. The circuit passes every gate and
  rings or oscillates on the bench.
- **Check.** The open-loop output resistance `Ro` and the load form a pole at
  `1/(2π·Ro·CL)`. For `Ro = 50 Ω` and 1 nF (10 m of cable) that is 3.2 MHz, which
  sits near the unity-gain crossover of a 10 MHz GBW part and erodes phase margin.
  Screen in `design.py`: assert the pole lies above the crossover by a ratio the
  project states and justifies. Then simulate with the vendor macro-model.
- **Class.** Screen: automatic-in-design.py. Margin: manual-review (simulation or
  step response on a prototype).
- **Source.** The op-amp datasheet's capacitive-load figure. Analog Devices "Op
  Amp Applications Handbook", stability chapter (needs-verification of chapter).

### 1.8 Input protection and RF rectification

- **Rule.** Every external analog input has a series resistor and a clamp, and an
  RC low-pass whose corner sits above the signal band and well below RF
  interference. Op-amp input stages rectify out-of-band RF into DC offset, so
  check the part's EMIRR at the interferer's frequency.
- **Gap.** The offset appears only when a cable picks up RF. No gate injects it.
- **Check.** Corner `1/(2π·R·C)`. `design.py` asserts an input pole of 72 kHz
  from 2.2 kΩ and 1 nF, above a 30 kHz floor (`CORNER_RF_HZ >= RF_POLE_MIN_HZ`).
  Clamp current: `I = (V_fault − V_rail − 0.6 V)/R` must stay below the part's
  input clamp rating. A 24 V fault into a 3.3 V rail through 10 kΩ gives
  `(24 − 3.3 − 0.6)/10 kΩ` = 2 mA.
- **Class.** automatic-in-design.py. EMIRR lookup: manual-review.
- **Source.** `hypercardiod_mic/kicad/design.py` (`CORNER_RF_HZ`). Texas
  Instruments, "EMI Rejection Ratio of Operational Amplifiers", SBOA128
  (needs-verification). Analog Devices MT-095 "EMI, RFI, and Shielded Cable
  Termination" (needs-verification).

### 1.9 Balanced line drive

- **Rule.** A balanced output drives two legs with matched source impedance,
  matched coupling capacitors, and matched routing. Rejection of cable
  common-mode noise depends on impedance balance more than on voltage balance.
- **Gap.** Two legs with different build-out resistors pass every gate.
- **Check.** Assert component-for-component equality of value and footprint for
  each pair, as `design.py` does with `SYMMETRY_PAIRS`. Route the legs together
  with equal length. Conversion of common mode to differential is about
  `ΔR/(2·R_in)`. A 1 Ω mismatch between two 100 Ω build-out resistors into
  10 kΩ receiver legs gives `1/(2 × 10 000)` = 5e-5, which is −86 dB.
- **Class.** Pair equality: automatic-in-design.py. Leg length equality:
  automatic-in-board. Receiver behaviour: manual-review.
- **Source.** `hypercardiod_mic/kicad/design.py` (`SYMMETRY_PAIRS`, asserted in
  `_selfcheck()`). Whitlock, "Balanced Lines in Audio Systems: Fact, Fiction, and
  Transformers", Journal of the Audio Engineering Society (needs-verification of
  volume and issue). AES48 on interconnecting cables, shielding, and EMC
  (needs-verification of revision).

```python
SYMMETRY_PAIRS = [("R11", "R12"), ("C8", "C9"), ("R13", "R14")]
by_ref = {ref: (val, fp) for ref, _, val, fp, _ in INSTANCES}
for p, n in SYMMETRY_PAIRS:
    assert by_ref[p] == by_ref[n], "pair %s/%s asymmetric" % (p, n)
```

### 1.10 Microphone bias

- **Rule.** Electret (two-wire, internal FET): the bias resistor sets the FET's
  drain voltage and current. Assert the drain voltage inside the capsule's window
  at both rail extremes, using 1.1. Phantom power (P48): 48 V ±4 V through two
  6.8 kΩ resistors, 10 mA maximum per the standard. MEMS microphone: a low-noise
  supply, no bias network, and a supply filter sized by 1.3.
- **Gap.** Nothing relates a resistor to a capsule's operating point. A fault on
  one phantom leg dissipates `(48 V)² / 6.8 kΩ` = 0.34 W, which exceeds a 0.25 W
  resistor's rating.
- **Check.** Reuse the 1.1 snippet for the bias node. For phantom inputs, assert
  resistor power rating at the single-leg fault above, and the blocking capacitor's
  voltage rating above 48 V plus margin.
- **Class.** automatic-in-design.py.
- **Source.** The capsule datasheet window. IEC 61938 for P48 (needs-verification
  of clause). `hypercardiod_mic/kicad/design.py` for the electret chain.

## 2. Power conversion

### 2.1 Switching-regulator hot loop and input capacitor placement

- **Rule.** The loop from the input capacitor through the high-side switch, the
  low-side switch or diode, and back through ground to the capacitor carries the
  pulsed current. Keep its area minimal. Put the ceramic input capacitor against
  the regulator's input and power-ground pins on the same layer, with no vias in
  the loop and a solid ground plane directly beneath on layer 2. The regulator
  datasheet's layout section governs.
- **Gap.** DRC has no concept of a loop. The same netlist routes with a 3 mm loop
  or a 30 mm loop.
- **Check.** Voltage overshoot is `L · di/dt`. A 5 nH loop with 2 A switching in
  5 ns gives 2 V on top of the input rail. From the board, assert the distance
  from the input capacitor's pad to the regulator's input pin, and that the loop
  nets carry no via.
- **Class.** automatic-in-board. Loop plausibility beyond distance:
  manual-review.
- **Source.** Texas Instruments AN-1149 "Layout Guidelines for Switching Power
  Supplies", SNVA021 (needs-verification of number). The specific regulator's
  datasheet, layout section.

```python
# board-side script, built on the parser in scripts/kicad_geom.py
HOT_LOOP_MAX_MM = 3.0     # from the regulator datasheet layout example
d = math.hypot(*(a - b for a, b in zip(pad_xy("C_IN1", "1"), pad_xy("U_BUCK", "VIN"))))
assert d <= HOT_LOOP_MAX_MM, "C_IN1 is %.2f mm from VIN" % d
# pad_xy: read the placed pad position back, never derive it (kicad-api.md §4)
```

### 2.2 Switch-node copper area

- **Rule.** Give the switch node the copper it needs for the inductor and the
  regulator pins, and no more. Route no sensitive net across or beside it on any
  layer.
- **Gap.** A larger pour passes DRC and looks like better thermal design.
- **Check.** The switch node couples through capacitance, `C = ε0·εr·A/d`.
  100 mm² over a plane 0.2 mm below on FR-4 (εr 4.3) is 19 pF. At 12 V in 5 ns
  (2.4 V/ns) it injects 46 mA into the plane. Assert the summed copper area of
  the switch-node net against a stated budget.
- **Class.** Area: automatic-in-board. Neighbouring nets: manual-review.
- **Source.** Texas Instruments AN-1149, SNVA021 (needs-verification of number).

### 2.3 Feedback routing and divider tolerance

- **Rule.** Route the feedback node from the divider to the output at the load
  or output capacitor, away from the inductor and switch node. Place the divider
  against the feedback pin. Dividers above about 100 kΩ pick up noise.
- **Gap.** The feedback net connects correctly wherever it runs. The output
  voltage also depends on tolerance, which no gate evaluates.
- **Check.** `Vout = Vref·(1 + Rtop/Rbot)`. Evaluate with reference tolerance and
  1 % resistors against you. From the board, assert the feedback track keeps a
  stated distance from the switch-node and inductor copper.
- **Class.** Output window: automatic-in-design.py. Routing distance:
  automatic-in-board.
- **Source.** The regulator datasheet (reference voltage and tolerance, layout).

```python
V_REF, V_REF_TOL, R_TOL = 0.8, 0.01, 0.01          # datasheet, 1 % resistors
vout_lo = V_REF * (1 - V_REF_TOL) * (1 + R_TOP * (1 - R_TOL) / (R_BOT * (1 + R_TOL)))
vout_hi = V_REF * (1 + V_REF_TOL) * (1 + R_TOP * (1 + R_TOL) / (R_BOT * (1 - R_TOL)))
assert V_OUT_MIN <= vout_lo and vout_hi <= V_OUT_MAX, (vout_lo, vout_hi)
```

### 2.4 Inductor saturation, ripple, and orientation

- **Rule.** The inductor's saturation current rating must exceed the regulator's
  peak current limit, not only the load current. Evaluate ripple with the
  inductance at its minimum: tolerance plus fall-off under DC bias.
- **Gap.** A part with the right inductance and a low saturation rating
  satisfies every gate. Saturation collapses inductance, peak current rises, and
  the regulator trips its current limit under load.
- **Check.** `ΔI = (Vin − Vout)·D / (L·fs)` with `D = Vout/Vin`, and
  `Ipk = Iout + ΔI/2`. For 12 V in, 3.3 V out, 4.7 µH, 500 kHz, 2 A out:
  `D = 0.275`, `ΔI = 1.02 A`, `Ipk = 2.51 A`. Assert
  `Isat >= I_limit_max`, where `I_limit_max` is the converter's cycle-by-cycle
  limit at its maximum specification. For an unshielded or semi-shielded part,
  connect the winding start to the switch node so the outer turns shield the
  inner (needs-verification against the inductor vendor's note), and keep the
  part's field away from the feedback node and analog sections.
- **Class.** Arithmetic: automatic-in-design.py. Orientation and field:
  manual-review.
- **Source.** Texas Instruments SLVA477B "Basic Calculation of a Buck
  Converter's Power Stage" (ripple formula). Inductor datasheet for `Isat` and
  the inductance-versus-current curve.

```python
def buck_ripple_a(vin, vout, l_h, fs_hz):
    return (vin - vout) * (vout / vin) / (l_h * fs_hz)

l_min = L_NOM_H * (1 - L_TOL) * L_BIAS_FALLOFF     # vendor curve at Ipk
ipk = I_OUT_MAX_A + buck_ripple_a(VIN_MAX, V_OUT, l_min, F_SW_HZ) / 2
assert ipk <= ISAT_A, "Ipk %.2f A" % ipk
assert I_LIMIT_MAX_A <= ISAT_A, "converter limit above Isat"
```

### 2.5 Thermal: junction temperature, copper, and vias

- **Rule.** For every dissipating part, compute `Tj = Ta + P·θ` and assert
  `Tj <= Tj_max − margin` at the maximum ambient. A datasheet `θJA` is measured on
  a JEDEC test board and applies to that board. Use the junction-to-top
  characterization parameter `ψJT` with a measured case temperature, or the
  vendor's thermal tool, for the real board. Connect the exposed pad to a plane
  through the array of vias the datasheet specifies.
- **Gap.** DRC does not model heat. A thermal pad with one via passes.
- **Check.** Converter loss is `P_out·(1/η − 1)`. 6.6 W out at 90 % is 0.73 W.
  With `θ = 40 K/W` that is a 29 K rise, so 89 °C at 60 °C ambient against a
  125 °C limit. Vias help less than expected: one 0.3 mm via with 25 µm plating
  and 1.6 mm length has a barrel resistance of `L/(k·A)` = 163 K/W (copper,
  385 W/m·K, 0.0255 mm² of barrel). Nine in parallel give 18 K/W. From the board,
  count vias inside the pad outline and assert at least the datasheet number.
- **Class.** Temperature arithmetic: automatic-in-design.py. Via count:
  automatic-in-board. Verification of `θ` for the real board: manual-review
  (thermal camera or thermocouple on a prototype).
- **Source.** Texas Instruments SPRA953 "Semiconductor and IC Package Thermal
  Metrics". JEDEC JESD51 series (needs-verification of the specific part).

### 2.6 Trace current capacity: IPC-2221

- **Rule.** For every net carrying more than about 0.3 A, state its current and
  assert that its narrowest copper (track, pour neck, pad neck) meets the width
  that the formula below gives for the allowed temperature rise. State the layer
  and the copper weight.
- **Gap.** DRC's minimum track width is a manufacturing floor, not a rating. No
  gate knows how much current a net carries.
- **Formula.** IPC-2221:

  ```
  I = k · ΔT^0.44 · A^0.725
  I  amperes, ΔT degrees C rise above ambient, A cross-section in mil²
  k = 0.048 for external layers, k = 0.024 for internal layers
  1 oz copper = 1.378 mil (35 µm) thick
  A = width_mil × thickness_mil
  ```

- **Worked example, 2 A with 10 K rise, 1 oz copper.**

  | Layer | Area | Width |
  |---|---|---|
  | External | 42.4 mil² | 30.8 mil = 0.78 mm |
  | Internal | 110.3 mil² | 80.0 mil = 2.03 mm |

  The reverse: a 0.25 mm external track on 1 oz carries 0.88 A at 10 K rise and
  1.19 A at 20 K rise. Voltage drop is separate:
  `R = ρ·L/(w·t)` with `ρ = 1.72e-8 Ω·m`. A 50 mm long, 0.78 mm wide, 35 µm
  thick track is 31.5 mΩ, so 63 mV and 126 mW at 2 A. Copper resistance rises
  0.393 % per K.
- **IPC-2152 caveat.** IPC-2221's chart derives from older measurements. IPC-2152
  replaced it with measured data and shows that an internal conductor is not
  half as capable as an external one when the board has planes, and that a nearby
  plane raises capacity. So IPC-2221 is a conservative screen, and the internal
  constant is the more pessimistic of the two. When a net fails the IPC-2221
  screen and the board has an adjacent plane, evaluate with the IPC-2152 charts or
  a field solver instead, and record which was used. The chart range of IPC-2221
  is limited (needs-verification of its stated range), so do not extrapolate.
- **Check.** Declare `NET_CURRENT_A` in `design.py`. Compute the minimum width.
  From the board, take the minimum segment width of each net, including the
  narrowest point of each pour, and compare.
- **Class.** Width arithmetic: automatic-in-design.py. Net minimum width:
  automatic-in-board.
- **Source.** IPC-2221 (Generic Standard on Printed Board Design), formula and
  chart. IPC-2152 (Standard for Determining Current-Carrying Capacity in Printed
  Board Design).

```python
OZ_MIL = 1.378                                   # mil per oz of copper

def ipc2221_min_width_mm(i_a, d_t_c, oz, external):
    k = 0.048 if external else 0.024
    area_mil2 = (i_a / (k * d_t_c ** 0.44)) ** (1 / 0.725)
    return area_mil2 / (OZ_MIL * oz) * 0.0254

assert abs(ipc2221_min_width_mm(2, 10, 1, True) - 0.78) < 0.01     # self-test
assert abs(ipc2221_min_width_mm(2, 10, 1, False) - 2.03) < 0.01
for net, (i_a, ext) in NET_CURRENT_A.items():
    assert TRACK_WIDTH_MM[net] >= ipc2221_min_width_mm(i_a, DT_MAX_C, COPPER_OZ, ext), net
```

### 2.7 Input protection: reverse polarity, TVS, and fuse

- **Rule.** For every external supply input, state the reverse-polarity element,
  the surge clamp, and the fuse, each with arithmetic. Choose from the table.

  | Element | Condition to assert |
  |---|---|
  | Series Schottky | `P = Vf × I`. Assert the drop does not break the regulator's minimum input (the `V_PLUS` headroom assertion in `design.py`). |
  | P-FET ideal diode | The input never exceeds the FET's `Vgs(max)`. A 24 V input on a ±20 V part needs a gate clamp. |
  | TVS | `V_RWM >= 1.1 × Vin_max`, and `V_clamp` at the rated pulse current `<= 0.9 ×` the lowest absolute maximum downstream. |
  | Fuse | Hold current above the worst-case load, and the inrush `I²t` below half the fuse's rated `I²t` (needs-verification of the derating factor). |

- **Gap.** ERC sees the parts connected. It does not check that a clamp's voltage
  is below a downstream part's limit.
- **Check.** Assert each condition from datasheet constants. Part curves are
  transcribed from the datasheet.
- **Class.** automatic-in-design.py. Datasheet transcription: manual-review.
- **Source.** The TVS and fuse datasheets. Texas Instruments SLVA139 "Reverse
  Current/Battery Protection Circuits" (needs-verification of number). For vehicle
  supplies, ISO 7637-2 and ISO 16750-2 define the surge pulses (needs-verification
  of edition).

### 2.8 Inrush and soft start

- **Rule.** Assert the inrush current at enable and at hot-plug against the
  source, the connector, and the fuse.
- **Gap.** No gate evaluates a transient.
- **Check.** With soft start, `I = C_total·Vout/t_ss`. 110 µF at 3.3 V with a
  1 ms soft start draws 0.36 A on top of the load. Without soft start the limit is
  source impedance: `I_pk = Vin/ESR_total`. Hot-plug overshoot on the input side
  is in 9.4.
- **Class.** automatic-in-design.py.
- **Source.** The regulator datasheet's soft-start time and current-limit
  parameters.

### 2.9 LDO dropout and dissipation

- **Rule.** Assert two things at the corners: `Vin_min >= Vout + Vdropout(I_max)`
  and `Tj <= Tj_max − margin` with `P = (Vin_max − Vout)·I + Vin·Iq`.
- **Gap.** The regulator connects and passes ERC at an input where it drops out
  or cooks.
- **Check.** 5.25 V in, 3.3 V out, 300 mA: `P = 1.95 × 0.3` = 0.585 W. At 60 K/W
  that is a 35 K rise, so 105 °C at 70 °C ambient. Add the end-of-discharge dropout
  check in `electronics.md` §5 when the input is a cell.
- **Class.** automatic-in-design.py.
- **Source.** Texas Instruments SLVA079 "Understanding the Terms and Definitions
  of LDO Voltage Regulators" (needs-verification of number). The regulator
  datasheet (dropout curve versus current and temperature).

```python
p_ldo = (VIN_MAX - V_OUT) * I_OUT_MAX_A + VIN_MAX * I_Q_A
assert VIN_MIN >= V_OUT + V_DROPOUT_AT_IMAX, "dropout"
assert T_AMB_MAX_C + p_ldo * THETA_JA_KW <= TJ_MAX_C - 15, "Tj %.0f C" % (T_AMB_MAX_C + p_ldo * THETA_JA_KW)
```

### 2.10 Output capacitor ESR window and DC-bias derating

- **Rule.** Some LDOs need output-capacitor ESR inside a window to stay stable,
  and a ceramic's ESR can sit below it. Many modern parts accept ceramics. Read
  the datasheet's output-capacitor table. Assert the effective capacitance after
  DC-bias derating exceeds the stated minimum, and the ESR window holds at
  tolerance and temperature.
- **Gap.** The part list shows a capacitor of the right nominal value. A 10 µF
  ceramic in a small package can lose half its capacitance at the rail voltage
  (needs-verification against the vendor curve for the exact part).
- **Check.** Hold a table of derating factors per capacitor part number from the
  vendor's DC-bias curve. Assert `C_nom × factor × (1 − tol) >= C_min`.
- **Class.** Arithmetic: automatic-in-design.py. Curve lookup: manual-review.
- **Source.** The regulator datasheet's output-capacitor requirements. The
  capacitor vendor's DC-bias characteristic.

### 2.11 Bulk capacitance, source impedance, and negative input impedance

- **Rule.** A regulated converter at constant power presents an incremental input
  impedance `Z_in = −Vin²/P_in`, which is negative. If the source or an input
  filter has an output impedance that approaches `|Z_in|`, the system can
  oscillate. Assert that the filter's peak output impedance stays below `|Z_in|`
  by a stated margin, evaluated at minimum input voltage, where `|Z_in|` is
  smallest.
- **Gap.** Both circuits are stable alone. Only their interaction oscillates, and
  no gate analyses interaction.
- **Check.** 3.3 V at 1 A from 5 V at 90 % is `P_in = 3.67 W`, so
  `|Z_in| = 25/3.67` = 6.8 Ω. An LC filter of 10 µH and 10 µF has
  `Z0 = sqrt(L/C)` = 1 Ω, so 16.7 dB below `|Z_in|` if damped to Q of 1. Add
  damping (series resistance or an electrolytic capacitor) when Q is high. A long
  supply lead is an inductor, so include it in `L`.
- **Class.** automatic-in-design.py.
- **Source.** Middlebrook, "Input Filter Considerations in Design and Application
  of Switching Regulators", IEEE Industry Applications Society Annual Meeting,
  1976. Erickson and Maksimovic, "Fundamentals of Power Electronics", input filter
  chapter (needs-verification of chapter number).

```python
p_in = V_OUT * I_OUT_MAX_A / ETA_MIN
z_in = VIN_MIN ** 2 / p_in                       # magnitude of the negative impedance
z_peak = (L_FILT_H / C_BULK_F) ** 0.5 * Q_FILT   # Q from the damping network
assert z_peak <= 0.316 * z_in, "filter %.2f ohm vs |Zin| %.2f ohm" % (z_peak, z_in)  # 10 dB margin
```

## 3. Digital and high-speed

### 3.1 Controlled impedance

- **Rule.** For every net that needs a stated impedance (USB, Ethernet, memory,
  clock lines, RF), compute the trace width from the stackup the fab will build,
  assert it with two methods, and confirm it with the fab's field solver. A track
  width that passes DRC has an impedance set by the dielectric height, the
  dielectric constant, and the copper thickness, none of which DRC reads.
- **Gap.** DRC checks that the width is above a manufacturing floor. Impedance
  moves roughly 10 % per 10 % change in dielectric height.
- **Formulas.**

  ```
  Microstrip, IPC-2141:
    Z0 = 87 / sqrt(er + 1.41) × ln( 5.98·h / (0.8·w + t) )
    valid for 0.1 < w/h < 2.0 and 1 < er < 15

  Microstrip, Hammerstad:
    eeff = (er + 1)/2 + (er − 1)/2 × 1/sqrt(1 + 12·h/w)
    w/h <= 1:  Z0 = 60/sqrt(eeff) × ln( 8·h/w + w/(4·h) )
    w/h >  1:  Z0 = 120·pi / ( sqrt(eeff) × (w/h + 1.393 + 0.667·ln(w/h + 1.444)) )

  Stripline, IPC-2141 (b = plane-to-plane spacing):
    Z0 = 60 / sqrt(er) × ln( 4·b / (0.67·pi·(0.8·w + t)) )
    valid for w/(b − t) < 0.35 and t/b < 0.25

  Edge-coupled microstrip pair, IPC-2141 (s = gap):
    Zdiff = 2·Z0 × (1 − 0.48·exp(−0.96·s/h))     (needs-verification of range)
  ```

  Propagation delay is `sqrt(eeff)/c`: 6.0 ps/mm for the microstrip below, and
  `sqrt(er)/c` = 6.9 ps/mm for a stripline in `er = 4.3`.
- **Worked example.** FR-4, `er = 4.3`, `h = 0.2 mm` prepreg to the reference
  plane, `t = 35 µm`. At `w = 0.36 mm` (`w/h = 1.8`, inside the validity range)
  IPC-2141 gives 47.7 Ω and Hammerstad gives 52.6 Ω. The two differ by 10 %, so
  neither is final. Solved for exactly 50 Ω they give 0.335 mm and 0.392 mm. On a
  1.6 mm two-layer board with the plane on the back (`h = 1.6 mm`), 50 Ω is a
  3.1 mm trace. The fab's solver and stackup report decide the final width.
- **Stackup dependence.** `h`, `er`, `t`, solder-mask coverage, and glass-weave
  resin content all move the result. Take the stackup from the fab's published
  table, not from a generic value. A common 4-layer stackup quotes a 0.2104 mm
  outer prepreg at `er` near 4.4 (needs-verification against the fab's current
  table).
- **Check.** `design.py` carries the stackup constants and the target widths, and
  asserts that both methods land within the tolerance of the target. The board
  script asserts every net of the class uses the declared width and sits over its
  reference plane. The fab's solver confirms.
- **Class.** Arithmetic and width: automatic-in-design.py and automatic-in-board.
  Solver confirmation: manual-review.
- **Source.** IPC-2141A "Design Guide for High-Speed Controlled Impedance Circuit
  Boards". Hammerstad and Jensen, "Accurate Models for Microstrip Computer-Aided
  Design", IEEE MTT-S 1980. Wadell, "Transmission Line Design Handbook". The
  validity ranges are those of the formulas as published.

```python
ER, H_MM, T_MM, Z_TARGET, Z_TOL = 4.3, 0.2, 0.035, 50.0, 0.10

def z_ipc2141(w, h=H_MM, t=T_MM, er=ER):
    return 87 / math.sqrt(er + 1.41) * math.log(5.98 * h / (0.8 * w + t))

def z_hammerstad(w, h=H_MM, er=ER):
    eeff = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 * h / w)
    if w / h <= 1:
        return 60 / math.sqrt(eeff) * math.log(8 * h / w + w / (4 * h))
    return 120 * math.pi / (math.sqrt(eeff) * (w / h + 1.393 + 0.667 * math.log(w / h + 1.444)))

W_MM = 0.36
assert 0.1 < W_MM / H_MM < 2.0, "outside the IPC-2141 validity range"
for z in (z_ipc2141(W_MM), z_hammerstad(W_MM)):
    assert abs(z - Z_TARGET) <= Z_TOL * Z_TARGET, z
```

### 3.2 Length matching and skew budgets

- **Rule.** For each differential or source-synchronous group, take the skew
  budget from the interface specification or the controller vendor's layout
  guide. Where only a bit time is known, take 10 % of the unit interval as a
  starting budget and say so. Convert skew to length with the propagation delay
  of the layer: `ΔL_mm = skew_ps / tpd_ps_per_mm`.
- **Gap.** DRC knows lengths only if a custom rule exists. A length difference of
  20 mm on a 480 Mb/s pair passes every default check.
- **Check.** From the board, sum segment lengths per net, including vias at the
  stack height, and assert `|ΔL|` below the budget. A custom DRC rule in the
  generated `.kicad_dru` with a `skew` or `length` constraint makes the DRC gate
  enforce it (needs-verification of the constraint names in the installed KiCad
  version).

  | Interface | Impedance and skew guidance | Source |
  |---|---|---|
  | USB 2.0 high-speed (480 Mb/s, UI 2.083 ns) | 90 Ω differential ±15 %. Intra-pair skew guidance of 100 ps appears in vendor guides, about 17 mm on microstrip at 6.0 ps/mm. Several vendors recommend 2.5 mm or less. Take the stricter. | USB 2.0 specification (cable impedance); controller vendor layout guide, for example Texas Instruments SLLA414 (needs-verification of title and number) |
  | USB 2.0 full-speed (12 Mb/s, UI 83 ns) | Skew is loose against the UI. Keep the pair together and the same length. | USB 2.0 specification |
  | 100BASE-TX, 1000BASE-T Ethernet | 100 Ω differential per pair. Pair length matching from the PHY vendor. | IEEE 802.3 clause 25 and clause 40; PHY layout guide (needs-verification of limits) |
  | LPDDR | Byte-lane and command-address matching in ps from the SoC vendor. Not a generic number. | JEDEC JESD209 series for the protocol; SoC hardware design guide (needs-verification of limits) |
- **Class.** Budget arithmetic: automatic-in-design.py. Net lengths:
  automatic-in-board.
- **Source.** As the table. Johnson and Graham, "High-Speed Digital Design", for
  skew as a fraction of rise time.

```python
TPD_PS_PER_MM = 6.0                       # microstrip, eeff 3.27 (3.1)
SKEW_BUDGET_PS = {"USB_D": 100.0}         # stricter vendor figure if one exists
for grp, budget in SKEW_BUDGET_PS.items():
    assert LENGTH_DELTA_MM[grp] * TPD_PS_PER_MM <= budget, grp
```

### 3.3 Return paths and plane splits

- **Rule.** Every fast-edge or high-speed signal runs over an unbroken reference
  plane for its full length. No route crosses a split, a slot, a cut in a filled
  zone, or a gap between two zones. A layer change that moves between reference
  planes needs a ground stitching via beside the signal via, within a distance
  the project states (start from 2 mm and justify any larger value).
- **Gap.** The net connects and DRC passes with a track across a plane gap.
  Return current at high frequency follows the path of least inductance, directly
  beneath the trace. The distribution falls with distance `d` from the trace as
  roughly `1/(1 + (d/h)²)`, so most of it lies within a few `h` (needs-verification
  of the exact fraction).
- **Check.** From the board with filled zones: sample points along each
  high-speed track and assert the reference layer has copper of the reference net
  within a margin at every point. `kicad_zonefill.py` fills zones for this check.
- **Class.** automatic-in-board (needs filled zones).
- **Source.** Johnson and Graham, "High-Speed Digital Design", ground planes and
  layer stacking. Bogatin, "Signal and Power Integrity: Simplified", return
  current distribution. Ott, "Electromagnetic Compatibility Engineering".

### 3.4 Decoupling placement and loop inductance

- **Rule.** Place each per-pin capacitor against its supply pin, with the via to
  the plane at the capacitor's pad, so the loop is pin, capacitor, plane. Assert
  the distance from the capacitor pad to the supply pin and the via count. The
  placement policy and values are in `electronics.md` §4. This rule adds the
  arithmetic.
- **Gap.** A capacitor 15 mm away connects to the same net and passes.
- **Check.** Inductance of a via: `L = 5.08·h·(ln(4·h/d) + 1)` nH, with `h` and
  `d` in inches. For `h = 1.6 mm` and `d = 0.3 mm` that is 1.30 nH. A loop of
  2 nH with a 100 nF capacitor gives an SRF of 11.3 MHz and an impedance of
  1.26 Ω at 100 MHz. Compare with a target impedance `Z_t = V·ripple / ΔI`:
  3.3 V, 5 % ripple, and 0.3 A step give 0.55 Ω. A loop of 2 nH misses that above
  about 44 MHz, and the plane pair's own capacitance carries the rest. Edge
  content extends to about `0.35/t_r`, so a 1 ns edge reaches 350 MHz.
- **Class.** Distance and via count: automatic-in-board. Impedance arithmetic:
  automatic-in-design.py.
- **Source.** Johnson and Graham (via inductance, knee frequency `0.35/t_r`).
  Smith, Anderson, Roy, "Power Plane SPICE Models and Simulated Performance for
  Materials and Geometries", IEEE Trans. Advanced Packaging, for target impedance
  (needs-verification of citation).

```python
f_srf = 1 / (2 * math.pi * math.sqrt(L_LOOP_H * C_DECOUPLE_F))
z_target = V_RAIL * RIPPLE_FRAC / I_STEP_A
f_ok_max = z_target / (2 * math.pi * L_LOOP_H)        # above this, plane capacitance carries the load
assert f_ok_max >= F_PLANE_TAKEOVER_HZ, "loop %.1f nH leaves a gap" % (L_LOOP_H * 1e9)
```

### 3.5 Reset and boot straps

- **Rule.** Keep a strap table in `design.py`: pin, the level required at the
  sampling instant, the external circuit on the net, and the state of every
  peripheral output that shares the net during reset. Assert that no external
  circuit forces the wrong level, and that no strap net carries an LED, a
  peripheral output, or a load the datasheet forbids.
- **Gap.** ERC sees a bidirectional pin wired to an LED and passes. A strap pin
  that reads the wrong level at reset boots into the wrong mode, or selects the
  wrong flash voltage.
- **Check.** Typical hazards, each documented in the vendor datasheet's
  strapping section: ESP32 flash-voltage select on an input that is also a
  peripheral line; STM32 `BOOT0` floating; RP2040 chip-select line used for boot
  mode. For each, the table states the required level and the assertion rejects
  any pull in the other direction. Include the peripheral side: a chip-select
  held floating while the controller is in reset leaves the peripheral
  selected. Pull it to the inactive level.
- **Class.** automatic-in-design.py. Reset timing on silicon: manual-review.
- **Source.** The controller datasheet's boot-mode or strapping-pin table
  (section names differ by vendor, needs-verification for each cited part).

```python
STRAPS = {   # net: (required level at reset, reason)
    "BOOT0": (0, "low boots from flash"),
    "MTDI":  (0, "high selects 1.8 V flash on this part"),
}
EXTERNAL_PULL = {"BOOT0": "down", "MTDI": None}       # derived from INSTANCES
for net, (level, why) in STRAPS.items():
    pull = EXTERNAL_PULL[net]
    assert pull in (None, "down" if level == 0 else "up"), "%s: %s" % (net, why)
```

### 3.6 Crystal layout

- **Rule.** Choose the two load capacitors so that the crystal sees its specified
  load capacitance, check drive level and gain margin, and lay out the crystal
  to the controller vendor's rules.
- **Gap.** Any capacitor values connect. Wrong load capacitance pulls the
  frequency and can stop oscillation. Overdriving a crystal ages it.
- **Check.**

  ```
  CL = (C1 × C2) / (C1 + C2) + Cstray
  C1 = C2 = 2 × (CL − Cstray)                     for equal capacitors
  ```

  Worked: `CL = 8 pF`, `Cstray = 3 pF`, so `C1 = C2 = 10 pF`. Check
  `10 × 10 / 20 + 3` = 8 pF. Stray capacitance of 2 to 5 pF covers pad, trace, and
  pin; take it from the controller's guide. Drive level
  `P = ESR × (2·π·f·V_rms·(C0 + CL))²`. For 8 MHz, 50 Ω ESR, `C0 = 3 pF`,
  `CL = 12 pF`, and 2.5 V peak-to-peak, `P = 22 µW`, which is under the typical
  100 µW rating (take the real rating from the crystal datasheet). The
  oscillator's gain margin is a ratio of the amplifier's transconductance to the
  critical value. Controller guides state a minimum (a ratio of 5 is common,
  needs-verification against ST AN2867).

  Layout: crystal and load capacitors against the controller pins; short, equal,
  direct traces; no other signal routed under or beside the crystal on any layer;
  a ground guard that connects at one point. Vendors differ on whether to remove
  the plane under the crystal, so follow the controller vendor's guide.
- **Class.** Arithmetic: automatic-in-design.py. Trace length and keep-out:
  automatic-in-board. Gain margin on silicon: manual-review.
- **Source.** Microchip AN826 "Crystal Oscillator Basics and Crystal Selection for
  rfPIC and PICmicro Devices". STMicroelectronics AN2867 "Oscillator design guide
  for STM8AF/AL/S, STM32 MCUs and MPUs". The crystal datasheet.

```python
C1_PF = C2_PF = 2 * (CL_PF - C_STRAY_PF)
assert abs(C1_PF * C2_PF / (C1_PF + C2_PF) + C_STRAY_PF - CL_PF) < 0.01
i_a = 2 * math.pi * F_HZ * (C0_F + CL_PF * 1e-12) * V_RMS
assert ESR_OHM * i_a ** 2 <= DRIVE_LEVEL_MAX_W * 0.5, "drive level"
```

### 3.7 Termination

- **Rule.** A trace is a transmission line when its one-way delay exceeds about
  one sixth of the signal's 10 to 90 % rise time (needs-verification of the
  factor). Beyond that length, terminate. Use a series resistor at the source,
  `Rs = Z0 − R_driver`, for point-to-point lines, and a parallel or AC termination
  at the far end for multi-drop buses.
- **Gap.** An unterminated 80 mm clock passes every gate and rings on silicon.
- **Check.** Critical length `L_crit = t_r / (6 × tpd)`. For `t_r = 2 ns` at
  6.0 ps/mm that is 55 mm. A 25 Ω driver on a 50 Ω line needs `Rs = 25 Ω`. Source
  termination also slows the edge, which helps emissions. From the board, assert
  every net above `L_crit` has the series resistor placed at the driver.
- **Class.** Arithmetic: automatic-in-design.py. Net length:
  automatic-in-board.
- **Source.** Bogatin, "Signal and Power Integrity: Simplified", and Johnson and
  Graham, "High-Speed Digital Design", transmission lines and termination.

### 3.8 SPI and I2C pull-ups and edge rates

- **Rule (I2C).** Size every pull-up to land inside the window set by the rise
  time and the sink current, and assert that the window is not empty.
- **Gap.** A pull-up of any value connects. A window that is empty, or a rise time
  that misses the mode's limit, passes every gate and fails on the bus.
- **What runs without this assertion.** `kicad_schrules.py`'s
  `open_drain_pullups` checks a fixed window per net class (defaults: I2C
  1 kΩ to 10 kΩ, reset 4.7 kΩ to 100 kΩ, `classes` in
  `templates/sch-rules.json`). It does not compute the window below, because
  the bus capacitance and speed mode are not in the netlist. A 1 kΩ to 10 kΩ
  pull-up can still miss the Fast-mode window of the worked example; only the
  `design.py` assertion below proves the bus.
- **Check.** From UM10204, Rev. 7.0, Tables 10 and 11 and §7.1:

  | Mode | `tr` max (30 to 70 %) | `Cb` max | `IOL` at `VOL` 0.4 V |
  |---|---|---|---|
  | Standard-mode, 100 kHz | 1000 ns | 400 pF | 3 mA |
  | Fast-mode, 400 kHz | 300 ns | 400 pF | 3 mA |
  | Fast-mode Plus, 1 MHz | 120 ns | 550 pF | 20 mA |

  ```
  Rp(max) = tr / (0.8473 × Cb)
  Rp(min) = (VDD − VOL(max)) / IOL
  ```

  Worked, `VDD = 3.3 V`: `Rp(min) = (3.3 − 0.4)/3 mA` = 967 Ω. Fast-mode with
  `Cb = 400 pF` gives `Rp(max) = 300 ns/(0.8473 × 400 pF)` = 885 Ω, so the window
  is empty: reduce `Cb` or use Standard-mode (2.95 kΩ). Fast-mode with 200 pF
  gives a window of 967 Ω to 1.77 kΩ. Estimate `Cb` as the sum of pin
  capacitances (up to 10 pF each, Table 10) plus trace capacitance of about
  `tpd/Z0` = 0.12 pF/mm, so 100 mm adds 12 pF.
- **Rule (SPI).** Keep the chip-select pulled inactive through reset (3.5). Put a
  series resistor at the driver on clock lines longer than `L_crit` (3.7).
- **Class.** automatic-in-design.py.
- **Source.** NXP UM10204 "I2C-bus specification and user manual", Rev. 7.0,
  1 October 2021 (read for this file). Section and table numbers are those of
  Rev. 7.0.

```python
def i2c_rp_window(vdd, cb_f, tr_s, iol_a, vol=0.4):
    return (vdd - vol) / iol_a, tr_s / (0.8473 * cb_f)     # UM10204 §7.1

rp_min, rp_max = i2c_rp_window(3.3, CB_F, 300e-9, 3e-3)    # Fast-mode
assert rp_min < RP_OHM < rp_max, "Rp window %.0f to %.0f ohm" % (rp_min, rp_max)
```

### 3.9 Unused pins

- **Rule.** Every unused input, output, and spare channel gets the treatment its
  datasheet states: tied high, tied low, left open, or tied off as a follower to
  a mid-supply reference for an op-amp section. Record the treatment per pin.
- **Gap.** A `no_connect` flag satisfies ERC whether the datasheet wants it open,
  grounded, or tied off. A floating CMOS input can sit near the threshold, draw
  shoot-through current, and oscillate.
- **Check.** Keep an `UNUSED_PINS` table in `design.py` with the treatment and
  the datasheet table that states it. Assert that every pin with no net appears in
  the table. This is the same discipline as `design.py`'s refusal to emit a symbol
  pin the row leaves unconnected.
- **Class.** automatic-in-design.py. The datasheet reading: manual-review.
- **Source.** Texas Instruments SCBA004 "Implications of Slow or Floating CMOS
  Inputs". The part's datasheet.

## 4. RF

### 4.1 50 Ω lines and coplanar waveguide

- **Rule.** Compute each RF trace's width for the stackup using 3.1, and confirm
  it in the fab's solver. On a two-layer 1.6 mm board, microstrip is 3.1 mm wide
  for 50 Ω, which is wider than most pads, so a coplanar waveguide with ground
  (CPWG) is common: a narrower trace, a stated gap to ground copper on each side,
  and a plane below. Set the gap in the solver, and tie both side pours with
  stitching vias (4.2).
- **Gap.** DRC accepts any width. A neck-down at a pad changes the impedance for
  that length, and nothing flags it.
- **Check.** Assert the width constant per class in `design.py`. From the board,
  assert every segment of the RF net uses it, except at the declared pad
  transitions. FR-4 loss grows with frequency; above about 6 GHz, evaluate a
  low-loss laminate (needs-verification of the crossover for the application).
- **Class.** Width: automatic-in-design.py and automatic-in-board. Solver
  confirmation: manual-review.
- **Source.** Simons, "Coplanar Waveguide Circuits, Components, and Systems".
  Wadell, "Transmission Line Design Handbook". The fab's stackup report.

### 4.2 Stitching via spacing against wavelength

- **Rule.** Space ground stitching vias along an RF line, and along shield and
  pour boundaries, at no more than one twentieth of the wavelength in the
  dielectric at the highest frequency of concern (the carrier and its second
  harmonic at least).
- **Gap.** DRC does not count vias along a trace.
- **Check.** `λ = c / (f × sqrt(eeff))` with `c = 299.8 mm/ns` and `eeff` about 3.2
  for 50 Ω microstrip on FR-4.

  | Frequency | λ | λ/20 | λ/10 |
  |---|---|---|---|
  | 2.4 GHz | 69.8 mm | 3.5 mm | 7.0 mm |
  | 4.8 GHz (2nd harmonic) | 34.9 mm | 1.7 mm | 3.5 mm |
  | 5.8 GHz | 28.9 mm | 1.4 mm | 2.9 mm |

  Use `λ/20`. A looser `λ/10` is sometimes used and needs a stated reason.
- **Class.** Arithmetic: automatic-in-design.py. Via spacing along each net:
  automatic-in-board.
- **Source.** Ott, "Electromagnetic Compatibility Engineering", the shielding
  chapter, for the `λ/20` aperture and spacing rule (needs-verification of the
  chapter and the attenuation it assumes).

```python
C_MM_PER_NS, EEFF = 299.792, 3.2
lam_mm = C_MM_PER_NS / (F_HIGHEST_GHZ * EEFF ** 0.5)
assert STITCH_PITCH_MM <= lam_mm / 20, "pitch %.1f mm > lambda/20 = %.1f mm" % (STITCH_PITCH_MM, lam_mm / 20)
```

### 4.3 Antenna keep-out

- **Rule.** The antenna vendor's keep-out drawing governs. Encode its rectangle
  as named constants in `design.py`, with the drawing's document reference.
  Forbid copper, vias, and components of every layer inside it. Place a module
  with an on-board antenna so the antenna overhangs the board edge or sits at the
  stated clearance from the ground plane, as the drawing shows.
- **Gap.** A pour fills the keep-out and every gate passes. The antenna detunes
  and the range halves.
- **Check.** The generator emits a rule area (keep-out for tracks, vias, copper
  pour, and pads) at the declared rectangle. DRC then fails if anything enters it.
  `design.py` asserts the rectangle equals the vendor figures. The enclosure
  matters as much: keep metal, a battery, and a display from the antenna's near
  field, and check that in the case `verify()` with the clearance the vendor
  states.
- **Class.** automatic-in-board, if the generator emits the keep-out. The
  pipeline does not emit one by default. Enclosure clearance: `verify()` in the
  case phase, once the project adds the check. Near-field effect of the real
  enclosure: manual-review (return loss on a VNA).
- **Source.** The module or antenna vendor's layout guide, keep-out figure. For
  example, an on-board PCB antenna module's datasheet "PCB layout recommendations"
  section.

### 4.4 Matching network placement

- **Rule.** Put a pi network (shunt, series, shunt) between the RF device and the
  antenna feed, with its parts adjacent to the feed and the shunt parts' ground
  vias at their pads. Keep the footprints even when the first build populates them
  with 0 Ω or leaves them unpopulated, because the final values come from VNA
  tuning. Use the package size the vendor's design uses, usually 0201 or 0402,
  since parasitics of the pad and part change with size.
- **Gap.** Any component values connect. A matching part 8 mm from the feed is a
  different network.
- **Check.** From the board, assert the pad-to-pad distance between the match
  parts and the feed. Quality of the match is return loss: `RL = −20·log10|Γ|`.
  A 2:1 VSWR has `|Γ| = 1/3`, so 9.5 dB return loss and 0.51 dB mismatch loss
  `(−10·log10(1 − Γ²))`. State the target return loss in the spec.
- **Class.** Distances: automatic-in-board. Tuning: manual-review (VNA).
- **Source.** Pozar, "Microwave Engineering", reflection coefficient and
  mismatch loss. The RF device vendor's reference design.

### 4.5 Ground reference continuity under the RF trace

- **Rule.** An RF trace runs over a solid ground plane on the adjacent layer for
  its whole length, with no other routing on that plane's layer under it, no plane
  split, and no layer change without ground vias beside the transition. Use
  layer 1 for RF and layer 2 for ground on a four-layer board.
- **Gap.** The route connects whether or not the plane is there.
- **Check.** As 3.3, with a tighter margin: the plane must exist within the
  trace's width on both sides.
- **Class.** automatic-in-board (needs filled zones).
- **Source.** Johnson and Graham, "High-Speed Digital Design". Wadell.

### 4.6 Connector launch: SMA and U.FL

- **Rule.** Use the connector vendor's footprint and keep-out drawing. Taper the
  50 Ω line to the launch pad. Cut the plane under the pad when the vendor's
  drawing shows it, to offset the pad capacitance. For an edge-launch SMA, the
  center-pin pad width, the ground clearance, and the board thickness are
  specified by the vendor.
- **Gap.** A generic footprint with the right pin count passes. Impedance at the
  launch is set by geometry that `kicad_fpcheck.py` does not check, since it
  compares pad geometry to a declared package.
- **Check.** Reference the vendor drawing in `design.py`. Measure the launch with
  a VNA or a time-domain reflection measurement on a prototype. U.FL connectors
  have a low rated mating count (the vendor states it, needs-verification),
  so state the use as a one-time connection in the assembly notes.
- **Class.** manual-review.
- **Source.** The connector datasheet's recommended footprint (for example Hirose
  U.FL series; Amphenol or Molex edge-launch SMA).

### 4.7 Filtering and harmonics

- **Rule.** Compute the harmonic level at the antenna from the transmit power and
  the filter's rejection. Compare against the applicable limit for the market.
- **Gap.** Nothing in the pipeline estimates a spectrum.
- **Check.** Conversion from field strength to EIRP:
  `EIRP_dBm = E_dBuV/m + 20·log10(d_m) − 104.77`. A limit of 54 dBµV/m at 3 m
  (the average limit above 960 MHz for general emissions in 47 CFR 15.209,
  needs-verification of the value and of which bands are restricted per 15.205)
  is `54 + 9.54 − 104.77` = −41.2 dBm. A 10 dBm transmitter then needs 51 dB of
  suppression of a harmonic that falls in a restricted band. Assert the filter's
  datasheet rejection at the harmonic frequency against that requirement.
- **Class.** Arithmetic: automatic-in-design.py. Measurement: manual-review
  (conducted measurement with a spectrum analyzer, then a radiated scan).
- **Source.** 47 CFR Part 15, sections 15.205, 15.209, and 15.247 (FCC, United
  States). ETSI EN 300 328 for 2.4 GHz in Europe (needs-verification of
  edition). Modular transmitters may carry a prior grant, which the module vendor
  documents.

### 4.8 Shielding cans

- **Rule.** A shield can is a ground-referenced box. Place its pad frame on a
  continuous ground net, with solder pads at a pitch of `λ/20` or less at the
  highest frequency to contain (4.2), and keep every part inside the frame below
  the can's inner height. Plan the can as an assembly step (placed by machine, or
  a two-piece frame and lid).
- **Gap.** A can footprint with four pads passes. Gaps in the frame leak at the
  wavelength they span.
- **Check.** From the board, assert the pad pitch around the frame. In `design.py`
  assert the tallest enclosed part height against the can's inner height. The
  enclosure `verify()` covers the can's outer height.
- **Class.** Pitch: automatic-in-board. Height: automatic-in-design.py.
- **Source.** Ott, "Electromagnetic Compatibility Engineering", shielding
  chapter. The can vendor's drawing.

## 5. Mixed-signal

### 5.1 ADC reference decoupling and routing

- **Rule.** Take the reference capacitor value, type, and ESR from the ADC
  datasheet. Place it against the reference pin with its own return via, and route
  the reference away from digital lines. Assert that reference noise leaves the
  target SNR intact.
- **Gap.** A capacitor of any value connects to the reference pin.
- **Check.** One code step is `LSB = Vref / 2^N`. 3.3 V at 12 bits is 0.81 mV. 4.096 V
  at 16 bits is 62.5 µV. The ideal converter SNR is `6.02·N + 1.76 dB`. Reference
  noise adds directly to the signal, so assert
  `20·log10(Vfs_rms / vn_ref_rms) >= SNR_target + margin`.
- **Class.** Arithmetic: automatic-in-design.py. Pad-to-pin distance:
  automatic-in-board.
- **Source.** The ADC datasheet's reference section. Analog Devices MT-001 "Taking
  the Mystery out of the Infamous Formula, SNR = 6.02N + 1.76dB" (needs-verification
  of title wording).

### 5.2 Analog and digital ground: one plane, partitioned by placement

- **Rule.** Default to one solid ground plane under the whole mixed-signal
  section. Do not split it. Place analog parts in one region, digital parts in
  another, and let the converter straddle the boundary. Keep digital traces out
  of the analog region, so digital return currents stay on their own side. Where
  a converter datasheet shows separate `AGND` and `DGND` pins, join both to the
  one plane at the package.
- **Gap.** A split plane passes DRC and breaks return paths (3.3). A single
  `GND` net passes while a digital trace crosses the analog input area.
- **Check.** Declare the analog region as a rectangle in `design.py`. Assert that
  no digital-class net has a segment inside it. Assert `AGND` and `DGND` are one
  net unless the design declares a net-tie and the datasheet requires it.
- **Class.** Region crossing: automatic-in-board. Single-net assertion:
  automatic-in-design.py. Return-path review: manual-review.
- **Source.** Analog Devices MT-031 "Grounding Data Converters and Solving the
  Mystery of AGND and DGND" (Kester, Bryant, Byrne): connect the converter's
  `DGND` pin to `AGND` at the package, at the same potential. Ott,
  "Electromagnetic Compatibility Engineering", grounding chapter.

```python
# board-side script
ANALOG_BOX = (x0, y0, x1, y1)            # mm, declared in design.py
for seg in segments_of_class("digital"):
    assert not _crosses(seg, ANALOG_BOX), "digital net %s enters the analog region" % seg.net
assert NET_AGND == NET_DGND, "grounds split without a declared net-tie"
```

### 5.3 Clock routing and jitter

- **Rule.** Sampling-clock jitter limits the SNR of the highest input frequency.
  Assert the limit and keep the clock source low-jitter, with its own supply
  filter and a route away from analog inputs.
- **Gap.** A clock that meets its frequency can still miss the SNR target.
- **Check.** `SNR_jitter = −20·log10(2·π·f_in·t_j)`. 20 kHz and 1 ns rms gives
  78 dB. 20 kHz and 100 ps gives 98 dB. 100 MHz and 1 ps gives 64 dB. Total jitter
  is the root-sum-square of the clock's and the converter's aperture jitter.
- **Class.** Arithmetic: automatic-in-design.py. Clock-to-input spacing:
  automatic-in-board.
- **Source.** Analog Devices MT-007 "Aperture Time, Aperture Jitter, Aperture
  Delay Time: Removing the Confusion".

```python
tj = (T_J_CLOCK_S ** 2 + T_J_APERTURE_S ** 2) ** 0.5
snr_jitter = -20 * math.log10(2 * math.pi * F_IN_MAX_HZ * tj)
assert snr_jitter >= SNR_TARGET_DB + 6.0, "jitter limits SNR to %.1f dB" % snr_jitter
```

### 5.4 Anti-alias filtering

- **Rule.** Attenuate the first alias band, `fs − f_in_max` and above, by at least
  the converter's dynamic range, using a filter whose order and corner are
  asserted.
- **Gap.** A filter on the schematic passes review. Whether its attenuation meets
  the converter's range is arithmetic that no gate does.
- **Check.** An order-`n` filter attenuates about `20·n·log10(f/fc)` for `f` well
  above `fc`. A 12-bit converter has 74 dB of range. A first-order RC would need
  `f_alias/fc = 5000`. At `fs = 48 kHz` and a 20 kHz band, the first alias is
  28 kHz, so no first-order RC can meet it. Oversample instead, or raise the
  order.
- **Class.** automatic-in-design.py.
- **Source.** Analog Devices MT-002 "What the Nyquist Criterion Means to Your
  Sampled Data System Design" (needs-verification of number).

### 5.5 Reference impedance, sample-and-hold kickback, and settling

- **Rule.** A SAR converter's input draws a charge packet each sample.
  Assert that the external filter settles the packet, and that the capacitor
  holding the reference or the input keeps the step below half an LSB.
- **Gap.** A resistor and capacitor of any value connect.
- **Check.** Settling to half an LSB needs `t_acq >= ln(2)·(N + 1)·R·C` = 0.693 ×
  13 × 1 kΩ × 10 pF = 90 ns for `N = 12`. Charge sharing: a sample capacitor
  `Csh` at a full-scale step moves the external capacitor `Cext` by
  `Vfs·Csh/(Cext + Csh)`. Keeping that below half an LSB needs
  `Cext >= 2^(N+1) × Csh`, which is 82 nF for 10 pF at 12 bits. Datasheets state
  a recommended RC. For a reference, `Zout × I_dynamic <= LSB/2`.
- **Class.** automatic-in-design.py.
- **Source.** The ADC datasheet's input section. Analog Devices AN-742 "Frequency
  Domain Response of Switched-Capacitor ADCs" (needs-verification of number).

### 5.6 Digital noise coupling into analog

- **Rule.** Keep digital edges away from analog nodes, slow the edges that do not
  need speed (series resistors at digital drivers), hold SPI clocks idle during
  conversion where the datasheet asks, and supply the analog section from a
  filtered or separate regulator.
- **Gap.** Coupling is capacitive and depends on spacing and parallel run length,
  which DRC clearance does not bound for noise.
- **Check.** Charge injection: `ΔV = Vstep × Cc / (Cc + Cnode)`. A 0.1 pF coupling
  from a 3.3 V edge into a 10 pF node moves it 33 mV, which is 40 LSB at 12 bits.
  From the board, assert a minimum spacing and a maximum parallel run between
  digital nets and nets of the high-impedance analog class.
- **Class.** automatic-in-board. Measurement: manual-review.
- **Source.** Ott, "Electromagnetic Compatibility Engineering", capacitive
  coupling. Johnson and Graham, crosstalk.

## 6. Sensors and MEMS

### 6.1 Acoustic ports

- **Rule.** A bottom-port microphone needs a hole in the board centred on the
  part's sound port within the vendor's tolerance, with the copper and solder-mask
  keep-out the vendor draws, and a gasket or seal from the part to the enclosure's
  sound hole. The back volume stays sealed. A top-port microphone needs an
  acoustic channel from the enclosure to the port, sealed to the part.
- **Gap.** The part's footprint passes `kicad_fpcheck.py`, which compares pad
  geometry to the declared package and does not read the port hole. A hole
  offset by 0.5 mm passes every gate.
- **Check.** From the board, read the hole and the footprint position and assert
  the offset against the vendor tolerance. The enclosure `verify()` asserts the
  hole in the case lines up with the board's port. A channel in front of a port
  forms a Helmholtz resonator, `f = (c/2π)·sqrt(A / (V·L_eff))` with
  `L_eff = L + 0.85·d`. A 1 mm diameter, 1 mm long channel into 20 mm³ resonates
  at 7.95 kHz, inside the audio band. Assert the resonance outside the band or
  document the peak.
- **Class.** Hole alignment: automatic-in-board. Case alignment: `verify()` once
  the project adds it. Resonance arithmetic: automatic-in-design.py. Seal quality:
  manual-review.
- **Source.** The microphone datasheet and its PCB design note, for example Analog
  Devices AN-1003 on mounting bottom-ported MEMS microphones (needs-verification of
  number and title). Kinsler et al., "Fundamentals of Acoustics", for the
  resonator formula.

### 6.2 Thermal isolation and self-heating

- **Rule.** Place a temperature-sensitive sensor away from regulators, inductors,
  power resistors, and radios. Slot the board between them if needed. State each
  dissipating part's power and assert a minimum distance to the sensor.
- **Gap.** A part beside a 0.5 W regulator passes every gate and reads 10 K high.
- **Check.** The sensor's own error is `P × θ`. 16.5 µW (5 µA at 3.3 V) with
  200 K/W is 3.3 mK. A neighbouring source is the larger term, so declare
  `HEAT_SOURCES_W` and assert a distance from the board. Slot width must meet the
  fab's routing minimum (needs-verification for the chosen fab).
- **Class.** Distance: automatic-in-board. Gradient on silicon: manual-review.
- **Source.** The sensor datasheet's layout and self-heating sections.

### 6.3 Orientation, frame, and mounting stress

- **Rule.** An accelerometer or gyroscope's axes follow the package, not the
  board. Declare the mapping from sensor axes to board axes, and assert it against
  the placement (rotation and side). A part on the bottom face is mirrored: its
  axes flip relative to the same part on the top, so the mirrored-board case needs
  its own mapping. Keep the sensor away from mounting holes, board edges,
  connectors, and V-grooves, whose stress shifts offset.
- **Gap.** A sensor rotated 90 degrees passes every gate. Firmware reads the
  wrong axis, or a mirrored sibling inverts one.
- **Check.** Compute the 3×3 mapping from rotation and side and compare it with the
  documented one. The composed rotate-and-flip transform and its sign traps are in
  `electronics.md` §8 and `kicad-api.md` §4: place the part, read it back, and
  never derive the orientation by hand. From the board, assert distance from the
  sensor to the nearest hole and edge against the vendor's stated value.
- **Class.** Mapping: automatic-in-design.py (if rotation and side are constants
  there) or automatic-in-board (read from the file). Distances: automatic-in-board.
  Verification on silicon: manual-review (tilt the board, read the output).
- **Source.** The sensor datasheet's axis-orientation figure and mounting section.

```python
def mount_matrix(rot_deg, bottom):          # sign and flip axis per kicad-api.md §4
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    rz = ((c, -s, 0), (s, c, 0), (0, 0, 1))
    return _matmul(rz, ((-1, 0, 0), (0, 1, 0), (0, 0, -1))) if bottom else rz

for name, (rot, bottom) in PLACEMENT.items():
    assert _close(mount_matrix(rot, bottom), EXPECTED_AXES[name]), name
```

### 6.4 Reflow stress, moisture, and handling

- **Rule.** For every MEMS part, record the moisture sensitivity level, peak
  reflow temperature, and handling restrictions, and confirm the assembly process
  respects them. Open-port parts (microphones, pressure, humidity, gas) take no
  wash, no ultrasonic cleaning, no conformal coating over the port, and no wave
  soldering.
- **Gap.** The bill of materials lists the part. It does not list that the part
  has a floor life.
- **Check.** Moisture classes set the time a part may sit in factory air
  (30 °C, 60 % relative humidity) before reflow:

  | MSL | Floor life |
  |---|---|
  | 1 | Unlimited |
  | 2 | 1 year |
  | 2a | 4 weeks |
  | 3 | 168 h |
  | 4 | 72 h |
  | 5 | 48 h |
  | 5a | 24 h |
  | 6 | Time on label |

  Keep an `MSL` and `PEAK_REFLOW_C` table in `design.py` and assert every MEMS
  reference designator appears in it. This checks completeness, not the values.
  Pressure sensors may need the port taped during reflow, and a post-reflow offset
  recalibration, per the vendor note.
- **Class.** Table completeness: automatic-in-design.py. Process:
  manual-review with the assembly house.
- **Source.** IPC/JEDEC J-STD-020 (classification of moisture and reflow
  sensitivity) and J-STD-033 (handling, packing, shipping, and use of
  moisture-sensitive devices). The part's datasheet handling section.

### 6.5 Capsule and electret bias

Bias and window arithmetic are in 1.1 and 1.10. A capsule's FET output sets the
bias node; the sensor-side rule is the same as for any biased node.

## 7. Motor and high current

### 7.1 Gate-drive loop, Miller turn-on, and bootstrap

- **Rule.** Keep the gate loop (driver output, gate resistor, gate, source,
  driver return) small. Where a power FET has a separate source sense pin, use it
  for the driver return. Choose gate resistors from the `dV/dt` target, and check
  the Miller turn-on of the off-state FET. Size the bootstrap capacitor from gate
  charge.
- **Gap.** A gate trace of any length connects.
- **Check.** During a `dV/dt` on the drain, the off-state FET's gate rises by
  `Cgd × dV/dt × (Rg_off + R_driver_pulldown)`. 50 pF, 48 V in 10 ns (4.8 V/ns),
  and 3 Ω gives 0.72 V, which leaves 28 % margin against a 1.0 V minimum
  threshold. Assert the spike below the minimum threshold with a stated margin.
  Bootstrap droop `ΔV = Qg/Cboot`: 30 nC and a 0.5 V allowance give 60 nF
  minimum. Use a margin above that (a factor of 10 is common, needs-verification)
  and a diode rated above the bus voltage.
- **Class.** Arithmetic: automatic-in-design.py. Driver-to-gate distance:
  automatic-in-board.
- **Source.** Texas Instruments SLUA618A "Fundamentals of MOSFET and IGBT Gate
  Driver Circuits". International Rectifier (now Infineon) AN-978 on high-voltage
  floating gate drivers (needs-verification of number). The FET datasheet.

### 7.2 Shunt resistor placement and Kelvin sensing

- **Rule.** Take the current-sense voltage with a four-terminal connection: sense
  traces join the shunt at the inner edge of its pads, or at separate sense pads,
  and run as a close pair to the amplifier. No load current flows in the sense
  traces.
- **Gap.** With the sense net named separately from the power net, parity and
  DRC enforce the topology. They do not see where on the pad the sense track
  attaches.
- **Check.** Copper in the measured path adds error. 5 mm of 1 mm wide, 1 oz track
  is 5 squares, so 2.5 mΩ. Against a 5 mΩ shunt, that is a 50 % error, and copper's
  0.393 %/K temperature coefficient adds drift. Shunt dissipation is `I²R`: 10 A
  through 5 mΩ is 0.5 W and 50 mV. Rate the part at twice that. Declare `SENSE_P`
  and `SENSE_N` as nets distinct from the high-current net. From the board, assert
  those nets touch no power copper except at the shunt.
- **Class.** automatic-in-design.py for the net split. Pad attachment geometry:
  automatic-in-board.
- **Source.** The shunt vendor's application note on four-terminal sensing, for
  example Vishay (needs-verification of the specific note). The current-sense
  amplifier's datasheet layout section.

### 7.3 Dead time and shoot-through

- **Rule.** Set the dead time to cover the slowest turn-off and the fastest
  turn-on, including driver propagation mismatch, plus a margin. Record the
  value as one constant shared by firmware configuration and `design.py`.
- **Gap.** Nothing checks switching times.
- **Check.** `t_dead >= t_off_max − t_on_min + t_mismatch`, then add margin. With
  60 ns, 15 ns, and 20 ns the floor is 65 ns, so 100 ns with margin. The cost is
  body-diode conduction, `2 × Vf × I × t_dead × fs` = 2 × 0.7 V × 10 A × 100 ns ×
  20 kHz = 28 mW.
- **Class.** Arithmetic: automatic-in-design.py. Confirmation: manual-review (probe
  both gates and the switch node).
- **Source.** SLUA618A. The FET and driver datasheets' switching characteristics.

### 7.4 Back-EMF, freewheel, and regeneration

- **Rule.** Give every inductive load a freewheel or clamp path rated above the
  load's peak current and below the switch's voltage rating. For a motor that can
  brake or be driven by its load, assert the bus voltage after regeneration.
- **Gap.** A bus that rises above a FET's rating shows no fault in any gate.
- **Check.** The energy returned to the bus capacitor `C` from stored energy `E`
  gives `V2 = sqrt(V1² + 2·E/C)`. 0.5 J into 470 µF at 24 V gives 52 V, above a
  40 V FET. Assert `V2 <= 0.8 × V_rating` of the lowest-rated part, or add a brake
  chopper or clamp.
- **Class.** automatic-in-design.py.
- **Source.** Energy conservation. Erickson and Maksimovic, "Fundamentals of Power
  Electronics" (needs-verification of chapter for converter clamps).

### 7.5 Bulk capacitance and ripple current

- **Rule.** Size the bus capacitors from ripple current rating as well as
  capacitance. Assert the number of capacitors from the RMS current each carries.
- **Gap.** Capacitance in the parts list says nothing about current rating.
- **Check.** For a half bridge, `I_C,rms ≈ I_out·sqrt(D·(1 − D))`, at most
  `0.5 × I_out`. 10 A gives 5 A rms. At 1.5 A per capacitor, that needs 4.
- **Class.** automatic-in-design.py.
- **Source.** Texas Instruments SLVA477B (input capacitor ripple of a buck
  converter, needs-verification of the equation's section). The capacitor
  datasheet's ripple rating at the frequency in use.

### 7.6 Thermal derating of the switch

- **Rule.** Evaluate conduction loss at the junction temperature the loss itself
  produces, because on-resistance rises with temperature. Iterate to a fixed
  point and assert it.
- **Check.** 10 A rms and 5 mΩ at 25 °C. The datasheet's normalized curve gives
  about 1.7× at 125 °C (needs-verification per part), so 8.5 mΩ, 0.85 W, and
  with 40 K/W a 34 K rise. Add switching loss.
- **Class.** automatic-in-design.py.
- **Source.** The FET datasheet's normalized on-resistance versus temperature
  curve. Texas Instruments SPRA953.

```python
tj = T_AMB_MAX_C
for _ in range(20):                         # fixed-point iteration
    rds = RDS_25C * (1 + RDS_TEMPCO_PER_K * (tj - 25.0))
    tj = T_AMB_MAX_C + (I_RMS_A ** 2 * rds + P_SW_W) * THETA_JA_KW
assert tj <= TJ_MAX_C - 15.0, "Tj %.0f C" % tj
```

### 7.7 Pour width and via count

- **Rule.** For each high-current transition between layers, assert the number of
  vias against the current. A via barrel is a small conductor.
- **Gap.** One via connects a net as well as ten. DRC does not count.
- **Check.** Barrel area is `π·(d + t_plating)·t_plating`. A 0.3 mm hole with 25 µm
  plating is 0.0255 mm² (39.6 mil²). Applying the IPC-2221 formula of 2.6 to that
  area gives 1.9 A at 10 K rise with the external constant, and 0.95 A with the
  internal constant. IPC-2221 does not define via ampacity, so this is an
  application of the trace formula to the barrel's cross-section, and a
  screening figure only (needs-verification against vendor or IPC-2152 data).
  Using the 0.95 A figure, 10 A needs 11 vias per transition. Assert the pour's
  neck width with the same function as 2.6.
- **Class.** Arithmetic: automatic-in-design.py. Via count per net transition:
  automatic-in-board.
- **Source.** IPC-2221 and IPC-2152, as 2.6.

### 7.8 Creepage and clearance

- **Rule.** Set the board's clearance per net class from the working voltage, from
  the table below, and assert that the configured value is at least the table
  value. DRC then enforces the geometry. For mains isolation, or any product
  standard (IEC 62368-1, IEC 60664-1), use that standard's creepage and clearance
  for the pollution degree and material group, and do a safety review. This file
  does not give mains values.
- **Gap.** DRC checks the clearance the project sets. The default is a
  manufacturing floor, far below what a 300 V net needs.
- **Check.** IPC-2221 Table 6-1, minimum conductor spacing, mm, DC or AC peak
  (the whole table is needs-verification):

  | Voltage between conductors | B1 internal | B2 external uncoated, to 3050 m | B4 external, permanent polymer coating |
  |---|---|---|---|
  | 0 to 15 V | 0.05 | 0.1 | 0.05 |
  | 16 to 30 V | 0.05 | 0.1 | 0.05 |
  | 31 to 50 V | 0.1 | 0.6 | 0.13 |
  | 51 to 100 V | 0.1 | 0.6 | 0.13 |
  | 101 to 150 V | 0.2 | 0.6 | 0.4 |
  | 151 to 170 V | 0.2 | 1.25 | 0.4 |
  | 171 to 250 V | 0.2 | 1.25 | 0.4 |
  | 251 to 300 V | 0.2 | 1.25 | 0.4 |
  | 301 to 500 V | 0.25 | 2.5 | 0.8 |

  Add `0.0025`, `0.005`, and `0.00305` mm per volt above 500 V for the three
  columns. These are clearances through air, not surface creepage. KiCad 9 and
  later can enforce creepage with a custom rule (needs-verification of the
  syntax).
- **Class.** Configured-value assertion: automatic-in-design.py, with the DRC gate
  enforcing the geometry. Product-standard compliance: manual-review.
- **Source.** IPC-2221 Table 6-1. IEC 62368-1 and IEC 60664-1 for product
  isolation.

```python
IPC2221_B2_MM = [(15, 0.1), (30, 0.1), (50, 0.6), (100, 0.6), (150, 0.6),
                 (170, 1.25), (250, 1.25), (300, 1.25), (500, 2.5)]    # needs-verification
def required_clearance_mm(v):
    return next(c for vmax, c in IPC2221_B2_MM if v <= vmax)
assert NETCLASS_CLEARANCE_MM["HV"] >= required_clearance_mm(V_WORKING_HV)
```

### 7.9 Ground bounce between power and sense grounds

- **Rule.** Return the sense and signal grounds to the shunt's low-side pad, or to
  a star point beside it, not to a distant power plane point.
- **Check.** `V = L·di/dt`. 10 nH with 10 A in 50 ns bounces the local ground by
  2 V. Assert one net-tie where the grounds join (1.6).
- **Class.** Net-tie count: automatic-in-board. Return path: manual-review.
- **Source.** Johnson and Graham, ground bounce. Analog Devices AN-202.

## 8. Battery

Cell sizing, swell, connectors, and charge-rate arithmetic are in `batteries.md`.
Protection posture is in `electronics.md` §6. This section lists the checks that
those files do not make.

### 8.1 Linear charger thermal

- **Rule.** A linear charger dissipates `(Vin − Vbat) × Ichg` plus quiescent loss.
  Assert the junction temperature below the part's thermal-regulation threshold at
  the worst corner, or accept and document the longer charge time that thermal
  regulation causes.
- **Gap.** The charger connects and passes. Thermal regulation silently lengthens
  the charge.
- **Check.** 5.25 V in, 3.0 V cell, 500 mA: 1.125 W. At 50 K/W that is a 56 K rise,
  96 °C at 40 °C ambient. Take the threshold from the datasheet.
- **Class.** automatic-in-design.py.
- **Source.** The charger datasheet's power dissipation and thermal regulation
  sections.

### 8.2 Protection thresholds against the system's

- **Rule.** Where a cell carries a PCM, the PCM's cutoffs must sit outside the
  charger's float and the system's own shutdown thresholds with margin. Where the
  cell is bare, the board needs its own protection (`electronics.md` §6).
- **Check.** Assert the order
  `V_pcm_uv + margin < V_uvlo_fall < V_fw_cutoff` and
  `V_charge_float + margin < V_pcm_ov`. If the PCM cuts off before the system
  turns itself off, the device dies without warning. Typical cutoffs are in
  `batteries.md` §4.
- **Class.** automatic-in-design.py.
- **Source.** The cell and PCM datasheets. IEC 62133-2 for cell safety.

### 8.3 Connector polarity and cell swell

Polarity of vendor pigtails is in `batteries.md` §5, and the swell allowance is in
`batteries.md` §3. The pipeline checks neither directly. For polarity, assert in
`design.py` that the connector's pin-to-net table matches the documented cell
polarity (automatic-in-design.py), and meter the pigtail before first mate
(manual-review). For swell, the case `verify()` asserts cavity depth against cell
thickness plus allowance.

### 8.4 Fuel gauge placement and sense resistor

- **Rule.** Follow the gauge datasheet's layout. For a coulomb-counting gauge,
  place the sense resistor in the battery path, take Kelvin traces to the gauge
  (7.2) with the filter the datasheet specifies, and keep them away from switching
  nodes. A voltage-model gauge needs a short, quiet sense to the cell terminals.
- **Check.** Offset error integrates. 10 µV of offset across 10 mΩ is a 1 mA error
  current, which is 24 mAh per day. Use the datasheet's offset figure.
- **Class.** Arithmetic: automatic-in-design.py. Routing: manual-review.
- **Source.** The gauge datasheet and its layout guide.

### 8.5 NTC placement and thresholds

- **Rule.** The thermistor must thermally touch the cell. A board-mounted NTC
  measures the board. Assert the divider voltage at each temperature threshold
  against the charger's comparator thresholds.
- **Check.** `R(T) = R25·exp(B·(1/T − 1/T25))`. For 10 kΩ and `B = 3380 K`, that is
  28.2 kΩ at 0 °C and 4.9 kΩ at 45 °C. The model differs from vendor tables by a
  few percent, so prefer the vendor's table at the thresholds. JEITA windows are
  typically 0 to 45 °C for full-rate charge (needs-verification of the guideline's
  current values).
- **Class.** automatic-in-design.py. Thermal contact: manual-review.
- **Source.** The charger datasheet's temperature-sense section. JEITA lithium
  charging guideline (needs-verification of document).

### 8.6 Termination current against system load

- **Rule.** Termination current must exceed the system's draw during charge, unless
  a power-path charger separates them.
- **Check.** A 500 mAh cell terminates at 0.1C = 50 mA. A system drawing 80 mA
  while charging never lets the charger see 50 mA, so the safety timer expires.
  Assert `I_term > I_system_charging` or declare a power-path part.
- **Class.** automatic-in-design.py.
- **Source.** The charger datasheet's termination section. `batteries.md` §6 for
  C-rate.

### 8.7 UVLO interactions and brown-out loops

- **Rule.** Assert that the loaded cell voltage at peak current stays above the
  regulator's falling UVLO threshold, and that the restart threshold is above the
  voltage after recovery under the restart load.
- **Check.** `V_cell = V_oc − I·(R_int + R_wire + R_pcm_fet)`. 1 A through 0.2 Ω
  drops 0.2 V. A radio burst that pulls the cell below UVLO resets the device,
  the cell recovers, and it restarts into the same burst, looping. The dropout
  check at end of discharge is in `electronics.md` §5.
- **Class.** automatic-in-design.py.
- **Source.** The regulator datasheet's UVLO thresholds and hysteresis.

### 8.8 Reverse current when VBUS is absent

- **Rule.** List every path from the cell to the external supply connector with the
  supply absent. Assert a blocking element on each.
- **Gap.** A charger's input pin or body diode can leak from the cell toward the
  connector. Connectivity is fine in every gate.
- **Check.** Keep a `REVERSE_PATHS` table in `design.py`: path, blocking element.
  Assert none is empty. Where a battery and USB feed one rail, use an ideal-diode
  controller or a diode, and include its drop in the headroom arithmetic. A USB
  sink must not drive VBUS (needs-verification of the specification clause).
- **Class.** Table completeness: automatic-in-design.py. Leakage: manual-review
  (measure with the supply absent).
- **Source.** The charger datasheet (reverse leakage). USB 2.0 and USB Type-C
  specifications for VBUS backdrive.

### 8.9 Shipping mode and shelf current

- **Rule.** Define how the device disconnects the cell for shipping and storage,
  and how it wakes. Assert that the shelf current over the shelf time costs under
  10 % of capacity.
- **Check.** 100 µA over 6 months (4380 h) is 438 mAh, which empties a 500 mAh
  cell below the PCM undervoltage cutoff and can ruin it. 20 µA over the same time
  is 88 mAh. Many chargers include a battery-disconnect FET with a ship mode.
- **Class.** automatic-in-design.py.
- **Source.** The charger datasheet's ship-mode section. `batteries.md` §4.

## 9. Connectors and ESD (cross-domain)

Per-interface pinout, protection parts, and mating geometry are in
`interfaces.md`. This section states only the rules that apply to every external
connector.

### 9.1 Every external pin has a stated ESD path

- **Rule.** Choose a target level from IEC 61000-4-2. List every net that leaves
  the board through a connector, with its protection element, its return path, and
  the element's stand-off and clamp voltages.

  | Level | Contact discharge | Air discharge |
  |---|---|---|
  | 1 | ±2 kV | ±2 kV |
  | 2 | ±4 kV | ±4 kV |
  | 3 | ±6 kV | ±8 kV |
  | 4 | ±8 kV | ±15 kV |

  The test pulse at 8 kV contact peaks near 30 A (3.75 A/kV, needs-verification),
  with a rise time under 1 ns, from a 150 pF capacitor through 330 Ω.
- **Gap.** An unprotected data pin passes every gate.
- **Check.** An `EXTERNAL_PINS` table in `design.py`, derived from the connector
  pad-to-net maps. Assert that each net appears with a protection element. The
  clamp voltage at the standard's pulse must stay below the downstream part's
  absolute maximum (datasheet transcription).
- **Class.** Table completeness: automatic-in-design.py. Clamp margin:
  manual-review.
- **Source.** IEC 61000-4-2 "Electromagnetic compatibility (EMC), Part 4-2:
  Testing and measurement techniques, Electrostatic discharge immunity test"
  (levels confirmed against secondary summaries, not the standard's text).

```python
EXTERNAL_PINS = {"USB_DP": "TVS1", "USB_DM": "TVS1", "VBUS": "TVS2", "GPIO_EXT": "R_SERIES+TVS3"}
for net in nets_on_connectors(INSTANCES, CONNECTOR_REFS):
    assert net in EXTERNAL_PINS or net in GND_NETS, "%s has no ESD element" % net
```

### 9.2 TVS placement and return

- **Rule.** Put the TVS within a stated distance of the connector pin (start from
  5 mm and justify any larger value), as the first element on the path. Route the
  signal to the TVS pad and onward, without a stub. Tie the TVS ground to the plane
  with a via at its pad. Place the protected part farther from the TVS than the TVS
  is from the connector, and route no unprotected circuit between the connector and
  the TVS.
- **Check.** Inductive overshoot `L·di/dt`: 1 nH per mm of trace over 5 mm is
  5 nH. At 30 A in 1 ns that is 150 V on top of the clamp. Assert the connector
  to TVS distance and the TVS ground via distance from the board.
- **Class.** automatic-in-board.
- **Source.** Texas Instruments SLVA680 "ESD Protection Layout Guide" (the placement
  and inductance guidance was confirmed by search summary; the document text was
  not read).

### 9.3 Cable shield termination

- **Rule.** State, per cable, how the shield terminates: 360-degree bond to chassis
  at the connector, a pigtail, a capacitor to ground, or one end only. Declare a
  separate `SHIELD` net and assert its tie to ground.
- **Check.** A pigtail adds inductance at about 1 nH per mm of wire
  (needs-verification against Ott). 25 mm is 25 nH, which is 15.7 Ω at 100 MHz, so a
  pigtail defeats RF shielding. A 360-degree bond to chassis at the connector
  serves radio frequencies. A capacitor to ground at the far end breaks DC ground
  loops and still passes RF. For audio, bond the shield to chassis at the connector
  rather than to signal ground.
- **Class.** Net declared and tied: automatic-in-design.py. Mechanical
  termination: manual-review.
- **Source.** Ott, "Electromagnetic Compatibility Engineering", cable shielding
  and grounding chapters (needs-verification of chapter). Analog Devices MT-095
  (needs-verification). AES48 (needs-verification).

### 9.4 Hot-plug transients

- **Rule.** Cable inductance with a low-ESR input capacitor rings when a live
  supply is plugged in. Assert that the supply's input absolute maximum, and the
  TVS stand-off, exceed twice the step.
- **Check.** An unprotected ceramic input can ring to about twice the input step.
  A 12 V plug gives 24 V against a 20 V part. A 5 V USB plug gives 10 V. Damp with
  an electrolytic capacitor or a series resistor with the ceramic, or clamp. Use
  connectors with ground pins that mate first.
- **Class.** automatic-in-design.py.
- **Source.** Linear Technology AN88 "Ceramic Input Capacitors Can Cause
  Overvoltage Transients" (Perica, March 2001, confirmed by search summary;
  text not read).

```python
assert 2.0 * VIN_PLUG_MAX_V <= INPUT_ABS_MAX_V or DAMPING_PRESENT, "hot-plug ring %.0f V" % (2 * VIN_PLUG_MAX_V)
```

### 9.5 Series elements

- **Rule.** Series resistors or beads on external lines limit clamp current and
  slow edges. Assert the clamp current and the edge time against the protocol, as
  in `electronics.md` §3. Use pulse-rated resistors where an ESD current can pass
  through them. A common-mode choke on a differential cable pair is part of the
  signal path and needs the impedance and bandwidth of 3.1. A ferrite bead's
  impedance falls under DC bias, so check the datasheet's bias curve.
- **Class.** automatic-in-design.py.
- **Source.** `electronics.md` §3. The bead and choke datasheets.

### 9.6 The cable as an antenna

- **Rule.** Common-mode current on a cable radiates. Assert nothing about it
  numerically in design; limit its sources: keep noisy ground away from the
  connector, filter digital edges before they reach the connector, bond the
  shield, and fit a common-mode choke or ferrite on a cable that needs it.
- **Check.** Radiated field from a short cable's common-mode current is
  `E = 1.26e-6 × f × L × I / d` (volts per metre, with `f` in Hz, `L` and `d` in
  metres, `I` in amperes; needs-verification of the factor and its range). At
  100 MHz, 1 m of cable, and `d = 3 m`, a limit of 100 µV/m (40 dBµV/m, the Class B
  limit from 30 to 88 MHz in the United States, needs-verification) allows
  `I = 100 µV/m × 3 / (1.26e-6 × 1e8 × 1)` = 2.4 µA. A few microamperes of
  common-mode current is enough to fail.
- **Class.** manual-review (pre-compliance scan with a current probe, then a
  radiated scan).
- **Source.** Ott, "Electromagnetic Compatibility Engineering", cable emissions.
  Paul, "Introduction to Electromagnetic Compatibility". 47 CFR 15.109 and
  CISPR 32 for the limits.

## 10. What runs automatically today

The pipeline's own checks are ERC, DRC at error severity with schematic parity, the
unconnected count, `kicad_fpcheck.py`, `kicad_silkcheck.py`, `kicad_schrules.py`,
`kicad_ifcheck.py`, the fit contract (`kicad_geom.py --contract`), the case `verify()`,
and whatever a project's `design.py` asserts. "Automatically today" below means
those, and only those. Entries marked "if written" are checks this file specifies
and that run only after a project writes them; the pipeline ships none of them.

| Domain | Checks that run automatically today | Checks still manual |
|---|---|---|
| 1. Analog and audio | `design.py` assertions if written: bias window at both rails, noise sum, supply filter attenuation, coupling corners and phase spread, input pole, symmetry pairs. ERC and parity for the net split of the guard and return nets. A capacitor to ground on every IC power pin's net, and a pull-up inside a fixed per-class window on I2C (1 kΩ to 10 kΩ) and reset (4.7 kΩ to 100 kΩ) nets (`kicad_schrules.py`, defaults in `templates/sch-rules.json`; not the UM10204 rise-time window of 3.8). | Datasheet curve transcription (PSRR, EMIRR), guard continuity and cleaning, return-path trace, op-amp stability simulation, leakage on silicon. |
| 2. Power conversion | `design.py` assertions if written: inductor `Ipk` against `Isat`, divider window, LDO dissipation, IPC-2221 widths, hot-plug and inrush, negative-impedance margin, TVS and fuse arithmetic. DRC enforces any clearance a project configures. | Hot-loop distance and via-free loop, switch-node area, via count under the thermal pad, inductor orientation, `θ` on the real board, part curves, IPC-2152 check where IPC-2221 fails. Board-side checks are possible with a script and are not shipped. |
| 3. Digital and high-speed | `design.py` assertions if written: impedance width by two methods, skew budgets, strap table, crystal load arithmetic, the I2C pull-up window from bus capacitance and speed mode (3.8), unused-pin table, termination length. `kicad_schrules.py` checks only that each I2C and reset pull-up sits in its fixed class window. DRC enforces a length or skew rule only if a custom rule is written. | Fab solver confirmation, plane-split crossings, decoupling distance, crystal keep-out, reset timing on silicon, vendor skew limits. |
| 4. RF | `design.py` assertions if written: width, stitching pitch against wavelength, keep-out constants, harmonic arithmetic. DRC enforces a keep-out only if the generator emits a rule area. | Antenna keep-out content from the vendor drawing, match tuning with a VNA, launch quality, ground continuity under the trace, regulatory measurement, enclosure effect on the antenna. |
| 5. Mixed-signal | `design.py` assertions if written: jitter SNR, reference noise, anti-alias attenuation, settling and kickback, single-ground assertion. | Analog-region crossings (script), reference routing, return-path review, noise measurement. |
| 6. Sensors and MEMS | `design.py` assertions if written: Helmholtz arithmetic, axis mapping, MSL table completeness. `kicad_fpcheck.py` covers pad geometry of the sensor's package only. Case `verify()` for enclosure geometry once the project adds a port check. | Port hole alignment (script), seal quality, thermal gradient, assembly process fit to MSL and wash restrictions, orientation on silicon. |
| 7. Motor and high current | `design.py` assertions if written: Miller spike, dead time, regeneration voltage, ripple current, switch temperature, via count, configured clearance against IPC-2221 Table 6-1. DRC enforces the configured clearance. | Gate-loop geometry, Kelvin pad attachment, scope confirmation of dead time, mains isolation review, ground-bounce measurement. |
| 8. Battery | `design.py` assertions if written: charger dissipation, threshold ordering, termination against load, UVLO and sag, shelf current, polarity table, reverse-path table. Case `verify()` for cell cavity depth. | Pigtail polarity metering, NTC contact, fuel gauge routing, reverse leakage measurement, charge behaviour on a real cell. |
| 9. Connectors and ESD | `design.py` assertion if written: every connector net appears in the ESD table, hot-plug margin, shield net declared. A fuse, bead, shunt TVS or zener (cathode on the input), series diode (anode on the input) or series resistor of at most `max_series_ohms` into a rail on each connector power-input net, by net name (`kicad_schrules.py`). | TVS distance (script not shipped), clamp margin against absolute maximum, shield termination hardware, pre-compliance ESD and emissions scans. |

Five of the nine rows depend on a board-side script that reads geometry from the
`.kicad_pcb`. The parser in `scripts/kicad_geom.py` already reads placements,
holes, and vias. Reading track segments, pad positions, and zone polygons for the
checks above is the work to add.

## Appendix: source verification status

Sources read in full or in the relevant tables while writing this file:

| Source | Use |
|---|---|
| NXP UM10204 Rev. 7.0 | I2C Table 10, Table 11, §7.1 (rise time, `Cb`, `Rp` formulas). |
| `hypercardiod_mic/kicad/design.py` | `_bias_arithmetic()`, `_selfcheck()`, `signal_phase_spread_deg()`, `_hz()`. |

Sources whose identity and a stated claim were confirmed by search results, with
the document text not read: Analog Devices MT-031 (title, authors, and the rule
that `DGND` joins `AGND` at the package), MT-007 (title, jitter formula), AN-202
(title, author); Texas Instruments SLUA618A, SLVA477B (ripple formula), SCBA004,
SLVA680, SPRA953; Linear Technology AN88; IEC 61000-4-2 levels; IPC-2221 formula
and constants; IPC-2141 microstrip formula and validity range; Microchip AN826 and
STMicroelectronics AN2867 (titles).

Every other citation is from the author's knowledge and carries either a document
number the author is confident of or a `(needs-verification)` marker.
