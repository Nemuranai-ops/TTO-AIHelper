# Domain Entities — U2 Ingestion and Analysis

**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

U2 introduces **one** new persisted entity and adds no column to any existing table.

---

## Schema Change: `discrepancy`

FR-ANA-08 requires disagreements between sources to be recorded and retained. U1's
schema has `screen.discrepancy_id` and `business_rule.contradicts_id` pointing at a
table that does not exist yet. Migration **003** creates it.

```sql
CREATE TABLE discrepancy (
    id            INTEGER PRIMARY KEY,
    kind          TEXT    NOT NULL,
    subject       TEXT    NOT NULL,
    source_a      TEXT    NOT NULL,
    claim_a       TEXT    NOT NULL,
    source_b      TEXT    NOT NULL,
    claim_b       TEXT    NOT NULL,
    detected_at   TEXT    NOT NULL,
    run_id        INTEGER,
    resolved_by   TEXT,
    resolution    TEXT,
    -- A resolution is a human act. Recording who made it is what separates a
    -- decision from a value that simply appeared.
    CHECK (resolved_by IS NULL OR resolution IS NOT NULL)
);
CREATE INDEX idx_discrepancy_kind ON discrepancy (kind);
```

**Symmetric by construction.** Both claims are stored with their sources, and neither
is marked correct. Storing one claim and a note about "the other source" would make
the record readable in only one direction — and the reader is often coming from the
side that was not chosen as primary.

`resolved_by` and `resolution` exist because a human eventually settles some of these.
Nothing in U2 writes them.

### Kinds

| Kind | Subject |
|---|---|
| `endpoint-not-implemented` | `METHOD /route` |
| `shape-mismatch` | `METHOD /route` |
| `status-code-undocumented` | `METHOD /route` |
| `auth-requirement-mismatch` | `METHOD /route` |
| `screen-not-in-live` | Screen name |
| `screen-differs-from-design` | Screen name |
| `rule-contradiction` | Rule condition |

---

## Computed Types

None persisted. These are what S1 and S2 return.

### `ResourceClassification`

| Field | Type | Notes |
|---|---|---|
| `raw_ref` | str | Exactly as written in `resources.md` |
| `type` | `ResourceType` | From BR-U2-1.1 |
| `rule_number` | int | Which of the nine rules fired |
| `pattern` | str | The pattern that matched |

`rule_number` and `pattern` become `resource.inferred_from`. A wrong inference is
otherwise a guess among nine rules.

### `IngestionReport`

| Field | Type | Notes |
|---|---|---|
| `succeeded` | list | Resource, artefact count |
| `skipped_unchanged` | list | Resource, hash |
| `failed` | list | Resource, error code, whether not-found or not-authorised |
| `unclassified` | list | Raw references |
| `totals` | dict | Counts per outcome |

Four outcomes rather than two. "Failed" and "skipped because nothing changed" are
opposite situations, and collapsing them would make a healthy re-run look like a
broken one.

### `ApiMergeResult`

| Field | Type | Notes |
|---|---|---|
| `endpoints` | list[ApiEndpoint] | Those that exist in code |
| `discrepancies` | list[Discrepancy] | Spec-only endpoints, shape and auth mismatches |
| `inferred_count` | int | Endpoints whose shapes came from the handler |

### `DesignAssetParse`

| Field | Type | Notes |
|---|---|---|
| `associated` | list | Filename, feature, screen, state, source of each value |
| `unassociated` | list[str] | Filenames that matched no convention |

`source of each value` records whether it came from the filename or the manifest,
which is what makes field-by-field override auditable.

---

## Entities U2 Populates

All defined in U1. U2 writes them; it defines none of them.

| Entity | Written by | Notes |
|---|---|---|
| `resource` | S1 | With `inferred_from` from BR-U2-1.2 |
| `artefact` | S1 | With content hash from BR-U2-3.1 and `detail_level` from BR-U2-2.2 |
| `feature` | S2 | From the agent's payload |
| `journey` | S2 | From the agent's payload |
| `business_rule` | S2 | With `contradicts_id` where the agent detects one |
| `api_endpoint` | S2 | **Derived by the toolchain**, not supplied |
| `screen`, `ui_element` | S2 | From the agent's payload |
| `discrepancy` | S1, S2 | New in this unit |

---

## Integrity Rules

| Rule | Enforcement |
|---|---|
| A resource is stored once per raw reference | UNIQUE on `resource.raw_ref` (U1) |
| Re-ingesting unchanged content creates no duplicate | UNIQUE on `(resource_id, source_identifier, content_hash)` (U1) |
| `detail_level` is `full` or `low` | CHECK (U1) |
| `auth_requirement` is `none`, `required` or `unknown` | CHECK (U1) |
| `shape_source` is `specified` or `inferred` | CHECK (U1) |
| A resolved discrepancy carries its resolution | CHECK (new) |
| A feature cites at least one source artefact | Domain validation (BR-U2-7.1) |
| The feature hierarchy is acyclic | Domain validation (BR-U2-7.1) |

The first five already hold from U1's schema. U2 adds one constraint and two domain
validations.

---

## Migration 003

Adds `discrepancy` and its index. The reverse drops both.

Straightforward to reverse — it creates a table rather than altering one, so no
rebuild is needed and no data is at risk. Still ships and tests its reverse, because
U1-NFR-DIST-04 makes that unconditional and an exception granted once becomes a habit.
