# <PROJECT>: KiCad-native build and validation loop.
#
# Copy this into your project and fill in the "project configuration" block.
# Everything below that line is generic.
#
#   make            regenerate every target, then validate all of them
#   make <name>     regenerate one target
#   make erc        the electrical rule check (ERC) only: the phase-3 gate,
#                   which needs no board
#   make check      validate only, no regeneration: the DRC half of the phase 4
#                   gate; `make review` is the whole gate
#   make fpcheck    every footprint against its declared package (design.py
#                   PACKAGES)
#   make silkcheck  silk readability: size/stroke floors, pad/text overlap,
#                   reading orientation, refdes distance, required labels
#   make schrules   schematic design rules ERC does not cover: decoupling, bulk
#                   capacitance, LED data resistor, pull-ups, connector input
#                   protection; a prerequisite of `erc`, and a row of `review`
#   make bom        BOM field completeness and board-inherent exclusion
#   make ifcheck    every connector against its interface standard (design.py
#                   PARTS[ref].interface)
#   make contract   the board-to-enclosure fit contract, fit-<board>.json; fails
#                   when a connector declares no mating_direction or its mating
#                   face does not point out of its edge
#   make review     the pre-order gate: hw_review.py runs preflight, gate,
#                   fpcheck, bom, schrules, silkcheck, ifcheck and the fit
#                   contract, plus the case, fab-export and 3D rows, and prints
#                   one readiness table; the only prerequisite of `fab`
#   make warnings   every surviving finding, grouped by owner; rotates the
#                   previous report aside and diffs the finding classes against
#                   it (or against a BASELINE=, which also fails on a new one)
#   make fab        gerbers + drill + pick-and-place + bill of materials (BOM)
#                   + zip, per board (depends on `review`: never export a
#                   board that has not passed the pre-order gate)
#   make renders    3D renders and layer plots, for eyeballing
#   make case       run the enclosure's checks against each board's fit
#                   contract (case-<board> depends on contract-<board>); with
#                   no BOARDS configured, the checks run without a contract
#   make determinism  prove a wipe-and-rebuild reproduces the same geometry
#   make preflight  prove the toolchain works before designing anything
#   make export-dsn / route-freerouting / import-ses / route-krt / adopt
#                   the autorouting bridge, manual; see references/autorouting.md
#   make install-tools [INSTALL=1]
#                   report (or install) the optional tools, pinned and checksummed
#
# The contract.  `make check` is the build's exit gate, not a report:
# `kicad-cli pcb drc --exit-code-violations` returns 5 when anything is wrong,
# so a failed check fails the build.  DRC here is KiCad's design rule check.
# Three rules keep the gate meaningful:
#
#   * `make fab` plots the board exactly as `make check` gated it.  No zone
#     refill on the way out, so the gerbers cannot differ from what the DRC
#     saw.  `fab` also depends on `review`, which runs `check` and every other
#     gate, so the documented ordering is not something anyone can forget.
#   * Nothing regenerates as a side effect of checking.  `make check` on a
#     clean tree must be reproducible and read-only.
#   * A target with no board yet is gated on ERC alone and says so
#     (`kicad_gate.py --sch-only`).  A partial gate that announces itself is
#     fine; a partial gate that reads as green is not.
#
# The loop.  Generate, read the JSON report, nudge one named constant in
# design.py or the generator, regenerate, re-gate.  Never settle a geometry
# dispute with hand arithmetic; the report carries the numbers.

# ------------------------------------------------------- project configuration

# Gate slices and test coupons: built and gated first, never fabbed.  A
# one-cell version of anything that repeats (one key, one LED, one fastener)
# finds the same bugs on a much smaller board.  See SKILL.md, "Proto slice
# first".
PROTO     := <proto>

# Board variants that get fabbed.  One entry each.
BOARDS    := <board_a> <board_b>

# Board basenames, if they differ from the target name.  Default: the same.
#<board_a>_NAME := <board_a>

# Directory per target, relative to this Makefile.  Default: the target's own
# name.  Set `.` for a single-board project whose files live in this directory
# next to the generator; that layout is normal and supported:
#   <board_a>_DIR := .
#<board_a>_DIR := <board_a>

# Extra generator flags per target (e.g. --mirror for a mirrored variant, or
# the slice flags that make the proto small).
#<proto>_FLAGS   := --keys c0 --no-mcu
#<board_b>_FLAGS := --mirror

# Scaffolder flags: design rule check severity overrides and any design-rule
# change, each with a comment saying why.  A demoted rule is a design decision
# on the record.  (You no longer need to restate hw_forge's own defaults here:
# `kicad_scaffold.py` persists the whole scaffolded rule set to
# hwforge-overrides.json, and `--repatch` restores all of it after SaveBoard.)
SCAFFOLD  :=

# Enclosure checks file, if this project has one (leave empty to skip).
CASE_CHECKS := case/checks.py
# The python the computer-aided design (CAD) library lives in.  case_verify.py
# is pure stdlib, but a real suite asserts valid solids and printability, which
# need build123d.
CASE_PY   := case/.venv/bin/python

# Where the hw_forge scripts live.  A plugin install is the first default; a
# development checkout is the second.  Override on the command line or in the
# environment: `make HW_FORGE=~/src/hw_forge check`.
HW_FORGE ?= $(firstword $(wildcard $(HOME)/.claude/plugins/hw_forge \
                                   $(HOME)/1_projects/dev/hw_forge))

# ------------------------------------------------------------ toolchain

# Discovery kept deliberately identical to scripts/preflight.py, so that what
# preflight blesses is what make runs.  Override KICAD to point at another
# install; run `make preflight` if anything here looks wrong.
KICAD ?= /Applications/KiCad/KiCad.app/Contents
CLI   := $(KICAD)/MacOS/kicad-cli
# KiCad's bundled interpreter: the only python that can import pcbnew.
KPY   := $(KICAD)/Frameworks/Python.framework/Versions/Current/bin/python3
PY    := python3

HERE  := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
SCRIPTS := $(HW_FORGE)/scripts

# Every kicad-cli / pcbnew invocation on some installs prints a wall of
# `Fontconfig warning:` and `wxApp` noise to stderr before its real output.
# The hw_forge scripts filter it themselves; direct $(CLI) calls need this.
DENOISE := 2>&1 | grep -Ev '^Fontconfig (warning|error):|wxApp' || true

# --schematic-parity is not optional: without it the DRC passes on a board
# whose netlist has drifted from the schematic, which is the failure a
# generated board is most prone to.  --exit-code-violations is what makes this
# a gate instead of a report.
DRCFLAGS := --schematic-parity --severity-error --format json --exit-code-violations
ERCFLAGS := --severity-error --format json --exit-code-violations

FABDIR := $(HERE)fab
REVDIR := $(HERE)review

# Proto first, always: the slice is gated before the boards that instantiate it.
TARGETS := $(strip $(PROTO) $(BOARDS))

# Per-target defaults.  `<t>_DIR := .` collapses to this directory, which is
# what a single-board project wants.
$(foreach t,$(TARGETS),$(eval $(t)_NAME ?= $(t)))
$(foreach t,$(TARGETS),$(eval $(t)_DIR  ?= $(t)))
$(foreach t,$(TARGETS),$(eval $(t)_AT   := $(HERE)$(patsubst ./,,$($(t)_DIR)/)))

.PHONY: all preflight install-tools erc check fpcheck silkcheck schrules bom ifcheck contract review \
        warnings fab renders case determinism clean \
        scrub introspect export-dsn route-freerouting route-krt import-ses adopt $(TARGETS) \
        $(addprefix erc-,$(TARGETS)) $(addprefix check-,$(TARGETS)) \
        $(addprefix fpcheck-,$(BOARDS)) $(addprefix silkcheck-,$(BOARDS)) $(addprefix bom-,$(BOARDS)) \
        $(addprefix ifcheck-,$(BOARDS)) $(addprefix contract-,$(BOARDS)) $(addprefix review-,$(BOARDS)) \
        $(addprefix schrules-,$(TARGETS)) \
        $(addprefix warnings-,$(TARGETS)) \
        $(addprefix fab-,$(BOARDS)) $(addprefix renders-,$(BOARDS)) \
        $(addprefix case-,$(BOARDS))

all: $(TARGETS) check

# Run this first, every session.  A toolchain problem found mid-design gets
# mistaken for a design problem.
preflight:
	@$(PY) $(SCRIPTS)/preflight.py --project $(HERE)

# The optional tools (Freerouting, the Fabrication Toolkit, KiCadRoutingTools),
# pinned and checksummed.  Reports by default; INSTALL=1 downloads and installs.
install-tools:
	@$(PY) $(SCRIPTS)/hw_install.py $(if $(INSTALL),--all,--check)

# ---------------------------------------------------------------- generation
#
# One target per board.  The schematic emitter runs under system python; the
# board emitter runs under KiCad's bundled python because it imports pcbnew.
# design.py must import cleanly under both, which is why it stays pure python.
#
# Order matters: schematic, then scaffold (library tables + .kicad_pro), then
# board.  The generator's own save wipes the .kicad_pro, so it re-patches
# afterwards (see scripts/kicad_scaffold.py).

define GEN_RULE
$(1):
	$$(PY) $$(HERE)gen_sch.py --out $$($(1)_AT)$$($(1)_NAME).kicad_sch $$($(1)_FLAGS)
	$$(PY) $$(SCRIPTS)/kicad_scaffold.py $$($(1)_AT) $$($(1)_NAME) $$(SCAFFOLD)
	$$(KPY) $$(HERE)gen_pcb.py --out $$($(1)_AT)$$($(1)_NAME).kicad_pcb $$($(1)_FLAGS) $$(DENOISE)
	$$(PY) $$(SCRIPTS)/kicad_scaffold.py $$($(1)_AT) --repatch
endef
$(foreach t,$(TARGETS),$(eval $(call GEN_RULE,$(t))))

# -------------------------------------------------------------------- the gate
#
# ERC + DRC + schematic parity + unconnected, per target.  kicad_gate.py writes
# erc.json / drc.json beside each project and exits nonzero on any failure, so
# `make check` fails the build rather than printing a warning nobody reads.
#
# `make erc` is the phase-3 gate: --sch-only asserts ERC and does not look for
# a board.  `make check` gates ERC, DRC with parity and unconnected on every
# target (the DRC half of the phase 4 gate; `make review` is the whole gate);
# a target that genuinely has no board yet is auto-detected and reports DRC as
# SKIPPED with a PARTIAL verdict.
#
# Read the JSON, not the summary line, when something fails: the violation
# type and coordinates are what tell you which constant to nudge.

erc: $(addprefix erc-,$(TARGETS)) schrules
check: $(addprefix check-,$(TARGETS))

define CHECK_RULE
erc-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_gate.py $$($(1)_AT) --name $$($(1)_NAME) --sch-only
check-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_gate.py $$($(1)_AT) --name $$($(1)_NAME)
endef
$(foreach t,$(TARGETS),$(eval $(call CHECK_RULE,$(t))))

# Warnings, and the question a revision asks.  `check` gates errors; warnings
# are not gated, so a warning class introduced by a revision otherwise arrives
# in silence.  This enumerates every surviving finding grouped by owner, then
# diffs the finding classes against the previous rev's report.
#
# The grouping by owner is also the proof a severity demotion has to keep
# making every rev ("25/25 name DISP1+MCU1", see references/kicad-api.md §4).
#
#   make warnings                          enumerate, and diff the previous run
#   make warnings BASELINE=some-report.json   ...against a named baseline, and
#                                             fail on any new class
#
# The baseline is a build artifact, not something to remember.  `report.py
# --baseline` is exactly the right check and it used to have no input: this
# target overwrote `drc-all-<t>.json` in place, so by the time you wanted a
# baseline the previous rev's report was gone, and a revision ended up
# reconstructing the previous class set out of prose in an as-built document.
#
# So the existing report is rotated to `drc-all-<t>.prev.json` first, and the
# diff runs automatically once a previous report exists.  Commit the report if
# you want a baseline that survives a clean checkout.
#
# The automatic diff does not pass --strict, because the previous run may have
# been mid-revision.  An explicit BASELINE= does, because that is a deliberate
# claim about a known-good rev.

warnings: $(addprefix warnings-,$(TARGETS))

define WARN_RULE
warnings-$(1):
	@if [ -f $$(HERE)drc-all-$(1).json ]; then \
	   cp $$(HERE)drc-all-$(1).json $$(HERE)drc-all-$(1).prev.json; fi
	-@$$(CLI) pcb drc --schematic-parity --severity-all --format json \
	   -o $$(HERE)drc-all-$(1).json \
	   $$($(1)_AT)$$($(1)_NAME).kicad_pcb $$(DENOISE)
	@if [ -n "$$(BASELINE)" ]; then \
	   $$(PY) $$(SCRIPTS)/report.py $$(HERE)drc-all-$(1).json --by-owner \
	     --baseline $$(BASELINE) --strict; \
	 elif [ -f $$(HERE)drc-all-$(1).prev.json ]; then \
	   $$(PY) $$(SCRIPTS)/report.py $$(HERE)drc-all-$(1).json --by-owner \
	     --baseline $$(HERE)drc-all-$(1).prev.json; \
	 else \
	   $$(PY) $$(SCRIPTS)/report.py $$(HERE)drc-all-$(1).json --by-owner; \
	   echo "  (no previous report to diff: this run wrote the first baseline)"; \
	 fi
endef
$(foreach t,$(TARGETS),$(eval $(call WARN_RULE,$(t))))

# ------------------------------------------------------------ package check
#
# kicad_fpcheck.py: does each footprint's pad geometry match the package the
# part is declared to be (design.py's PACKAGES table), not just whether the
# board is internally self-consistent, which `check` already proves.  `fab`
# runs it through `review`: never export a board whose footprints have not
# been checked against their declared packages.
# A footprint with no declared package is checked against its own name only
# and counted in the summary as a self-consistency check.  See
# scripts/kicad_fpcheck.py and docs/BACKLOG.md B3.

fpcheck: $(addprefix fpcheck-,$(BOARDS))

define FPCHECK_RULE
fpcheck-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_fpcheck.py $$($(1)_AT)$$($(1)_NAME).kicad_pcb \
	  --design $$(HERE)design.py
endef
$(foreach b,$(BOARDS),$(eval $(call FPCHECK_RULE,$(b))))

# ------------------------------------------------------------- silk readability
#
# kicad_silkcheck.py: can a human read this silkscreen, not just is it
# geometrically legal, which `check` already proves. Size/stroke floors,
# text-over-pad/text overlap, reading orientation, refdes distance from its
# own footprint, and required labels (--require / --require-file). Run after
# DRC, not instead of it. See references/silkscreen.md.
#
# Since the pre-order review, silk readability gates `fab` through `review`
# (hw_review.py's silkcheck row), like every other check here.

silkcheck: $(addprefix silkcheck-,$(BOARDS))

define SILKCHECK_RULE
silkcheck-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_silkcheck.py $$($(1)_AT)$$($(1)_NAME).kicad_pcb
endef
$(foreach b,$(BOARDS),$(eval $(call SILKCHECK_RULE,$(b))))

# ---------------------------------------------------------- schematic rules
#
# kicad_schrules.py: the design rules ERC does not cover.  Decoupling on every
# IC power pin, bulk capacitance per rail, a series resistor on the first
# addressable LED, pull-ups on I2C and reset nets, protection on connector
# power inputs.  Connectivity only; placement distance is a board check.  It
# needs a schematic and no board, so it runs for every target, the proto slice
# included, and `erc` (the phase-3 gate) depends on it.  `fab` reaches it
# through `review` (hw_review.py's schrules row).
#
# Defaults are templates/sch-rules.json.  A project that changes any key keeps
# its own copy next to this Makefile as sch-rules.json; it is picked up here.
# A decision not to fit a part is a `waive` entry with a reason in that file,
# never a lowered severity.

SCHRULES_FILE := $(wildcard $(HERE)sch-rules.json)

schrules: $(addprefix schrules-,$(TARGETS))

define SCHRULES_RULE
schrules-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_schrules.py $$($(1)_AT)$$($(1)_NAME).kicad_sch \
	  $$(if $$(SCHRULES_FILE),--rules $$(SCHRULES_FILE),)
endef
$(foreach t,$(TARGETS),$(eval $(call SCHRULES_RULE,$(t))))

# -------------------------------------------------------------------- BOM
#
# kicad_bom.py audit: every sourced part carries the fields a buyer needs
# (description, manufacturer, MPN, package, datasheet, and LCSC when the
# assembly service is JLCPCB), and every board-inherent symbol (mounting
# hole, fiducial, test point, logo) is excluded from the BOM.  The fields
# live in design.py's PARTS table; the schematic emitter writes them.  `fab`
# runs it through `review`: a BOM with empty cells is not a fab output.
#
#   make bom BOM_ASSEMBLY=jlcpcb      also require an LCSC number per part

BOM_ASSEMBLY ?=

bom: $(addprefix bom-,$(BOARDS))

define BOM_RULE
bom-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_bom.py audit $$($(1)_AT)$$($(1)_NAME).kicad_sch \
	  --board $$($(1)_AT)$$($(1)_NAME).kicad_pcb --design $$(HERE)design.py \
	  $$(if $$(BOM_ASSEMBLY),--assembly $$(BOM_ASSEMBLY),)
endef
$(foreach b,$(BOARDS),$(eval $(call BOM_RULE,$(b))))

# ------------------------------------------------------- interfaces and fit
#
# kicad_ifcheck.py: every connector that declares an `interface` in design.py
# PARTS is checked against its standard's definition (scripts/interfaces/,
# kb/interfaces/), with the rule ids of references/interfaces.md.
# kicad_geom.py --contract: the board-to-enclosure fit contract.  It fails
# when a connector (a PARTS role/interface/mating_direction, a J/P/USB/CN/X
# reference, or a Connector* library footprint) declares no mating_direction,
# or when its mating face does not point out through a board edge within
# edge_max_mm; the case suite reads it (case_verify.py --contract).

ifcheck: $(addprefix ifcheck-,$(BOARDS))
contract: $(addprefix contract-,$(BOARDS))

define IF_RULE
ifcheck-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_ifcheck.py $$($(1)_AT)$$($(1)_NAME).kicad_sch \
	  --design $$(HERE)design.py --board $$($(1)_AT)$$($(1)_NAME).kicad_pcb
contract-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_geom.py $$($(1)_AT)$$($(1)_NAME).kicad_pcb \
	  --contract $$(HERE)fit-$(1).json --design $$(HERE)design.py
endef
$(foreach b,$(BOARDS),$(eval $(call IF_RULE,$(b))))

# -------------------------------------------------------- pre-order review
#
# hw_review.py: preflight, gate, fpcheck, bom, schrules (kicad_schrules.py,
# with SCHRULES_FILE when this project has one), silkcheck, ifcheck, the fit
# contract, the case suite (when CASE_CHECKS exists), the fab export
# assertions and the 3D assembly, in that order, as one table.  Exit 0 is the
# pre-order gate (SKILL.md phase 5a, docs/QUALITY.md).  The individual targets
# above stay for the nudge loop; `fab` depends on this one.

review: $(addprefix review-,$(BOARDS))

define REVIEW_RULE
review-$(1):
	@$$(PY) $$(SCRIPTS)/hw_review.py $$($(1)_AT) --name $$($(1)_NAME) \
	  --design $$(HERE)design.py \
	  $$(if $$(SCHRULES_FILE),--rules $$(SCHRULES_FILE),) \
	  $$(if $$(wildcard $$(HERE)$$(CASE_CHECKS)),--case $$(HERE)$$(CASE_CHECKS),) \
	  $$(if $$(wildcard $$(HERE)$$(CASE_PY)),--case-python $$(HERE)$$(CASE_PY),) \
	  $$(if $$(wildcard $$($(1)_AT)fab-profile.json),--fab $$($(1)_AT)fab-profile.json,) \
	  $$(if $$(BOM_ASSEMBLY),--assembly $$(BOM_ASSEMBLY),)
endef
$(foreach b,$(BOARDS),$(eval $(call REVIEW_RULE,$(b))))

# ---------------------------------------------------------------- fab outputs
#
# One self-contained directory per board: gerbers, excellon drill files split
# into plated through-hole (PTH) and non-plated through-hole (NPTH) with map
# PDFs and a report, both-sides pick-and-place, BOM, the zip the fab wants
# uploaded, and a manifest recording what was exported and what the gate said
# about it.  Copper layer count is read from the board, so a two-layer and a
# four-layer variant need no different invocation.
#
# $(PROTO) is deliberately absent: a gate slice has no bezel, no mounting holes
# and no fab package.  Say so in the profile of the board that is fabbed.
#
# The per-board profile JSON (optional but strongly recommended) holds the
# assertions that catch what DRC cannot: hole diameters and counts, the
# per-side placement split, intentionally-empty layers, minimum file sizes, and
# the BOM's project-specific notes.  It lives next to the board, never under
# $(FABDIR): the export wipes its output directory and would delete it.
#
# Commit the zip and the BOM; ignore the loose intermediates (see the
# .gitignore shipped alongside this template).

fab: $(addprefix fab-,$(BOARDS))

define FAB_RULE
fab-$(1): review-$(1)
	@$$(PY) $$(SCRIPTS)/kicad_fab.py $$($(1)_AT) -o $$(FABDIR)/$(1) \
	  --name $$($(1)_NAME) \
	  $$(if $$(wildcard $$($(1)_AT)fab-profile.json),--profile $$($(1)_AT)fab-profile.json,)
endef
$(foreach b,$(BOARDS),$(eval $(call FAB_RULE,$(b))))

# --------------------------------------------------------------------- renders
#
# 3D render (top and bottom) plus a flat layer plot per side. These are for a
# human to eyeball; they are not a gate and must never be treated as one.

renders: $(addprefix renders-,$(BOARDS))

define RENDER_RULE
renders-$(1):
	@mkdir -p $$(REVDIR)
	@echo "--- renders: $(1) ---"
	@$$(CLI) pcb render -o $$(REVDIR)/$(1)_3d_top.png --side top \
	  -w 2000 --height 1450 --zoom 1.35 --background opaque --quality high \
	  $$($(1)_AT)$$($(1)_NAME).kicad_pcb $$(DENOISE)
	@$$(CLI) pcb render -o $$(REVDIR)/$(1)_3d_bottom.png --side bottom \
	  -w 2000 --height 1450 --zoom 1.35 --background opaque --quality high \
	  $$($(1)_AT)$$($(1)_NAME).kicad_pcb $$(DENOISE)
	@$$(CLI) pcb export svg -o $$(REVDIR)/$(1)_plot_front.svg --mode-single \
	  --layers F.Cu,F.Mask,F.Silkscreen,Edge.Cuts --exclude-drawing-sheet \
	  --page-size-mode 2 $$($(1)_AT)$$($(1)_NAME).kicad_pcb $$(DENOISE)
	@$$(CLI) pcb export svg -o $$(REVDIR)/$(1)_plot_back.svg --mode-single --mirror \
	  --layers B.Cu,B.Mask,B.Silkscreen,Edge.Cuts --exclude-drawing-sheet \
	  --page-size-mode 2 $$($(1)_AT)$$($(1)_NAME).kicad_pcb $$(DENOISE)
endef
$(foreach b,$(BOARDS),$(eval $(call RENDER_RULE,$(b))))

# ------------------------------------------------------------------ enclosure
#
# The enclosure's gate.  The checks file must read its geometry out of the
# board files (scripts/kicad_geom.py), never from a spec table alone, or the
# case and the PCB will drift.  Run it with the python build123d lives in.
#
# case-<board> depends on contract-<board>, so the suite always reads the fit
# contract the board just produced (fit-<board>.json, written by
# contract-<board> above), never a stale one.  A project with no BOARDS (a
# proto-only or case-only tree) has no contract, so `make case` then runs the
# checks file alone.

CASE_RUN = $(if $(wildcard $(HERE)$(CASE_PY)),$(HERE)$(CASE_PY),$(PY)) \
  $(SCRIPTS)/case_verify.py $(HERE)$(CASE_CHECKS)

ifeq ($(strip $(CASE_CHECKS)),)
case:
	@echo "no CASE_CHECKS configured, skipping"
else ifeq ($(strip $(BOARDS)),)
case:
	@$(CASE_RUN)
else
case: $(addprefix case-,$(BOARDS))
endif

define CASE_RULE
case-$(1): contract-$(1)
	@$$(CASE_RUN) --contract $$(HERE)fit-$(1).json
endef
$(foreach b,$(BOARDS),$(eval $(call CASE_RULE,$(b))))

# ------------------------------------------------------------------ autorouting
#
# The bridge to an external Specctra autorouter, for a board whose routing
# is NOT fully scripted (references/autorouting.md has the decision rule).
# Manual, not part of `make check`: routing.py, once adopted, is a committed
# input like any other, and re-routing is a deliberate act, not a build step.
# Any footprint move makes routing.py stale in full; re-run all four steps.
#
#   make export-dsn T=<target>
#   make route-freerouting T=<target> [PASSES=20] [JAR=...]
#   make import-ses T=<target> [SES=...]
#   make adopt T=<target>
#
# T defaults to the first target when there is only one; name it explicitly
# on a multi-board project.  The jar is never downloaded by make; the route
# script prints the install command when it is missing.

T ?= $(firstword $(TARGETS))

export-dsn:
	@$(KPY) $(SCRIPTS)/kicad_route.py export-dsn \
	  $($(T)_AT)$($(T)_NAME).kicad_pcb $(DENOISE)

route-freerouting:
	@$(PY) $(SCRIPTS)/kicad_route.py route \
	  $($(T)_AT)$($(T)_NAME).dsn -o $($(T)_AT)$($(T)_NAME).ses \
	  $(if $(PASSES),--passes $(PASSES),) $(if $(JAR),--jar $(JAR),)

import-ses:
	@$(KPY) $(SCRIPTS)/kicad_route.py import-ses \
	  $($(T)_AT)$($(T)_NAME).kicad_pcb \
	  $(if $(SES),$(SES),$($(T)_AT)$($(T)_NAME).ses) $(DENOISE)

# KiCadRoutingTools reads and writes the board directly: no DSN, no SES.  The
# subcommand refills zones afterwards, which its output needs before any gate.
route-krt:
	@$(KPY) $(SCRIPTS)/kicad_route.py route-krt \
	  $($(T)_AT)$($(T)_NAME).kicad_pcb $(if $(POWER_NETS),--power-nets $(POWER_NETS),) $(DENOISE)

adopt:
	@$(PY) $(SCRIPTS)/kicad_route.py adopt \
	  $($(T)_AT)$($(T)_NAME).kicad_pcb -o $($(T)_AT)routing.py

# --------------------------------------------------------------------- utility

# Prove regeneration is deterministic: digest, wipe, rebuild, digest, compare.
# Boards are not byte-stable, because pcbnew mints fresh KIIDs (its per-item
# unique identifiers) and reorders footprints on save.  So the comparison is on
# the canonical uuid-free form, which is the only honest form of "the generator
# is reproducible".
BOARD_FILES := $(foreach t,$(TARGETS),$($(t)_AT)$($(t)_NAME).kicad_pcb)

determinism:
	@$(PY) $(SCRIPTS)/kicad_digest.py $(BOARD_FILES) > $(HERE).digest-before
	@$(MAKE) --no-print-directory scrub
	@$(MAKE) --no-print-directory $(TARGETS) >/dev/null
	@$(PY) $(SCRIPTS)/kicad_digest.py $(BOARD_FILES) > $(HERE).digest-after
	@diff $(HERE).digest-before $(HERE).digest-after \
	  && cat $(HERE).digest-after \
	  && echo "  deterministic: canonical digests match across a wipe+rebuild"
	@rm -f $(HERE).digest-before $(HERE).digest-after

# Dump what is actually on a board, when a report and your mental model
# disagree.  Trust this over the model.  It also reports each footprint's
# courtyard and which face its hardware really protrudes on, which is what an
# enclosure's obstacle ledger is made of.
introspect:
	@$(PY) $(SCRIPTS)/kicad_geom.py \
	  $(firstword $(BOARD_FILES)) --max-rows 20

clean:
	rm -f $(foreach t,$(TARGETS),$($(t)_AT)erc.json $($(t)_AT)drc.json)

# Deliberately separate from `clean`: this deletes generated design files, and
# `make determinism` is the only thing that should call it casually.
scrub:
	rm -f $(BOARD_FILES)
