# Code Generation Plan — U2 Ingestion and Analysis

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: Code Generation (Part 1: Planning)
**Created**: 2026-08-29T18:06:00Z
**Status**: COMPLETE 2026-08-29 - all 16 steps executed

**This plan is the single source of truth for U2 Code Generation.**

---

## 1. Unit Context

### Stories (8)

| Story | Title | Release |
|---|---|---|
| US-ING-01 | Declare inputs in a resources file | R1 |
| US-ING-02 | Ingest Jira issues and Confluence pages | R1 / R2 |
| US-ING-03 | Ingest Bitbucket repositories and the API surface | R1 |
| US-ING-04 | Ingest UI designs from the screenshot folder | R2 |
| US-ANA-01 | Build the feature model and user journeys | R1 / R2 |
| US-ANA-02 | Extract business rules and integration points | R1 |
| US-ANA-03 | Build the API model | R1 |
| US-ANA-04 | Build the UI model with verified selectors | R2 |

### Dependencies

U1 and U7, both complete. U2 uses the ports, `unit_of_work`, `Result`, retry,
isolation, and U7's gates.

### Interfaces U2 exposes

| Consumer | Contract |
|---|---|
| U3 | Stored artefacts, feature model, business rules, API model, UI model — read through P1 |
| U8 | Bitbucket change ranges and commit records for delta detection |
| The agent | 4 new write tools, already named in U7's chat modes |

### Release depth

**R1 for the deterministic path**: `resources.md`, Jira ingest, Bitbucket repos and
endpoints, the API model, and the payload contracts for features and business rules.

**R2 items included in this pass**: Confluence ingest and the Figma adapter. Both are
adapters against protocols that already exist, and each is a few hours' work whose
absence would leave `resources.md` able to declare a resource type nothing can ingest.

**R2 items deferred**: journeys and the UI model with live selector verification.
Those depend on the agent exploring a running application, which is a different kind
of work from everything else here.

---

## 2. Code Location

```
src/tto_testgen/
  adapters/sqlite/migrations/m003_discrepancy.py
  adapters/mcp_client.py                    L6 McpClientSession
  adapters/paging.py                        L7 PagedFetcher
  adapters/sources/__init__.py              new package
  adapters/sources/manifest.py              A6 - resources.md, type inference
  adapters/sources/atlassian.py             A3
  adapters/sources/bitbucket.py             A4
  adapters/sources/design_assets.py         A5
  domain/discrepancy.py                     detectors, pure
  domain/apimodel.py                        merge algorithm, pure
  services/ingestion.py                     S1
  services/analysis.py                      S2
  mcp/tools_write.py                        + 4 U2 tools
tests/
  unit/test_manifest_inference.py
  unit/test_domain_apimodel.py
  unit/test_domain_discrepancy.py
  properties/test_u2_properties.py
  integration/test_ingestion_service.py
  integration/test_analysis_service.py
```

`domain/discrepancy.py` and `domain/apimodel.py` are **pure**: the merge algorithm and
the detectors take claims as arguments and return records. That keeps them inside the
import contract and property-testable without a network.

---

## 3. Generation Steps

16 steps.

### Phase A — Foundation

- [x] **Step 1**: Migration 003 — the `discrepancy` table and its index, with a
      tested reverse
      *Serves*: FR-ANA-08

- [x] **Step 2**: L6 `adapters/mcp_client.py` — session lifecycle, fail-fast spawn,
      timeout, credentials via child environment
      *Serves*: U2-NFR-REL-01, U2-NFR-SEC-02

- [x] **Step 3**: L7 `adapters/paging.py` — bounded paging with ceiling reporting
      *Serves*: US-ING-02, U2-NFR-SCL-02 to -05

### Phase B — Pure Domain

- [x] **Step 4**: `domain/apimodel.py` — the code-versus-spec merge per BR-U2-5
      *Serves*: US-ANA-03

- [x] **Step 5**: `domain/discrepancy.py` — the seven detectors per BR-U2-6
      *Serves*: US-ANA-02, US-ANA-04

- [x] **Step 6**: Unit tests for both, exhaustive over the merge cases
      *Serves*: US-ANA-03

### Phase C — Adapters

- [x] **Step 7**: A6 `sources/manifest.py` — the nine inference rules per BR-U2-1
      *Serves*: US-ING-01

- [x] **Step 8**: A3 `sources/atlassian.py` — Jira and Confluence, with `detail_level`
      *Serves*: US-ING-02

- [x] **Step 9**: A4 `sources/bitbucket.py` — repos, endpoints, files, log, changes
      *Serves*: US-ING-03

- [x] **Step 10**: A5 `sources/design_assets.py` — filename convention and manifest
      override per BR-U2-4
      *Serves*: US-ING-04

- [x] **Step 11**: Adapter unit tests, including the read-only posture assertion
      *Serves*: US-ING-01 to US-ING-04, U2-NFR-SEC-03

### Phase D — Services

- [x] **Step 12**: S1 `services/ingestion.py` — isolation, hash-skip, four-outcome
      report
      *Serves*: US-ING-01 to US-ING-04

- [x] **Step 13**: S2 `services/analysis.py` — payload validation, API derivation,
      discrepancy recording
      *Serves*: US-ANA-01 to US-ANA-04

- [x] **Step 14**: 4 write tools registered — `ingest_resources`, `analysis_upsert`,
      `api_model_derive`, `ui_model_upsert`
      *Serves*: all 8 stories

- [x] **Step 15**: Service integration tests and the 10 U2 property tests
      *Serves*: all 8 stories

### Phase E — Completion

- [x] **Step 16**: Verification and the code generation summary

---

## 4. Not In This Unit

| Item | Reason |
|---|---|
| Journeys and the live UI model | R2, and dependent on agent exploration of a running AUT |
| Requirement derivation | U3 |
| Delta detection | U8 uses A4; the adapter is built here, the detection is not |

---

## 5. Scope

| Measure | Estimate |
|---|---|
| New source files | 10 |
| Modified | 1 (`tools_write.py`) |
| Test files | 6 |
| Property tests | 10 |
| MCP tools added | 4 |

---

## 6. Verification at Completion

- [x] All 16 steps marked `[x]`
- [x] All 8 U2 stories marked `[x]` at their planned release depth
- [x] Migration 003 applies and reverses
- [x] Import contracts pass — `domain/apimodel.py` and `domain/discrepancy.py` stay pure
- [x] All 10 U2 properties passing
- [x] A3 and A4 name no Atlassian or Bitbucket write tool (U2-NFR-SEC-03)
- [x] U7's Agent Layer check passes with the 4 new tools registered
- [x] The full U1 and U7 suites still pass
