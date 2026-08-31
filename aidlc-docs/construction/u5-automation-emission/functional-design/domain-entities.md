# Domain Entities — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

U5 adds almost nothing to the model. `automated_test` was created by U1's migration
001 with the shape U5 needs, and hand-edit detection reuses U4's table rather than
building a second one.

---

## Entities U5 Populates

| Entity | First written by U5? |
|---|---|
| `automated_test` | **Yes** — declared in migration 001, unwritten until now |
| `emitted_view` | No — U4 created it; U5 records TypeScript files in it |
| `gap` | No — U5 adds `manual-only` and `needs-review-not-automated` entries |

### `automated_test`, as it already stands

```sql
CREATE TABLE automated_test (
    id               TEXT    PRIMARY KEY CHECK (id GLOB 'AT-*'),
    case_id          TEXT    NOT NULL UNIQUE REFERENCES test_case(id),
    spec_path        TEXT    NOT NULL,
    test_name        TEXT    NOT NULL,
    page_object_refs TEXT    NOT NULL DEFAULT '[]',
    input_hash       TEXT,
    output_hash      TEXT,
    is_at_risk       INTEGER NOT NULL DEFAULT 0,
    at_risk_reason   TEXT,
    CHECK (is_at_risk = 0 OR at_risk_reason IS NOT NULL)
);
```

**`case_id` is UNIQUE; `spec_path` is not.** One case yields at most one test, and many
tests share a spec file — which is precisely BR-U5-1's per-feature scoping expressed as
a constraint. A schema that made `spec_path` unique would have forced one file per case.

**`input_hash` and `output_hash` are the pair determinism rests on.** The input hash
covers what the test was generated *from*; the output hash covers what was written.
Equal input hashes with differing output hashes means the generator is
non-deterministic, which FR-AUT-11 forbids and which no amount of reviewing the output
would reveal.

**`is_at_risk`** is where the unverified-locator flag lands. A test built on locators
that no live exploration confirmed is not wrong — it is unconfirmed, and BR-U5-3 keeps
the two distinguishable.

---

## One Migration: 006

`emitted_view` was built for Markdown and YAML. It now also records TypeScript, and
two columns make that honest rather than implicit.

```sql
ALTER TABLE emitted_view ADD COLUMN kind TEXT NOT NULL DEFAULT 'view';
CREATE INDEX idx_emitted_view_kind ON emitted_view (kind);
```

| `kind` | Written by | Scope of `feature_slug` |
|---|---|---|
| `view` | U4 | The feature |
| `automation` | U5 | The feature, or `<project>` for scaffold files |

**Why generalise rather than add a table.** The problem is identical: a file was
written, a person may have edited it, and the hash at last emission is the only thing
that distinguishes their edit from a corpus change. Two tables would mean two
implementations of one rule, and the second would drift — the divergence surfacing as
"hand-edits are protected in the views but not in the specs", which is the worst
possible way to discover it.

`<project>` is a reserved slug. BR-U5-1's slug validation rejects `<` and `>`, so no
real feature can collide with it.

---

## Computed Types

### `EmissionRequest`

What S6 is asked to produce. Not stored.

| Field | Meaning |
|---|---|
| `feature_slug` | The feature to emit, or all features |
| `include_scaffold` | Whether project-level files are (re)written |
| `destination` | Root of the generated project |

### `GeneratedFile`

| Field | Meaning |
|---|---|
| `path` | Relative to the project root |
| `kind` | `spec`, `page-object`, `fixture`, `config`, `doc` |
| `content_hash` | SHA-256 of the rendered bytes |
| `case_ids` | The cases it carries, empty for scaffold files |

### `AutomationManifest`

Three outcomes, inherited from U4's P-U4-04 rather than reinvented.

`written`, `unchanged`, `hand_edited` — plus `not_automated`, which is not a file
outcome at all but the list of cases that produced no test.

**`not_automated` sits in the manifest rather than a separate report** because the
question an Automation Engineer asks after a run is "what did I get, and what am I
missing?" — one question, and splitting the answer across two documents means the
second one goes unread.

### `NotAutomated`

| Field | Meaning |
|---|---|
| `case_id` | The case |
| `classification` | `manual-only` or `needs-review` |
| `reason` | D6's own words, carried through unchanged |

**The two classes are reported apart.** `manual-only` is a decision; `needs-review` is
an absence of one, and it is the actionable half — a case D6 could not judge is a case
the engineer can resolve by supplying one missing signal.

---

## Entities U5 Does Not Own

| Entity | Owner | Why not U5 |
|---|---|---|
| `test_case`, `test_step`, `test_data` | U4 | U5 reads; writing would let the corpus be edited by a generator |
| `screen`, `ui_element` | U2 | The locators come from the UI model, and U5 must not improve them silently |
| The handover package | U6 | U5 produces code; assembling and verifying a project is a different job |

**U5 writes nothing U4 or U2 owns.** The one-directional flow matters here more than
elsewhere: if the emitter could adjust a locator it found inconvenient, the UI model
and the generated code would disagree, and the model is what the next run reads.

---

## Integrity Rules

| Rule | Enforcement | New? |
|---|---|---|
| An automated test references an existing case | FK on `case_id` | No |
| One test per case | UNIQUE on `case_id` | No |
| An at-risk test states why | CHECK | No |
| A test exists only for an `automatable` case | S6, BR-U5-2 | **Yes** |
| Generated files record what they were rendered from | `input_hash` | **Yes** |

The fourth is enforced in the service rather than the schema: `automatability` lives on
`test_case`, and a CHECK spanning two tables would need a trigger whose failure mode is
a rejected write with no useful message. The rule is asserted in tests instead, which
is the honest trade — and BR-U5-2 is a policy that may change, unlike the three
structural rules above it.
