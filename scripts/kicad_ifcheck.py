#!/usr/bin/env python3
"""Check every declared connector against the standard it follows.

ERC, DRC, schematic parity and kicad_fpcheck.py prove a board is consistent
with its own schematic and its declared packages.  None of them knows what a
USB-C device port must carry.  A port with no CC pulldowns passes all of them
and then draws no current from a compliant USB-C charger
(`references/interfaces.md` §1.4).  This script is that missing comparison:
the netlist the schematic exports, against a machine-readable definition of
the standard.

    python3 scripts/kicad_ifcheck.py PROJECT.kicad_sch --design design.py
    python3 scripts/kicad_ifcheck.py PROJECT.kicad_sch --design design.py \\
        --board PROJECT.kicad_pcb            # also the mating rules
    python3 scripts/kicad_ifcheck.py --list   # the definitions it can load

Inputs
------
`design.py`'s PARTS table, keyed by ref then value (`templates/design.py`):

    interface         "usb-c-device", "jst-ph-2:battery", ...: which standard
    pin_map           optional {role: [pin, ...]}: this part's own pin for a
                      role, replacing the definition's default (a pigtail's
                      vendor polarity is stated here)
    interface_wiring  "module" when the connector belongs to a module (a
                      nice!nano's USB-C): netlist rules are reported SKIP,
                      mating rules still run
    ifcheck_exempt    optional {rule_id: reason}: a recorded exemption,
                      printed as EXEMPT with the reason, never as PASS
    mating_direction, access, edge_max_mm   read through the fit contract

A footprint property named `interface` or `mating_direction` fills a key the
PARTS row leaves unset (kicad_geom.FIT_FIELDS).

Definitions
-----------
`scripts/interfaces.schema.json` is the format.  Definitions load, in this
order, from:

  1. `scripts/interfaces/*.json`;
  2. any fenced ```json block whose object has `"schema":
     "hw_forge.interface"` inside a `kb/interfaces/*.md` card under every
     knowledge-base root (the plugin's `kb/`, then `HW_FORGE_KB_ROOTS`);
  3. the project's own, with no environment variable: `PROJECT/interfaces/
     *.json` and `PROJECT/kb/interfaces/*.md` blocks, where PROJECT is the
     directory of the schematic, of --design, or of --project, and up to two
     directories above each (so a schematic in PROJECT/kicad/ finds
     PROJECT/kb/).

The first definition of an id wins, and a later one with the same id is a
definition problem (printed as WARN, naming both files).  An exact id match
wins over an alias.  The rule ids are those of `references/interfaces.md`'s
tables, so a FAIL line names the rule a human can read up.

Rule kinds are listed in the schema.  `part_to_net` is the one for a part
between a connector pin and a net that is neither ground nor another role:
an electret load resistor from the capsule pad to a bias rail, a series
build-out resistor or coupling capacitor between an output pad and the
amplifier.  `to_net` (a regex on the net name) names the far net; without it
any net that is not ground and not a role's net counts.  `count` makes it
exact (`count: 0` means none), `value_ohms` / `value_farads` with `tolerance`
bound the value.  A part counts once however many of its pins reach a far
net.  A rule with no `prefixes` counts only passives (PASSIVE_PREFIXES: R, C,
L, D, FB), never an IC or connector pin that happens to share the net.

The netlist is `kicad-cli sch export netlist --format kicadsexpr`, found
through `_kicad_env.py`.  Pins match a role by pad number or by symbol pin
name (the netlist's `pinfunction`).  A pin counts as connected only when its
net reaches a node of another reference: a net made only of this part's own
pads (a shell strapped to a shield pad, or KiCad's single-node
`unconnected-(...)`) is not connected.  A part marked do-not-populate (the
netlist's `dnp` property) is not fitted, so it is dropped from every rule,
as kicad_schrules.py does; a declared connector that is DNP is reported SKIP.

Output is one block per connector with one line per rule: PASS, FAIL, WARN,
SKIP, EXEMPT or MANUAL.  Exit 1 on any FAIL.  A declared interface with no
definition is a FAIL (`--allow-undefined` reports it as WARN), because an
interface nobody can check must not read as a checked one.  With --board, a
declared ref that is not on the board is a FAIL ("ref not on board").

Runs under any python3, stdlib only.
"""

import argparse
import glob
import json
import os
import re
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import kicad_geom                                            # noqa: E402
from _kicad_env import find_cli, run                         # noqa: E402

SCHEMA = "hw_forge.interface"
DEFAULT_GROUND = r"^(gnd|vss|0v|agnd|dgnd|pgnd|gnd_.*|.*_gnd)$"
# The parts a rule with no `prefixes` counts: passives only.
PASSIVE_PREFIXES = ("R", "C", "L", "D", "FB")
_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.S)


# ---------------------------------------------------------------- definitions

def kb_roots():
    roots = [os.path.join(os.path.dirname(HERE), "kb")]
    roots += [r for r in os.environ.get("HW_FORGE_KB_ROOTS", "").split(":")
              if r]
    return roots


def project_roots(*anchors):
    """Directories that may hold a project's interfaces/ or kb/interfaces/:
    each anchor (a file or a directory) and up to two directories above it,
    nearest first, the plugin's own tree excluded."""
    plugin = os.path.dirname(HERE)
    out = []
    for anchor in anchors:
        if not anchor:
            continue
        here = os.path.abspath(anchor)
        if not os.path.isdir(here):
            here = os.path.dirname(here)
        for _ in range(3):
            if here not in out and here != plugin:
                out.append(here)
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent
    return out


def validate(defn, where):
    """Problems with one definition, as strings (empty when it is usable).

    The subset of interfaces.schema.json this checker depends on, checked by
    hand so the script stays stdlib-only.
    """
    out = []
    for key in ("schema", "version", "id", "title", "reference", "roles",
                "rules"):
        if key not in defn:
            out.append("%s: missing %r" % (where, key))
    if defn.get("schema") != SCHEMA or defn.get("version") != 1:
        out.append("%s: not a %s v1 object" % (where, SCHEMA))
    roles = defn.get("roles") or {}
    for i, rule in enumerate(defn.get("rules") or []):
        if rule.get("kind") not in RULES:
            out.append("%s: rule %d kind %r unknown" % (where, i,
                                                        rule.get("kind")))
        for role in rule.get("roles") or []:
            if role not in roles:
                out.append("%s: rule %s names undefined role %r"
                           % (where, rule.get("id"), role))
        to = rule.get("to_role")
        if to and to != "ground" and to not in roles:
            out.append("%s: rule %s to_role %r undefined"
                       % (where, rule.get("id"), to))
        if rule.get("to_net"):
            try:
                re.compile(rule["to_net"])
            except re.error as exc:
                out.append("%s: rule %s to_net is not a regex: %s"
                           % (where, rule.get("id"), exc))
    return out


def _json_files(directory, found, problems):
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        try:
            with open(path) as fh:
                found.append((json.load(fh), path))
        except ValueError as exc:
            problems.append("%s: %s" % (path, exc))


def _md_blocks(directory, found):
    for path in sorted(glob.glob(os.path.join(directory, "*.md"))):
        with open(path, errors="replace") as fh:
            text = fh.read()
        for block in _FENCE.findall(text):
            try:
                obj = json.loads(block)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("schema") == SCHEMA:
                found.append((obj, path))


def load_definitions(projects=()):
    """({id: definition}, {alias: id}, [problems]).

    `projects` are project roots (project_roots()); their interfaces/*.json
    and kb/interfaces/*.md load after the shipped and knowledge-base ones.
    """
    found, problems = [], []
    _json_files(os.path.join(HERE, "interfaces"), found, problems)
    seen_dirs = set()
    for root in kb_roots():
        seen_dirs.add(os.path.abspath(os.path.join(root, "interfaces")))
        _md_blocks(os.path.join(root, "interfaces"), found)
    for root in projects:
        _json_files(os.path.join(root, "interfaces"), found, problems)
        kdir = os.path.abspath(os.path.join(root, "kb", "interfaces"))
        if kdir not in seen_dirs:
            seen_dirs.add(kdir)
            _md_blocks(kdir, found)
    defs, aliases = {}, {}
    for defn, path in found:
        bad = validate(defn, path)
        if bad:
            problems += bad
            continue
        defn["_path"] = path
        if defn["id"] in defs:
            if defs[defn["id"]]["_path"] != path:
                problems.append("%s: id %r already defined in %s; the first "
                                "definition is used"
                                % (path, defn["id"], defs[defn["id"]]["_path"]))
            continue
        defs[defn["id"]] = defn
        for alias in defn.get("aliases") or ():
            aliases.setdefault(alias.lower(), defn["id"])
    return defs, aliases, problems


def resolve(interface, defs, aliases):
    key = (interface or "").strip().lower()
    if key in defs:
        return defs[key]
    if key in aliases:
        return defs[aliases[key]]
    return None


# ------------------------------------------------------------------- netlist

def export_netlist(sch, out_path):
    cli, how = find_cli()
    if not cli:
        raise SystemExit("error: kicad-cli not found (%s)\n"
                         "  fix: python3 scripts/preflight.py" % how)
    proc = run([cli, "sch", "export", "netlist", "--format", "kicadsexpr",
                "-o", out_path, sch])
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise SystemExit("error: netlist export failed for %s\n  %s"
                         % (sch, (proc.stderr or "").strip()[-400:]))
    return out_path


def _is_dnp(comp):
    """True when a netlist comp carries (property (name "dnp")), unless its
    value says no, as kicad_schrules.py reads it."""
    for prop in kicad_geom.kids(comp, "property"):
        name = kicad_geom.kid(prop, "name")
        if name and len(name) > 1 and str(name[1]).lower() == "dnp":
            value = kicad_geom.kid(prop, "value")
            text = str(value[1]).lower() if value and len(value) > 1 else ""
            return text not in ("no", "false", "0")
    return False


def read_netlist(path):
    """{'values': {ref: value}, 'pins': {ref: [(pin, name, net)]},
    'nodes': {net: [(ref, pin)]}, 'dnp': {ref: value}}.

    Do-not-populate parts are kept only in 'dnp': they are absent from
    'values', 'pins' and every net's nodes, so no rule can count them.
    """
    root = kicad_geom.parse_file(path)
    values, dnp = {}, {}
    comps = kicad_geom.kid(root, "components")
    for comp in kicad_geom.kids(comps, "comp") if comps else []:
        ref = kicad_geom.kid(comp, "ref")
        val = kicad_geom.kid(comp, "value")
        if ref:
            (dnp if _is_dnp(comp) else values)[ref[1]] = (
                val[1] if val and len(val) > 1 else "")
    pins, nodes = {}, {}
    nets = kicad_geom.kid(root, "nets")
    for net in kicad_geom.kids(nets, "net") if nets else []:
        name = kicad_geom.kid(net, "name")
        net_name = name[1] if name and len(name) > 1 else ""
        for node in kicad_geom.kids(net, "node"):
            ref = (kicad_geom.kid(node, "ref") or [None, ""])[1]
            if ref in dnp:
                continue
            pin = (kicad_geom.kid(node, "pin") or [None, ""])[1]
            func = kicad_geom.kid(node, "pinfunction")
            pins.setdefault(ref, []).append(
                (pin, func[1] if func and len(func) > 1 else "", net_name))
            nodes.setdefault(net_name, []).append((ref, pin))
        nodes.setdefault(net_name, [])
    return {"values": values, "pins": pins, "nodes": nodes, "dnp": dnp}


_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0,
       "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "R": 1.0}


def parse_value(text):
    """'5.1k', '5k1', '5100', '4.7uF', '100n/X7R' -> float, or None."""
    t = (text or "").strip().replace("Ω", "").replace("ohm", "")
    m = re.match(r"^(\d+)([pnuµmkKMGR])(\d+)", t)          # 5k1, 4R7
    if m:
        return float("%s.%s" % (m.group(1), m.group(3))) * _SI[m.group(2)]
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([pnuµmkKMGR]?)", t)
    if not m:
        return None
    return float(m.group(1)) * _SI[m.group(2)]


def prefix(ref):
    return kicad_geom.designator(ref)["prefix"].upper()


# ------------------------------------------------------------------- the rules

class Ctx(object):
    def __init__(self, ref, defn, entry, net):
        self.ref, self.defn, self.entry, self.net = ref, defn, entry, net
        self.ground = re.compile(defn.get("ground_pattern") or DEFAULT_GROUND,
                                 re.I)
        pin_map = entry.get("pin_map") or {}
        self.role_pins = {}
        for role, spec in defn["roles"].items():
            pins = [str(p) for p in (pin_map.get(role) or spec.get("pins")
                                     or [])]
            names = [n.lower() for n in (spec.get("names") or [])
                     if role not in pin_map]
            got = [(p, f, n) for p, f, n in net["pins"].get(ref, [])
                   if p in pins or (f or "").lower() in names]
            self.role_pins[role] = got

    def nets(self, role):
        return sorted({n for _, _, n in self.role_pins.get(role, [])})

    def connected(self, net):
        # Another reference must sit on the net: two pads of this same part
        # (a connector's shell tabs) on one net do not wire it to anything.
        return any(r != self.ref for r, _ in self.net["nodes"].get(net, []))

    def clean(self, net):
        return (net or "").lstrip("/").split("/")[-1]

    def ground_nets(self):
        return {n for n in self.net["nodes"] if self.ground.match(self.clean(n))}

    def target_nets(self, rule):
        to = rule.get("to_role")
        if to == "ground":
            return self.ground_nets()
        return set(self.nets(to)) if to else set()

    def parts_between(self, net, targets, prefixes):
        """[(ref, value, far nets)] of fitted parts with a pin on `net` and
        one on `targets`, one entry per part.  No `prefixes` means passives
        only (PASSIVE_PREFIXES)."""
        out = []
        allowed = [p.upper() for p in (prefixes or PASSIVE_PREFIXES)]
        on_net = {r for r, _ in self.net["nodes"].get(net, [])
                  if r != self.ref}
        for ref in sorted(on_net):
            if prefix(ref) not in allowed:
                continue
            far = sorted({n for _, _, n in self.net["pins"].get(ref, [])
                          if n != net} & targets)
            if far:
                out.append((ref, self.net["values"].get(ref, ""), far))
        return out

    def parts_from_role(self, role, targets, prefixes):
        """parts_between over every net of `role`, each part once."""
        seen, out = set(), []
        for net in self.nets(role):
            for ref, val, far in self.parts_between(net, targets - {net},
                                                    prefixes):
                if ref not in seen:
                    seen.add(ref)
                    out.append((ref, val, far))
        return out


def r_connected(c, rule):
    out = []
    for role in rule.get("roles") or []:
        got = c.role_pins.get(role)
        if not got:
            out.append(("FAIL", "%s: no pin of this part matches the role"
                        % role))
            continue
        loose = ["%s" % p for p, _, n in got if not c.connected(n)]
        out.append(("FAIL" if loose else "PASS",
                    "%s pins %s %s" % (role, ",".join(p for p, _, _ in got),
                                       "unconnected: " + ",".join(loose)
                                       if loose else "connected")))
    return out


def r_same_net(c, rule):
    out = []
    for role in rule.get("roles") or []:
        nets = c.nets(role)
        if not nets:
            out.append(("FAIL", "%s: no pin matches" % role))
        else:
            out.append(("PASS" if len(nets) == 1 else "FAIL",
                        "%s on %d net(s): %s" % (role, len(nets),
                                                 ", ".join(nets))))
    return out


def r_distinct(c, rule):
    roles = rule.get("roles") or []
    seen, clash = {}, []
    for role in roles:
        for net in c.nets(role):
            if net in seen and seen[net] != role:
                clash.append("%s and %s share %s" % (seen[net], role, net))
            seen[net] = role
    return [("FAIL" if clash else "PASS",
             "; ".join(clash) or "%s on different nets" % "/".join(roles))]


def _pattern(c, rule):
    pat = rule.get("pattern") or ""
    return c.ground if pat == "ground" else re.compile(pat, re.I)


def r_pattern(c, rule, negate=False):
    out, pat = [], _pattern(c, rule)
    for role in rule.get("roles") or []:
        nets = c.nets(role)
        if not nets:
            out.append(("FAIL", "%s: no pin matches" % role))
            continue
        bad = [n for n in nets if bool(pat.match(c.clean(n))) == negate]
        if negate:
            word = "matches %s, and must not" if bad else "does not match %s"
        else:
            word = "does not match %s" if bad else "matches %s"
        out.append(("FAIL" if bad else "PASS",
                    "%s net %s %s" % (role, ", ".join(nets),
                                      word % rule.get("pattern"))))
    return out


def r_passive(c, rule, mode="passive_to"):
    out, targets = [], c.target_nets(rule)
    want = rule.get("value_ohms") or rule.get("value_farads")
    tol = rule.get("tolerance") or 0.0
    for role in rule.get("roles") or []:
        nets = c.nets(role)
        if not nets:
            out.append(("FAIL", "%s: no pin matches" % role))
            continue
        parts = c.parts_from_role(role, targets, rule.get("prefixes"))
        label = "%s -> %s" % (role, rule.get("to_role"))
        named = ", ".join("%s %s" % (r, v) for r, v, _ in parts)
        if mode == "no_passive_to":
            out.append(("FAIL" if parts else "PASS",
                        "%s: %s" % (label, named or "none")))
            continue
        if mode == "part_on_net":
            out.append(("PASS" if parts else "FAIL",
                        "%s: %s" % (label, named or "no %s part" % "/".join(
                            rule.get("prefixes") or PASSIVE_PREFIXES))))
            continue
        good, bad = [], []
        for ref, val, _ in parts:
            got = parse_value(val)
            ok = (want is None or (got is not None
                                   and abs(got - want) <= want * tol + 1e-12))
            (good if ok else bad).append("%s %s" % (ref, val))
        count = rule.get("count")
        if count is None:
            count = 1
        verdict = "PASS" if len(good) == count and not bad else "FAIL"
        out.append((verdict, "%s: %d in band (%s)%s%s"
                    % (label, len(good), ", ".join(good) or "none",
                       "; out of band: " + ", ".join(bad) if bad else "",
                       "" if want is None else "; want %g x (1 +/- %g), "
                       "exactly %d" % (want, tol, count))))
    return out


def r_part_to_net(c, rule):
    """Parts from each role's net to a net that is neither ground nor a
    role's net; `to_net` narrows the far net by name."""
    out = []
    role_nets = set()
    for role in c.defn["roles"]:
        role_nets.update(c.nets(role))
    pat = re.compile(rule["to_net"], re.I) if rule.get("to_net") else None
    targets = {n for n in c.net["nodes"]
               if n not in role_nets and not c.ground.match(c.clean(n))
               and (pat is None or pat.search(c.clean(n)))}
    want = rule.get("value_ohms") or rule.get("value_farads")
    tol = rule.get("tolerance") or 0.0
    count = rule.get("count")
    for role in rule.get("roles") or []:
        nets = c.nets(role)
        if not nets:
            out.append(("FAIL", "%s: no pin matches" % role))
            continue
        parts = c.parts_from_role(role, targets, rule.get("prefixes"))
        good, bad = [], []
        for ref, val, far in parts:
            got = parse_value(val)
            ok = (want is None or (got is not None
                                   and abs(got - want) <= want * tol + 1e-12))
            (good if ok else bad).append("%s %s -> %s" % (
                ref, val, "/".join(c.clean(f) for f in far)))
        label = "%s -> %s" % (role, rule.get("to_net") or
                              "a net that is not ground or a role")
        if count is None:
            verdict = "PASS" if good and not bad else "FAIL"
        else:
            verdict = "PASS" if len(good) == count and not bad else "FAIL"
        out.append((verdict, "%s: %d in band (%s)%s%s"
                    % (label, len(good), ", ".join(good) or "none",
                       "; out of band: " + ", ".join(bad) if bad else "",
                       "" if want is None and count is None else
                       "; want %s%s" % (
                           "%g x (1 +/- %g)" % (want, tol)
                           if want is not None else "any value",
                           ", exactly %d" % count if count is not None
                           else ""))))
    return out


def r_manual(c, rule):
    return [("MANUAL", rule.get("text") or "review step")]


RULES = {
    "connected": r_connected,
    "same_net": r_same_net,
    "distinct_nets": r_distinct,
    "net_pattern": lambda c, r: r_pattern(c, r),
    "net_not_pattern": lambda c, r: r_pattern(c, r, negate=True),
    "passive_to": r_passive,
    "no_passive_to": lambda c, r: r_passive(c, r, "no_passive_to"),
    "part_on_net": lambda c, r: r_passive(c, r, "part_on_net"),
    "part_to_net": r_part_to_net,
    "manual": r_manual,
}


def check_wiring(c):
    rows = []
    for role, spec in c.defn["roles"].items():
        got = c.role_pins.get(role)
        if spec.get("required") and not got:
            rows.append(("roles", "FAIL", "required role %s matches no pin "
                         "(pins %s, names %s)" % (role, spec.get("pins"),
                                                  spec.get("names"))))
    exempt = c.entry.get("ifcheck_exempt") or {}
    for rule in c.defn["rules"]:
        if rule["id"] in exempt:
            rows.append((rule["id"], "EXEMPT", exempt[rule["id"]]))
            continue
        for verdict, msg in RULES[rule["kind"]](c, rule):
            if verdict == "FAIL" and rule.get("severity") == "WARN":
                verdict = "WARN"
            rows.append((rule["id"], verdict, msg))
    return rows


def check_mating(ref, defn, part, board_given=False):
    """Rows from the fit contract against the definition's mating block."""
    spec, rows = defn.get("mating") or {}, []
    if not spec:
        return rows
    rid = spec.get("id") or "mating"
    m = (part or {}).get("mating")
    if part is None and board_given:
        return [(rid, "FAIL", "ref not on board: %s has no footprint in the "
                              "--board file" % ref)]
    if part is None:
        return [(rid, "SKIP", "no --board given; mating rules not checked")]
    if not m:
        return [(rid, "FAIL" if spec.get("direction_required") else "SKIP",
                 "no mating_direction declared (design.py PARTS or the "
                 "footprint field)")]
    if m.get("kind") == "internal":
        ok = spec.get("internal_allowed", False)
        return [(rid, "PASS" if ok else "FAIL",
                 "access internal%s" % ("" if ok else ", but this interface "
                                         "must mate through an edge"))]
    if spec.get("edge_required") and m.get("kind") != "edge":
        return [(rid, "FAIL", "mates through the %s face; this interface "
                              "must mate through a board edge" % m.get("kind"))]
    if m.get("verdict") == "FAIL":
        return [(rid, "FAIL", m.get("reason"))]
    if m.get("kind") == "edge":
        d = m.get("body_to_edge_mm")
        inset, over = spec.get("max_inset_mm"), spec.get("max_overhang_mm")
        if inset is not None and d is not None and d > inset + 1e-6:
            rows.append((rid, "FAIL", "mating face %.3f mm inboard of the %s "
                         "edge (max %.3f)" % (d, m.get("wall"), inset)))
        elif over is not None and d is not None and -d > over + 1e-6:
            rows.append((rid, spec.get("overhang_severity") or "WARN",
                         "body overhangs the %s edge by %.3f mm (max %.3f "
                         "unless the case captures it)" % (m.get("wall"), -d,
                                                           over)))
        else:
            rows.append((rid, "PASS", m.get("reason")))
    else:
        rows.append((rid, "PASS", m.get("reason")))
    return rows


# ---------------------------------------------------------------------- main

def run_checks(sch, design, board=None, netlist=None, allow_undefined=False,
               project=None):
    tables = kicad_geom.load_design_tables(design, ("PARTS",))
    parts = tables["PARTS"]
    defs, aliases, problems = load_definitions(
        project_roots(project, sch, design))
    contract = (kicad_geom.fit_contract(board, design) if board else None)
    by_ref = dict((p["ref"], p) for p in (contract or {}).get("parts", []))

    # Declared connectors: PARTS rows with an interface, plus footprint fields.
    declared = {}
    for key, entry in parts.items():
        if isinstance(entry, dict) and entry.get("interface"):
            declared[key] = dict(entry)
    for ref, part in by_ref.items():
        if part.get("interface") and ref not in declared:
            declared[ref] = {"interface": part["interface"]}

    if declared and sch:
        if netlist is None:
            tmpdir = tempfile.mkdtemp(prefix="hwforge_ifcheck_")
            netlist = export_netlist(sch, os.path.join(tmpdir, "net.net"))
        net = read_netlist(netlist)
    else:
        net = {"values": {}, "pins": {}, "nodes": {}, "dnp": {}}

    # A PARTS row keyed by value applies to every ref carrying that value.
    results = []
    for key, entry in sorted(declared.items()):
        refs = ([key] if key in net["pins"] or key in by_ref
                or key in net["dnp"] else sorted(
                    r for r, v in net["values"].items() if v == key) or [key])
        for ref in refs:
            defn = resolve(entry["interface"], defs, aliases)
            rows = []
            if defn is None:
                rows.append(("definition",
                             "WARN" if allow_undefined else "FAIL",
                             "no definition for interface %r (scripts/"
                             "interfaces/*.json, PROJECT/interfaces/*.json, "
                             "or a hw_forge.interface block in "
                             "kb/interfaces/*.md or PROJECT/kb/interfaces/"
                             "*.md)"
                             % entry["interface"]))
            elif str(entry.get("interface_wiring", "")).lower() == "module":
                rows.append(("wiring", "SKIP", "interface_wiring = module: "
                             "the standard's circuit is inside the module"))
            elif ref in net.get("dnp", {}):
                rows.append(("wiring", "SKIP", "%s is marked do-not-populate"
                             " (dnp): not fitted, so no wiring to check"
                             % ref))
            elif ref not in net["pins"]:
                rows.append(("wiring", "FAIL", "%s is not in the schematic "
                             "netlist" % ref))
            else:
                rows += check_wiring(Ctx(ref, defn, entry, net))
            if defn is not None:
                rows += check_mating(ref, defn, by_ref.get(ref),
                                     bool(board))
            results.append({"ref": ref, "interface": entry["interface"],
                            "definition": defn["id"] if defn else None,
                            "source": defn["_path"] if defn else None,
                            "rows": [{"rule": r, "verdict": v, "message": m}
                                     for r, v, m in rows]})
    return results, problems


def print_results(results, problems):
    for p in problems:
        print("  WARN definition problem: %s" % p)
    if not results:
        print("  no connector declares an interface (design.py PARTS "
              "[ref].interface)")
    for r in results:
        print("--- %s  %s -> %s ---" % (r["ref"], r["interface"],
                                         r["definition"] or "UNDEFINED"))
        for row in r["rows"]:
            print("  %-6s %-10s %s" % (row["verdict"], row["rule"],
                                       row["message"]))
    fails = sum(1 for r in results for row in r["rows"]
                if row["verdict"] == "FAIL")
    print("  %d connector(s), %d FAIL" % (len(results), fails))
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("schematic", nargs="?", help="the project's .kicad_sch")
    ap.add_argument("--design", help="design.py with the PARTS table")
    ap.add_argument("--board", help="the .kicad_pcb, for the mating rules "
                                     "(through the fit contract)")
    ap.add_argument("--netlist", help="an already-exported kicadsexpr "
                                      "netlist, instead of running kicad-cli")
    ap.add_argument("--allow-undefined", action="store_true",
                    help="report an interface with no definition as WARN "
                         "instead of FAIL")
    ap.add_argument("--project", metavar="DIR",
                    help="a project root whose interfaces/ and "
                         "kb/interfaces/ also load (default: found from the "
                         "schematic and --design)")
    ap.add_argument("--list", action="store_true",
                    help="list the loadable definitions and exit")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.list:
        defs, aliases, problems = load_definitions(
            project_roots(args.project, args.schematic, args.design))
        for did, d in sorted(defs.items()):
            print("%-22s %s  (%s)" % (did, d["title"], d["_path"]))
            al = sorted(a for a, i in aliases.items() if i == did)
            if al:
                print("%-22s aliases: %s" % ("", ", ".join(al)))
        for p in problems:
            print("WARN %s" % p)
        return
    if not args.schematic:
        ap.error("pass the schematic (or --list)")
    results, problems = run_checks(args.schematic, args.design, args.board,
                                   args.netlist, args.allow_undefined,
                                   args.project)
    if args.json:
        json.dump({"results": results, "problems": problems}, sys.stdout,
                  indent=2)
        sys.stdout.write("\n")
        fails = sum(1 for r in results for row in r["rows"]
                    if row["verdict"] == "FAIL")
    else:
        print("--- kicad_ifcheck: %s ---" % args.schematic)
        fails = print_results(results, problems)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
