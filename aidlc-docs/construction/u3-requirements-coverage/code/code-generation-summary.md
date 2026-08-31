# Code Generation Summary — U3 Requirements and Coverage

**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: Code Generation (Part 2 complete)
**Date**: 2026-08-30

---

## Result

All 15 steps executed. **566 tests passing**, 4 import contracts kept, all 10 U3
stories complete. Benchmarks pass, including the new coverage build budget.

| Measure | Planned | Actual |
|---|---|---|
| New source files | 7 | 7 |
| Modified | 3 | 5 |
| Test files | 4 | 5 |
| Property tests | 10 | 12 |
| MCP tools added | 4 | 4 |

---

## Files

```
src/tto_testgen/
  adapters/sqlite/migrations/m004_gaps_and_reductions.py
  adapters/commit_index.py              L8, bounded, three failure modes kept apart
  domain/coverage_hash.py               canonical form, pinned separators
  domain/atomicity.py                   conservative heuristic with a logged escape
  services/requirements.py              S3
  services/coverage.py                  S4
  mcp/tools_u3.py                       4 tools
modified:
  adapters/sqlite/queries/__init__.py    gap, reduction, coverage versioning
  adapters/sqlite/repositories.py        GapRepository, ReductionRepository, versioning
  adapters/sqlite/migrations/__init__.py
  composition.py                         constructs S3 and S4
  tests/benchmark/…                      + coverage build budget
tests/
  unit/test_coverage_hash.py  unit/test_domain_atomicity.py
  unit/test_commit_index.py   integration/test_u3_services.py
  properties/test_u3_properties.py
```

---

## The Defect That Mattered

### Every rebuild would have invalidated the approval

`build_model` allocated coverage item ids starting from `len(existing)`. On a rebuild
the items therefore got **new ids**, which changed the content hash, which invalidated
the Test Lead's approval — on a rebuild that changed nothing.

That is precisely the failure BR-U3-4.1 was written to prevent: an operator re-running
coverage to check something would have cost the Test Lead a fresh approval of an
unchanged model, and after the second or third time they would have stopped reading
before approving.

The fix is `sequence_start=0` always. A coverage item is identified by its
(requirement, test type) pair, so the same requirements in the same order must produce
the same ids — and `upsert_many` overwrites by id, so collisions are the intent rather
than something to avoid. Requirement order is stable because the query orders by id.

**Caught by `test_an_unchanged_rebuild_keeps_the_version`**, which existed only because
BR-U3-4.1 stated the guarantee explicitly enough to test.

### Two fixture errors the foreign keys caught

Both were tests referencing a resource that did not exist. Neither was a production
defect, and both are worth noting because they are the second and third time the
`foreign_keys = ON` assertion from U1's L1 has caught something. Without it these would
have written orphaned rows that looked fine until something tried to follow them.

---

## Deviations from Plan

| Deviation | Reason |
|---|---|
| 5 modified files, not 3 | `composition.py` and the benchmark suite were not in the plan's file list but both needed changes to wire and measure the new services |
| 5 test files, not 4 | `test_commit_index.py` was split out from the adapter tests; L8 has enough distinct behaviour — three failure modes, two bounds — to warrant its own file |
| 12 properties, not 10 | Two extras on atomicity determinism and the force-atomic escape, both cheap and both guarding behaviour the services depend on |
| 9 write tools registered at composition | U7's 5 plus U3's 4. U2's four need live MCP sessions and are wired at ingestion time, which the composition root now documents |

---

## Verification

| Check | Result |
|---|---|
| All 15 steps `[x]` | Yes |
| All 10 U3 stories complete | Yes |
| Migration 004 applies and reverses, including the table rebuild | Yes |
| Migration 004 constraints reject | 4 of 4 verified: yield increase, high-risk without override, blank gap subject, closed gap without closer |
| Import contracts | 4 of 4 |
| U3 properties | 12 passing |
| U3 holds no coverage arithmetic or risk formula | Asserted by source inspection |
| Test Lead restriction delegated, not re-implemented | `approve_baseline` calls U7's `stage_approve` |
| U7 Agent Layer check with 4 more tools | Passing; the "future tools" list is now empty |
| Full U1, U7, U2 suites | Passing |
| Coverage build budget | Under 5 s per feature at 100 requirements |

**The Agent Layer "future tools" list is now empty.** Every tool named in U7's chat
modes is registered by some unit. U4, U5 and U6 will add to both sides together, and
the check will catch it if they do not.
