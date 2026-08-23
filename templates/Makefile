# <PROJECT> — KiCad-native build and validation loop.
#
# COPY THIS INTO YOUR PROJECT and set the four variables under "project
# configuration".  Everything below that line is generic.
#
#   make            regenerate every board, then validate all of them
#   make <name>     regenerate one board
#   make check      validate only, no regeneration  <- THE GATE
#   make fab        gerbers + drill + pick-and-place + BOM + zip, per board
#   make renders    3D renders and layer plots, for eyeballing
#   make case       run the enclosure's numeric checks
#   make preflight  prove the toolchain works before designing anything
#
# THE CONTRACT.  `make check` is the build's exit gate, not a report:
# `kicad-cli pcb drc --exit-code-violations` returns 5 when anything is wrong,
# so a failed check fails the build.  Two rules keep that meaningful:
#
#   * `make fab` plots the board exactly as `make check` gated it.  No zone
#     refill on the way out, so the gerbers cannot differ from what DRC saw.
#   * Nothing regenerates as a side effect of checking.  `make check` on a
#     clean tree must be reproducible and read-only.
#
# THE LOOP.  Generate, read the JSON report, nudge ONE named constant in
# design.py or the generator, regenerate, re-gate.  Never settle a geometry
# dispute with hand arithmetic — that is what the report is for.

# ------------------------------------------------------- project configuration

# One entry per board variant.  Each needs a directory under $(HERE) and a
# generator invocation in the "generation" section below.
PROJECTS  := <board_a> <board_b>

# Board basenames, if they differ from the directory names.  Default: same.
<board_a>_NAME := <board_a>
<board_b>_NAME := <board_b>

# Extra generator flags per board (e.g. --mirror for a mirrored variant).
<board_b>_FLAGS := <--mirror>

# Enclosure checks file, if this project has one (leave empty to skip).
CASE_CHECKS := case/checks.py

# Where the hw_forge scripts live.  Adjust if the plugin is elsewhere.
HW_FORGE ?= $(HOME)/.claude/plugins/hw_forge

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

# --schematic-parity is NOT optional: without it the DRC passes on a board
# whose netlist has drifted from the schematic, which is exactly the failure a
# generated board is most prone to.  --exit-code-violations is what makes this
# a gate instead of a report.
DRCFLAGS := --schematic-parity --severity-error --format json --exit-code-violations
ERCFLAGS := --severity-error --format json --exit-code-violations

FABDIR := $(HERE)fab
REVDIR := $(HERE)review

.PHONY: all preflight check fab renders case clean introspect \
        $(PROJECTS) $(addprefix check-,$(PROJECTS)) \
        $(addprefix fab-,$(PROJECTS)) $(addprefix renders-,$(PROJECTS))

all: $(PROJECTS) check

# Run this first, every session.  A toolchain problem found mid-design gets
# mistaken for a design problem and costs a whole session.
preflight:
	@$(PY) $(SCRIPTS)/preflight.py --project $(HERE)

# ---------------------------------------------------------------- generation
#
# One target per board.  The schematic emitter runs under system python; the
# board emitter runs under KiCad's bundled python because it imports pcbnew.
# design.py must import cleanly under BOTH — that is why it stays pure python.
#
# Order matters: schematic, then scaffold (library tables + .kicad_pro), then
# board.  The generator's own save wipes the .kicad_pro, so it re-patches
# afterwards (see scripts/kicad_scaffold.py).

define GEN_RULE
$(1):
	$$(PY) $$(HERE)gen_sch.py --out $$(HERE)$(1)/$$($(1)_NAME).kicad_sch $$($(1)_FLAGS)
	$$(PY) $$(SCRIPTS)/kicad_scaffold.py $$(HERE)$(1) $$($(1)_NAME)
	$$(KPY) $$(HERE)gen_pcb.py --out $$(HERE)$(1)/$$($(1)_NAME).kicad_pcb $$($(1)_FLAGS)
	$$(PY) $$(SCRIPTS)/kicad_scaffold.py $$(HERE)$(1) --repatch
endef
$(foreach p,$(PROJECTS),$(eval $(call GEN_RULE,$(p))))

# -------------------------------------------------------------------- the gate
#
# ERC + DRC + schematic parity + unconnected, per board.  kicad_gate.py writes
# erc.json / drc.json beside each project and exits nonzero on any failure, so
# `make check` fails the build rather than printing a warning nobody reads.
#
# Read the JSON, not the summary line, when something fails: the violation
# type and coordinates are what tell you which constant to nudge.

check: $(addprefix check-,$(PROJECTS))

define CHECK_RULE
check-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_gate.py $$(HERE)$(1) --name $$($(1)_NAME)
endef
$(foreach p,$(PROJECTS),$(eval $(call CHECK_RULE,$(p))))

# ---------------------------------------------------------------- fab outputs
#
# One self-contained directory per board: gerbers, separate PTH/NPTH excellon
# with map PDFs and a report, both-sides pick-and-place, BOM, and the zip the
# fab wants uploaded.  Copper layer count is read from the board, so a
# two-layer and a four-layer variant need no different invocation.
#
# The per-board profile JSON (optional but strongly recommended) holds the
# assertions that catch what DRC cannot: hole diameters and counts, placement
# count, minimum file sizes — plus the BOM's project-specific notes.  Without
# a profile only non-emptiness is asserted.

fab: $(addprefix fab-,$(PROJECTS))

define FAB_RULE
fab-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_fab.py $$(HERE)$(1) -o $$(FABDIR)/$(1) \
	  --name $$($(1)_NAME) \
	  $$(if $$(wildcard $$(HERE)$(1)/fab-profile.json),--profile $$(HERE)$(1)/fab-profile.json,)
endef
$(foreach p,$(PROJECTS),$(eval $(call FAB_RULE,$(p))))

# --------------------------------------------------------------------- renders
#
# 3D render (top and bottom) plus a flat layer plot per side.  These are for a
# human to eyeball; they are not a gate and must never be treated as one.

renders: $(addprefix renders-,$(PROJECTS))

define RENDER_RULE
renders-$(1):
	@mkdir -p $$(REVDIR)
	@echo "--- renders: $(1) ---"
	@$$(CLI) pcb render -o $$(REVDIR)/$(1)_3d_top.png --side top \
	  -w 2000 --height 1450 --zoom 1.35 --background opaque --quality high \
	  $$(HERE)$(1)/$$($(1)_NAME).kicad_pcb >/dev/null
	@$$(CLI) pcb render -o $$(REVDIR)/$(1)_3d_bottom.png --side bottom \
	  -w 2000 --height 1450 --zoom 1.35 --background opaque --quality high \
	  $$(HERE)$(1)/$$($(1)_NAME).kicad_pcb >/dev/null
	@$$(CLI) pcb export svg -o $$(REVDIR)/$(1)_plot_front.svg --mode-single \
	  --layers F.Cu,F.Mask,F.Silkscreen,Edge.Cuts --exclude-drawing-sheet \
	  --page-size-mode 2 $$(HERE)$(1)/$$($(1)_NAME).kicad_pcb >/dev/null
	@$$(CLI) pcb export svg -o $$(REVDIR)/$(1)_plot_back.svg --mode-single --mirror \
	  --layers B.Cu,B.Mask,B.Silkscreen,Edge.Cuts --exclude-drawing-sheet \
	  --page-size-mode 2 $$(HERE)$(1)/$$($(1)_NAME).kicad_pcb >/dev/null
endef
$(foreach p,$(PROJECTS),$(eval $(call RENDER_RULE,$(p))))

# ------------------------------------------------------------------ enclosure
#
# The enclosure's gate.  The checks file must read its geometry out of the
# BOARD FILES (scripts/kicad_geom.py), never from a spec table alone, or the
# case and the PCB will drift.

case:
ifneq ($(strip $(CASE_CHECKS)),)
	@$(PY) $(SCRIPTS)/case_verify.py $(HERE)$(CASE_CHECKS)
else
	@echo "no CASE_CHECKS configured — skipping"
endif

# --------------------------------------------------------------------- utility

# Dump what is actually on a board, when a report and your mental model
# disagree.  Trust this over the model.
introspect:
	@$(PY) $(SCRIPTS)/kicad_geom.py \
	  $(HERE)$(firstword $(PROJECTS))/$($(firstword $(PROJECTS))_NAME).kicad_pcb \
	  --max-rows 20

clean:
	rm -f $(HERE)*/erc.json $(HERE)*/drc.json
