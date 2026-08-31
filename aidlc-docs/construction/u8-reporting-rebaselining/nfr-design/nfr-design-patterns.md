# NFR Design Patterns — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-31

Three patterns specific to U8, on top of the 49 inherited from U1, U7, U2, U3, U4, U5
and U6.

**The fewest of any unit**, which is the right shape for the last one: U8 reads what
seven others wrote, and almost every guarantee it needs was established by one of them.

---

## 1. Inherited

| Pattern | Use in U8 |
|---|---|
| P-U6-03 Degrade and report | Every uncomputable section — its **third** use |
| P-RES-03 Isolate per source | Bitbucket and Jira detected independently |
| P-U5-03 Deterministic rendering | Reports are committed and diffed |
| P-U4-04 Three-outcome emission | The shape `not_available` follows |
| P-SEC-03 Message sanitisation | Report content before it is written |
| P-U7-02 Read-only gate evaluation | Before a delta run — FR-DLT-06's gates |
| P-MNT-01 Dependency inversion | S8 and S9 depend on ports |
| P-MNT-02 Import contracts | Enforce that U8 holds no classification logic |

**P-U6-03 reaching a third use is the point of having named it.** U6 skipped a
verification tier; U2 reported a partial ingestion; U8 renders a report with a section
it could not compute. Three different problems, one shape: do what you can, say plainly
what you did not, let the operator decide.

---

## 2. P-U8-01: Guarded Baseline Advance

**Delivers**: U8-NFR-REL-04

The baseline is advanced by one function, and the delta service never writes
`head_commits` or `jira_watermark` directly.

```python
def advance_baseline(run_id: int, detection: DetectionResult, runs) -> bool:
    """Advance only when every source was reached.

    Returns whether it advanced, so the caller reports the fact rather than
    assuming it.
    """
    if detection.unavailable_sources:
        return False
    runs.record_baseline(run_id, detection.head_commits, detection.jira_watermark)
    return True
```

### Why this needs a pattern rather than an `if`

The rule is one line and its violation is **permanent and silent**.

| | A typical bug | This one |
|---|---|---|
| Surfaces as | A wrong value, a failed test | **Nothing** |
| Detected by | The next run, a report, a user | **Never** |
| Consequence | Corrected | Changes skipped for ever |

Advancing after a partial detection means the next run compares from the newer head, so
every change in the window the failed source covered is silently skipped. The corpus is
then wrong in a way no downstream check can reveal, because there is nothing to compare
against.

A conditional at the end of `delta_detect` would be correct today. It is also one `if`
that a later refactor can move above the early return, invert while tidying, or lose in
a branch — and nothing would fail.

### The property, not the example

Two or three hand-written cases would cover Bitbucket-down and Jira-down. The property
enumerates **every combination of source outcomes** and asserts the same rule, including
the combinations nobody thought to write:

```
PBT-U8-10: advance_baseline returns True only when unavailable_sources is empty
```

That is the shape this failure requires. An invisible bug cannot be caught by testing
what you expected.

---

## 3. P-U8-02: Declarative Section Registry

**Delivers**: U8-NFR-REL-01, -02, U8-NFR-MNT-03

Every report section is a row, not a method.

```python
SECTIONS = (
    Section("coverage-per-feature",
            precondition=has_approved_coverage,
            query=coverage_per_feature,
            producing_stage="coverage",
            derivation="sum of coverage_item.planned_count against non-obsolete cases"),
    Section("gap-summary",
            precondition=always,            # gaps are worth reporting from run one
            query=gaps_by_category,
            producing_stage=None,
            derivation="open gap rows by category, including empty categories"),
    ...
)
```

### It makes a negative testable

U8-NFR-REL-02 says every `not_available` section carries a reason and a producing
stage. With a method per section, a test can only check the sections someone remembered
to add to it — **which are exactly the sections that were never going to be the
problem.**

With a registry, the property enumerates it:

```
PBT-U8-2: for every Section in SECTIONS, a not_available result carries
          a reason and a producing stage
```

Adding a section is adding a row, and the row cannot be added without the fields.

### The derivation lives beside the query

`derivation` sits in the same row as the query that produces the figure. U8-NFR-MNT-03
requires every rendered number to carry one, and holding the two together means a
changed query with an unchanged derivation string is visible in a single diff hunk.

**A figure whose derivation describes a different calculation is worse than a figure
with none** — it is an auditable-looking number that cannot be audited.

---

## 4. P-U8-03: Source-Outcome Result

**Delivers**: U8-NFR-REL-03, and P-U8-01's precondition

Detection returns what succeeded *and* what did not, as data:

```python
@dataclass
class DetectionResult:
    changes: list[ChangedRef]
    head_commits: dict[str, str]
    jira_watermark: str | None
    unavailable_sources: list[tuple[str, str]]   # (source, reason)
```

### Why the failures are a field rather than a log line

P-U8-01 depends on knowing whether every source was reached. If that fact lived only in
a log, the guard would have to infer it — from an empty change list, say, which is
ambiguous: **no changes and no connection look identical from the outside.**

Making it a field means the guard reads a fact rather than deducing one, and the report
can name the unreachable source without re-deriving it.

This is the same reasoning that made U6's `skipped` a status rather than an absence, and
U2's not-found distinct from not-authorised. A missing thing and an unavailable thing
are different, and the type should say which.

---

## 5. Patterns Considered and Declined

| Pattern | Why not |
|---|---|
| **Caching report output** | The corpus changes constantly during a baseline, and a stale coverage figure is the one number that must never be wrong. The same objection made at U1, U3 and U4, at its sharpest here |
| **Incremental report assembly** | It would make a figure depend on which sections were rebuilt rather than on the corpus — the same objection that ruled out U3's incremental coverage rebuild |
| **A retry around change detection** | U1's retry already wraps the source adapters. A second layer would multiply the attempts and delay the honest partial result |
| **Advancing the baseline per source** | Superficially better than all-or-nothing, and it would leave the corpus in a state where one source is current and another is not — with no single point to compare from, and no way to report coherently what was seen |
| **An `EdgeBuilder` component** | A query and four boolean lookups S9 already holds the repositories for |
| **Rebuilding the traceability matrix here** | U4 owns it. Two implementations would give two answers, and the one in the report would be the untested one |

**The per-source baseline is the decline worth dwelling on**, because it is the most
plausible of the six. Advancing Jira's watermark while leaving Bitbucket's head
unchanged sounds strictly better than advancing neither — and it produces a baseline
that is not a point in time. Two sources at different positions cannot be reported
against coherently, and the next partial failure compounds it. All-or-nothing keeps the
baseline a single fact about a single moment.

---

## 6. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U8-NFR-PRF-01 to -03 | SQL aggregation, streamed writes, L17 |
| U8-NFR-PRF-04 | Indexed lookup of the last completed run |
| U8-NFR-PRF-05 | Inherited retry and timeout |
| U8-NFR-SCL-01 to -03 | SQL aggregation, never Python counting |
| U8-NFR-SCL-04 | L16 streamed rendering |
| U8-NFR-SCL-05 | Inherited caps |
| U8-NFR-REL-01, -02 | **P-U8-02**, P-U6-03 |
| U8-NFR-REL-03 | **P-U8-03**, P-RES-03 |
| U8-NFR-REL-04 | **P-U8-01** |
| U8-NFR-REL-05, -06 | `mark_obsolete`'s narrow signature; S9 has no create method |
| U8-NFR-REL-07 | **P-U5-03** |
| U8-NFR-REL-08 | L2 migration runner |
| U8-NFR-SEC-01, -02 | L16 rendering rules and path handling |
| U8-NFR-SEC-03 | L9 and L13 re-run over rendered output |
| U8-NFR-SEC-04 | **P2 source protocols declare no write method** |
| U8-NFR-SEC-05 | No `eval`; reports are strings |
| U8-NFR-MNT-01 | **P-MNT-02** import contracts |
| U8-NFR-MNT-02 | U4's matrix, rendered not rebuilt |
| U8-NFR-MNT-03 | **P-U8-02**, derivation beside the query |
| U8-NFR-MNT-04, -05 | Source inspection; no create method on S9 |

**All 28 U8 NFR requirements have a delivering pattern or component.**
