---
description: Regenerate fab outputs (gerbers, drill, pick-and-place, BOM) and/or renders for a KiCad project, assert they are real, and summarize the artifact list.
argument-hint: "<project-dir> [-o outdir] [--profile profile.json]"
---

# /hw-export

Produce the artifacts you actually send to a fab, or look at before you do.

## 1. Gate first

Export from a gated board only. Run the gate before exporting:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kicad_gate.py" <project-dir>
```

If it fails, **stop and say so**. Exporting a board that does not pass produces
plausible-looking files for a board nobody should fab, and those files are
indistinguishable from good ones once they are in a zip.

## 2. Export

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/kicad_fab.py" $ARGUMENTS
```

`kicad_fab.py PROJECT_DIR -o OUTDIR [--profile PROFILE.json]` writes one
self-contained directory per board: gerbers for every copper/mask/silk/paste layer
plus the outline with a job file, separate plated and unplated Excellon drill
files in mm with map PDFs and a drill report, pick-and-place for both sides and
each side alone, a grouped BOM, and the upload zip. It then runs its assertion
checks and exits nonzero if any fail.

The `--profile` file carries the per-project numbers to assert (see below). A
board with more than one variant wants one profile per variant — a four-layer
reversible board and a two-layer half do not have the same layer set, hole tally
or placement count.

**Do not refill zones on the way out.** The plotted copper must be bit-for-bit
the geometry the gate saw; a refill between gating and plotting means the gerbers
are of a board that was never validated.

## 3. Verify — assertions, not vibes

The script asserts, and you should report, that:

- **every artifact exists and is non-empty.** A zero-byte gerber is the classic
  silent export failure.
- **the drill files carry the expected tools and counts** — the mounting-hole
  diameter at the expected quantity, and each mechanical hole family at its
  expected count. Getting this wrong is a board that arrives undrillable.
- **the pick-and-place has exactly the expected number of placements.** Not
  "about right".
- **the BOM covers every placed part**, with an explicit populate/DNP column.

Two things that *look* wrong in a correct export and should be called out rather
than fixed:

- **Rotations that alternate** across instances of the same part. If the design
  rotates a component per row or per orientation for routing reasons, the
  pick-and-place shows it, and that is correct. Check the project's notes before
  "fixing" it.
- **Holes exported as routed slots** rather than drilled circles, where two
  overlapping drills were deliberately merged into one slot (overlapping drills
  are a fab reject).

## 4. Renders, for eyeballing

When the user wants to look at the board rather than fab it, produce a 3D render
top and bottom plus a flat layer plot front and back, per board, into the
project's review directory. Renders are the one place where human inspection is
the check — the gate cannot tell you that a silkscreen label sits under a
connector, or that a part is on the wrong face.

Report each image's path and size, and say what is worth looking at in it.

## 5. Report

List every artifact with its size, grouped by board, and state the assertion
result explicitly:

```
fab/<variant>/            <n> files
  <name>-F_Cu.gbr                    123456
  <name>-PTH.drl                       4567
  <name>-pos-all.csv                   8901
  <name>-bom.csv                       2345
  <name>-gerbers.zip                 234567
  assertions: PASS  (<n> mount holes @ <d>mm, <n> placements)
```

Then say what the user can do with it — which zip to upload, and anything the fab
will ask about (layer count, minimum track and clearance, any non-default rule
the board relies on). If the board carries a **relaxed design rule**, name it
here: a custom rule is something the fab's own minimum has to be checked against,
and it should never be a surprise found at order time.
