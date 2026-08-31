# Code Generation Summary — U4 Test Case Generation

**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: Code Generation (Part 2)
**Version**: 1.0 | **Date**: 2026-08-30

All 18 steps executed. **675 tests pass**, 4/4 import contracts kept, 13 benchmarks
within budget.

---

## 1. What Was Built

| File | Content |
|---|---|
| `adapters/sqlite/migrations/m005_emitted_view.py` | Migration 005, with a tested reverse |
| `domain/privacy.py` | **L9** — five patterns, the allow-list, the Luhn and issuer checks |
| `adapters/view_renderer.py` | **L10** — deterministic rendering, three-way emission |
| `services/generation.py` | **S5** — stages A–F, deferred allocation, ordered commit |
| `mcp/tools_u4.py` | `testcases_upsert`, `views_emit`, `volume_report` |

**Modified**: `ports/repositories.py` (`EmittedViewRepository`, `stream_links`,
`coverage.get`, `volume_for_feature`, `for_feature_slug`), `adapters/sqlite/
repositories.py`, `queries/__init__.py`, `domain/validation.py`, `platform/result.py`,
`platform/config.py`, `mcp/tools_read.py`, `composition.py`.

**Tests**: `test_domain_privacy.py` (46), `test_view_renderer.py` (24),
`test_u4_generation.py` (17), `test_u4_properties.py` (14), 4 new benchmarks.

---

## 2. Measured

| Budget | Target | Measured |
|---|---|---|
| 200-case batch commit | < 10 s | **0.04 s** for 2,000 cases |
| Duplicate selection, crowded bucket | < 50 ms | **3.7 ms** against 2,000 candidates |
| One feature's views | < 2 s | **0.18 s** for 500 cases |
| Matrix construction | < 30 s | **< 0.01 s** over 12,000 links |

**The duplicate figure is the one worth reading carefully.** U1 reported 0.29 ms
selecting 8 candidates from 10,000 — but that corpus distributed evenly across
buckets because it was generated to. The new benchmark crowds 2,000 cases into one
bucket, which is what a busy feature actually looks like. 3.7 ms is 13× slower than
U1's number and 13× inside the budget, and it is the honest one.

---

## 3. Defects Found and Fixed

### L9 rejected values the team is told to use

Three separate false positives, all caught by the tests written from the allow-list
rather than from the patterns:

| Value | Wrongly reported as | Cause | Fix |
|---|---|---|---|
| `000-12-3456` | phone | The phone pattern is broader than the SSN one | Phone yields to any recognised shape |
| `2026-08-30T12:00:00Z` | phone | Open-ended digit run | Three specific phone shapes, not one |
| `378282246310005` | phone | An allow-listed Amex card is 15 digits | Same fix |
| `900000000000001` | card | A batch id that happens to pass Luhn | Issuer range 2–6 required |

**The last one is the instructive one.** Roughly one arbitrary digit string in ten
passes Luhn, so Luhn alone is not a card test. Every payment scheme issues from major
industry identifier 2–6, so requiring one costs no detection and removes the whole
class. Without it the detector fires on batch ids, and a check that fires on ordinary
test data is a check somebody turns off.

### `TestCase` is frozen and validates its own identifier

The design called for constructing a case, validating it, and allocating an
identifier afterwards. `TestCase` rejects an empty id at construction, and sequence 0
is out of range, so neither obvious placeholder worked.

Resolved with a provisional identifier that stage F always replaces, and the frozen
dataclass turned out to help: `dataclasses.replace` makes the validated case and the
stored case visibly different values, so nothing can accidentally write the first.

### The traceability link carried no resolved key

`_construct` built `TraceLink` without `resolved_jira_key`, which the domain refuses
for any link type that resolves one. Fixed by carrying the agent's claimed key into
the field — the claim, not the verdict. D7 then checks it against the ingested set,
which is what separates "this case cites PAY-12" from "PAY-12 exists".

### Three property tests filtered themselves into uselessness

`assume(finding is not None)` over random text produced 0 useful examples in 50.
Rewritten to generate values that must be refused — including a Luhn completion
function, because filtering random digit strings for validity discards nine in ten.

---

## 4. Corrections to Approved Documents

**P-U4-01's rationale was wrong about the mechanism.** The design argued that a
rollback would leave an identifier counter stranded. Implementation showed U1 built
the sequence as a *derived* value — `SequenceState.from_existing` rebuilds it from
the stored identifiers — so a rollback restores it exactly and that half of the
concern was moot.

The pattern still holds, on a sharper argument: allocating during construction would
store TC-1, TC-3, TC-5 for a batch of five with two rejections. **Two permanent holes,
and a question the operator asks on every review for the life of the corpus.**
`nfr-design-patterns.md` now records both the correction and the surviving reason.

**P-U4-05 names `stream_links()`**, added alongside `all_links()` rather than
replacing it. Two existing callers in `tools_read.py` filter and cap in memory anyway,
and changing a port signature to serve one new caller rewrites working code for no
gain.

---

## 5. Enforcement Made Structural

Consistent with every prior unit:

| Rule | How it cannot be violated |
|---|---|
| No caller-supplied identifier | `CasePayload` has no id field |
| No personal data in test data | D7 stage B, before anything is stored |
| Gapless numbering | Allocation runs after every rejection is known |
| Foreign-key order | `foreign_keys = ON`, undeferred — wrong order fails outright |
| No domain algorithm copied into U4 | `.importlinter`, checked in CI |
| Views under `generated/` | Slug validated against `^[a-z0-9][a-z0-9-]*$`, refused not sanitised |
| A narrowed privacy pattern set | Logged at startup and carried in the run fingerprint |

**One new error code**: `REJECTED_PERSONAL_DATA`, the 11th rejection. Reusing an
existing code was the alternative and would have misdescribed the fault — the
remediation is to substitute a synthetic value, which no other code's guidance says.

---

## 6. Verification

- [x] All 18 steps `[x]`
- [x] All 7 U4 stories delivered
- [x] Migration 005 applies and reverses (`verify_reversibility` → True)
- [x] Import contracts: 4 kept, 0 broken
- [x] 14 U4 properties passing
- [x] A rejected batch allocates nothing — asserted directly
- [x] A hand-edited view survives a re-emission, including when the corpus also moved
- [x] Two renders of unchanged content are byte-identical
- [x] Agent Layer check passes with 3 more tools registered
- [x] U1, U7, U2 and U3 suites still pass — 675 total
- [x] All four U4 budgets met with wide margins
