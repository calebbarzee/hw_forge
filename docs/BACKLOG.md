# hw_forge — backlog

Work that is **real, understood, and not bounded today.** Everything here came
out of a validation run and was triaged deliberately: it is not a wishlist, and
it is not a list of things nobody looked at. Each item names the gap numbers it
covers in `hexpad/GAPS.md`, why it is deferred rather than done, and what would
have to be true to close it.

The rule that put these here rather than in the last harvest: **a fix that
cannot be verified in the same pass that writes it is not a fix.** Three of the
four below need a mechanism the pipeline does not yet have; the fourth needs a
packaging decision. Writing a doc line about any of them would have produced a
rule with nothing behind it, which is worse than a known gap.

---

## B1 — Shipping emitter templates vs. the adapt-a-sibling doctrine

**Covers:** gap 11.

`templates/` ships `design.py`, `Makefile`, `.gitignore` and five role prompts —
but nothing for the `design.py → .kicad_sch` step, which is the deliverable of
phase 3, and nothing for the `one pin table → symbol + footprint` step, which is
a named cross-cutting rule with no template behind it. So a new project is told
to adapt a sibling project's `gen_sch.py`. hexpad did exactly that and reported
what it actually copied: ~200 lines of *pipeline* infrastructure with no hexpad
in it — a balanced-paren s-expression walker, symbol extraction out of the
installed libraries with the `(extends …)` guard, the `Lib:Name`-on-outer-symbol
rewrite, deterministic hashed UUIDs, pin-position and pin-direction maths,
global-label wiring, `no_connect` emission, and a `lib_symbols` cache. Only
`build()`, `emit_support()` and a few sheet-layout constants were the project's
own.

Adapting beat rewriting, easily. The cost is structural: **a sibling project is
now load-bearing infrastructure that hw_forge does not own**, so a bug fixed in
one project's copy is not fixed in the next one, and hw_forge's own doctrine
("everything is code-generated from one source") rests on code the plugin cannot
version.

**Why deferred.** Shipping `templates/gen_sch.py` means owning a KiCad
s-expression emitter as pipeline code, and that is a scope decision, not an
afternoon: it needs a stable contract with `design.py` (what shape a part table
has, what a sheet is, how a net gets a label), it needs to survive a KiCad file
format bump, and it needs its own regression fixture — otherwise the first
format change breaks every project that adopted it and hw_forge is on the hook
for all of them. `docs/ARCHITECTURE.md` §5 currently states the opposite
position deliberately ("`design.py` and `gen_pcb.py` themselves stay project
code"), and that position has to be *revisited*, not quietly contradicted by a
new template.

**To close:** decide the scope question first (does hw_forge own emitters, or
does it own a documented extraction procedure and a named canonical sibling?).
If emitters: ship `gen_sch.py` and `mklib.py` skeletons with a stub `build()`,
plus a fixture project that regenerates and gates in CI, so a format bump breaks
the plugin's own test rather than a user's board. If not: say so in
`SKILL.md`, name the canonical sibling to adapt, and list what is generic vs.
project-specific in it — which is most of the value at a fraction of the cost.

---

## B2 — Two-source independence: detecting a shared ancestor

**Covers:** gaps 3 and 2.

The doctrine's definition of independence is "different lineage — a vendor
datasheet and a shipped reference board, not two blog posts copying each other".
That names the failure mode and gives no way to *detect* it. hexpad's nice!view
pin order was verified against two footprints separately authored by different
people, on different dates, in different repos — independent by every checkable
signal — and **both cite the same vendor page as their datasheet**, a page whose
pin table exists only as a PNG. So the two sources may both be downstream of one
photograph. That is agreement between two transcriptions, not confirmation
against a primary source.

The doctrine half of this is now fixed (`agents/resource-scout.md`, "When the
primary source is an image"): the fallback is documented, and the transcription
caveat must be flagged inline in the provenance row and the report. What is
*not* fixed is the detection.

**Why deferred.** Detecting a shared ancestor needs something the pipeline does
not have. The candidates each cost real work: parse the cited sources out of
vendored assets and compare them transitively (needs a provenance format
machines read, not the markdown table humans read); require a *physical*
cross-check — a photo of a purchased unit's silkscreen, or a continuity check —
before a pin *order* is treated as fully verified (needs hardware in the loop,
and a way to record that evidence); or grant the scout a vision-capable fetch
tool so the image primary can be read directly (not hw_forge's to grant: it is
the harness's tool list, and it also would not help for a source that is a
photograph of a part nobody has).

**To close:** make `lib/PROVENANCE.md` machine-readable enough that "these two
assets cite the same URL" is a query, and add that check to the phase-1 gate.
The physical-cross-check requirement can then be stated as the *escalation* for
the one case the query flags, instead of a blanket rule nobody can satisfy.

---

## B3 — Verifying a stock footprint against the physical part

**Covers:** gap 19.

Resolving a part to a stock KiCad footprint is the right call for cost and the
wrong thing to call verification. hexpad resolved five parts as "reference stock
KiCad, no copy needed", and then found that KiCad 10's
`Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02` — the footprint for a locked part —
places its three signal pads at **x = −2.25, +0.75, +2.25 mm**: spacings of 3.0
and 1.5, not a uniform three-terminal pitch. It may be correct for an offset-pin
variant. It could not be checked, because the LCSC datasheet was not reachable
from that phase.

**No gate can see this.** ERC does not know about pads. DRC and schematic parity
compare the board to the *schematic*, not to reality. A wrong stock footprint is
therefore invisible until a part will not sit on the pads — after a fab order and
an assembly attempt.

**Why deferred.** The check needs a source of truth the pipeline does not have: a
machine-readable pad geometry for the physical part. Datasheets are PDFs, most of
them drawings; vendor CAD downloads are per-vendor and per-format; and "compare
the footprint to the datasheet" is exactly the manual step the pipeline exists to
replace. A partial answer exists and is cheap — record pad pitch and pad count
against the datasheet in the provenance row for every stock footprint on a
mechanically critical part (connector, switch, module socket), one row each,
once — but that is a discipline, not a gate, and it was not added as a gate
because a gate that cannot fail is theatre.

**To close:** pick the evidence source. The most promising is the one hw_forge
already trusts elsewhere: **parse the pads out of a board file that was actually
fabbed and worked** — the same argument that makes "local machine first" the
search order. A small library of "pad geometry, confirmed on a built board" per
part number, in `kb/`, would make the check real for exactly the parts anyone
uses twice.

---

## B4 — `/hw-kb` (and friends) outside a plugin install

**Covers:** gap 6.

`commands/hw-kb.md` exists, is well-specified, and matches `kb/README.md`'s
harvest convention exactly. It was not invokable during the dry run, because the
session was rooted in the *project* directory rather than in hw_forge, and slash
commands resolve against the project a session is rooted in. The agent followed
the procedure by hand — read the command file, applied its steps — which works
and is invisible: nothing in the pipeline says that is what is supposed to
happen. Meanwhile `commands/hw-research.md`'s own report section tells the agent
to run `/hw-kb harvest` as though it always resolves.

**Why deferred.** This is a packaging and installation question, not a wording
one, and the honest fix depends on how hw_forge is meant to be consumed. If the
answer is "install the plugin", then the docs should say that the commands
require it and stop implying they are always available. If the answer is "work
from any project", then something has to register the commands globally, and that
is a decision about the user's environment that a repo cannot make for itself.
Either way the fix touches installation, which the roadmap's "plugin packaging"
milestone owns.

**To close:** as part of plugin packaging, state the requirement once in
`README.md`'s install section and make every command file's cross-references
conditional on it — or, better, give each command's procedure a "read this file
and follow it directly" fallback line, so an agent operating cross-project does
the right thing by instruction rather than by improvisation.

---

## Not in this file

Two things worth stating so they are not mistaken for backlog:

- **Every other gap from the dry run is either fixed or explicitly wontfix.**
  44 of 49 landed in this pass; one (gap 9) is works-as-intended. See
  `hexpad/GAPS.md` for the per-gap disposition and `docs/DRYRUN-HEXPAD.md` for
  the verdict.
- **The SWIG → IPC (`kipy`) migration is roadmap, not backlog.** It is forced
  work with a known deadline (SWIG is deprecated in KiCad 9 and removed in 11),
  it is scheduled, and it is tracked in `README.md` and
  `docs/ARCHITECTURE.md` §6.
