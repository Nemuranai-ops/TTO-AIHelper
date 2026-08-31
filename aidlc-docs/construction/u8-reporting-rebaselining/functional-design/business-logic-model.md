# Business Logic Model — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-31

---

## 1. Two Sequences

### 1.1 Reporting (S8)

```
reports_generate(kinds, feature_slug?)
        |
   [A] per requested report, per section:
        |
        +-- preconditions met? --- no ---> ReportSection(not_available, reason, stage)
        |
       yes
        |
   [B] one SQL aggregation per section         <- never composed by the model
        |
   [C] A9 renders: Markdown, plus CSV for the matrix
        |
   report: sections, each computed or explicitly not available
```

**No stage can fail the whole report.** A section that cannot be computed becomes a
`not_available` row and the rest renders — U6's degrade-and-report pattern, reaching
its second use.

### 1.2 Delta (S9)

```
delta_detect()
        |
   [A] baseline = last run with ended_at set
        |
        +-- none? ---> report "no completed run to compare against", stop
        |
   [B] per repository: bitbucket_changes(baseline.head -> current head)
       plus Jira: updated >= baseline.watermark        <- each under isolate
        |
   [C] build TraceEdges from the traceability graph
        |
   [D] D8.map_impact(changes, edges, corpus_size)      <- U8 classifies nothing
        |
   [E] record the change_event, with its unmapped flag and impact scale
        |
   [F] retire the obsolete; report requires-update untouched
        |
   report: baseline, changes, impact, retired, requires_update, unmapped
```

**Stage F is the only write.** U8 creates no requirement and no case: S9 has no method
that could.

---

## 2. Algorithms

### 2.1 Section availability (BR-U8-2)

```
def section(name, precondition, query, stage):
    ok, reason = precondition()
    if not ok:
        return ReportSection(name, NOT_AVAILABLE, reason, producing_stage=stage)
    return ReportSection(name, COMPUTED, rows=query())
```

| Section | Precondition | Stage named when absent |
|---|---|---|
| Coverage per feature | An approved coverage model exists | `coverage` |
| Planned versus generated | The same | `coverage` |
| Automation | At least one `automated_test` row | `automation` |
| Traceability matrix | At least one trace link | `cases` |
| Gap | **None** — always computable | — |

The gap report has no precondition, which is deliberate: **gaps are the one thing worth
reporting from the very first run**, and a report that says "no requirements yet" is
itself the useful finding at that point.

### 2.2 Building trace edges (BR-U8-6)

```
def edges_for(changes):
    edges = []
    for change in changes:
        for link in traces.for_target(change.ref):
            case = cases.get(link.source_id)
            edges.append(TraceEdge(
                case_id=case["id"],
                changed_ref=change.ref,
                requirement_deleted=requirement_missing(case["coverage_item_id"]),
                target_removed=change.kind == "removed",
                statement_changed=statement_hash_differs(case),
                rule_changed=rule_hash_differs(case),
            ))
    return edges
```

U8 assembles the four booleans from the corpus and hands them to D8. **It does not
decide what they mean** — `classify_edge` does, using rules reviewed at U1.

The four are the whole interface between this unit and the classification logic, which
is what makes the delegation checkable: if S9 ever needed a fifth signal, that would be
a change to D8 rather than a local special case.

### 2.3 Retirement (BR-U8-7)

```
def retire(impacts, change_event_id):
    retired = []
    for impact in impacts:
        if impact.classification is not OBSOLETE:
            continue                      # requires-update is reported, not touched
        cases.mark_obsolete(impact.case_id, impact.reason, change_event_id)
        retired.append(impact)
    return retired
```

Three lines of writing, because U1 built `mark_obsolete` to take exactly the reason and
the change id this loop has. Nothing is deleted, and nothing cascades: the steps, the
data, the links and the automated test all remain.

### 2.4 The coverage figures (BR-U8-1.2, BR-U8-3)

```
SELECT f.slug, ci.test_type,
       SUM(ci.planned_count)                        AS planned,
       COUNT(DISTINCT tc.id)                        AS generated
FROM feature f
JOIN testable_requirement tr ON tr.feature_id = f.id
JOIN coverage_item ci        ON ci.requirement_id = tr.id
LEFT JOIN test_case tc       ON tc.coverage_item_id = ci.id AND tc.is_obsolete = 0
GROUP BY f.id, ci.test_type
```

`LEFT JOIN` and `is_obsolete = 0` are both load-bearing. The first keeps a coverage item
that produced nothing in the result, which is the row the report exists to show. The
second is where retirement takes effect: **a retired case stops counting the moment it
is marked, with no separate step**.

### 2.5 Degrading on an unreachable source (BR-U8-5.2)

```
with isolate("bitbucket") as guard:
    changes += bitbucket_changes(baseline.head_commits, current_heads())
if guard.failed:
    report.sources_unavailable.append(("bitbucket", guard.reason))
```

U1's `isolate`, used the same way U2 used it for ingestion. A Bitbucket outage yields a
delta run reporting Jira changes and stating that repository changes could not be
detected.

---

## 3. What U8 Never Does

| Not done | Why |
|---|---|
| Create a requirement or a case | **No such method on S9.** A delta run that regenerated would bypass every gate |
| Delete a case | No delete method exists on the repository, and none is added |
| Delete an automated test | U5's hand-edit protection would not apply — U8 would be the deleter |
| Classify impact itself | D8's rules, reviewed at U1 |
| Rebuild the traceability matrix | U4 owns it; U8 renders it |
| Compose a figure | Every number is a query result (FR-RPT-05) |

---

## 4. Interaction with Other Units

| Unit | Use |
|---|---|
| U1 | D8 `impact.py`, `isolate`, repositories, `mark_obsolete`, `unit_of_work` |
| U2 | The Bitbucket and Jira adapters, for change detection |
| U3 | The coverage model, and the gaps it wrote |
| U4 | The corpus, the matrix, and the gaps it wrote |
| U5 | `automated_test` rows for the automation report |
| U6 | The handover manifest, for the delivered-versus-corpus comparison |
| U7 | `is_gate_open` before a delta run — FR-DLT-06's gates |

**A delta run passes the same gates as the baseline.** That is the requirement, and it
falls out of S9 calling `is_gate_open` exactly as every other service does.

---

## 5. Property Surface

| Property | Statement |
|---|---|
| PBT-U8-1 | A section with no precondition is never `not_available` |
| PBT-U8-2 | A `not_available` section always carries a reason and a producing stage |
| PBT-U8-3 | A report never fails because one section could not be computed |
| PBT-U8-4 | Retirement changes only the three obsolete columns |
| PBT-U8-5 | A `requires-update` case is never modified by a delta run |
| PBT-U8-6 | Every change reaching no trace edge appears in `unmapped` |
| PBT-U8-7 | A retired case never appears in a coverage count |
| PBT-U8-8 | Report rendering is byte-stable for an unchanged corpus |
| PBT-U8-9 | Every rendered figure has a derivation string |

**PBT-U8-4 and -5 are the pair that pins the unit boundary.** They are the properties
that would fail first if someone later added a convenient regeneration step to the
delta path.

---

## 6. Story Coverage

| Story | Rules | Algorithms |
|---|---|---|
| US-RPT-01 | BR-U8-1, BR-U8-2, BR-U8-3 | §2.1, §2.4 |
| US-RPT-02 | BR-U8-1.3, BR-U8-3 | §2.1 |
| US-RPT-03 | BR-U8-1, BR-U8-3 | §2.1 |
| US-DLT-01 | BR-U8-4, BR-U8-5 | §1.2, §2.5 |
| US-DLT-02 | BR-U8-5, BR-U8-6 | §2.2 |
| US-DLT-03 | BR-U8-7, BR-U8-8 | §2.3 |

**All 6 U8 stories are covered.**
