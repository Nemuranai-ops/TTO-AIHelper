# NFR Design Plan — U6 Handover

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: NFR Design
**Created**: 2026-08-30T15:48:00Z
**Status**: APPROVED 2026-08-30 — all recommendations accepted

---

## What U6 inherits

45 patterns across six units. U6 uses fewer of them than any unit since U7, which is
correct for a unit that reads files and runs three commands.

| Inherited | Use in U6 |
|---|---|
| P-SEC-03 Message sanitisation | Every line of subprocess output |
| P-U7-02 Read-only gate evaluation | Before assembly |
| P-U5-03 Deterministic rendering | The manifest, for the same reason |
| P-U4-04 Three-outcome emission | The shape `skipped` follows |
| P-MNT-01 Dependency inversion | S7 depends on a port, not on `subprocess` |
| P-RES-02 Bounded external call | The per-command timeout |

**Three questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Security: how subprocess invocation is contained

A) **A `CommandRunner` port with one method, and an adapter that is the only module in
the system importing `subprocess`. The port takes a fixed argv list — never a string —
so a caller cannot pass a shell command even by mistake.**
**(Recommended — it makes "no shell, no interpolation" a property of the type rather
than of every call site, and the import contract can then assert that `subprocess`
appears in exactly one file)**

B) **Call `subprocess.run` directly in S7.** Fewer moving parts, and verification then
cannot be tested without actually running `npm`.

C) **A general-purpose shell helper** taking a command string. Flexible, and it
reintroduces the one form where a metacharacter in a path becomes executable.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — an argv-only `CommandRunner` port with one adapter, plus an import contract (accepted via "Accept all recommendations")

## Question 2 — Reliability: how the skipped tier is represented

A) **A three-valued `CheckStatus` enum — `PASSED`, `FAILED`, `SKIPPED` — with readiness
computed as an explicit expression naming all three, and a property test pinning both
directions.** **(Recommended — a boolean plus a "was it run" flag is the same
information in a shape where a later change can read the boolean alone and get the
wrong answer)**

B) **A boolean plus `was_run`.** Familiar, and every caller must remember to check both.

C) **`None` for skipped** in an optional boolean. Compact, and `None` is falsy in a
conditional, so the first `if not result:` written by anyone treats a skip as a failure.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — a three-valued `CheckStatus` enum with readiness naming all three (accepted via "Accept all recommendations")

## Question 3 — Logical Components: what U6 needs

A) **Two: `CommandRunner`** (the subprocess adapter behind the port from Question 1)
and **`StructuralVerifier`** (file presence, import resolution, path and credential
re-scan). **(Recommended — the runner isolates the only place external code executes;
the verifier holds the check set, which will grow as the team learns what breaks)**

B) **One** — the runner only, with structural checks as methods on S7.

C) **Three** — add a `ManifestBuilder`, though the manifest is a sorted list of rows
and two totals, which S7 assembles directly.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — two components: L14 CommandRunner, L15 StructuralVerifier (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Record which inherited patterns U6 uses
- [x] 1.2 Specify the command containment pattern per Question 1
- [x] 1.3 Specify the three-valued status pattern per Question 2
- [x] 1.4 Specify the atomic-write pattern
- [x] 1.5 Specify the degrade-and-report pattern
- [x] 1.6 Record patterns considered and declined
- [x] 1.7 Map every pattern to the U6 NFR it delivers
- [x] 1.8 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the components chosen in Question 3
- [x] 2.2 Define responsibilities, interfaces and the pattern set
- [x] 2.3 Place them within the hexagonal rings
- [x] 2.4 Define configuration additions
- [x] 2.5 Verify no new component violates the dependency rule
- [x] 2.6 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 29 U6 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify U6 holds no emission logic and no domain algorithm
- [x] 3.3 Verify Security and Resiliency compliance at design level
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u6-handover/nfr-design/nfr-design-patterns.md`
- [x] `.../u6-handover/nfr-design/logical-components.md`
