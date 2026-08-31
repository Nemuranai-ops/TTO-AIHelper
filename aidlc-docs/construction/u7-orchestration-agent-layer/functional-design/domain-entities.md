# Domain Entities — U7 Orchestration and Agent Layer

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

U7 introduces no new persisted entity. It adds three computed types and three columns
to an existing table.

---

## Schema Change: `unit_state` gains three columns

The heartbeat mechanism (BR-U7-2) needs state U1's schema does not carry. This is
migration **002**, with a tested reverse per U1-NFR-DIST-04.

| Column | Type | Purpose |
|---|---|---|
| `leased_at` | TEXT | When the claim was made |
| `last_heartbeat` | TEXT | Last sign of life from the holding session |
| `lease_holder` | TEXT | Correlation id of the claiming session |

```sql
-- migration 002 UP
ALTER TABLE unit_state ADD COLUMN leased_at TEXT;
ALTER TABLE unit_state ADD COLUMN last_heartbeat TEXT;
ALTER TABLE unit_state ADD COLUMN lease_holder TEXT;

-- migration 002 DOWN
-- SQLite before 3.35 cannot DROP COLUMN, so the reverse rebuilds the table.
-- The rebuild is written explicitly rather than relying on the SQLite version,
-- because the reverse must work on whatever the operator's machine has.
```

**Why a migration rather than amending 001.** U1's migration 001 has been generated,
tested and approved. Amending it now would mean the approved artefact and the shipped
schema differ — the situation the versioning rule exists to prevent. The earlier
amendment to 001's index was made *during* U1's own generation, before approval, and
that distinction is what makes the two cases different.

---

## Computed Types

These are values the service returns. None is persisted.

### `LeaseStatus`

Classification of an `in-progress` unit, per BR-U7-2.1.

| Field | Type | Notes |
|---|---|---|
| `classification` | enum | `active`, `stale`, `orphaned-lock` |
| `age_minutes` | int | Since `last_heartbeat`, or `leased_at` if never refreshed |
| `holder` | str? | Correlation id, where known |
| `produced_so_far` | dict | From `metrics` — what the interrupted unit had achieved |
| `guidance` | str | The exact action that would clear it |

`produced_so_far` is what makes the report actionable rather than merely accurate:
an operator deciding whether to restart a unit needs to know whether it got nowhere
or nearly finished.

### `GateEvaluation`

Result of BR-U7-3.

| Field | Type | Notes |
|---|---|---|
| `is_open` | bool | All three conditions hold |
| `stage` | StageName | The stage being entered |
| `prior_stage` | StageName? | None for `ingest` |
| `failed_condition` | enum? | `not-completed`, `not-approved`, `content-changed` |
| `detail` | str | Human-readable statement of the failure |
| `remediation` | str | The exact action that opens it, naming the role if restricted |
| `approved_by`, `approved_at` | str? | Where an approval exists |

`failed_condition` is a distinct field rather than parsed from `detail`, so the agent
branches on the cause without reading prose.

### `StatusReport`

Result of BR-U7-4. Facts only.

| Field | Type | Notes |
|---|---|---|
| `units` | list[UnitStatusRow] | Sorted by `(unit_ref, stage_order)` — stable, carrying no readiness signal |
| `corpus` | dict | Active cases, features, requirements, coverage items |
| `generated_at` | str | |
| `business_rules` | dict | The tunables in force, from run metadata |

**`UnitStatusRow`**: `unit_ref`, `stage`, `state`, `changed_at`, `approved_by`,
`approved_at`, `gate_open`, `lease_status` (where `in-progress`), `metrics`.

There is deliberately no `next`, no `recommended`, no `ready` collection, and no
ordering by readiness. `business_rules` is included because a status report read
weeks later must show which similarity threshold and lookback window produced the
corpus it describes.

---

## Enumerations

| Enum | Values |
|---|---|
| `LeaseClassification` | `active`, `stale`, `orphaned-lock` |
| `GateFailure` | `not-completed`, `not-approved`, `content-changed` |
| `Role` | `test-analyst`, `test-automation-engineer`, `test-lead` |

`Role` becomes an enumeration here. U1 accepted it as a free string in
`stage_approve`, which was adequate for a thin wrapper but lets a typo — `testlead`
instead of `test-lead` — silently fail the coverage restriction closed. A typo
should be refused as an invalid role, not read as an unauthorised one.

---

## Stage Ordering

The pipeline order is data, not scattered conditionals:

```
ingest(0) -> analyse(1) -> requirements(2) -> coverage(3)
          -> cases(4) -> automation(5) -> handover(6)
```

`prior_stage(S)` returns the stage at index `n-1`, or `None` for `ingest`. Used by
gate evaluation and by status sorting, so the two cannot disagree about what order
the pipeline runs in.

---

## Agent Layer Artefacts

Configuration files, not database entities. Specified in
[frontend-components.md](frontend-components.md).

| Artefact | Path | Count |
|---|---|---|
| Repository instructions | `.github/copilot-instructions.md` | 1 |
| Path-scoped instructions | `.github/instructions/*.instructions.md` | 3 |
| Chat modes | `.github/chatmodes/*.chatmode.md` | 7 |
| Prompt files | `.github/prompts/*.prompt.md` | 6 |
| MCP registration | `.vscode/mcp.json` | 1 |

---

## Integrity Rules

| Rule | Enforcement |
|---|---|
| `in-progress` requires a lease | Existing `unit_state` CHECK (U1) |
| `failed` requires a reason | Existing `unit_state` CHECK (U1) |
| A lease implies `leased_at` | Domain construction |
| `last_heartbeat` is never earlier than `leased_at` | Domain construction |
| An approval implies both `approved_by` and `approved_at` | Domain construction |
| `(unit_ref, stage)` is unique | Existing UNIQUE constraint (U1) |

Only the two new lease invariants are added; the rest already hold from U1's schema.
