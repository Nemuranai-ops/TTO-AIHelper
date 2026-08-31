# Business Logic Summary — U1 Core Platform

**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Code Generation (Steps 4-9)
**Date**: 2026-08-29

---

## Files Created

| Path | Component | Purpose |
|---|---|---|
| `src/tto_testgen/domain/model.py` | D1 | 18 entities, 11 value objects, 10 enumerations, construction invariants, serialisation |
| `src/tto_testgen/domain/identity.py` | D5 | Identifier allocation, stability, sequence rebuild |
| `src/tto_testgen/domain/similarity.py` | D4 | Normalisation, shingles, Jaccard, bucketing, BR-1.4 override |
| `src/tto_testgen/domain/traceability.py` | D3 | Jira key enforcement, commit derivation, matrix |
| `src/tto_testgen/domain/validation.py` | D7 | The ten-check pipeline, batch validation |
| `src/tto_testgen/domain/coverage.py` | D2 | ISTQB depth, yield forecast, reduction |
| `src/tto_testgen/domain/classification.py` | D6 | Weighted risk, ten-rule automatability list |
| `src/tto_testgen/domain/impact.py` | D8 | Delta impact classification, scale reporting |
| `tests/unit/test_domain_rules.py` | — | 84 example-based tests covering BR-1 to BR-9 |
| `tests/properties/strategies.py` | — | Domain-specific Hypothesis strategies (PBT-07) |
| `tests/properties/test_domain_properties.py` | — | The 16-property surface |

---

## Verification

| Check | Result |
|---|---|
| Full test suite | **155 passing** |
| Property surface | **16 of 16** present and passing |
| Import contracts | **3 of 3** kept — domain imports nothing outside stdlib and domain |
| Business rules implemented | **BR-1 to BR-9**, all 9 |

The import contract is the one that protects the rest. The property suite runs
against `domain/` with no database, no network and no fixtures — the moment a domain
module imports an adapter, that stops being true, and `lint-imports` fails the build
before it can happen.

---

## Behaviours Worth Recording

These are places where the implementation encodes a decision that is easy to get
wrong and hard to notice afterwards.

**Construction invariants remove downstream checking.** A `TestCase` with an empty
step list cannot be constructed. Nothing later has to ask whether the steps are
present, because a case that violated the rule never existed. The same applies to a
step without an expected result, test data without an equivalence class, and a
`derived-from-commit` link without a selection basis.

**The equivalence-class override short-circuits before the score.** BR-1.4 is
checked first, so a differing class returns DISTINCT without computing similarity.
That makes the override unconditional rather than a correction applied afterwards,
and it is cheaper. Property 10 asserts it holds at threshold 0.0, which is the
strongest form of the claim.

**Unknown-key rejection is distinguished from no-key rejection.** Both fail the
traceability rule, but the remediation differs: ingest the issue, versus add a link.
Collapsing them into one code would make the agent's next action a guess.

**Partial risk ratings keep the ratio among known signals.** An unavailable factor
leaves both numerator and denominator. Scoring it zero instead would let an
unmeasured requirement read as low risk, which is precisely backwards. The example
in the tests is stark: the same two known factors produce 84/critical as a partial
rating and 65/high when the two missing factors are supplied as low values.

**Not-required coverage rows are stored, not omitted.** An absent row and a
deliberate exclusion look identical to a reviewer. Property 14 asserts every
requirement has at least one coverage item, required or not.

**Batch validation collects every failure.** At batch sizes of forty, failing on the
first fault would force as many correction rounds as there are faults. Stage A (the
gate) still stops the batch, because a closed gate makes every case in it moot.

**The commit lookback window is load-bearing.** Without it, a five-year-old refactor
becomes the recorded provenance of today's behaviour — a link that is technically
present and substantively meaningless, which is worse than an honest gap because it
satisfies the rule while defeating its purpose.

---

## Deviations from Plan

**One dependency change.** `cyclonedx-bom==5.1.1` was removed from the dev extras.
It pins `cyclonedx-python-lib>=8` while `pip-audit==2.7.3` pins `<8`, so the two
cannot coexist. `pip-audit` emits CycloneDX itself via `--format cyclonedx-json`, so
one tool covers both the vulnerability scan and the SBOM required by NFR-SEC-09 —
and carrying two tools for one job would have breached the same requirement's
no-unused-dependencies rule.

**Two test-side renames.** Domain classes named `TestCase`, `TestStep`, `TestData`
and `TestType` collide with pytest's `Test*` collection prefix, and the `test_cases`
Hypothesis strategy collided with the `test_*` function prefix. Both are aliased at
the point of import in the test files. The production names are unchanged, because
they are the right domain names and the collision is a test-runner concern.

---

## Story Progress

| Story | Status after Phase B |
|---|---|
| US-ENB-01 Schema and durability | Domain entities complete; schema in Phase C |
| US-ENB-05 Scale and performance | Bucketing implemented; benchmark in Phase E |
| US-ENB-06 Test suite including PBT | **Complete** — 155 tests, 16 properties |
| US-TRC-01 Mandatory Jira key | Domain enforcement complete; constraint in Phase C |
