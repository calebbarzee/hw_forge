# <PROJECT> — KiCad-native build and validation loop.
#
# COPY THIS INTO YOUR PROJECT and fill in the "project configuration" block.
# Everything below that line is generic.
#
#   make            regenerate every target, then validate all of them
#   make <name>     regenerate one target
#   make erc        ERC only — THE PHASE-3 GATE (no board needed)
#   make check      validate only, no regeneration  <- THE PHASE-4 GATE
#   make warnings   every surviving finding, grouped by owner; diffs a rev
#                   against a BASELINE= report and fails on a new class
#   make fab        gerbers + drill + pick-and-place + BOM + zip, per board
#                   (depends on `check`: never export an ungated board)
#   make renders    3D renders and layer plots, for eyeballing
#   make case       run the enclosure's numeric checks
#   make determinism  prove a wipe-and-rebuild reproduces the same geometry
#   make preflight  prove the toolchain works before designing anything
#
# THE CONTRACT.  `make check` is the build's exit gate, not a report:
# `kicad-cli pcb drc --exit-code-violations` returns 5 when anything is wrong,
# so a failed check fails the build.  Three rules keep that meaningful:
#
#   * `make fab` plots the board exactly as `make check` gated it.  No zone
#     refill on the way out, so the gerbers cannot differ from what DRC saw —
#     and `fab` *depends* on `check`, because the documented ordering should
#     not be a thing anyone can forget.
#   * Nothing regenerates as a side effect of checking.  `make check` on a
#     clean tree must be reproducible and read-only.
#   * A target with no board yet is gated on ERC alone and says so
#     (`kicad_gate.py --sch-only`).  A partial gate that announces itself is
#     fine; a partial gate that reads as green is not.
#
# THE LOOP.  Generate, read the JSON report, nudge ONE named constant in
# design.py or the generator, regenerate, re-gate.  Never settle a geometry
# dispute with hand arithmetic — that is what the report is for.

# ------------------------------------------------------- project configuration

# Gate slices and test coupons: built and gated FIRST, never fabbed.  A
# one-cell version of anything that repeats (one key, one LED, one fastener) is
# the cheapest bug-finder in the pipeline — see SKILL.md, "Proto slice first".
PROTO     := <proto>

# Board variants that get fabbed.  One entry each.
BOARDS    := <board_a> <board_b>

# Board basenames, if they differ from the target name.  Default: the same.
#<board_a>_NAME := <board_a>

# Directory per target, relative to this Makefile.  Default: the target's own
# name.  Set `.` for a SINGLE-BOARD project whose files live in this directory
# next to the generator — that layout is normal and supported:
#   <board_a>_DIR := .
#<board_a>_DIR := <board_a>

# Extra generator flags per target (e.g. --mirror for a mirrored variant, or
# the slice flags that make the proto small).
#<proto>_FLAGS   := --keys c0 --no-mcu
#<board_b>_FLAGS := --mirror

# Scaffolder flags: DRC severity overrides and any design-rule change, each
# with a comment saying why.  A demoted rule is a design decision on the
# record.  (You no longer need to restate hw_forge's own defaults here:
# `kicad_scaffold.py` persists the whole scaffolded rule set to
# hwforge-overrides.json, and `--repatch` restores all of it after SaveBoard.)
SCAFFOLD  :=

# Enclosure checks file, if this project has one (leave empty to skip).
CASE_CHECKS := case/checks.py
# The python the CAD library lives in.  case_verify.py is pure stdlib, but a
# real suite asserts valid solids and printability, which need build123d.
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

# --schematic-parity is NOT optional: without it the DRC passes on a board
# whose netlist has drifted from the schematic, which is exactly the failure a
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

.PHONY: all preflight erc check warnings fab renders case determinism clean \
        scrub introspect $(TARGETS) \
        $(addprefix erc-,$(TARGETS)) $(addprefix check-,$(TARGETS)) \
        $(addprefix warnings-,$(TARGETS)) \
        $(addprefix fab-,$(BOARDS)) $(addprefix renders-,$(BOARDS))

all: $(TARGETS) check

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
# a board.  `make check` gates everything; a target that genuinely has no board
# yet is auto-detected and reports DRC as SKIPPED with a PARTIAL verdict.
#
# Read the JSON, not the summary line, when something fails: the violation
# type and coordinates are what tell you which constant to nudge.

erc: $(addprefix erc-,$(TARGETS))
check: $(addprefix check-,$(TARGETS))

define CHECK_RULE
erc-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_gate.py $$($(1)_AT) --name $$($(1)_NAME) --sch-only
check-$(1):
	@$$(PY) $$(SCRIPTS)/kicad_gate.py $$($(1)_AT) --name $$($(1)_NAME)
endef
$(foreach t,$(TARGETS),$(eval $(call CHECK_RULE,$(t))))

# WARNINGS, and the question a REVISION asks.  `check` gates errors; warnings
# are not gated, so a warning class introduced by a revision otherwise arrives
# in silence.  This enumerates every surviving finding grouped BY OWNER — which
# is also the proof a severity demotion has to keep making every rev ("25/25
# name DISP1+MCU1", see references/kicad-api.md §4) — and can diff the finding
# classes against the previous rev's report.
#
#   make warnings                          enumerate, grouped by owner
#   make warnings BASELINE=drc-all-old.json   ...and FAIL on any new class
#
# Keep a baseline: commit the report, or copy it aside before a revision.

warnings: $(addprefix warnings-,$(TARGETS))

define WARN_RULE
warnings-$(1):
	-@$$(CLI) pcb drc --schematic-parity --severity-all --format json \
	   -o $$(HERE)drc-all-$(1).json \
	   $$($(1)_AT)$$($(1)_NAME).kicad_pcb $$(DENOISE)
	@$$(PY) $$(SCRIPTS)/report.py $$(HERE)drc-all-$(1).json --by-owner \
	  $$(if $$(BASELINE),--baseline $$(BASELINE) --strict,)
endef
$(foreach t,$(TARGETS),$(eval $(call WARN_RULE,$(t))))

# ---------------------------------------------------------------- fab outputs
#
# One self-contained directory per board: gerbers, separate PTH/NPTH excellon
# with map PDFs and a report, both-sides pick-and-place, BOM, the zip the fab
# wants uploaded, and a manifest recording what was exported and what the gate
# said about it.  Copper layer count is read from the board, so a two-layer and
# a four-layer variant need no different invocation.
#
# $(PROTO) is deliberately absent: a gate slice has no bezel, no mounting holes
# and no fab package.  Say so in the profile of the board that IS fabbed.
#
# The per-board profile JSON (optional but strongly recommended) holds the
# assertions that catch what DRC cannot: hole diameters and counts, the
# PER-SIDE placement split, intentionally-empty layers, minimum file sizes —
# plus the BOM's project-specific notes.  It lives NEXT TO THE BOARD, never
# under $(FABDIR): the export wipes its output directory and would delete it.
#
# Commit the zip and the BOM; ignore the loose intermediates (see the
# .gitignore shipped alongside this template).

fab: check $(addprefix fab-,$(BOARDS))

define FAB_RULE
fab-$(1): check-$(1)
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
# BOARD FILES (scripts/kicad_geom.py), never from a spec table alone, or the
# case and the PCB will drift.  Run it with the python build123d lives in.

case:
ifneq ($(strip $(CASE_CHECKS)),)
	@$(if $(wildcard $(HERE)$(CASE_PY)),$(HERE)$(CASE_PY),$(PY)) \
	  $(SCRIPTS)/case_verify.py $(HERE)$(CASE_CHECKS)
else
	@echo "no CASE_CHECKS configured — skipping"
endif

# --------------------------------------------------------------------- utility

# Prove regeneration is deterministic: digest, wipe, rebuild, digest, compare.
# Boards are NOT byte-stable — pcbnew mints fresh KIIDs and reorders footprints
# on save — so the comparison is on the canonical uuid-free form.  This is the
# only honest form of "the generator is reproducible".
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
# courtyard and which face its hardware really protrudes on — which is what an
# enclosure's obstacle ledger is made of.
introspect:
	@$(PY) $(SCRIPTS)/kicad_geom.py \
	  $(firstword $(BOARD_FILES)) --max-rows 20

clean:
	rm -f $(foreach t,$(TARGETS),$($(t)_AT)erc.json $($(t)_AT)drc.json)

# Deliberately separate from `clean`: this deletes generated CAD files, and
# `make determinism` is the only thing that should call it casually.
scrub:
	rm -f $(BOARD_FILES)
