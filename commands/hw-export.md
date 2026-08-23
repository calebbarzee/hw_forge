---
description: Regenerate fab outputs (gerbers, drill, pick-and-place, BOM) and/or renders for a KiCad project, assert they are real, and summarize the artifact list.
argument-hint: "<project-dir> [-o outdir] [--profile <project-dir>/fab-profile.json]"
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

`kicad_fab.py PROJECT_DIR -o OUTDIR [--profile PROJECT_DIR/fab-profile.json]` writes one
self-contained directory per board: gerbers for every copper/mask/silk/paste layer
plus the outline with a job file, separate plated and unplated Excellon drill
files in mm with map PDFs and a drill report, pick-and-place for both sides and
each side alone, a grouped BOM, and the upload zip. It then runs its assertion
checks and exits nonzero if any fail.

The `--profile` file carries the per-project numbers to assert (see below). A
board with more than one variant wants one profile per variant — a four-layer
reversible board and a two-layer half do not have the same layer set, hole tally
or placement count.

**Exception: a gate slice has no profile.** A proto slice or test coupon is a
variant with **no fab package** — it exists to be gated, never to be ordered, and
its only consumer is `kicad_gate.py`. Writing it a profile means inventing a hole
census and a placement count for a board that will never be plotted. Do not; put
the reason in the `_comment` of the profile of the board that *is* fabbed, so the
missing profile reads as a decision rather than an omission. (A one-key slice with
no bezel outline, no mounting holes and no MCU is the standard case.)

**Where the profile lives.** Next to the board project it describes:
`<project_dir>/fab-profile.json`. Never under the output directory. The export
**wipes its output directory**, so a profile stored inside the outdir is deleted
by the run that reads it — that run succeeds, the profile is gone, and the *next*
run fails with "no such profile" far from the cause. `kicad_fab.py` now refuses to
start when the profile resolves inside the output directory.

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
- **the per-side placement split** — `"placements": {"top": 12, "bottom": 21}` —
  because the total is the one number a flip-sign error cannot change. Flip a part
  to the wrong face and the total is still 33; only the split moves.
- **intentionally-empty layers, declared as `expect_empty_layers`** and checked by
  counting aperture definitions (`%AD`), not bytes. A paste layer that is pure
  451-byte header passes any non-emptiness test and is indistinguishable from a
  layer dropped by accident. On an all-one-face board that check is worth more
  than every file-size floor combined.
- **the BOM covers every placed part**, with an explicit populate/DNP column.

The export also writes a **`-manifest.txt`** into the output directory recording
the board file's hash, the layer set, the tool versions, every assertion result
and the gate's verdict. Report that it exists. A directory of gerbers is not
self-evidently a plot of a validated board, and the export rewrites that directory
on every run — so any note a human leaves there is destroyed, and "was this zip
gated?" is otherwise archaeology six months later.

Three things that *look* wrong in a correct export and should be called out rather
than fixed:

- **Rotations that alternate** across instances of the same part. If the design
  rotates a component per row or per orientation for routing reasons, the
  pick-and-place shows it, and that is correct. Check the project's notes before
  "fixing" it.
- **Holes exported as routed slots** rather than drilled circles, where two
  overlapping drills were deliberately merged into one slot (overlapping drills
  are a fab reject).
- **A footprint placed on one face whose copper pads are all on the other.** A
  hotswap keyboard socket is the standard case: the switch inserts from the top,
  the socket solders to the underside. The pos file reports the *footprint's* own
  layer, so it reads `Side=top` and must be soldered on the back. The export
  **reports** such footprints rather than failing on them; relay the list and say
  which side each is actually soldered to.

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
  <name>-manifest.txt                    812
  assertions: PASS  (<n> mount holes @ <d>mm, <n> placements: top <n> /
              bottom <n>, <n> layers declared empty)
```

Then say what the user can do with it — which zip to upload, and anything the fab
will ask about (layer count, minimum track and clearance, any non-default rule
the board relies on). If the board carries a **relaxed design rule**, name it
here: a custom rule is something the fab's own minimum has to be checked against,
and it should never be a surprise found at order time.

## 6. "Did the geometry actually change?" — proving old gerbers still valid

When a board was regenerated for a non-geometric reason (rule changes, doc
edits, generator refactors) and the user asks whether an already-exported
gerber set is still good, do not answer from the diff of the `.kicad_pcb` —
regeneration reshuffles footprint order and UUIDs, so the board file *always*
diffs. And do not diff the gerbers as text either: aperture D-codes and draw
order also change between identical plots. Instead:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/gerber_diff.py" OLD_FAB_DIR FRESH_EXPORT_DIR
```

It resolves apertures and drill tools to their shapes and compares the sorted
multiset of draw operations per file; exit 0 means every layer and drill file
is geometrically identical and the old upload zip remains exactly what the
gate validated.
