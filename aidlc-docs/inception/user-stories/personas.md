# Personas

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - User Stories
**Depth**: Working profiles
**Version**: 1.0
**Date**: 2026-08-28

---

## How to read these

Three roles operate TAAS. They are not variations of one user — they want different things, they
are accountable for different outcomes, and two of them hold approvals the others cannot bypass.
Where a design argument arises, these profiles are the tiebreaker.

Each profile states what the person is accountable for, what they approve, what makes their current
working day worse, and what "good" would look like. That is deliberately narrower than a full
persona narrative: enough to settle arguments, not so much that it becomes invented biography.

---

## P1: Test Analyst (Operator)

**Role**: Member of the test team. Runs TAAS day to day from VS Code.
**Primary epic exposure**: All seven pipeline stages. This is the person at the keyboard.

### Accountable for

- Naming the scope of every batch and driving the pipeline forward
- Reviewing generated test cases for correctness and sense before they enter the corpus
- Deciding when a feature's analysis is good enough to proceed

### Approves

- The ingested artefact inventory at the end of Stage 1
- The application model at the end of Stage 2
- The testable requirement set at the end of Stage 3
- Generated test cases, per batch, at Stage 5

### What makes the current day worse

- **Reading the same story four times.** Once to understand it, once to find the edge cases, once
  to write the cases, once to check nothing was missed. The re-reading is where the time goes.
- **Losing the thread.** Coming back after two days and not knowing which features were covered,
  which were half-covered, and which were skipped because a question was never answered.
- **Writing the thousandth case to a different standard than the first.** Consistency decays and
  the analyst is the one who notices, usually too late to fix cheaply.
- **Being unable to answer "is this tested?"** without reading the whole suite.

### What good looks like

- Naming a feature and a stage, and getting back work that is already to standard
- Every generated case obviously derived from something real, with the source one click away
- Being able to stop mid-batch, close the laptop, and resume on Monday with nothing lost
- Reviewing rather than authoring — judging what the system produced rather than producing it

### Design implications

- The system must never advance without the analyst's word (FR-BAT-01, FR-BAT-07)
- Status must be answerable on demand, not reconstructed from memory (FR-BAT-03)
- Every artefact must be readable in the editor without special tooling (NFR-USA-02)
- The system must say plainly what it could not determine rather than filling the gap
  with something plausible (NFR-USA-03) — an analyst who cannot trust the output has to
  re-derive it, which is the whole problem again

---

## P2: Test Automation Engineer

**Role**: Owns the automated suite after generation. Reviews generated code, pushes it to the test
team's Bitbucket repository, and configures the Jenkins jobs.
**Primary epic exposure**: Generate Automation, Handover Package, Reporting.

### Accountable for

- Whether the generated automation is maintainable by a human six months from now
- Pushing the suite to Bitbucket and wiring it into Jenkins
- Diagnosing failures once the suite runs in CI

### Approves

- Generated automation, per batch, at Stage 6
- The assembled handover project at Stage 7, before pushing it

### What makes the current day worse

- **Generated code nobody can maintain.** Machine-produced tests that work once, break on the
  first UI change, and are cheaper to delete than to fix.
- **Brittle selectors.** Deep CSS chains and XPath that encode the DOM's accidents rather than
  the interface's meaning.
- **Fixed waits.** `waitForTimeout` scattered through a suite, making it slow when it passes and
  flaky when it does not.
- **Failures that cannot be traced.** A red test in Jenkins with no route back to what it was
  meant to prove.
- **Structure that has to be reverse-engineered.** Having to read the generator to understand
  the generated code.

### What good looks like

- A project that looks like one a competent engineer wrote by hand — Page Object Model,
  conventional structure, no bespoke wrapper framework
- Locators built from roles and labels, verified against the running application
- Every test annotated with its case identifier and Jira key, so a CI failure has provenance
- `npm ci && npx playwright test --list` working on a clean machine with no modification
- Being able to hand-edit a file without the next generation run silently overwriting it

### Design implications

- Standard `@playwright/test`, no custom framework (FR-AUT-01)
- Role and label locators verified live (FR-AUT-03), no fixed waits (FR-AUT-09)
- Traceability annotations that survive into the execution report (FR-AUT-06)
- Hand-edit detection on regeneration (FR-AUT-11) — this is what makes the generated suite a
  starting point rather than a cage
- Both HTML and JUnit XML reporters configured (FR-AUT-08)

---

## P3: Test Lead

**Role**: Accountable to the wider organisation for whether the application is adequately tested.
**Primary epic exposure**: Establish Coverage Baseline, Reporting, Traceability.

### Accountable for

- Whether coverage is adequate for the risk the application carries
- Defending the coverage position to delivery managers and auditors
- Deciding where coverage may legitimately be thinner

### Approves

- **The coverage baseline at Stage 4.** This is the approval nobody else can give, and the one
  with the largest downstream consequence: a wrong coverage model multiplied across thousands of
  cases is expensive to unwind.
- Risk-based coverage reductions

### What makes the current day worse

- **Being asked "what's our coverage?" and having only an opinion.** Coverage that is asserted
  rather than computed cannot be defended.
- **Discovering a gap in production.** A feature nobody tested because nobody noticed it was
  untested.
- **Suites that grow without improving.** Case counts rising while risk coverage stays flat,
  because near-duplicates are cheaper to add than real scenarios.
- **Numbers with no derivation.** A report saying 6,000 cases, with no way to see how that
  number was arrived at or what it omits.

### What good looks like

- Coverage as a computed fact with the derivation visible, not a claim
- A gap report that names what is *not* covered, which is the more useful half
- Seeing the expected yield per feature *before* generation, while changing course is still cheap
- Being able to trace any requirement forward to its tests and any test back to its requirement
- Knowing that a case count reflects distinct scenarios, not padding

### Design implications

- The baseline gate is explicit and belongs to this role (FR-COV-06)
- Yield is forecast before generation, not discovered after (FR-COV-04)
- Volume derives from the coverage model and is never padded to a target (FR-TCG-07)
- The gap report is a first-class artefact, not an appendix (FR-RPT-02)
- De-duplication is deterministic and enforced (FR-TCG-05)
- Bidirectional traceability (FR-TRC-05)

---

## Persona-to-Epic Map

| Epic | P1 Test Analyst | P2 Automation Engineer | P3 Test Lead |
|---|---|---|---|
| E1 Input Sources | Primary | - | Informed |
| E2 Analyse and Understand | Primary | Informed | Informed |
| E3 Identify Testable Requirements | Primary | - | Informed |
| E4 Establish Coverage Baseline | Contributor | - | **Approver** |
| E5 Generate Test Cases | **Approver** | Informed | Informed |
| E6 Generate Automation | Informed | **Approver** | - |
| E7 Handover Package | Informed | **Approver** | - |
| E8 Traceability | Contributor | Consumer | **Primary consumer** |
| E9 Batch, State and Resumability | Primary | Informed | Informed |
| E10 Incremental Re-baselining | Primary | Contributor | Approver |
| E11 Reporting | Consumer | Consumer | **Primary consumer** |
| E12 Agent Layer | Primary | Contributor | - |
| E13 Technical Enablers | Indirect | Indirect | Indirect |

**Approver** means the stage cannot advance without this role. **Primary** means this role does
the work. **Consumer** means this role reads the output. **Informed** means visibility without
a decision right.

---

## Where the roles disagree, and how it resolves

Two tensions are worth stating, because they will surface during design.

**Volume versus adequacy.** The Test Lead wants defensible coverage; the Analyst wants a
reviewable workload. More cases serve the first and hurt the second. This resolves through
FR-TCG-05 and FR-TCG-07 — de-duplication and the prohibition on padding — which reduce volume
without reducing coverage, so the two goals stop competing.

**Automation breadth versus maintainability.** The Test Lead would automate everything; the
Automation Engineer maintains whatever is automated. This resolves through FR-TCG-06: the
automatability classifier decides per case with a recorded reason, so the argument is had once
per case against stated criteria rather than repeatedly as a matter of preference.
