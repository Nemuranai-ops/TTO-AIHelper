# Domain Entities — U3 Requirements and Coverage

**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

One new persisted entity, one new table for reduction decisions, and two columns on
`coverage_item`. Migration **004**.

---

## New Entity: `gap`

FR-TRC-04, FR-COV-05 and FR-TRQ-05 all produce gaps. Until now they had nowhere to go.

```sql
CREATE TABLE gap (
    id           INTEGER PRIMARY KEY,
    category     TEXT    NOT NULL
                 CHECK (category IN ('untraceable-behaviour','uncovered-requirement',
                                     'boundaries-undetermined','reduced-depth',
                                     'rejected-duplicate','manual-only')),
    subject      TEXT    NOT NULL CHECK (length(trim(subject)) > 0),
    source_ref   TEXT    NOT NULL DEFAULT '',
    attempted    TEXT    NOT NULL DEFAULT '[]',
    feature_slug TEXT,
    detail       TEXT    NOT NULL DEFAULT '',
    detected_at  TEXT    NOT NULL,
    run_id       INTEGER,
    closed_at    TEXT,
    closed_by    TEXT,
    -- A gap closes when the thing that made it a gap stops being true: a Jira story
    -- is written, a boundary is stated. Recording how it closed is what lets a
    -- delta run distinguish "resolved" from "stopped being reported".
    CHECK (closed_at IS NULL OR closed_by IS NOT NULL)
);
CREATE INDEX idx_gap_category ON gap (category);
CREATE INDEX idx_gap_open ON gap (closed_at);
```

**Six categories, not four.** `rejected-duplicate` and `manual-only` belong to U4 and
are declared here so U4 needs no further migration — the constraint would otherwise
reject its writes, and discovering that mid-unit is avoidable by reading
`business-rules.md` §BR-1.5 and FR-RPT-02 now.

**Why a table rather than a flag on `testable_requirement`.** A gap is not a
requirement. Storing it there would oblige every downstream query to exclude it, and
the first query that forgot would generate test cases for behaviour explicitly ruled
untestable.

**Why gaps close rather than being deleted.** A gap that stops appearing might have
been resolved or might have stopped being detected. `closed_at`/`closed_by` separate
the two, which the delta pipeline needs.

---

## New Entity: `coverage_reduction`

```sql
CREATE TABLE coverage_reduction (
    id             INTEGER PRIMARY KEY,
    feature_id     INTEGER NOT NULL REFERENCES feature(id),
    model_version  INTEGER NOT NULL,
    technique      TEXT    NOT NULL,
    reason         TEXT    NOT NULL CHECK (length(trim(reason)) > 0),
    full_yield     INTEGER NOT NULL,
    reduced_yield  INTEGER NOT NULL,
    decided_by     TEXT    NOT NULL,
    decided_at     TEXT    NOT NULL,
    risk_band      TEXT,
    was_override   INTEGER NOT NULL DEFAULT 0,
    -- Reduction never increases coverage. A record claiming otherwise is a bug in
    -- D2, and the constraint catches it at the storage layer.
    CHECK (reduced_yield <= full_yield),
    -- A high-risk reduction is permitted but must be deliberate.
    CHECK (risk_band NOT IN ('high','critical') OR was_override = 1)
);
```

**Both yields are stored.** The gap report can then state how much coverage was given
up. A record holding only the reduced figure can say a feature is reduced but not by
how much, and "reduced" without a magnitude is not something anyone can weigh.

---

## Columns Added to `coverage_item`

| Column | Purpose |
|---|---|
| `model_version_int` | The monotonic integer from BR-U3-4.1. U1's `model_version` is TEXT and stays for compatibility |
| `content_hash` | The per-model hash the approval binds to, denormalised for cheap gate checks |

Adding rather than altering: U1's `model_version` column is written by U1's
repository, and changing its type would mean rewriting code that is complete and
approved for no behavioural gain.

---

## Computed Types

### `RiskSignals`

| Field | Type | Notes |
|---|---|---|
| `business_criticality` | int? | Agent-supplied; None means unavailable |
| `criticality_evidence` | str | The field, label or judgement it rests on |
| `complexity` | int? | Derived from rule and transition counts |
| `integration_surface` | int? | Derived from endpoint and dependency counts |
| `change_frequency` | int? | Derived from commits in 90 days; None when history is unavailable |

**None is never 0.** Zero commits and no commit data are different facts.

### `RequirementValidation`

`accepted`, `rejections` (subject, code, detail), and `derived_links`. Mirrors
`BatchValidation` from U1 so the agent meets one shape across units.

### `CoverageBuildResult`

`model_version`, `content_hash`, `items`, `forecast`, `gaps`, `reductions`,
`approval_invalidated` — the last being true when a rebuild changed the hash and a
prior approval no longer applies.

---

## Entities U3 Populates

| Entity | Notes |
|---|---|
| `testable_requirement` | With risk rating and factors |
| `coverage_item` | Including `is_required = false` rows |
| `trace_link` | Direct and `derived-from-commit` |
| `gap` | **New** |
| `coverage_reduction` | **New** |
| `unit_state` | Via U7, for the requirements and coverage stages |

---

## Integrity Rules

| Rule | Enforcement |
|---|---|
| A requirement id uses the `TR-` prefix | CHECK (U1) |
| A not-required coverage item plans zero cases | CHECK (U1) |
| A derived link records its selection basis | CHECK (U1) |
| A gap has a non-empty subject | CHECK (new) |
| A closed gap records who closed it | CHECK (new) |
| A reduction never increases yield | CHECK (new) |
| A high-risk reduction carries an override | CHECK (new) |
| A requirement is atomic | Domain validation (BR-U3-2.1) |
| Criticality without evidence is unavailable | Domain validation (BR-U3-1.2) |

Four of the nine are new, and three of those four are storage-level. The reduction
constraints in particular exist because a reduction is a decision the Test Lead will
be asked to defend later, and a record that cannot be defended is worse than none.
