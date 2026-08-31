# NFR Requirements Plan — U6 Handover

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: NFR Requirements
**Created**: 2026-08-30T15:32:00Z
**Status**: APPROVED 2026-08-30 — all recommendations accepted

---

## What U6 inherits

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, and the project
NFRs owned by U1, U2, U3, U4, U5 and U7. **Nothing re-opened.**

**No new dependency.** `subprocess` and `shutil` are stdlib.

---

## Why U6's non-functionals are unlike any prior unit's

U6 is the first unit that **runs code it did not write**, on the operator's machine.
Every prior unit's slowest operation was a database read; U6's is `npm ci`, which
reaches the network, writes hundreds of megabytes, and can take minutes.

| | Prior units | U6 |
|---|---|---|
| Slowest operation | A corpus read | **A network install** |
| Failure mode | A wrong record | **A hung workstation, or arbitrary code** |
| Budget shape | Milliseconds to seconds | **Minutes, with a hard stop** |

That is why BR-U6-7 exists at functional-design level rather than waiting for this
stage: subprocess invocation is a business rule here, not only an implementation
concern.

**Three questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Performance: budgets for two very different tiers

A) **Separate budgets. Structural verification and reconciliation under 10 seconds at
6,000 cases; the toolchain tier gets a per-command timeout of 300 seconds and no
overall budget — it is bounded, not fast.**
**(Recommended — the structural tier is the one an operator waits for interactively
and the one that always runs; putting a performance budget on `npm ci` would be
measuring the operator's network, which is not a property of this system)**

B) **One combined budget** of, say, 10 minutes for the whole handover. Simple, and it
hides the fact that one tier is deterministic work and the other is a network install.

C) **No toolchain budget at all.** Simplest, and an unresponsive registry then hangs
the handover with no upper bound.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — separate budgets; the toolchain tier is bounded by a 300 s per-command timeout, not a performance budget (accepted via "Accept all recommendations")

## Question 2 — Reliability: what a re-run does

Handover is not a batch that commits; it writes files and reports.

A) **Fully idempotent. Re-running produces the same manifest bytes for an unchanged
corpus, re-runs every check, and never leaves a partial artefact — the manifest is
written whole or not at all.**
**(Recommended — the operator will re-run this after every fix, so it must be cheap to
repeat and must never leave a half-written manifest that reconciliation then reads)**

B) **Resume from the last outcome**, skipping checks that passed. Faster on repeat, and
it would report a stale pass for a file changed since.

C) **Refuse to re-run** once ready. Prevents accidental overwrite, and the first fix
the engineer makes would then require a manual reset.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — fully idempotent, nothing cached, manifest written atomically (accepted via "Accept all recommendations")

## Question 3 — Security: what happens to subprocess output

`npm ci` and `tsc` write to stdout and stderr, and that output can contain absolute
paths, registry URLs, and occasionally an auth header in a proxy error.

A) **Captured, truncated to a bounded size, sanitised through the existing
`sanitise` helper, and included in the report only for a failed check.**
**(Recommended — a failure is unreadable without its output, a success does not need
it, and the sanitiser already strips the patterns U1 defined for exactly this)**

B) **Captured and included in full**, pass or fail. Most informative, and it puts
megabytes of install log into a report the agent may read into its context.

C) **Discarded entirely**; report only the exit code. Safest, and it makes a
compilation failure a fact with no detail, which sends the engineer to re-run the
command by hand — the work U6 was supposed to save.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — captured, truncated, sanitised, and included only for a failed check (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Assessment

- [x] 1.1 Record what U6 inherits unchanged
- [x] 1.2 Identify the project NFRs U6 owns or shares
- [x] 1.3 Note that U6 is the first unit to execute external code

## Phase 2: Requirements

- [x] 2.1 Performance requirements per Question 1
- [x] 2.2 Scalability requirements
- [x] 2.3 Reliability and idempotence requirements per Question 2
- [x] 2.4 Security requirements per Question 3, and subprocess containment
- [x] 2.5 Maintainability requirements
- [x] 2.6 Extension compliance: Security, Resiliency, PBT
- [x] 2.7 Write `nfr-requirements.md`

## Phase 3: Tech Stack

- [x] 3.1 Confirm no new dependency
- [x] 3.2 Record the subprocess approach and what was declined
- [x] 3.3 Write `tech-stack-decisions.md`

---

# Mandatory Artifacts

- [x] `.../u6-handover/nfr-requirements/nfr-requirements.md`
- [x] `.../u6-handover/nfr-requirements/tech-stack-decisions.md`
