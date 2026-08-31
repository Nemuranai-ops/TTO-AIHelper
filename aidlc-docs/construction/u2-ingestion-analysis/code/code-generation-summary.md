# Code Generation Summary — U2 Ingestion and Analysis

**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: Code Generation (Part 2 complete)
**Date**: 2026-08-29

---

## Result

All 16 steps executed. **462 tests passing**, 4 import contracts kept, all 8 U2
stories complete at their planned release depth. Benchmarks unaffected.

| Measure | Planned | Actual |
|---|---|---|
| New source files | 10 | 11 |
| Modified | 1 | 4 |
| Test files | 6 | 4 |
| Property tests | 10 | 11 |
| MCP tools added | 4 | 4 |

---

## Files

```
src/tto_testgen/
  adapters/sqlite/migrations/m003_discrepancy.py
  adapters/mcp_client.py                L6 McpClientSession
  adapters/paging.py                    L7 PagedFetcher
  adapters/sources/manifest.py          A6 - nine inference rules
  adapters/sources/atlassian.py         A3
  adapters/sources/bitbucket.py         A4
  adapters/sources/design_assets.py     A5
  domain/apimodel.py                    merge, pure
  domain/discrepancy.py                 detectors, pure
  services/ingestion.py                 S1
  services/analysis.py                  S2
  mcp/tools_u2.py                       4 tools + OpenAPI traversal
modified:
  adapters/sqlite/queries/__init__.py   write paths for 5 entities + discrepancy
  adapters/sqlite/repositories.py       the same, plus resources.id_for
  adapters/sqlite/migrations/__init__.py
  composition.py                        constructs AnalysisService
tests/
  unit/test_source_adapters.py  unit/test_domain_apimodel.py
  unit/test_domain_discrepancy.py  integration/test_u2_services.py
  properties/test_u2_properties.py
```

---

## Five Defects Found During Generation

### 1. A documented dependency claim was false

`tech-stack-decisions.md` stated PyYAML "arrives as a transitive dependency of the MCP
SDK already". It does not — `mcp` requires anyio, httpx, httpx-sse, pydantic,
pydantic-settings, sse-starlette, starlette and uvicorn, and no YAML parser.

The claim failed at the first import. PyYAML is now a declared direct dependency and
the document corrected. Asserting a dependency graph without checking it is how a
lockfile ends up disagreeing with the prose that explains it.

### 2. A business rule contradicted its own rationale

BR-U2-2.2 decided `low` when a description is short **and** criteria are absent — both
conditions, per the approved answer. The rationale paragraph beneath it argued that "a
long description without criteria is still thin", which is the case for the option
that was *not* chosen.

The code followed the decision; a test written from the rationale failed. The prose
was corrected to match the decision. **The contradiction was invisible in review** —
both halves read sensibly on their own.

### 3. Five entity tables had no write path

U1 created `journey`, `business_rule`, `api_endpoint`, `screen` and `ui_element`, and
`application-design.md` §6 assigned them to S2 through `FeatureRepository`. That
repository implemented only `feature`.

No U1 story needed the others, so the gap was invisible until U2 became the first unit
to populate them. Six methods added, plus `SqliteDiscrepancyRepository` for migration
003's table.

### 4. A foreign key violation the PRAGMA assertion caught

`resources.upsert()` returns the domain object it was given, which carries no id —
SQLite assigns that. `resource_id` fell back to `0`, and every artefact insert
violated the foreign key.

**This is precisely what L1's `foreign_keys = ON` read-back assertion exists for.**
Without it, SQLite would have silently written orphaned artefacts pointing at a
resource that does not exist, and the corpus would have looked fine until something
tried to trace an artefact to its source. Fixed with `resources.id_for(raw_ref)`,
added to the shared fake as well so U3-U8 develop against the same contract.

### 5. A resource returning nothing vanished from the report

`ingest_one` appended to `succeeded` only when something was stored and to
`skipped_unchanged` only when something was skipped. A resource that legitimately
returned zero records hit neither branch and disappeared.

That is the outcome an operator would most want to see: the query ran and found
nothing. Every non-failed resource now lands in exactly one bucket, and a property
test asserts the accounting.

---

## Deviations from Plan

| Deviation | Reason |
|---|---|
| 11 source files, not 10 | `mcp/tools_u2.py` is separate rather than appended to U7's `tools_write.py`. Eight units appending to one file is how a merge conflict becomes a weekly event |
| 4 modified files, not 1 | The five missing write paths (defect 3) and `resources.id_for` (defect 4) required touching the query and repository modules |
| 4 test files, not 6 | Adapter tests and domain tests consolidated where they shared fixtures; coverage is unchanged |
| One U1 test rewritten | `test_schema_has_the_designed_shape` asserted an exact global table count, which migration 003 broke. It now names U1's own objects, so later units adding tables no longer break a test that says nothing about U1's schema being intact |

---

## Story Completion

| Story | Status | Depth |
|---|---|---|
| US-ING-01 Declare inputs | **Complete** | R1 |
| US-ING-02 Jira and Confluence | **Complete** | R1 + R2 |
| US-ING-03 Bitbucket and API surface | **Complete** | R1 |
| US-ING-04 UI designs | **Complete** | R2 |
| US-ANA-01 Feature model | **Complete (features, rules)** | R1; journeys stored, live derivation deferred |
| US-ANA-02 Business rules and integration | **Complete** | R1 |
| US-ANA-03 API model | **Complete** | R1 |
| US-ANA-04 UI model | **Storage complete** | R2 storage; live Playwright derivation is agent work, deferred |

---

## Verification

| Check | Result |
|---|---|
| All 16 steps `[x]` | Yes |
| Migration 003 applies and reverses | Yes |
| Import contracts | 4 of 4 |
| U2 properties | 11 passing |
| A3 and A4 name no write tool | Asserted two ways: denylist, and an AST check that every tool string passed to `call` is a known read tool |
| U7 Agent Layer check with 4 new tools | Passing; the "future tools" list shrank by four |
| Full U1 and U7 suites | Passing |
| Benchmarks | 7 of 7 within budget |

**On the read-only assertion.** U2's NFR Design recorded a genuine weakening: L6
exposes a general `call`, so absence of write capability is no longer visible from a
signature. The compensating check turned out stronger than planned — rather than only
a denylist of today's write tools, an AST pass enumerates every tool name the adapters
actually pass and asserts each is on the known-read list. A denylist catches the write
tools that exist; this catches any tool that is not a known read.
