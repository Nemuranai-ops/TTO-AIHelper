# Unit of Work Story Map

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Units Generation
**Version**: 1.0
**Date**: 2026-08-28

All 55 stories assigned to exactly one unit. No story unassigned, none assigned twice.

---

## U1: Core Platform — 7 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-ENB-01 | Versioned SQLite schema and durability | R1/R2 | Indirect | A1, A2 |
| US-ENB-02 | MCP server with typed, validated tools | R1 | Indirect | M1, M2 |
| US-ENB-03 | Observability and failure isolation | R1 | Indirect | X2, X4, X5 |
| US-ENB-04 | Secrets and confidentiality controls | R1 | Indirect | X3, A2 |
| US-ENB-05 | Scale and performance | R2 | Indirect | A2, D4 |
| US-ENB-06 | Test suite including property-based tests | R2 | Indirect | D1-D8 |
| US-TRC-01 | Enforce the mandatory Jira key | R1 | P3, P1 | A1, D3, D7 |

**Why US-TRC-01 is here rather than in a traceability unit**: the Jira key rule exists in three
places at once — a SQLite `CHECK` constraint in A1, validation in D7, and resolution in D3. All
three must change together or the rule develops two behaviours.

---

## U2: Ingestion and Analysis — 8 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-ING-01 | Declare inputs in a resources file | R1 | P1 | A6, S1 |
| US-ING-02 | Ingest Jira issues and Confluence pages | R1/R2 | P1 | A3, S1 |
| US-ING-03 | Ingest Bitbucket repositories and the API surface | R1 | P1 | A4, S1 |
| US-ING-04 | Ingest UI designs from the screenshot folder | R2 | P1 | A5, S1 |
| US-ANA-01 | Build the feature model and user journeys | R1/R2 | P1 | S2 |
| US-ANA-02 | Extract business rules and integration points | R1 | P1 | S2 |
| US-ANA-03 | Build the API model | R1 | P1, P2 | S2, A4 |
| US-ANA-04 | Build the UI model with verified selectors | R2 | P1, P2 | S2 |

---

## U3: Requirements and Coverage — 10 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-TRQ-01 | Derive atomic testable requirements | R1 | P1 | S3, D7 |
| US-TRQ-02 | Rate requirement risk | R2 | P1, P3 | S3, D6 |
| US-TRQ-03 | Identify edge cases and failure scenarios | R2 | P1 | S3 |
| US-COV-01 | Build the coverage model | R1 | P3, P1 | S4, D2 |
| US-COV-02 | Derive coverage depth from test design techniques | R2 | P3 | S4, D2 |
| US-COV-03 | Forecast the yield before generation | R2 | P3, P1 | S4, D2 |
| US-COV-04 | Approve the baseline before generation | R1 | P3 | S4 |
| US-COV-05 | Apply risk-based coverage reduction | R3 | P3 | S4, D2 |
| US-TRC-02 | Derive Jira keys from commit history | R2 | P1, P3 | S3, D3 |
| US-TRC-03 | Route untraceable behaviour to the gap report | R2 | P1, P3 | S3, D3 |

---

## U4: Test Case Generation — 7 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-TCG-01 | Generate structured test cases with mandatory steps | R1 | P1 | S5, D1, D5, D7 |
| US-TCG-02 | Specify synthetic test data with equivalence classes | R1 | P1 | S5, D1 |
| US-TCG-03 | Detect duplicate and near-duplicate cases | R2 | P1, P3 | S5, D4 |
| US-TCG-04 | Classify automatability | R2 | P1, P2 | S5, D6 |
| US-TCG-05 | Derive corpus volume without padding | R2 | P3 | S5, D2 |
| US-TCG-06 | Publish reviewable sharded views with tags | R1 | P1 | S5, A8 |
| US-TRC-04 | Produce the bidirectional traceability matrix | R2 | P3 | S5, D3 |

---

## U5: Automation Emission — 6 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-AUT-01 | Generate a standard Playwright project with page objects | R1 | P2 | S6, A7 |
| US-AUT-02 | Generate resilient locators without fixed waits | R2 | P2 | S6, A7 |
| US-AUT-03 | Generate API tests in the same project | R1 | P2 | S6, A7 |
| US-AUT-04 | Annotate tests with tags and traceability | R1 | P2, P3 | S6, A7 |
| US-AUT-05 | Externalise configuration and configure reporters | R1 | P2 | A7 |
| US-AUT-06 | Regenerate safely and automate only what qualifies | R2 | P2 | S6 |

---

## U6: Handover — 3 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-HND-01 | Assemble a standalone Playwright project | R1 | P2 | S7, A7 |
| US-HND-02 | Verify integrity before declaring handover ready | R2 | P2 | S7 |
| US-HND-03 | Produce a handover manifest | R2 | P2, P3 | S7 |

---

## U7: Orchestration and Agent Layer — 8 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-BAT-01 | Name the batch scope | R1 | P1 | S10 |
| US-BAT-02 | Track unit state durably and transactionally | R1 | P1 | S10 |
| US-BAT-03 | Resume after interruption | R1 | P1 | S10 |
| US-BAT-04 | Stop at every stage gate | R1 | P1, P3 | S10 |
| US-AGT-01 | Establish repository instructions | R1 | P1 | Agent Layer |
| US-AGT-02 | Provide per-stage chat modes | R1 | P1 | Agent Layer |
| US-AGT-03 | Register the MCP servers | R1 | P1 | Agent Layer |
| US-AGT-04 | Provide path-scoped instructions and prompt files | R2 | P1, P2 | Agent Layer |

---

## U8: Reporting and Re-baselining — 6 stories

| Story | Title | Release | Persona | Components |
|---|---|---|---|---|
| US-RPT-01 | Produce the coverage report | R2 | P3 | S8, A9 |
| US-RPT-02 | Produce the gap report | R2 | P3 | S8, A9 |
| US-RPT-03 | Produce the automation report | R2 | P2, P3 | S8, A9 |
| US-DLT-01 | Detect changes since the last run | R3 | P1 | S9, A3, A4 |
| US-DLT-02 | Map changes to affected artefacts and classify them | R3 | P1, P3 | S9, D8 |
| US-DLT-03 | Retire obsolete cases without deleting them | R3 | P3 | S9 |

---

# Verification

## Assignment completeness

| Unit | Stories | Cumulative |
|---|---|---|
| U1 | 7 | 7 |
| U2 | 8 | 15 |
| U3 | 10 | 25 |
| U4 | 7 | 32 |
| U5 | 6 | 38 |
| U6 | 3 | 41 |
| U7 | 8 | 49 |
| U8 | 6 | 55 |

**55 of 55 assigned. 0 unassigned. 0 duplicated.**

## Epic-to-unit mapping

| Epic | Unit | Split? |
|---|---|---|
| E1 Input Sources | U2 | No |
| E2 Analyse and Understand | U2 | No |
| E3 Identify Testable Requirements | U3 | No |
| E4 Establish Coverage Baseline | U3 | No |
| E5 Generate Test Cases | U4 | No |
| E6 Generate Automation | U5 | No |
| E7 Handover Package | U6 | No |
| **E8 Traceability** | **U1, U3, U4** | **Yes — 3 units** |
| E9 Batch, State and Resumability | U7 | No |
| E10 Incremental Re-baselining | U8 | No |
| E11 Reporting | U8 | No |
| E12 Agent Layer | U7 | No |
| E13 Technical Enablers | U1 | No |

**E8 Traceability is the only split epic, and the split is deliberate.** Traceability is not a
pipeline stage — it is a property the whole pipeline maintains. Its four stories land where the
enforcement actually happens: the constraint and domain resolver in U1 (US-TRC-01), key derivation
and gap routing at requirement creation in U3 (US-TRC-02, US-TRC-03), and matrix construction over
the corpus in U4 (US-TRC-04). Forcing it into one unit would create a unit that owns a rule it
cannot enforce, because enforcement lives in the schema and in the services that write.

## Release distribution across units

| Unit | R1 stories | R2 stories | R3 stories |
|---|---|---|---|
| U1 | 5 | 2 | 0 |
| U2 | 6 | 2 | 0 |
| U3 | 3 | 6 | 1 |
| U4 | 3 | 4 | 0 |
| U5 | 4 | 2 | 0 |
| U6 | 1 | 2 | 0 |
| U7 | 7 | 1 | 0 |
| U8 | 0 | 3 | 3 |

Counts treat a story spanning two releases as belonging to its earliest.

**Every unit except U8 contributes to R1.** That is what makes the walking skeleton a genuine slice
rather than a subset — the first pass touches almost the whole system thinly, which is precisely
where architectural mistakes become visible while they are still cheap to correct.

## Persona coverage per unit

| Unit | P1 Analyst | P2 Automation Engineer | P3 Test Lead |
|---|---|---|---|
| U1 | 1 | 0 | 1 |
| U2 | 8 | 2 | 0 |
| U3 | 6 | 0 | 7 |
| U4 | 6 | 1 | 3 |
| U5 | 0 | 6 | 1 |
| U6 | 0 | 3 | 1 |
| U7 | 8 | 1 | 1 |
| U8 | 2 | 1 | 6 |

Counts include secondary personas, so rows may exceed the unit's story count.

**The reviewer for each unit is legible from this table.** U5 and U6 are reviewed by the Automation
Engineer, U3 and U8 by the Test Lead, U2 and U7 by the Test Analyst. That alignment is a consequence
of the pipeline-capability grouping rather than something imposed on top of it, which is the main
practical argument for that grouping.
