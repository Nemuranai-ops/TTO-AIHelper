# Functional Design Plan — U5 Automation Emission

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: Functional Design
**Created**: 2026-08-30T13:40:00Z
**Status**: APPROVED 2026-08-30 — all recommendations accepted

---

## Unit Context

**Responsibility**: render automatable cases into TypeScript, deterministically.

**Boundary**: U5 produces code. It does not assemble or verify a project — that is U6.

**Components** (2): S6 AutomationService, A7 PlaywrightEmitter with its Jinja2 template set.

**Stories** (6): US-AUT-01 to US-AUT-06.

**Depends on**: U1, U4 — both complete.

---

## Why this unit is different

Every other unit's output is data that the system itself reads back. **U5's output is
TypeScript that a person maintains and Jenkins runs**, and nothing downstream reads it.
Three consequences:

| | Every prior unit | U5 |
|---|---|---|
| Reviewer | Test Analyst / Test Lead | **Automation Engineer** |
| Correctness criterion | Semantic — is the rule right? | **Byte-identical reproducibility** |
| Where the standard lives | Business rules | **The templates themselves** |

The templates are a review artefact in their own right. A generated project that no
engineer wants to maintain has failed, however correct its logic — and the user's
constraint is explicit: *"need as a pure playwright project"*, pushed to a Bitbucket
repository the test team already has, with Jenkins jobs configured by hand.

**U5 inherits U4's hardest-won rule.** Hand-edited files are skipped, never
overwritten. In U4 that protected a Markdown view; here it protects an engineer's
work on a spec they have made real.

**Five questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Business Rules: how a spec file is scoped

One `.spec.ts` per what?

A) **One spec per feature**, containing a `describe` block per coverage item and a
`test` per case. Page objects live in `pages/`, one per screen.
**(Recommended — it matches U4's view sharding, so a reviewer reads the Markdown view
and the spec side by side with the same boundaries; and it keeps file counts at 150
rather than 6,000)**

B) **One spec per case.** Maximum isolation, and 6,000 files — a repository nobody
can navigate and a Jenkins run that spends its time on process startup.

C) **One spec per coverage item.** Finer than A, roughly 1,200 files, and it splits a
feature across many files for no reviewer benefit.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — one spec per feature, describe per coverage item, page objects in `pages/` (accepted via "Accept all recommendations")

## Question 2 — Business Rules: what happens to a case that cannot be automated

US-AUT-06 AC1 says manual-only cases produce no test and are listed with their reason.
What about `needs-review`?

A) **Emit `automatable` only. `needs-review` and `manual-only` both produce no test
and both appear in the automation report, distinguished by class and reason.**
**(Recommended — `needs-review` means D6 could not decide, and generating a test from
an undecided classification produces a spec the engineer must audit before trusting,
which is worse than an honest gap)**

B) **Emit `automatable` and `needs-review`, with the latter marked `test.fixme()`.**
The engineer sees the skeleton, and the suite carries entries nobody has judged.

C) **Emit all three**, with manual-only as a skipped test carrying its reason. Every
case is visible in one place, and the suite then contains 6,000 entries of which a
large share can never pass.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — emit `automatable` only; `needs-review` and `manual-only` both reported, distinguished (accepted via "Accept all recommendations")

## Question 3 — Business Rules: locator strategy when the UI model is thin

US-AUT-02 AC1 prefers `getByRole`/`getByLabel`; AC2 falls back to `getByTestId`. U2
stores locators with `is_verified` and `is_fragile` flags, and the live-exploration
work was deferred, so **most locators in the first run will be unverified**.

A) **Emit the best available locator, and annotate every unverified one in the
generated code with a comment naming it as unverified.** The test runs; the engineer
sees exactly which locators to confirm first. **(Recommended — the flag already exists
precisely so the distinction survives downstream, and a comment in the file is where
the engineer is actually looking when it fails)**

B) **Refuse to emit a test whose locators are all unverified.** Safest, and on the
first run it would emit almost nothing.

C) **Emit without distinction.** Simplest, and it presents a guess as a confirmed fact
— which is what `is_verified` exists to prevent.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — emit the best available locator, annotate every unverified one in the generated code (accepted via "Accept all recommendations")

## Question 4 — Data Model: how a hand-edit is detected here

U4 solved this with an `emitted_view` table holding the hash at last emission.

A) **Reuse the same mechanism**, generalising `emitted_view` to cover generated
TypeScript — one table, one rule, one place to fix a bug in it.
**(Recommended — the problem is identical and a second table would let the two
implementations drift; the U4 table's columns already fit)**

B) **A separate `emitted_artefact` table** for automation output, keeping the two
concerns apart at the cost of duplicating the logic.

C) **A checked-in manifest file** listing hashes. Visible in the repository, and it is
edited or deleted along with what it guards.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — generalise U4's `emitted_view` to cover generated TypeScript (accepted via "Accept all recommendations")

## Question 5 — Business Rules: what the generated project contains beyond specs

US-AUT-05 needs config, reporters and environment handling. The project is pushed to
Bitbucket and wired to Jenkins by hand.

A) **A complete, runnable project**: `playwright.config.ts` with HTML and JUnit
reporters, `package.json` with a pinned Playwright version, `tsconfig.json`,
`.env.example` documenting every variable, `fixtures/auth.ts` shared by UI and API
tests, `pages/`, `tests/`, and a `README.md` stating what is generated and what is
safe to edit. **(Recommended — the user asked for a pure Playwright project they can
push and run; anything less makes the Automation Engineer assemble the scaffold by
hand, which is the work this unit exists to remove)**

B) **Specs and page objects only.** The engineer supplies the scaffold once. Smaller
output, and the first run cannot be executed to see whether it works.

C) **A, plus a Jenkinsfile.** More complete, and it presumes a pipeline shape the team
has not described — and test execution is explicitly outside this system's scope.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — a complete, runnable Playwright project (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Domain Entities

- [x] 1.1 Define the automation-side entities and their relationship to `test_case`
- [x] 1.2 Specify the hand-edit record per Question 4
- [x] 1.3 Specify the generated project layout per Question 5
- [x] 1.4 Define `AutomationManifest` and the automation report shape
- [x] 1.5 Verify no U5 entity duplicates one U4 owns
- [x] 1.6 Write `domain-entities.md`

## Phase 2: Business Rules

- [x] 2.1 BR-U5-1 spec scoping and file layout (Question 1)
- [x] 2.2 BR-U5-2 which classifications are emitted (Question 2)
- [x] 2.3 BR-U5-3 locator strategy and the unverified annotation (Question 3)
- [x] 2.4 BR-U5-4 no fixed waits, and what replaces them
- [x] 2.5 BR-U5-5 no literal credentials, tokens or environment URLs
- [x] 2.6 BR-U5-6 annotations carrying case id, Jira key and tags into JUnit XML
- [x] 2.7 BR-U5-7 deterministic regeneration and hand-edit protection
- [x] 2.8 BR-U5-8 the emission sequence
- [x] 2.9 Rule-to-requirement traceability
- [x] 2.10 Write `business-rules.md`

## Phase 3: Business Logic Model

- [x] 3.1 The emission orchestration, stage by stage
- [x] 3.2 The template set and what each template owns
- [x] 3.3 Locator selection, in order of preference
- [x] 3.4 Determinism: what is excluded from generated output and why
- [x] 3.5 Interaction with U1, U4 and U6
- [x] 3.6 The property surface
- [x] 3.7 Story coverage
- [x] 3.8 Write `business-logic-model.md`

## Phase 4: Validation

- [x] 4.1 Verify all 6 U5 stories are covered by a rule
- [x] 4.2 Verify U5 holds no copy of a domain algorithm
- [x] 4.3 Verify Security and Resiliency compliance at design level
- [x] 4.4 Validate content per `common/content-validation.md`
- [x] 4.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u5-automation-emission/functional-design/domain-entities.md`
- [x] `.../u5-automation-emission/functional-design/business-rules.md`
- [x] `.../u5-automation-emission/functional-design/business-logic-model.md`
