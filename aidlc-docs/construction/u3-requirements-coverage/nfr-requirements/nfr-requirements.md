# NFR Requirements — U3 Requirements and Coverage

**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## 1. Inherited, Unchanged

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, U1's 37 project
NFRs, and U2's scale figures. **Nothing re-opened.**

**U3 owns no project NFR outright** — the first unit for which that is true. It is a
consequence of U3 being orchestration over logic U1 already built: the coverage
arithmetic, the risk formula and the traceability rules all carry their own
requirements, and they are U1's.

---

## 2. Scalability

| ID | Requirement | Measurement |
|---|---|---|
| U3-NFR-SCL-01 | Handle 1,500 testable requirements across 150 features | Benchmark |
| U3-NFR-SCL-02 | `coverage_item` holds one row per test type per requirement, including not-required | Row count matches requirements x test types |
| U3-NFR-SCL-03 | Remain responsive at 15,000 coverage items | Benchmark |
| U3-NFR-SCL-04 | Coverage queries are indexed on `requirement_id` and `is_required` | `EXPLAIN QUERY PLAN` asserted |
| U3-NFR-SCL-05 | The `gap` table is queryable by category and open/closed state | Indexed |

### On the not-required rows

At 1,500 requirements and nine test types, `coverage_item` reaches **13,500 rows
before a single test case exists**, and roughly two-thirds are `is_required = false`.

Dropping them would cut the table by two-thirds and destroy BR-2.6. Those rows exist
so a *deliberate exclusion* stays distinguishable from an *oversight* — which is the
difference between a coverage model that can be defended and one that merely exists.

13,500 rows is small for SQLite. Trading a load-bearing property for a saving nothing
needs would be the wrong exchange, and it is worth stating plainly because the
temptation returns whenever someone looks at the row count without knowing why.

---

## 3. Performance

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U3-NFR-PRF-01 | Coverage build for one feature at 100 requirements | < 5 s | Benchmark |
| U3-NFR-PRF-02 | Whole-project rebuild at 1,500 requirements | < 60 s | Benchmark |
| U3-NFR-PRF-03 | Coverage content hash over 15,000 items | < 2 s | Benchmark |
| U3-NFR-PRF-04 | Requirement batch validation for 100 candidates | < 3 s | Benchmark |
| U3-NFR-PRF-05 | Commit history is fetched at most once per distinct file per run | Call counting |

**Why five seconds and not one.** A per-feature build happens interactively while the
operator waits, so seconds matter. One second would push the design toward caching the
derivation — the kind of complexity U1 declined for good reason, and for a saving of
four seconds on an operation performed a few times per feature.

A whole-project rebuild is rare and a minute is tolerable.

---

## 4. Reliability

| ID | Requirement | Measurement |
|---|---|---|
| U3-NFR-REL-01 | A requirement batch is accepted entirely or not at all | Asserted |
| U3-NFR-REL-02 | Every failure in a rejected batch is reported together | Asserted |
| U3-NFR-REL-03 | A gap is not a rejection and does not fail its batch | Asserted |
| U3-NFR-REL-04 | An unchanged rebuild preserves the existing version and approval | Asserted |
| U3-NFR-REL-05 | A changed rebuild reports `approval_invalidated` rather than leaving it to be discovered | Asserted |
| U3-NFR-REL-06 | Migration 004 ships a tested reverse | `verify_reversibility` |

**U3-NFR-REL-05 is the one that saves an operator's afternoon.** Without it, a rebuild
that invalidated the approval looks successful, and the failure surfaces later when
the cases gate refuses — at which point it reads as a bug rather than a consequence.

---

## 5. Commit Index Bounds

| ID | Requirement | Value |
|---|---|---|
| U3-NFR-IDX-01 | Distinct files per run | 200, configurable |
| U3-NFR-IDX-02 | Commits held per file | 500, configurable |
| U3-NFR-IDX-03 | Reaching either bound is reported, not silent | Asserted |
| U3-NFR-IDX-04 | Files beyond the bound route to gaps stating the reason | Asserted |

**Bounded because the unbounded version fails on the repository that most needs it.**
A large monorepo with deep history would hold the whole thing in memory. A gap saying
"commit index limit reached for src/legacy/" is honest; a run that slows to a crawl
and then succeeds anyway is not.

---

## 6. Security

| ID | Requirement | Source |
|---|---|---|
| U3-NFR-SEC-01 | Only the Test Lead approves the coverage baseline, delegated to U7 | FR-COV-06 |
| U3-NFR-SEC-02 | A reduction records actor, reason, risk band and override flag | NFR-SEC-13 |
| U3-NFR-SEC-03 | An atomicity override records its actor | NFR-SEC-13 |
| U3-NFR-SEC-04 | No requirement or coverage item is stored without a resolvable Jira key | FR-TRC-01 |

**U3-NFR-SEC-01 delegates rather than re-implements.** One place decides who may
approve what, so U3, U4, U5 and U6 cannot drift apart on it.

---

## 7. Maintainability

| ID | Requirement | Measurement |
|---|---|---|
| U3-NFR-MNT-01 | The atomicity heuristic has a documented escape: `force_atomic` | Asserted |
| U3-NFR-MNT-02 | Every override records its actor and the statement it applied to | Asserted |
| U3-NFR-MNT-03 | Overrides are queryable, so clustering is visible | Indexed or reportable |
| U3-NFR-MNT-04 | U3 contains no coverage arithmetic and no risk formula | Source inspection |
| U3-NFR-MNT-05 | Risk banding thresholds live in one place | Source inspection |

**On the escape.** A heuristic with no escape becomes a wall the agent works around by
mangling wording. One with an *unrecorded* escape becomes a habit nobody notices. The
override is available and logged, so if it clusters the heuristic needs work — and
that is visible rather than inferred.

**U3-NFR-MNT-04 is worth asserting rather than trusting.** The coverage formula and
the risk weights are U1's. A copy here would drift, and the drift would be silent
because both would produce plausible numbers.

---

## 8. Extension Compliance

**Security Baseline**: SECURITY-06 via U3-NFR-SEC-01; SECURITY-13 via -SEC-02 and
-SEC-03. All others inherited. **No blocking findings.**

**Resiliency Baseline**: RESILIENCY-12 inherited; migration 004 triggers the existing
rehearsal requirement. **No blocking findings.**

**Property-Based Testing (partial)**: PBT-03 extended with the 10 U3 properties,
three of which pin down what "modifying an approved model" means. **No blocking
findings.**

---

## 9. Open Items

**None.** AS-02 remains outstanding from U1 and is unaffected.
