---
description: Check the hardware toolchain is present, correct and capable before any design work. Stops with exact fix commands on failure.
argument-hint: "[project-dir]"
---

# /hw-preflight

Run the environment doctor. This is the **first** thing to do on a new machine, a
new project, or after any toolchain change — a broken generator and a broken
design are indistinguishable from the outside, and confusing them costs a
session.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py"              # machine-level only
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py" --project $ARGUMENTS
```

Use the second form when `$ARGUMENTS` names a project directory; the first when
it is empty.

(If hw_forge is installed by symlinking the skill rather than as a plugin, the
scripts live next to it — resolve `scripts/preflight.py` relative to the
`hw-design` skill directory.)

Pass `--project DIR` when a specific project should be checked too — that adds
project-scoped checks (library tables resolve, the CAD Python can import the
project's design module, expected targets exist) to the machine-level ones.

## On success (exit 0)

Report what it verified, in two or three lines. Name the versions it found —
KiCad, `kicad-cli`, Python, and the CAD-side Python — because those are the
numbers that matter when something breaks later. Then say what the user can do
next (`/hw-validate` on an existing project, or start a design run).

## On failure (nonzero exit)

**STOP.** Do not proceed to any other phase, and do not work around it.

1. Relay the printed report as-is. `preflight.py` prints the exact fix commands;
   pass them through **verbatim** rather than paraphrasing — a paraphrased install
   command is a new source of error.
2. State plainly which capability is missing and what it blocks.
3. Stop and wait for the user.

**Explicitly forbidden**, no matter how convenient:

- skipping a gate because the tool that runs it is missing;
- hand-editing a CAD file because the generator cannot run;
- substituting a different tool, a different KiCad, or a GUI step;
- proceeding "for now" without zone fills, without parity checking, or without
  DRC;
- installing things the user did not ask for, or changing `KICAD_ROOT`,
  `PATH` or environment configuration on your own initiative.

A worked-around gate is an ungated phase, and the only thing this pipeline
guarantees is that the gates ran. Reporting a blocked environment is the correct
outcome, not a failure to be clever.

## Common causes worth naming in your report

- **KiCad too old.** The pipeline needs 10 or newer: headless zone filling works
  there and aborts under 8, and the CLI flags the gate depends on
  (`--schematic-parity`, `--exit-code-violations`) want a current version.
- **`kicad-cli` / `pcbnew` not found.** Discovery checks the platform defaults,
  including `/Applications/KiCad/KiCad.app/...` on macOS. If KiCad lives
  elsewhere, the fix is to set `KICAD_ROOT` — tell the user that, and let them
  set it.
- **Wrong Python.** Anything importing `pcbnew` must run under KiCad's *bundled*
  interpreter, not the system one. If preflight reports this, it is a command
  problem in the project's Makefile, not a missing package.
- **Missing CAD packages.** Enclosure work needs build123d. Report the exact
  install line preflight prints.
