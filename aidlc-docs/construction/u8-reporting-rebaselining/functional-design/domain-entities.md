# Domain Entities — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-31

U8 adds **two columns** and no table. Everything else it needs was built by U1 and has
been waiting for a writer.

---

## What Was Already Built For This

| Entity | Built by | Unused until now |
|---|---|---|
| `change_event` | U1, migration 001 | **Yes** — no unit has written one |
| `run.kind = 'delta'` | U1 | **Yes** — every run so far is a baseline |
| `test_case.is_obsolete`, `obsolete_reason`, `obsoleted_by_change_id` | U1 | **Yes** |
| `D8 impact.py` | U1 | **Yes** — `classify_edge` and `map_impact` are complete |
| `mark_obsolete` | U1 | **Yes** |

**Five things designed at U1 and left dormant for seven units.** That is the intended
outcome of designing the schema once against the whole requirement set rather than per
unit — and it is why U8 needs almost no new storage.

---

## Migration 007: Two Columns on `run`

```sql
ALTER TABLE run ADD COLUMN head_commits TEXT NOT NULL DEFAULT '{}';
ALTER TABLE run ADD COLUMN jira_watermark TEXT;
```

| Column | Holds |
|---|---|
| `head_commits` | `{"<repo-slug>": "<sha>"}` — the head this run saw, per repository |
| `jira_watermark` | The ISO timestamp of the latest Jira `updated` this run ingested |

### Why on `run` rather than a `delta_baseline` table

The baseline **is a property of a run**: it is what the system saw when that run
completed. `run` already carries `ended_at`, so "the last completed run" is one query
with no separate record to fall out of step with it.

A dedicated table would introduce a second answer to "when did we last look at this",
and the two would eventually disagree — most likely after a run that failed partway,
where one record was updated and the other was not.

### Why not derive it from `artefact.last_ingested_at`

That answers "when did we last fetch this artefact". `bitbucket_changes` needs "what
was the repository head when the run completed", which is a different fact: an artefact
can be re-fetched without the head moving, and the head can move without any artefact
being re-fetched.

---

## Computed Types

### The four reports

| Report | Answers | Requirement |
|---|---|---|
| `CoverageReport` | Per feature and test type, planned versus generated, with derivation | FR-RPT-01 |
| `GapReport` | Uncovered requirements, untraceable behaviours, manual-only, reduced depth | FR-RPT-02 |
| `AutomationReport` | Automated, deferred, and the reason for each deferral | FR-RPT-04 |
| `TraceMatrixReport` | Both directions, Markdown and CSV | FR-RPT-03 |

The traceability matrix is U4's `trace_matrix`, rendered to file by A9 rather than
recomputed. **U8 owns the rendering; U4 owns the matrix**, and duplicating the
construction would give two answers to one question.

### `ReportSection`

| Field | Meaning |
|---|---|
| `name` | The section |
| `status` | `computed`, or **`not_available`** |
| `unavailable_reason` | Why, in the reader's terms |
| `producing_stage` | Which stage would supply it |
| `rows` | The data, empty when not computed |

**`not_available` is distinct from an empty section**, and the distinction is the
point. A coverage section with no rows means every requirement is uncovered; a section
that could not be computed means the coverage model has not been approved. Those call
for opposite responses, and a silent omission makes them look the same.

`producing_stage` turns the report into an instruction: "not available — no approved
coverage model; run the coverage stage for this feature" is actionable in a way that
"not available" alone is not.

### `DeltaBaseline`

| Field | Source |
|---|---|
| `run_id`, `ended_at` | The last completed run |
| `head_commits` | That run's `head_commits` |
| `jira_watermark` | That run's `jira_watermark` |

`None` when no run has completed — a first delta run has nothing to compare against,
and saying so is better than treating the whole repository as changed.

### `DeltaReport`

| Field | Meaning |
|---|---|
| `baseline` | What it compared against, or why it could not |
| `changes` | Detected `ChangedRef`s, by source |
| `impact` | D8's `ImpactSet`, unmodified |
| `retired` | Cases marked obsolete this run, with reasons |
| `requires_update` | Reported, **not touched** |
| `unmapped` | Changes that reached nothing traceable |

`unmapped` is carried through to the top level of the report rather than left inside
`ImpactSet`, because it is the finding an operator most needs to see and the one most
easily lost in a nested structure.

---

## What Retirement Writes

| Column | Set to |
|---|---|
| `is_obsolete` | 1 |
| `obsolete_reason` | D8's classification reason, unchanged |
| `obsoleted_by_change_id` | The `change_event` row that caused it |
| `last_modified_run_id` | The delta run |

**Nothing is deleted.** Steps, test data, trace links and the automated test all
remain. The case stops appearing in coverage counts, in generated views and in
duplicate candidate selection — because U4's bucket query already excludes obsolete
cases, and U3's coverage aggregation already counts only active ones.

Three earlier decisions converge here:

| Decision | Made at | Pays off now |
|---|---|---|
| `mark_obsolete` with a reason and a change id | U1 | The columns exist |
| An obsolete case never yields its identifier | U1 D5, U4 BR-6.2 | A retired number is never reissued |
| Bucket candidates exclude obsolete cases | U1, U4 | A retired case cannot block a new one as a duplicate |

An archive table was the alternative and would split the corpus in two, so every query
and every report would have to remember to check both — and the first one that forgot
would silently understate coverage.

---

## Entities U8 Reads and Never Writes

| Entity | Owner |
|---|---|
| `testable_requirement`, `coverage_item` | U3 |
| `test_case`, `test_step`, `test_data` | U4 — **except** the three obsolete columns |
| `automated_test` | U5 |
| `gap` | U3 and U4 write; U8 renders |
| `artefact`, `feature` | U2 |

**U8 creates no requirement and no case.** A delta run classifies and retires; anything
that needs regenerating re-enters the pipeline at U3 for the affected scope, through
the same gates the baseline passed (FR-DLT-06).

---

## Integrity Rules

| Rule | Enforcement | New? |
|---|---|---|
| A case is never deleted | No `delete` method on the case repository | No — absent since U1 |
| An obsolete case records why and what caused it | `mark_obsolete` requires both | No |
| An obsolete identifier is never reissued | D5, `stable_id_for` skips obsolete | No |
| A change touching nothing traceable is reported, not assumed harmless | D8 `map_impact` | No |
| A report section that could not be computed says so | S8, BR-U8-2 | **Yes** |
| A delta run creates no case and no requirement | **No such method on S9** | **Yes** |

Five of six were already true. That is what it looks like when the constraints were
designed in rather than added at the end.
