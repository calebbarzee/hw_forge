# <PROJECT>: decisions doc

Copy this file into the project root as `SPEC.md` and replace every <ANGLE>
placeholder. This file is the arbiter: when the spec and the code later
disagree, this file wins.

It is produced at phase 0 from the intake question bank
(`skills/hw-design/references/intake.md`), asked in one batch. It changes
after that only by appending a dated bullet to the section a later decision
belongs to, with the reason: a mid-run DECISION REQUEST answered, a REGRESSION
note written back, or a barrier's resolution. Never delete or silently reword
an existing entry; append the change next to it.

Keep the section order below. Anyone who has read one project's `SPEC.md`
should be able to read any other.

## 1. Locked

The user's choices, verbatim. No paraphrase, no summarizing. These become the
LOCKED DECISIONS block pasted into every agent prompt.

- L1. <decision, exactly as the user stated it>
- L2. <decision, exactly as the user stated it>

## 2. Delegated

Questions the user answered "your call," "take the defaults," or equivalent,
rather than choosing a value themselves. Record the question, the
recommendation that was offered, and that the user adopted it. Once written
here, a delegated item carries the same force as a locked one in §1. It is
not open for relitigation, and an agent may not re-argue it on the theory that
nobody chose it deliberately.

- Dg1. <question, as asked>. Recommendation: <the option offered>. Adopted.
- Dg2. <question, as asked>. Recommendation: <the option offered>. Adopted.

## 3. Design intent

Two blocks, read out of the intake's placement and rules domains
(`references/intake.md` §2.2 and §2.3). Paste both into every agent prompt
alongside §1 and §2, exactly as the locked-decisions block already is.

### 3a. Placement intent

Which part goes where: face, edge or zone, and what the user touches or sees.
A spec sentence that names parts but not their placement is exactly the gap
that leaves package and footprint choices to guesswork; see `intake.md` §4 for
the worked case.

| Part | Face | Edge / zone | User-facing? | Notes |
|---|---|---|---|---|
| <part reference, e.g. SW1> | <top / bottom> | <edge, corner, or "center"> | <touched / seen / hidden> | <anything an emitter needs that the other columns do not capture> |

One row per instance, not per part type: SW1 to SW4 get four rows even when
they share a package, because each sits somewhere different. Include the parts
the request implies rather than names, such as a module's USB connector.

### 3b. Rules

The constraints every phase must honor, one line each. A later phase cites the
line rather than re-deriving the rule, and an agent prompt quotes the relevant
lines verbatim.

- R1. Layer count: <n>.
- R2. Fab and assembly service: <vendor>, <PCB only / PCB + assembly>.
- R3. Part sourcing constraint: <e.g. JLCPCB basic parts only, extended allowed to $<n> per part, no constraint>.
- R4. Trace and clearance class: <e.g. fab default, or a stated tighter class and why>.
- R5. Autorouter: <permitted / not permitted / per net family by the rule in `references/autorouting.md` §1>. Critical nets are scripted and locked in every case; list them here: <power, differential pairs, crystal, USB, or whichever of these the design has>.
- R6. Enclosure and mounting: <printed / off-the-shelf / none>, <how it is fastened and how the assembly is held or mounted in use>.
- R7. Power source: <USB / battery / wall adapter / more than one, with switch-over behavior>.
- R8. Interfaces: <every connector, header, and protocol the design must expose>.
- R9. Unit cost ceiling and the escalation threshold: <e.g. "no stated ceiling; tier-3 cost threshold defaults to 20%, per `SKILL.md`'s escalation ladder"> or <the user's stated number>.
- R10. <anything else the intake's "anything else" domain surfaced that governs every phase, e.g. a package constraint that applies design-wide, a firmware pin reservation, an aesthetic constraint>.
