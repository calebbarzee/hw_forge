#!/usr/bin/env python3
"""Check a schematic against the design rules ERC does not cover.

ERC proves a schematic is electrically consistent. It does not notice a supply
pin with no decoupling capacitor, a rail with no bulk capacitance, an I2C bus
with no pull-up, or a connector that brings in power with nothing in front of
it. This script exports the netlist with

    kicad-cli sch export netlist --format kicadxml

and runs five rules over it:

  decoupling_present          every power_in pin of a U or IC part, and the
                              power pins of addressable LEDs (matched by value
                              pattern), has a capacitor to ground on its net
  bulk_capacitance            each supply rail carries at least a stated total
                              capacitance to ground
  led_data_series_resistor    the first addressable LED of a chain has a series
                              resistor on its data input.  When addressable
                              LEDs exist but no pin matches
                              patterns.led_data_in_pin, nothing was checked
                              and the rule reports SKIP, not ok.
  open_drain_pullups          I2C and reset nets carry a pull-up to a supply
                              rail, inside a resistance window per net class
                              (defaults: i2c 1 k to 10 k, reset 4.7 k to
                              100 k; `classes` in templates/sch-rules.json)
  connector_input_protection  a connector power-input net carries a fuse, a
                              series inductor or bead, a shunt TVS or zener
                              (cathode on the input, anode on ground), a
                              series diode (anode on the input, cathode on
                              the far net, such as a reverse-polarity
                              Schottky), or a series resistor of at most
                              max_series_ohms into a power rail (warning
                              severity by default).  A divider's top leg or
                              a diode fitted backwards does not count.

A part marked do-not-populate (the netlist's `dnp` property) is not fitted, so
no rule counts it: its pins are dropped from every net before any rule runs,
and the report says how many DNP parts were excluded.

    python3 scripts/kicad_schrules.py SCHEMATIC.kicad_sch [--json]
        [--rules FILE] [--set RULE.KEY=VALUE ...] [--netlist EXISTING.xml]
    python3 scripts/kicad_schrules.py --selftest

Exit code: 0 when no error-severity finding exists (warnings do not fail), 1
when one does, 2 when the tool or the input failed (no kicad-cli, no such
file, bad configuration). Output is one block per rule, then one line per
finding with its severity, the symbols and the nets involved. `--json` prints
the same as one JSON document on stdout.

Configuration.  The defaults are `templates/sch-rules.json`, beside this
script's directory, and the file documents every key in its `_doc` object. A
project copies the file, keeps the keys it changes, and passes it as
`--rules FILE`; the file is merged over the defaults. `--set RULE.KEY=VALUE`
overrides one key after that, for example

    --set bulk_capacitance.min_farads=4u7
    --set decoupling_present.severity=warning
    --set patterns.open_drain='^(SDA|SCL|RST)$'

RULE is a rule name, or `patterns` or `prefixes`. VALUE is read as JSON when it
parses (numbers, true, lists) and as a plain string otherwise. An unknown rule
or key is an error, so a typo cannot disable a check.

Waivers.  Each rule takes `waive`, a list of {"match": REGEX, "reason": TEXT}.
A finding is waived when the regex matches any symbol reference or net name it
names. The reason is required. A waived finding is printed with its reason and
does not count toward the exit code. This is the rejection table of
`references/electronics.md` section 6 in machine form: the design decided
against a part (no bulk capacitor on a raw input, no reset pull-up under a
module that carries one) and the check records why.

Limits, stated so a clean run is not over-read.

  * Every rule works on connectivity. Nothing here sees placement, so a
    capacitor counts when it is on the net, not when it is near the pin, and
    one capacitor on a rail satisfies every pin on that rail. Distance is a
    board-side check (DRC `decoupling_distance`, `domains.md` 3.4).
  * A capacitor or resistor is a two-pin part whose reference prefix matches
    `prefixes.capacitor` or `prefixes.resistor`. A network or a multi-pin part
    is not seen.
  * Pin electrical types come from the netlist. A supply pin typed passive is
    not a power input, so it is not checked (`schematic-engineer.md` gate 5).
  * Power symbols (GND, PWR_FLAG) are not components in the netlist, so ground
    is recognised by net name (`patterns.ground_net`).
  * A net named /sheet/NAME is matched by NAME, so hierarchical sheets work.

Capacitance and resistance are read from the Value field: "100n", "100nF",
"4u7", "4.7uF", "4,7uF" (a comma between digits is a decimal separator),
"10k", "4k7", "1R0", and values with a rating, a dielectric or a size code
beside them such as "100u/25V", "220n/X7R", "10uF 16V" or "0603 100n".  A
token that carries an SI prefix or a unit wins over a bare number, so a size
code (0603), a dielectric (X7R) or a voltage rating (25V) is never the value
when another token has a unit, and "10u 1" is 10 uF, not 10.1 uF.  A bare
number is ohms for a resistor but not a capacitance: a capacitor whose value
has no unit is reported as an unparseable WARN by bulk_capacitance and is not
counted.  `--selftest` runs the parser's cases and every rule against a small
synthetic netlist, with no KiCad needed; it passes under the system
interpreter and KiCad's bundled one.

Source.  The rule set, the regex-driven configuration and the value parser are
ported from `tools/ai_pipeline/sch_rules.py` in the author's KiCad fork, which
is not upstream KiCad code. Changes from it: rule names
`led_data_series_resistor` (was series_resistor_on_led_data),
`open_drain_pullups` (was pullups_on_open_drain) and
`connector_input_protection` (was power_input_protection); the placeholder rule
single_pin_nets_excluded is dropped, ERC covers it; kicad-cli is found through
`_kicad_env.find_cli`; the ERC-shaped report file is replaced by `--json`; the
value parser accepts a rating after the value; net names match by last path
segment; a data-line resistor to ground or to a supply no longer counts as a
series resistor; a chain whose first LED sits behind an inter-LED resistor is
not misread; bulk_capacitance also covers rails found by a power_in pin;
waivers, `--set` and key validation are new. The principle and citation lines
in each rule's docstring are carried over from the source and have not been
re-verified here.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _kicad_env import cli_version, find_cli, run  # noqa: E402

# ------------------------------------------------------------ named constants

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES = os.path.join(os.path.dirname(HERE), "templates",
                             "sch-rules.json")

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_TOOL = 2

SEVERITIES = ("error", "warning")

SI_PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
             "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "R": 1.0,
             "F": 1.0}


def die(message):
    """Print an error and exit EXIT_TOOL. SystemExit(str) would exit 1,
    which this script reserves for a failed gate."""
    sys.stderr.write("error: %s\n" % message)
    sys.exit(EXIT_TOOL)


# ----------------------------------------------------------------- utilities

# A whitespace-separated unit that belongs to the number before it: the
# "uF" of "10 uF", the "ohm" of "100 ohm".
_UNIT_TOKEN = re.compile(r"^(?:[pnuµμmkKMR]|[pnuµμmkKM]?(?:[Ff]|[Ff]arads?"
                         r"|[Oo]hms?|Ω))$")


def _parse_token(t, unit):
    """(value in base units, carries a unit) for one token, or None.

    "Carries a unit" means an SI prefix, an R/k-style infix, or a unit
    suffix: the evidence that the token is a value and not a size code.
    """
    if unit == "F":
        stripped = re.sub(r"(farads?|f)$", "", t, flags=re.IGNORECASE)
    else:
        stripped = re.sub(r"(ohms?|Ω)$", "", t, flags=re.IGNORECASE)
    suffix = stripped != t
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([pnuµμmkKMR]?)", stripped)
    if m:
        return (float(m.group(1)) * SI_PREFIX[m.group(2)],
                suffix or bool(m.group(2)))
    m = re.fullmatch(r"(\d+)([pnuµμmkKMR])(\d+)", stripped)  # 4u7, 4k7, 1R0
    if m:
        return (float("%s.%s" % (m.group(1), m.group(3)))
                * SI_PREFIX[m.group(2)], True)
    return None


def _tokens(segment):
    """Split on whitespace, rejoining a number with the unit after it."""
    raw, out, i = segment.split(), [], 0
    while i < len(raw):
        tok = raw[i]
        if (i + 1 < len(raw) and re.fullmatch(r"\d+(?:\.\d+)?", tok)
                and _UNIT_TOKEN.match(raw[i + 1])):
            tok += raw[i + 1]
            i += 1
        out.append(tok)
        i += 1
    return out


def parse_value(text, unit):
    """Parse a component value into a float in base units, or None.

    Accepts "100n", "100nF", "4.7uF", "4,7uF", "0.1uF", "4u7", "10k", "4k7",
    "1M", "1R0", "10 uF", and a rating, dielectric or size code beside the
    value: "100u/25V", "220n/X7R", "10uF 16V", "0603 100n".  The first token
    that carries a unit is the value; a bare number ("470") is used only when
    no token carries one, and only for a resistance (`unit` "R"): a bare
    number is not a capacitance.  Returns None when the text does not look
    like a value.  `unit` is "F" or "R".
    """
    if text is None:
        return None
    # European notation: a comma between digits is the decimal separator.
    text = re.sub(r"(?<=\d),(?=\d)", ".", text.strip())
    bare = None
    for segment in re.split(r"[/,;]", text):
        for token in _tokens(segment):
            got = _parse_token(token, unit)
            if got is None:
                continue
            if got[1]:
                return got[0]
            if bare is None:
                bare = got[0]
    return bare if unit == "R" else None


def as_number(x, unit):
    """A config number: a float, or a string with a unit such as "4u7"."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    return parse_value(x, unit) if isinstance(x, str) else None


def fmt_si(value, unit):
    """Format a float with an SI prefix: 1.1e-5 F gives "11 uF"."""
    if value is None:
        return "?"
    for prefix, scale in (("M", 1e6), ("k", 1e3), ("", 1.0), ("m", 1e-3),
                          ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if abs(value) >= scale * 0.9999:
            return ("%.3g %s%s" % (value / scale, prefix, unit)).strip()
    return "0 %s" % unit


def ref_prefix(ref):
    """Letters before the first digit: "LED13" gives "LED"."""
    m = re.match(r"([A-Za-z_]+)", ref or "")
    return m.group(1) if m else (ref or "")


def short_name(name):
    """Last path segment of a net name: "/sheet/SDA" gives "SDA"."""
    return (name or "").rsplit("/", 1)[-1]


def matches(pattern, text):
    return bool(pattern) and text is not None \
        and re.search(pattern, text) is not None


def prefix_matches(patterns, prefix):
    """True when the reference prefix fully matches one of `patterns`.

    `patterns` is a regex string or a list of them, so "C[A-Z]*" covers C, CB
    and CF while "C" alone covers only C.
    """
    if isinstance(patterns, str):
        patterns = [patterns]
    return any(re.fullmatch(p, prefix) for p in patterns)


# ------------------------------------------------------------------- netlist

class Component:
    def __init__(self, ref, value, footprint, lib, part, fields):
        self.ref = ref
        self.value = value or ""
        self.footprint = footprint or ""
        self.lib = lib or ""
        self.part = part or ""
        self.fields = fields
        self.prefix = ref_prefix(ref)
        self.nodes = []
        self.dnp = False


class Node:
    def __init__(self, comp, pin, name, pintype, net):
        self.comp = comp
        self.pin = pin
        self.name = name
        self.pintype = pintype or ""
        self.net = net

    def label(self):
        return "%s.%s (%s)" % (self.comp.ref, self.pin, self.name or "-")


class Net:
    def __init__(self, name):
        self.name = name
        self.nodes = []


class Netlist:
    """The parsed kicadxml netlist.

    Shape, verified against KiCad 10.0.5: components/comp[@ref] with value,
    footprint, libsource[@lib,@part] and fields/field[@name];
    libparts/libpart/pins/pin[@num,@name,@type]; nets/net[@name]/node[@ref,
    @pin,@pinfunction,@pintype]. pinfunction is "<pin name>_<pin number>", so
    the pin name comes from the libpart and pinfunction is the fallback.

    A comp carrying <property name="dnp"/> is do-not-populate.  It is kept in
    `dnp` and left out of `components` and of every net's nodes, so no rule
    can count it as fitted.
    """

    def __init__(self, root):
        self.tool = (root.findtext("design/tool") or "").strip()
        self.components = {}
        self.dnp = {}
        self.nets = {}
        self.libparts = {}
        for lp in root.iter("libpart"):
            pins = {}
            for p in lp.iter("pin"):
                pins[p.get("num")] = (p.get("name") or "", p.get("type") or "")
            self.libparts[(lp.get("lib"), lp.get("part"))] = pins
        for c in root.iter("comp"):
            ls = c.find("libsource")
            fields = {}
            for f in c.iter("field"):
                fields[f.get("name")] = (f.text or "").strip()
            comp = Component(
                c.get("ref"), (c.findtext("value") or "").strip(),
                (c.findtext("footprint") or "").strip(),
                ls.get("lib") if ls is not None else "",
                ls.get("part") if ls is not None else "", fields)
            comp.dnp = any(
                p.get("name") == "dnp"
                and (p.get("value") or "yes").lower() not in ("no", "false",
                                                              "0")
                for p in c.findall("property"))
            if comp.dnp:
                self.dnp[comp.ref] = comp
                continue
            self.components[comp.ref] = comp
        for n in root.iter("net"):
            net = Net(n.get("name"))
            for nd in n.iter("node"):
                comp = self.components.get(nd.get("ref"))
                if comp is None:
                    continue
                pin = nd.get("pin")
                name = self.pin_name(comp, pin, nd.get("pinfunction"))
                node = Node(comp, pin, name, nd.get("pintype"), net)
                net.nodes.append(node)
                comp.nodes.append(node)
            self.nets[net.name] = net

    def pin_name(self, comp, pin, pinfunction):
        """Libpart pin name, else pinfunction without its "_<num>" suffix."""
        pins = self.libparts.get((comp.lib, comp.part), {})
        if pin in pins and pins[pin][0]:
            return pins[pin][0]
        if pinfunction:
            suffix = "_%s" % pin
            if pinfunction.endswith(suffix) and len(pinfunction) > len(suffix):
                return pinfunction[:-len(suffix)]
            return pinfunction
        return ""

    def by_prefix(self, prefixes):
        return [c for c in self.components.values()
                if prefix_matches(prefixes, c.prefix)]


def export_netlist(cli, sch, out_xml):
    proc = run([cli, "sch", "export", "netlist", "--format", "kicadxml",
                "-o", out_xml, sch])
    if proc.returncode != 0 or not os.path.exists(out_xml):
        tail = [l for l in ((proc.stderr or "") + "\n"
                            + (proc.stdout or "")).splitlines() if l.strip()]
        die("netlist export failed (kicad-cli exit %d)\n  %s"
            % (proc.returncode, "\n  ".join(tail[-3:])))


# ------------------------------------------------------------------ findings

class Finding:
    def __init__(self, rule, severity, message, symbols, nets):
        self.rule = rule
        self.severity = severity
        self.message = message
        self.symbols = sorted(set(symbols))
        self.nets = sorted(set(nets))
        self.waived = None              # the waiver's reason, when waived

    def to_json(self):
        d = {"severity": self.severity, "message": self.message,
             "symbols": self.symbols, "nets": self.nets}
        if self.waived is not None:
            d["waived"] = self.waived
        return d

    def subjects(self):
        return self.symbols + self.nets


class Context:
    """The netlist plus the merged configuration, with the shared lookups."""

    def __init__(self, netlist, config):
        self.nl = netlist
        self.cfg = config
        self.pat = config["patterns"]
        self.pre = config["prefixes"]

    def rule(self, name):
        return self.cfg["rules"][name]

    def net_is(self, key, net):
        return matches(self.pat[key], short_name(net.name))

    def is_ground_net(self, net):
        return self.net_is("ground_net", net)

    def supply_pins(self, net, pin_types=("power_in",)):
        """Nodes on `net` that are a non-ground power input."""
        if self.is_ground_net(net):
            return []
        return [n for n in net.nodes
                if n.pintype.startswith(tuple(pin_types))
                and not matches(self.pat["ground_pin"], n.name)]

    def is_power_net(self, net):
        """A supply rail: by name, by a power_out pin, or by a supply pin."""
        if self.is_ground_net(net):
            return False
        return (self.net_is("power_net", net)
                or any(n.pintype.startswith("power_out") for n in net.nodes)
                or bool(self.supply_pins(net)))

    def two_pin_to(self, net, prefix, predicate):
        """Two-pin parts with `prefix` on `net` whose far net satisfies
        `predicate`. Returns (component, far_net) pairs."""
        out = []
        for node in net.nodes:
            comp = node.comp
            if not prefix_matches(prefix, comp.prefix) or len(comp.nodes) != 2:
                continue
            far = [n for n in comp.nodes if n is not node][0].net
            if far is not net and predicate(far):
                out.append((comp, far))
        return out

    def is_addressable_led(self, comp):
        p = self.pat["addressable_led"]
        return (matches(p, comp.value) or matches(p, comp.footprint)
                or matches(p, comp.part))


# --------------------------------------------------------------------- rules

def rule_decoupling_present(ctx):
    """Every IC power-input pin has a capacitor from its net to ground.

    Principle: each supply pin of a digital IC needs a local decoupling
    capacitor between that supply and ground. Source, as cited in the fork's
    sch_rules.py: Texas Instruments application report SLVA640 "Decoupling
    techniques"; Nordic nRF52840 PS reference circuitry; SK6812MINI-E
    datasheet application circuit. Addressable LEDs are checked only when
    their value, footprint or library part matches patterns.addressable_led
    and the pin is named by led_power_pin_names. Pins of one part on one net
    are reported together.
    """
    r = ctx.rule("decoupling_present")
    pin_types = tuple(r["power_pin_types"])
    led_prefixes = r["led_prefixes"]
    targets = ctx.nl.by_prefix(r["prefixes"])
    for comp in ctx.nl.by_prefix(led_prefixes):
        if ctx.is_addressable_led(comp) and comp not in targets:
            targets.append(comp)
    checked = 0
    bad = {}                                 # (ref, net name) -> [nodes]
    for comp in sorted(targets, key=lambda c: c.ref):
        is_led = prefix_matches(led_prefixes, comp.prefix) \
            and ctx.is_addressable_led(comp)
        for node in comp.nodes:
            if node not in ctx.supply_pins(node.net, pin_types):
                continue
            if is_led and not matches(r["led_power_pin_names"], node.name):
                continue
            checked += 1
            if not ctx.two_pin_to(node.net, ctx.pre["capacitor"],
                                  ctx.is_ground_net):
                bad.setdefault((comp.ref, node.net.name), []).append(node)
    out = []
    for (ref, net_name), nodes in sorted(bad.items()):
        pins = ", ".join("%s (%s)" % (n.pin, n.name or "-") for n in nodes)
        out.append(Finding(
            "decoupling_present", r["severity"],
            "Power input pin %s of %s on net '%s' has no capacitor to ground"
            % (pins, ref, net_name), [ref], [net_name]))
    return out, "%d power pin(s) checked" % checked


def _bulk_nets(ctx, r):
    """(nets, findings for named nets that do not exist)."""
    names = r["nets"]
    if names:
        missing = [n for n in names if n not in ctx.nl.nets]
        return [ctx.nl.nets[n] for n in names if n in ctx.nl.nets], missing
    nets = []
    for net in ctx.nl.nets.values():
        if ctx.is_ground_net(net):
            continue
        if matches(r["net_pattern"], short_name(net.name)):
            nets.append(net)
        elif r["include_power_out_nets"] and any(
                n.pintype.startswith("power_out") for n in net.nodes):
            nets.append(net)
        elif r["include_power_in_nets"] and ctx.supply_pins(net) \
                and not ctx.net_is("vin_net", net):
            nets.append(net)
    return nets, []


def rule_bulk_capacitance(ctx):
    """Total capacitance to ground on each supply rail meets a minimum.

    Principle: a regulator or module output needs bulk capacitance at the load
    for transient current. Source, as cited in the fork's sch_rules.py: the
    ME6217 datasheet asks 1 uF minimum output capacitance; Adafruit NeoPixel
    Uberguide ("add a capacitor across the power supply"). Rails are the
    configured list, else names matching net_pattern, nets driven by a
    power_out pin, and nets feeding a non-ground power_in pin (raw input nets,
    patterns.vin_net, excepted).
    """
    r = ctx.rule("bulk_capacitance")
    minimum = as_number(r["min_farads"], "F")
    nets, missing = _bulk_nets(ctx, r)
    out = []
    notes = []
    for name in missing:
        out.append(Finding("bulk_capacitance", r["severity"],
                           "Named rail '%s' is not in the netlist" % name,
                           [], [name]))
    warned = set()
    for net in sorted(nets, key=lambda n: n.name):
        total = 0.0
        unparsed = []
        caps = ctx.two_pin_to(net, ctx.pre["capacitor"], ctx.is_ground_net)
        for cap, _far in caps:
            v = parse_value(cap.value, "F")
            if v is None:
                unparsed.append(cap.ref)
                if cap.ref not in warned:
                    # A warning whatever the rule's severity: the value is
                    # unknown, which is neither a pass nor a proven failure.
                    warned.add(cap.ref)
                    out.append(Finding(
                        "bulk_capacitance", "warning",
                        "Capacitor %s value %r is unparseable as a "
                        "capacitance (a bare number has no unit); not counted"
                        % (cap.ref, cap.value), [cap.ref], [net.name]))
            else:
                total += v
        notes.append("%s=%s" % (net.name, fmt_si(total, "F")))
        if total < minimum:
            msg = ("Net '%s' has %s of capacitance to ground, %s required"
                   % (net.name, fmt_si(total, "F"), fmt_si(minimum, "F")))
            if unparsed:
                msg += " (unparsed values on %s)" % ", ".join(unparsed)
            drivers = [n.comp.ref for n in net.nodes
                       if n.pintype.startswith("power_out")][:1]
            out.append(Finding("bulk_capacitance", r["severity"], msg,
                               drivers + [c.ref for c, _ in caps],
                               [net.name]))
    return out, ", ".join(notes) if notes else "no supply rails found"


def rule_led_data_series_resistor(ctx):
    """The first addressable LED's data input is driven through a resistor.

    Principle: a series resistor of a few hundred ohms between the driver and
    the first pixel damps ringing and limits current when the LED is
    unpowered. Source, as cited in the fork's sch_rules.py: Adafruit NeoPixel
    Uberguide best practices (300 to 500 ohm); WorldSemi WS2812B datasheet
    application note. The resistor's far net must reach a signal pin of a
    driver part: a resistor to ground or to a supply is not in series.
    """
    r = ctx.rule("led_data_series_resistor")
    res = ctx.pre["resistor"]
    drivers = r["driver_prefixes"]

    def is_driver_net(far):
        if ctx.is_ground_net(far) or ctx.is_power_net(far):
            return False
        return any(prefix_matches(drivers, n.comp.prefix)
                   and not n.pintype.startswith("power") for n in far.nodes)

    def led_out(n):
        return ctx.is_addressable_led(n.comp) \
            and matches(ctx.pat["led_data_out_pin"], n.name)

    def has_upstream_led(comp, net):
        if any(n.comp is not comp and led_out(n) for n in net.nodes):
            return True
        return any(any(led_out(n) for n in far.nodes)
                   for _c, far in ctx.two_pin_to(net, res, lambda f: True))

    out = []
    firsts = leds = data_in = 0
    for comp in sorted(ctx.nl.components.values(), key=lambda c: c.ref):
        if not ctx.is_addressable_led(comp):
            continue
        leds += 1
        for node in comp.nodes:
            if not matches(ctx.pat["led_data_in_pin"], node.name):
                continue
            data_in += 1
            if has_upstream_led(comp, node.net):
                continue                          # not the first of a chain
            firsts += 1
            if ctx.two_pin_to(node.net, res, is_driver_net):
                continue
            direct = [n for n in node.net.nodes
                      if prefix_matches(drivers, n.comp.prefix)]
            out.append(Finding(
                "led_data_series_resistor", r["severity"],
                "First LED %s data input %s on net '%s' has no series "
                "resistor to its driver" % (comp.ref, node.name,
                                            node.net.name),
                [comp.ref] + [n.comp.ref for n in direct], [node.net.name]))
    if leds and not data_in:
        # LEDs exist but none has a pin the pattern names: nothing was
        # checked, which must not read as a pass.
        return out, ("%d addressable LED(s), no pin matches "
                     "patterns.led_data_in_pin" % leds), True
    if not leds:
        return out, "no addressable LED"
    return out, "%d chain start(s)" % firsts


def pullup_window(r, net):
    """(class name, lo, hi) for one net: the first entry of r["classes"]
    whose `match` regex hits the net name or a pin name on it, else the
    rule's own min_ohms/max_ohms as class "default"."""
    for name, cls in sorted((r.get("classes") or {}).items()):
        if matches(cls["match"], short_name(net.name)) or any(
                matches(cls["match"], x.name) for x in net.nodes):
            return (name, as_number(cls["min_ohms"], "R"),
                    as_number(cls["max_ohms"], "R"))
    return ("default", as_number(r["min_ohms"], "R"),
            as_number(r["max_ohms"], "R"))


def rule_open_drain_pullups(ctx):
    """Open-drain and reset nets have a pull-up resistor to a supply.

    Principle: I2C lines are open-drain and need a pull-up per bus; reset
    inputs need a defined idle level. Source, as cited in the fork's
    sch_rules.py: NXP UM10204 "I2C-bus specification and user manual"
    section 7.1; ST AN4661 reset circuitry. Skipped when no net or pin name
    matches patterns.open_drain.

    The window is a fixed range per net class (`classes`: i2c 1 k to 10 k,
    reset 4.7 k to 100 k by default), not the UM10204 rise-time window.
    That window depends on the bus capacitance and speed mode, which no
    netlist carries; references/domains.md 3.8 derives it as a design.py
    assertion.
    """
    r = ctx.rule("open_drain_pullups")
    pat = ctx.pat["open_drain"]
    nets = [n for n in ctx.nl.nets.values()
            if matches(pat, short_name(n.name))
            or any(matches(pat, x.name) for x in n.nodes)]
    if not nets:
        return [], "no matching nets, skipped"
    out = []
    for net in sorted(nets, key=lambda n: n.name):
        cls, lo, hi = pullup_window(r, net)
        pulls = ctx.two_pin_to(net, ctx.pre["resistor"], ctx.is_power_net)
        ok = [p for p, _ in pulls
              if parse_value(p.value, "R") is not None
              and lo <= parse_value(p.value, "R") <= hi]
        if ok:
            continue
        have = ", ".join("%s=%s" % (p.ref, p.value) for p, _ in pulls) \
            or "none"
        out.append(Finding(
            "open_drain_pullups", r["severity"],
            "Net '%s' (%s) has no pull-up resistor between %s and %s "
            "(found: %s)" % (net.name, cls, fmt_si(lo, "Ohm"),
                             fmt_si(hi, "Ohm"), have),
            [n.comp.ref for n in net.nodes], [net.name]))
    return out, "%d net(s) checked" % len(nets)


def diode_pin_role(node):
    """'K', 'A', 'bi' (one pin of a bidirectional TVS, named A1 or A2) or
    None, from the pin name the netlist's libpart gives.  A pin with no name
    falls back to the number, by KiCad's Device:D convention: pin 1 is K,
    pin 2 is A."""
    name = (node.name or "").strip().upper()
    if name in ("K", "CATHODE"):
        return "K"
    if name in ("A", "ANODE"):
        return "A"
    if re.fullmatch(r"A\d", name):
        return "bi"
    if name in ("", "~"):
        return {"1": "K", "2": "A"}.get(node.pin)
    return None


def rule_connector_input_protection(ctx):
    """Power-input connectors have a fuse, a TVS diode or a series element.

    Principle: an external supply or battery entering the board should meet
    overcurrent or transient protection. Source, as cited in the fork's
    sch_rules.py: IEC 61000-4-2 ESD immunity; USB-IF ESD guidance; ST AN4275
    on TVS selection. A warning by default, because a module often carries
    the protection (`electronics.md` section 6).

    What counts, so a part that merely touches the net does not:
      * a fuse, inductor or bead on the net (by reference prefix);
      * a shunt TVS or zener: a two-pin part with its cathode on the input
        net and its anode on ground, or a bidirectional TVS (pins A1/A2)
        with one pin on each; a part with more pins (a TVS array) needs a
        pin on the input and a pin on ground;
      * a series diode: anode on the input net, cathode on a net that is not
        ground;
      * a series resistor of at most max_series_ohms whose far net is a
        power rail (it has a power_in pin, or its name matches
        patterns.power_net).  A divider's top leg feeds a sense net, not a
        rail, and does not count.
    """
    r = ctx.rule("connector_input_protection")
    diode = ctx.pre["diode"]
    diode = [diode] if isinstance(diode, str) else list(diode)
    tvs_prefixes = diode + list(r["tvs_prefixes"])
    max_ohms = as_number(r["max_series_ohms"], "R")

    def is_rail(net):
        return not ctx.is_ground_net(net) and (
            ctx.net_is("power_net", net) or bool(ctx.supply_pins(net)))

    def shunt(n):
        """A TVS or zener from the input pin `n` to ground, fitted the right
        way round."""
        c = n.comp
        lib_part = "%s:%s" % (c.lib, c.part)
        if not ((prefix_matches(tvs_prefixes, c.prefix)
                 and (matches(ctx.pat["tvs_value"], c.value)
                      or matches(ctx.pat["tvs_value"], c.part)))
                or matches(r["shunt_diode_symbol"], lib_part)):
            return False
        grounded = [m for m in c.nodes
                    if m is not n and ctx.is_ground_net(m.net)]
        if not grounded:
            return False
        if len(c.nodes) != 2:
            return True
        return (diode_pin_role(n), diode_pin_role(grounded[0])) in (
            ("K", "A"), ("bi", "bi"))

    def series(n, net):
        """A two-pin diode (anode on the input) or a low-value resistor
        into a rail: a series element, not a shunt and not a divider."""
        c = n.comp
        if len(c.nodes) != 2:
            return False
        far_node = [m for m in c.nodes if m is not n][0]
        far = far_node.net
        if far is net or ctx.is_ground_net(far):
            return False
        if (prefix_matches(r["series_diode_prefixes"], c.prefix)
                or matches(r["series_diode_symbol"],
                           "%s:%s" % (c.lib, c.part))):
            return (diode_pin_role(n), diode_pin_role(far_node)) == ("A",
                                                                     "K")
        if prefix_matches(r["series_resistor_prefixes"], c.prefix):
            ohms = parse_value(c.value, "R")
            return (ohms is not None and max_ohms is not None
                    and ohms <= max_ohms and is_rail(far))
        return False
    out = []
    checked = 0
    seen = set()
    for comp in sorted(ctx.nl.by_prefix(r["connector_prefixes"]),
                       key=lambda c: c.ref):
        for node in comp.nodes:
            net = node.net
            if not ctx.net_is("vin_net", net) or net.name in seen:
                continue
            seen.add(net.name)
            checked += 1
            found = []
            for n in net.nodes:
                c = n.comp
                if prefix_matches(r["fuse_prefixes"], c.prefix) \
                        or prefix_matches(r["series_prefixes"], c.prefix):
                    found.append(c.ref)
                elif shunt(n):
                    found.append(c.ref)
                elif series(n, net):
                    found.append(c.ref)
            if not found:
                out.append(Finding(
                    "connector_input_protection", r["severity"],
                    "Power input net '%s' on %s has no fuse, bead, shunt "
                    "TVS or zener (cathode on the input), series diode "
                    "(anode on the input) or series resistor of at most %s "
                    "into a rail" % (net.name, comp.ref,
                                     fmt_si(max_ohms, "Ohm")),
                    [comp.ref], [net.name]))
    return out, "%d input net(s) checked" % checked


RULES = (
    ("decoupling_present", rule_decoupling_present),
    ("bulk_capacitance", rule_bulk_capacitance),
    ("led_data_series_resistor", rule_led_data_series_resistor),
    ("open_drain_pullups", rule_open_drain_pullups),
    ("connector_input_protection", rule_connector_input_protection),
)


# -------------------------------------------------------------- configuration

def _load_json(path, what):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        die("cannot read %s %s: %s" % (what, path, exc))


def merge(cfg, overlay, origin):
    """Merge `overlay` into `cfg` in place, refusing any key `cfg` lacks."""
    for key in overlay:
        if key.startswith("_"):
            continue
        if key not in ("prefixes", "patterns", "rules"):
            die("%s: unknown top-level key %r (want prefixes, patterns, "
                "rules)" % (origin, key))
    for section in ("prefixes", "patterns"):
        for key, val in (overlay.get(section) or {}).items():
            if key not in cfg[section]:
                die("%s: unknown key %s.%s (known: %s)" % (
                    origin, section, key, ", ".join(sorted(cfg[section]))))
            cfg[section][key] = val
    for name, params in (overlay.get("rules") or {}).items():
        if name not in cfg["rules"]:
            die("%s: unknown rule %r (known: %s)" % (
                origin, name, ", ".join(sorted(cfg["rules"]))))
        for key, val in params.items():
            if key not in cfg["rules"][name]:
                die("%s: unknown key %s.%s (known: %s)" % (
                    origin, name, key, ", ".join(sorted(cfg["rules"][name]))))
            cfg["rules"][name][key] = val


def parse_set(items):
    """['RULE.KEY=VALUE', ...] to an overlay dict."""
    overlay = {"prefixes": {}, "patterns": {}, "rules": {}}
    for item in items or []:
        if "=" not in item or "." not in item.split("=", 1)[0]:
            die("--set wants RULE.KEY=VALUE, got %r" % item)
        lhs, raw = item.split("=", 1)
        scope, key = lhs.split(".", 1)
        try:
            val = json.loads(raw)
        except ValueError:
            val = raw
        if scope in ("prefixes", "patterns"):
            overlay[scope][key] = val
        else:
            overlay["rules"].setdefault(scope, {})[key] = val
    return overlay


def validate(cfg):
    """Fail early on a bad severity, regex, number or waiver."""
    def check_regex(label, pattern):
        for p in ([pattern] if isinstance(pattern, str) else pattern):
            try:
                re.compile(p)
            except (re.error, TypeError) as exc:
                die("config: %s is not a valid regex (%s): %r"
                    % (label, exc, p))
    for section in ("prefixes", "patterns"):
        for key, val in cfg[section].items():
            check_regex("%s.%s" % (section, key), val)
    for name, r in cfg["rules"].items():
        if r["severity"] not in SEVERITIES:
            die("config: %s.severity is %r, want error or warning"
                % (name, r["severity"]))
        for key, val in r.items():
            if key.endswith("prefixes") or key in ("led_power_pin_names",
                                                   "net_pattern",
                                                   "series_diode_symbol"):
                check_regex("%s.%s" % (name, key), val)
        for w in r["waive"]:
            if not (isinstance(w, dict) and w.get("match")
                    and str(w.get("reason", "")).strip()):
                die("config: %s.waive entries need a match regex and a "
                    "reason, got %r" % (name, w))
            check_regex("%s.waive match" % name, w["match"])
    b = cfg["rules"]["bulk_capacitance"]
    if as_number(b["min_farads"], "F") is None:
        die("config: bulk_capacitance.min_farads is %r, want farads or a "
            "value such as 4u7" % (b["min_farads"],))
    o = cfg["rules"]["open_drain_pullups"]
    for key in ("min_ohms", "max_ohms"):
        if as_number(o[key], "R") is None:
            die("config: open_drain_pullups.%s is %r, want ohms or a value "
                "such as 4k7" % (key, o[key]))
    if not isinstance(o["classes"], dict):
        die("config: open_drain_pullups.classes is %r, want {name: {match, "
            "min_ohms, max_ohms}}" % (o["classes"],))
    for name, cls in o["classes"].items():
        if not isinstance(cls, dict) or set(cls) != {"match", "min_ohms",
                                                     "max_ohms"}:
            die("config: open_drain_pullups.classes.%s is %r, want exactly "
                "match, min_ohms, max_ohms" % (name, cls))
        check_regex("open_drain_pullups.classes.%s.match" % name,
                    cls["match"])
        for key in ("min_ohms", "max_ohms"):
            if as_number(cls[key], "R") is None:
                die("config: open_drain_pullups.classes.%s.%s is %r, want "
                    "ohms or a value such as 4k7" % (name, key, cls[key]))


def load_config(rules_path=None, set_items=None):
    cfg = _load_json(DEFAULT_RULES, "default rules")
    cfg.pop("_doc", None)
    if rules_path and os.path.abspath(rules_path) \
            != os.path.abspath(DEFAULT_RULES):
        merge(cfg, _load_json(rules_path, "rules file"), rules_path)
    merge(cfg, parse_set(set_items), "--set")
    validate(cfg)
    return cfg


# --------------------------------------------------------------------- driver

def evaluate(netlist, cfg):
    """Run every enabled rule. Returns the result list, one dict per rule."""
    ctx = Context(netlist, cfg)
    results = []
    for name, fn in RULES:
        r = cfg["rules"][name]
        if not r["enabled"]:
            results.append({"rule": name, "status": "disabled", "note": "",
                            "findings": [], "waived": []})
            continue
        res = fn(ctx)
        found, note = res[0], res[1]
        skipped = len(res) > 2 and res[2]       # the rule checked nothing
        for f in found:
            for w in r["waive"]:
                if any(re.search(w["match"], s) for s in f.subjects()):
                    f.waived = w["reason"]
                    break
        live = [f for f in found if f.waived is None]
        results.append({
            "rule": name,
            "status": "fail" if any(f.severity == "error" for f in live)
            else ("warn" if live else "skip" if skipped else "ok"),
            "note": note,
            "findings": live,
            "waived": [f for f in found if f.waived is not None]})
    return results


def count(results):
    errors = sum(1 for r in results for f in r["findings"]
                 if f.severity == "error")
    warnings = sum(1 for r in results for f in r["findings"]
                   if f.severity == "warning")
    waived = sum(len(r["waived"]) for r in results)
    return errors, warnings, waived


def print_report(sch, results, dnp=()):
    print("--- kicad_schrules: %s ---" % sch)
    if dnp:
        print("  %d DNP part(s) excluded from every rule: %s"
              % (len(dnp), ", ".join(sorted(dnp))))
    for r in results:
        if r["status"] == "disabled":
            print("  %-27s skipped (disabled)" % r["rule"])
            continue
        e = sum(1 for f in r["findings"] if f.severity == "error")
        w = len(r["findings"]) - e
        status = ("%d error, %d warning" % (e, w) if r["findings"]
                  else "SKIP" if r["status"] == "skip" else "ok")
        print("  %-27s %-20s %s" % (r["rule"], status, r["note"]))
        for f in r["findings"]:
            print("      %-7s %s  [symbols: %s; nets: %s]" % (
                f.severity, f.message, ", ".join(f.symbols) or "-",
                ", ".join(f.nets) or "-"))
        for f in r["waived"]:
            print("      waived  %s  [reason: %s]" % (f.message, f.waived))
    errors, warnings, waived = count(results)
    tail = "%d error, %d warning, %d waived" % (errors, warnings, waived)
    print("  FAILED (%s)" % tail if errors else "  ok      %s" % tail)


def to_json(sch, tool, results, dnp=()):
    errors, warnings, waived = count(results)
    return {
        "schematic": sch, "tool": tool, "dnp_excluded": sorted(dnp),
        "errors": errors, "warnings": warnings, "waived": waived,
        "rules": [{"rule": r["rule"], "status": r["status"],
                   "note": r["note"],
                   "findings": [f.to_json() for f in r["findings"]],
                   "waived": [f.to_json() for f in r["waived"]]}
                  for r in results]}


def resolve_schematic(path):
    """Accept a .kicad_sch or a .kicad_pro; return the schematic path."""
    sch = path[:-len(".kicad_pro")] + ".kicad_sch" \
        if path.endswith(".kicad_pro") else path
    if not os.path.isfile(sch):
        die("no such schematic: %s" % sch)
    return sch


def load_netlist(sch, netlist_xml):
    """(Netlist, kicad-cli version) from an export, or from `netlist_xml`."""
    if netlist_xml:
        return Netlist(ET.parse(netlist_xml).getroot()), None
    cli, how = find_cli()
    if not cli:
        die("kicad-cli not found (%s)\n  fix: install KiCad 10, or set "
            "KICAD_ROOT=/Applications/KiCad/KiCad.app/Contents\n  check: "
            "python3 scripts/preflight.py" % how)
    with tempfile.TemporaryDirectory(prefix="kicad_schrules_") as tmp:
        out = os.path.join(tmp, "netlist.xml")
        export_netlist(cli, sch, out)
        return Netlist(ET.parse(out).getroot()), cli_version(cli)


# ------------------------------------------------------------------ selftest

def _synthetic(comps, nets, dnp=()):
    """kicadxml text from {ref: (value, part[, lib])} and {net: [(ref, pin, name,
    pintype)]}. No libparts: pin names come from pinfunction. Refs in `dnp`
    carry the do-not-populate property, as KiCad 10 writes it."""
    root = ET.Element("export")
    ET.SubElement(ET.SubElement(root, "design"), "tool").text = "selftest"
    cs = ET.SubElement(root, "components")
    for ref, spec in comps.items():
        value, part = spec[0], spec[1]
        lib = spec[2] if len(spec) > 2 else "L"
        c = ET.SubElement(cs, "comp", ref=ref)
        ET.SubElement(c, "value").text = value
        ET.SubElement(c, "libsource", lib=lib, part=part)
        if ref in dnp:
            ET.SubElement(c, "property", name="dnp")
    ns = ET.SubElement(root, "nets")
    for name, nodes in nets.items():
        n = ET.SubElement(ns, "net", name=name)
        for ref, pin, pname, ptype in nodes:
            ET.SubElement(n, "node", ref=ref, pin=pin,
                          pinfunction="%s_%s" % (pname, pin), pintype=ptype)
    return ET.tostring(root, encoding="unicode")


def _two(ref, a, b):
    return {a: [(ref, "1", "~", "passive")], b: [(ref, "2", "~", "passive")]}


def selftest():
    """Parser cases, then every rule on a small synthetic netlist. Returns the
    number of failed checks and prints each failure."""
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append("%s: got %r, want %r" % (label, got, want))

    def near(label, got, want):
        ok = got is not None and want is not None \
            and abs(got - want) <= 1e-9 * abs(want)
        if not ok and not (got is None and want is None):
            failures.append("%s: got %r, want %r" % (label, got, want))

    for text, unit, want in (
            ("100n", "F", 1e-7), ("100nF", "F", 1e-7), ("4u7", "F", 4.7e-6),
            ("4.7uF", "F", 4.7e-6), ("0.1uF", "F", 1e-7), ("1u", "F", 1e-6),
            ("22pF", "F", 2.2e-11), ("10 uF", "F", 1e-5),
            ("100u/25V", "F", 1e-4), ("220n/X7R", "F", 2.2e-7),
            ("10uF 16V", "F", 1e-5), ("X7R 100n", "F", 1e-7),
            ("10k", "R", 1e4), ("4k7", "R", 4700.0), ("1R0", "R", 1.0),
            ("470", "R", 470.0), ("1M", "R", 1e6), ("2.2k", "R", 2200.0),
            ("10kΩ", "R", 1e4), ("100 ohm", "R", 100.0),
            ("10k 1%", "R", 1e4), ("NC", "F", None), ("", "F", None),
            (None, "R", None), ("nice!nano", "F", None),
            ("1N4148W", "R", None),
            # European decimal comma
            ("4,7uF", "F", 4.7e-6), ("1,5k", "R", 1500.0),
            ("0,1u/50V", "F", 1e-7),
            # a bare number is ohms, never farads
            ("470", "F", None), ("100", "F", None),
            # size code, dielectric and rating lose to a token with a unit
            ("0603 100n", "F", 1e-7), ("0603 10k", "R", 1e4),
            ("X7R 0603 4u7 16V", "F", 4.7e-6), ("25V 10u", "F", 1e-5),
            ("0805 X7R", "F", None),
            # a stray number after a value is not a decimal tail
            ("10u 1", "F", 1e-5), ("10 uF 1", "F", 1e-5)):
        near("parse_value(%r, %s)" % (text, unit), parse_value(text, unit),
             want)
    for value, unit, want in ((4.8e-6, "F", "4.8 uF"), (1e-7, "F", "100 nF"),
                              (1e-6, "F", "1 uF"), (4700.0, "Ohm", "4.7 kOhm"),
                              (0.0, "F", "0 F"), (None, "F", "?")):
        check("fmt_si(%r)" % (value,), fmt_si(value, unit), want)
    check("short_name", short_name("/sheet/SDA"), "SDA")
    check("ref_prefix", ref_prefix("LED13"), "LED")

    comps = {
        "U1": ("MCU", "mcu"), "U2": ("IC2", "ic"), "U3": ("IC3", "ic"),
        "J1": ("USB", "conn"),
        "J2": ("BAT", "conn"), "D1": ("SMAJ5.0A", "tvs"),
        "LED1": ("SK6812MINI-E", "led"), "LED2": ("SK6812MINI-E", "led"),
        "LED3": ("SK6812MINI-E", "led"), "LED4": ("SK6812MINI-E", "led"),
        "C1": ("100n", "c"), "C2": ("4u7/16V", "c"), "C3": ("100n", "c"),
        "R1": ("470", "r"), "R2": ("470", "r"), "R3": ("4k7", "r"),
        "R4": ("100k", "r"), "R5": ("470", "r"), "R6": ("470", "r"),
        "R7": ("100k", "r"), "R8": ("1k", "r"),
        "C4": ("470", "c"),                    # no unit: unparseable
        "C9": ("10u", "c"),                    # DNP: must not count
        # connector inputs: a series Schottky by symbol (prefix not D), a
        # series resistor, and a shunt diode to ground that does not count
        "J3": ("RAW", "conn"), "CR5": ("1N5819", "D_Schottky", "Device"),
        "J4": ("BAT", "conn"), "R9": ("10", "r"),
        "D6": ("1N4148", "d"),
        # must warn: a divider's top leg into a sense net, a series diode
        # fitted backwards, a TVS fitted backwards
        "J5": ("BAT", "conn"), "R10": ("10", "r"), "R11": ("100k", "r"),
        "J6": ("BAT", "conn"), "D7": ("1N5819", "D", "Device"),
        "J7": ("BAT", "conn"), "D8": ("SMAJ5.0A", "tvs"),
    }
    nets = {
        "GND": [("U1", "2", "GND", "power_in"), ("C1", "2", "~", "passive"),
                ("D6", "2", "A", "passive"), ("D1", "2", "A", "passive"),
                ("R11", "2", "~", "passive"), ("D8", "1", "K", "passive"),
                ("C2", "2", "~", "passive"), ("C3", "2", "~", "passive"),
                ("C4", "2", "~", "passive"), ("C9", "2", "~", "passive"),
                ("R5", "2", "~", "passive"), ("J1", "9", "GND", "passive")],
        "3V3": [("U1", "1", "VDD", "power_in"), ("C1", "1", "~", "passive"),
                ("C2", "1", "~", "passive"),
                ("LED1", "1", "VDD", "power_in"),
                ("R3", "2", "~", "passive"), ("R4", "2", "~", "passive"),
                ("R7", "2", "~", "passive"), ("R8", "2", "~", "passive"),
                ("R9", "2", "~", "passive")],
        "VX": [("U2", "1", "VCC", "power_in"), ("C3", "1", "~", "passive"),
               ("C4", "1", "~", "passive")],
        "VY": [("U3", "1", "VCC", "power_in"), ("C9", "1", "~", "passive")],
        "nRESET": [("U1", "7", "nRESET", "input"),
                   ("R7", "1", "~", "passive")],
        "RESET": [("U2", "2", "RESET", "input"),
                  ("R8", "1", "~", "passive")],
        "/s/SDA": [("U1", "5", "SDA", "bidirectional"),
                   ("R3", "1", "~", "passive")],
        "SCL": [("U1", "6", "SCL", "bidirectional"),
                ("R4", "1", "~", "passive")],
        "BAT_P": [("J1", "1", "VBAT", "passive"),
                  ("D6", "1", "K", "passive")],
        "RAW": [("J3", "1", "VIN", "passive"), ("CR5", "2", "A", "passive")],
        "RAW_D": [("CR5", "1", "K", "passive")],
        "BAT2": [("J4", "1", "VIN", "passive"), ("R9", "1", "~", "passive")],
        "BAT_DIV": [("J5", "1", "VIN", "passive"),
                    ("R10", "1", "~", "passive")],
        "VSENSE": [("R10", "2", "~", "passive"), ("R11", "1", "~", "passive"),
                   ("U1", "8", "ADC", "input")],
        "BAT_REV": [("J6", "1", "VIN", "passive"), ("D7", "1", "K", "passive")],
        "BAT_REV_D": [("D7", "2", "A", "passive")],
        "BAT_TVSREV": [("J7", "1", "VIN", "passive"),
                       ("D8", "2", "A", "passive")],
        "VIN": [("J2", "1", "VIN", "passive"), ("D1", "1", "K", "passive")],
        "D_DIRECT": [("U1", "3", "IO3", "bidirectional"),
                     ("LED1", "4", "DIN", "input")],
        "D_PULL": [("LED4", "4", "DIN", "input"), ("R5", "1", "~", "passive")],
        "D_SERIES_A": [("U1", "4", "IO4", "bidirectional"),
                       ("R1", "1", "~", "passive")],
        "D_SERIES_B": [("R1", "2", "~", "passive"),
                       ("LED2", "4", "DIN", "input")],
        "D_CHAIN": [("LED2", "2", "DOUT", "output"),
                    ("R2", "1", "~", "passive")],
        "D_CHAIN_B": [("R2", "2", "~", "passive"),
                      ("LED3", "4", "DIN", "input")],
    }
    nl = Netlist(ET.fromstring(_synthetic(comps, nets, dnp=("C9",))))

    def run_rules(set_items=None, waive=None, netlist=None):
        cfg = load_config(None, set_items)
        if waive:
            cfg["rules"][waive[0]]["waive"] = [waive[1]]
        out = {}
        for r in evaluate(netlist or nl, cfg):
            out[r["rule"]] = ([f.nets for f in r["findings"]],
                              [f.severity for f in r["findings"]],
                              [f.nets for f in r["waived"]], r["status"])
        return out

    base = run_rules()
    check("dnp: C9 is excluded", (sorted(nl.dnp), "C9" in nl.components),
          (["C9"], False))
    check("decoupling: VY has only a DNP capacitor, VX has one",
          base["decoupling_present"][0], [["VY"]])
    check("bulk: unparseable C4 warns; 100n on VX and DNP-only VY fail",
          base["bulk_capacitance"][:2],
          ([["VX"], ["VX"], ["VY"]], ["warning", "error", "error"]))
    check("led: direct and pulldown fail, series and chain pass",
          sorted(base["led_data_series_resistor"][0]),
          [["D_DIRECT"], ["D_PULL"]])
    check("pullups: SDA 4k7 and nRESET 100k pass; SCL 100k (i2c) and "
          "RESET 1k (reset) fail", base["open_drain_pullups"][0],
          [["RESET"], ["SCL"]])
    check("protection: BAT_P warns (a shunt diode is not series), BAT_DIV "
          "warns (a divider's 10 ohm top leg feeds a sense net, not a "
          "rail), BAT_REV warns (series diode cathode on the input), "
          "BAT_TVSREV warns (TVS anode on the input); VIN has a TVS K to "
          "input A to ground, RAW a series Device:D symbol anode on the "
          "input, BAT2 a 10 ohm series resistor into the 3V3 rail",
          sorted(base["connector_input_protection"][0]),
          [["BAT_DIV"], ["BAT_P"], ["BAT_REV"], ["BAT_TVSREV"]])
    check("protection: max_series_ohms=4.7 drops BAT2's 10 ohm resistor",
          ["BAT2"] in run_rules(["connector_input_protection."
                                 "max_series_ohms=4.7"])
          ["connector_input_protection"][0], True)
    check("waiver moves a finding", run_rules(
        waive=("bulk_capacitance", {"match": "^VX$", "reason": "t"}))
        ["bulk_capacitance"][0:3:2], ([["VY"]], [["VX"], ["VX"]]))
    check("--set min_farads=10u fails 3V3 too",
          sorted(run_rules(["bulk_capacitance.min_farads=10u"])
                 ["bulk_capacitance"][0]), [["3V3"], ["VX"], ["VX"], ["VY"]])
    check("--set severity=warning",
          run_rules(["open_drain_pullups.severity=warning"])
          ["open_drain_pullups"][1], ["warning", "warning"])
    check("--set classes={} and max_ohms=200k: every net on the 1k..200k "
          "default window passes",
          run_rules(["open_drain_pullups.classes={}",
                     "open_drain_pullups.max_ohms=200k"])
          ["open_drain_pullups"][0], [])
    led_only = Netlist(ET.fromstring(_synthetic(
        {"LED9": ("WS2812B", "led"), "U9": ("MCU", "mcu")},
        {"D9": [("U9", "1", "IO1", "bidirectional"),
                ("LED9", "4", "DATA_IN", "input")]})))
    check("led: no pin matches led_data_in_pin -> skip, not ok",
          run_rules(netlist=led_only)["led_data_series_resistor"][3], "skip")
    return failures


def run_selftest():
    failures = selftest()
    for line in failures:
        print("  FAIL  %s" % line)
    if failures:
        print("selftest FAILED (%d check(s))" % len(failures))
        return EXIT_FINDINGS
    print("selftest ok (python %d.%d)" % sys.version_info[:2])
    return EXIT_OK


# ----------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("schematic", nargs="?", help=".kicad_sch or .kicad_pro")
    ap.add_argument("--rules", metavar="FILE",
                    help="rules JSON, merged over templates/sch-rules.json")
    ap.add_argument("--set", action="append", default=[],
                    metavar="RULE.KEY=VALUE",
                    help="override one key; repeatable; applied after --rules")
    ap.add_argument("--netlist", metavar="XML",
                    help="reuse this kicadxml file instead of exporting")
    ap.add_argument("--json", action="store_true",
                    help="print one JSON document instead of text")
    ap.add_argument("--selftest", action="store_true",
                    help="run the parser and rule tests, then exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return run_selftest()
    if not args.schematic:
        ap.error("a schematic is required (or --selftest)")
    sch = resolve_schematic(args.schematic)
    cfg = load_config(args.rules, args.set)
    nl, version = load_netlist(sch, args.netlist)
    results = evaluate(nl, cfg)
    if args.json:
        print(json.dumps(to_json(sch, version or nl.tool, results, nl.dnp),
                         indent=2))
    else:
        print_report(sch, results, nl.dnp)
    return EXIT_FINDINGS if count(results)[0] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
