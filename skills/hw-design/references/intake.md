# Phase-0 intake: the question bank

What to ask before locking a spec, and how to ask it. Load this at phase 0,
before drafting the question batch.

The premise: a device idea stated in one or two sentences carries far less
intent than the autonomous phases that follow need. Every question this
document does not ask gets answered anyway, either by the user later, at the
most expensive point to find out, or by an agent guessing silently. The intake
step trades a few minutes of upfront reading for phases 1 through 7 running
without rediscovering the user's intent. See §4 for a real case where a
one-sentence spec cost exactly this.

The output is `SPEC.md` (skeleton at `templates/SPEC.md`), with the sections
Locked, Delegated, and Design intent (a placement table and a rules list). §5
maps intake answers onto those sections.

## 1. How to run it

**Ask every question in one batch.** One message, organized by domain, not a
back-and-forth of single questions. A user who has to answer forty questions
one at a time will stop answering carefully by question ten; a user reading
one organized list can skim past the questions that do not apply and answer
the rest in one pass. This is also the escalation ladder's first anti-pattern
(`SKILL.md`, "Locked decisions and the escalation ladder"): asking one
question at a time wastes the user's attention on process instead of content.

**Mark every question as one of two kinds, inline:**

- `[default: <value>]`: a safe default exists. Silence, or "take the
  defaults," accepts it.
- `[no default, must answer]`: no answer is safe to assume. Phase 1 does
  not start until this one has a value.

State the escape hatch once, at the top of the batch: *"Reply 'take the
defaults' to accept every default-marked answer below. The questions marked
'must answer' still need your input."* A user who wants to move fast gets a
one-line path; a user with opinions can override any default while accepting
the rest.

**Do not ask about a question this project's kind of device makes moot.** A
device with no battery does not need the battery-charging question answered;
skip it and say why in one line, so the decisions doc shows it was considered
rather than missed. A question is moot only when the request itself settles
the condition. When the condition is another question in the same batch (Q3.11
depends on Q3.8), ask it anyway, marked "only if Q3.8 names a battery", so the
user answers both in one pass instead of a second round.

**An unanswered "must answer" question blocks phase 1**, exactly as an
unanswered open question blocked it before this document existed. "Use your
judgment" is a valid answer to any question, default or not; it converts the
question into a Delegated entry with the stated recommendation as its value.

**A question found mid-run that this bank did not anticipate** is not a
reason to skip the batch discipline. Add it to a future batch, or, if it
blocks the current phase, raise it as a tier-3 DECISION REQUEST
(`SKILL.md`, "Locked decisions and the escalation ladder"). Either way it
gets recorded in `SPEC.md`, never decided silently.

## 2. The domains

Four domains. Ask all of them; skip only what a device's kind makes
inapplicable, and say so.

### 2.1 Objective and users

The intent everything else derives from. A placement or a rules decision that
seems arbitrary in isolation is usually implied by the answer here.

- **Q1.1** What does this device do, in one sentence? `[no default, must answer]`
- **Q1.2** Who uses it, and in what setting: desk, pocket, worn, industrial
  floor, inside another product? `[no default, must answer]`
- **Q1.3** Is this a one-off for the requester, a small batch for others, or a
  product with a target unit cost at volume?
  `[default: one-off prototype, no cost target]`
- **Q1.4** Any safety, regulatory, or certification context: worn against
  skin, near liquids, charged while unattended, used by a child?
  `[default: none stated]`. Note: a battery-charging circuit is
  safety-relevant regardless of this answer; see Q3.11 and the escalation
  ladder's tier-3 list.
- **Q1.5** Duty cycle: always powered, intermittent, single-session demo?
  `[default: intermittent, battery-portable assumption]`
- **Q1.6** Anything a casual reading of the request might imply is in scope,
  that is actually out of scope? `[default: nothing excluded beyond what is
  stated]`

### 2.2 Component placement

Where each part goes, physically, and what the user does with it. This is the
domain a short spec skips most often, because the requester pictures it and
does not think to say it. Ask per named part, not just once for the board,
and for a repeated part (four buttons, six LEDs) per instance, because each
instance sits somewhere different. Name every user-facing part explicitly in
the batch, including the ones the request implies rather than states, such as
the USB connector of a module or a programming header.

- **Q2.1** For each named part: which face of the board, top or bottom?
  `[default: user-facing parts on top; everything else wherever routing is
  cheapest]`
- **Q2.2** For each user-facing part (button, display, connector, LED): where
  relative to the enclosure: centered, which edge, which corner?
  `[no default, must answer]`. A part's existence does not imply its
  position, and guessing here is guessing at the thing the user actually
  cares about.
- **Q2.3** For each part: what does the user touch (button, encoder, port)
  versus only see (display, indicator LED) versus never interact with
  (regulator, crystal)? `[no default, must answer]`
- **Q2.4** Any part that must not be reachable or visible in normal use, such
  as a programming header meant to live inside the closed case?
  `[default: nothing hidden]`
- **Q2.5** Orientation: which edge is "up" for a display's image or a
  connector's expected cable direction? `[no default, must answer, whenever
  the device has a display, a directional connector, or printed graphics]`
- **Q2.6** Board outline: freeform sized to the components, or constrained to
  match something else, such as an existing enclosure, a display's own dimensions, a
  panel cutout? `[default: freeform, sized to fit components with the
  generator's standard edge margin]`. When the outline is locked to another
  part's dimensions, add a follow-up in the same batch: the named parts'
  footprints must fit inside that outline with the fab's edge clearance, and
  if the arithmetic does not close (a 21 by 51 mm module inside a 37 by 32 mm
  display outline), say so now as a tier-3 DECISION REQUEST rather than
  discovering it at placement.

### 2.3 General rules

The constraints that apply to the whole board, not to one part. These become
`SPEC.md` §3b, the Rules list, quoted by line in every agent prompt.

- **Q3.1** Layer count? `[default: 2]`
- **Q3.2** Fab and assembly service? `[default: JLCPCB]`
- **Q3.3** Part sourcing constraint: basic parts only, extended parts allowed
  (and up to what added cost), or no constraint?
  `[default: basic parts only, extended allowed case-by-case with the added
  cost stated in the report]`
- **Q3.4** Trace and clearance class: the fab's default, or a tighter class
  for density? `[default: fab's standard class]`
- **Q3.5** Is an autorouter permitted? `[default: decide per net family by
  the rule in references/autorouting.md §1: regular repeated cells are
  scripted, irregular placement routes critical nets by script and the rest
  by autorouter, adopted back into the generator]`. Answer "not permitted"
  to force fully scripted routing, or "permitted" to allow the hybrid flow
  everywhere the rule would choose it.
- **Q3.6** Enclosure: printed, off-the-shelf, or none?
  `[default: printed, two-shell, heat-set inserts]`
- **Q3.7** Mounting in use: handheld, desk stand, wall mount, DIN rail, sits
  loose? `[no default, must answer]`
- **Q3.8** Power source: USB only, battery, wall adapter, or more than one
  with switch-over behavior? `[no default, must answer]`
- **Q3.9** Interfaces: every connector, header, and protocol the design must
  expose (USB-C, JST, I2C header, wireless radio, a debug/programming
  header)? `[no default, must answer]`
- **Q3.10** Unit cost ceiling, if any, and the percentage above which a cost
  change should stop and ask rather than proceed?
  `[default: no ceiling; the escalation ladder's tier-3 cost threshold
  defaults to 20%, see SKILL.md]`
- **Q3.11** If there is a battery: chemistry, and is charging on-board or
  handled by an external charger only? `[no default, must answer whenever
  Q3.8 names a battery; this is a stated tier-3, safety-relevant item in the
  escalation ladder regardless of how it is answered]`

### 2.4 Anything else needed to intuit design decisions later

The catch-all domain. Its purpose is to surface the facts that do not fit the
first three domains but that an agent will otherwise have to guess mid-phase.

- **Q4.0** For every named part: is it a complete module (a Pico 2 board, a
  nice!nano, a display with its own driver board) or a bare chip or component
  (an RP2350 die, an e-ink glass on a flex cable)? `[no default, must answer
  per part]`. "The rpi pico 2350" names either. A module brings its own
  flash, crystal, regulator, and USB connector; a bare chip makes every one of
  those a part this bank has to ask about. Settle this before Q4.1, because
  Q4.1 cannot be answered for a part whose identity is open.
- **Q4.1** For every named part that is not a fixed module (a raw IC, a
  transistor, a passive with more than one common package): which package?
  `[no default, must answer per part]`. This is the single highest-value
  question in this bank; see §4. Ask it per part type, not per instance:
  four identical buttons are one Q4.1 answer, while placement (§2.2) is asked
  per instance because each one sits somewhere different.
- **Q4.2** Does any part need to match something already owned or adjacent:
  footprint reuse, connector compatibility with an existing cable or dock?
  `[default: no compatibility constraint]`
- **Q4.3** Does firmware or software reserve any pin, peripheral, or address
  that the schematic must respect? `[default: none stated]`
- **Q4.4** Aesthetic constraints: color, silkscreen content, "must not look
  like a hobby board," must match a brand? `[default: no constraint]`
- **Q4.5** Timeline or urgency that should lower tolerance for long-lead or
  single-source parts? `[default: no urgency stated]`
- **Q4.6** Anything else the user has an opinion about that the first three
  domains did not surface? `[no default, always ask this one open-ended, even
  when everything else defaults cleanly]`

## 3. Why "which package" is not optional

A footprint choice made without a stated package is not a smaller decision
than a locked one; it is an unlocked one wearing the same clothes. Two parts
with the same function and the same pin count routinely ship in packages with
different pad geometry, and nothing about the schematic symbol reveals which
one an agent assumed. The gates that would catch this, design rule check
(DRC), electrical rule check (ERC), and the fab export assertions, cannot see
it either, because a wrong-but-internally-consistent footprint passes every
one of them. It surfaces only when a human, or a fab house's own checker,
compares the footprint against the part actually ordered.

Q4.1 exists because this is cheap to ask and expensive to discover.

## 4. Worked case: the one-sentence spec

A blog post documents the failure mode this document exists to prevent
(a6mzero, "This PCB is brought to you by Fable 5,"
https://a6mzero.com/posts/this-pcb-is-brought-to-you-by-fable-5/). The entire
spec handed to the agent was one sentence: an RP2350 microcontroller, four
buttons, an e-ink display, and, in the author's words, "board the size of the
display."

From that sentence alone, the agent made three choices nobody had reviewed:

- It chose a serial flash chip in a small-outline integrated circuit, wide
  (SOIC-8) package, but drew footprint pads for the narrow small-outline
  package (SOP-8) variant. Same pin count, different pad geometry, silently
  wrong.
- It chose a transistor whose footprint did not match the package it had
  specified for that same part.
- It picked parts that the named fab's assembly service did not stock, so the
  design could not be ordered as populated without a substitution pass.

None of this surfaced until the design reached the fab's upload step, the
most expensive place to find a package mismatch: every downstream file
already agrees with the wrong footprint by then, and the fix is a respin, not
a constant change.

Three questions in this bank close the gap before phase 1 starts:

- **Q3.2** and **Q3.3** would have named the assembly service and its parts
  policy before any part was chosen, turning "not stocked" from a phase-5
  surprise into a phase-1 search filter that `resource-scout` applies while
  choosing parts, not after.
- **Q4.1** would have forced a stated package for the flash chip and the
  transistor before either footprint was drawn, so a SOIC-8-versus-SOP-8
  mismatch becomes a one-line answer instead of an unstated default nobody
  checked.

Answering these three questions requires no hardware expertise from the
person asked. It requires being asked.

## 5. Mapping answers into SPEC.md

| Answer | Goes to |
|---|---|
| User stated a value explicitly (any domain) | §1 Locked, verbatim |
| User said "your call," "take the defaults," or equivalent | §2 Delegated, with the offered recommendation recorded as adopted |
| User said "use your judgment" on a must-answer question | §2 Delegated. State the recommendation you are adopting in the entry itself, since a must-answer question carried none in the batch, and mark it `judgment call` so a later reader knows nobody chose it |
| Q2.x (placement domain) answers | §3a Placement intent table, one row per part |
| Q3.x (rules domain) answers | §3b Rules list, one line per rule |
| Q1.x and Q4.x answers that are not placement or a whole-board rule | §1 or §2, whichever applies; cross-reference from §3b R10 if a rule depends on it |

A "must answer" question left unanswered after one round of asking is not
silently defaulted. Ask it again, named specifically, rather than proceeding.
