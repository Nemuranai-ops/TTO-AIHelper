# Domain Entities — U4 Test Case Generation

**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

**No new persisted entity, and no migration.** U4 is the first unit for which that is
true, and it is the expected outcome: U1 designed the corpus schema, and U4 is the
unit that fills it.

One table gains rows it has never held — `test_case`, `test_step`, `test_data` and
`automated_test` have existed since migration 001 and been exercised only by tests.

---

## One New Table: `emitted_view`

Hand-edit detection (BR-U4-5.2) needs to remember what was written.

```sql
CREATE TABLE emitted_view (
    id            INTEGER PRIMARY KEY,
    path          TEXT    NOT NULL UNIQUE,
    feature_slug  TEXT    NOT NULL,
    content_hash  TEXT    NOT NULL CHECK (length(content_hash) = 64),
    emitted_at    TEXT    NOT NULL,
    case_count    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_emitted_view_feature ON emitted_view (feature_slug);
```

Migration **005**.

**Why a table and not a sidecar file.** A `.hash` file beside each view would be
edited or deleted along with the view it guards, and a guard that disappears with what
it guards is not a guard. The database is where the corpus lives; the record of what
was emitted from it belongs there too.

---

## Computed Types

### `CasePayload`

What the agent submits. Validated by Pydantic at the MCP boundary, then by D7.

| Field | Type | Supplied by |
|---|---|---|
| `coverage_item_id` | str | Agent |
| `title`, `test_type`, `priority`, `preconditions` | str | Agent |
| `steps` | list[{ordinal, action, expected}] | Agent |
| `test_data` | list[{field, value, equivalence_class, boundary_relation?}] | Agent |
| `tags` | list[str] | Agent |
| `trace_links` | list[{type, jira_key, evidence}] | Agent |
| `requires_visual_judgement` and three siblings | bool, default false | Agent |
| `referenced_screen_ids` | list[int] | Agent, for locator signals |

The identifier is **absent from this type**. There is no field for it, so a caller
cannot supply one by accident — D7's `REJECTED_SELF_SUPPLIED_ID` catches the
deliberate case, and the type catches the careless one.

### `CaseBatchReport`

| Field | Meaning |
|---|---|
| `accepted` | Case ids |
| `rejections` | Case ref, code, detail, and for duplicates the matched id and score |
| `gaps_recorded` | Duplicates and manual-only cases written to the gap table |
| `automatability` | Counts by class |
| `planned_vs_generated` | Per coverage item |
| `view_manifest` | Files written, skipped and hand-edited |

### `ViewManifest`

`written`, `unchanged`, `hand_edited` — three outcomes, not two.

**`unchanged` is separate from `written`** for the same reason U2's ingestion report
separates skipped from succeeded: a re-emission that writes nothing is exactly right
and indistinguishable from a broken one unless the report says so.

### `TraceMatrixView`

`forward`, `reverse`, `uncovered`, `counts_by_link_type`, `format`. Built on demand,
never stored.

---

## Entities U4 Populates

| Entity | First written by U4? |
|---|---|
| `test_case` | **Yes** |
| `test_step` | **Yes** |
| `test_data` | **Yes** |
| `trace_link` | No — U3 writes requirement links; U4 adds case links |
| `gap` | No — U4 adds `rejected-duplicate` and `manual-only` |
| `emitted_view` | **Yes**, new |
| `unit_state` | Via U7 |

The four `gap` categories U3 did not use are now used. Declaring all six in migration
004 rather than four means U4 needs no constraint change — which was the point of
reading FR-RPT-02 at the time rather than discovering it here.

---

## Integrity Rules

All but one already exist. U4 is where they finally bite on real data.

| Rule | Enforcement | New? |
|---|---|---|
| A case has at least one step | Trigger + D1 + D7 | No — migration 001 |
| A case carries a Jira key | Trigger + D3 + D7 | No — migration 001 |
| A step has a non-empty expected result | CHECK | No |
| Test data carries an equivalence class | CHECK | No |
| Case identifiers are immutable | Trigger | No |
| An emitted view records a 64-character hash | CHECK | **Yes** |
| A case's test type matches its coverage item | Domain validation | **Yes** |

**The two triggers from migration 001 have been tested since U1 but never exercised in
production flow.** U4 is the first unit whose normal operation passes cases through
them, which makes it the first real proof that the storage layer holds the traceability
rule rather than merely claiming to.
