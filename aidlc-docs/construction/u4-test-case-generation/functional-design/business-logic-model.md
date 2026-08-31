# Business Logic Model — U4 Test Case Generation

**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

---

## 1. The Orchestration

S5 is the only place in the system where six domain components run in one transaction.

```
testcases_upsert(feature, cases[])
        |
   [A] gate: coverage approved and unchanged?  ---- closed ----> REJECTED_GATE_CLOSED
        |                                                        (batch stops)
   [A] batch within the 200 cap?              ---- over ------->  REJECTED, count given
        |
   [B] per case, structural:  D1 construction -> D7 validation
        |                     test type matches its coverage item
        |
   [C] per case, traceability: D3 resolve against known keys
        |
   [D] per case, corpus:       D4 against bucket + batch
        |
   any failure? --- yes ---> roll back, report EVERY failure, store nothing
        |
       no
        |
   [E] D6 classify automatability (derived + supplied signals)
   [F] D5 allocate identifiers
        |
   commit: cases, steps, data, links, integrity sentinel
        |
   A8 emit views (skipping hand-edited files)
        |
   report: accepted, rejections, gaps, planned vs generated, view manifest
```

**Why E and F run last.** Classification and allocation mutate sequence state. Running
them before validation would mean unwinding allocations on rollback, and an identifier
that was allocated and then released is an identifier that might be reissued — which
BR-6.2 forbids.

---

## 2. Algorithms

### 2.1 Signal gathering (BR-U4-2)

```
gather_signals(payload, coverage_item, uow):
    is_api = coverage_item.test_type == API_CONTRACT
    is_ui  = coverage_item.test_type == UI_BEHAVIOUR

    elements = [e for sid in payload.referenced_screen_ids
                  for e in uow.features.elements_for_screen(sid)]

    return CaseSignals(
        # Supplied. Default false, which can only move a case toward automatable or
        # needs-review - never toward a wrong manual-only, which would quietly
        # remove it from automation with nobody deciding to.
        requires_visual_judgement=payload.requires_visual_judgement,
        requires_external_step=payload.requires_external_step,
        requires_unprovisionable_data=payload.requires_unprovisionable_data,
        is_exploratory=payload.is_exploratory,
        # Derived.
        is_api_case=is_api,
        api_shape_source=endpoint_shape_source(coverage_item, uow) or "inferred",
        is_ui_case=is_ui,
        all_elements_have_locators=bool(elements) and all(e["locator_chain"] for e in elements),
        all_locators_verified=bool(elements) and all(e["is_verified"] for e in elements),
        has_fragile_locator_without_alternative=any(
            e["is_fragile"] and len(json.loads(e["locator_chain"])) <= 1 for e in elements
        ),
    )
```

### 2.2 The batch (BR-U4-8)

```
upsert_cases(feature_slug, payloads):
    gate = run_state.is_gate_open(feature_slug, CASES)
    if not gate.is_open:
        return REJECTED_GATE_CLOSED(gate.detail, gate.remediation)
    if len(payloads) > MAX_BATCH:
        return REJECTED(f"{len(payloads)} cases exceeds the {MAX_BATCH} cap")

    known_keys = uow.artefacts.known_jira_keys()
    accepted, rejections, seen_in_batch = [], [], {}

    for payload in payloads:
        item = uow.coverage.get(payload.coverage_item_id)
        failures = []

        if item is None:
            failures.append(REJECTED_INVALID_STEPS, "unknown coverage item")
        elif item.test_type != payload.test_type:
            # Without this, generated-vs-planned would be meaningless: five cases
            # could satisfy one item while another went uncovered, and the totals
            # would still balance.
            failures.append(REJECTED_INVALID_STEPS, "test type does not match its item")

        case = try_construct(payload)          # D1 rejects no-steps, blank expected
        if case is None:
            failures.append(REJECTED_NO_STEPS, construction_error)
        else:
            failures += D7.validate_case(case, known_keys)
            candidates = uow.cases.bucket_candidates(bucket_key(case, feature_slug))
            candidates += seen_in_batch.get(bucket_key(case, feature_slug), [])
            finding = D4.find_duplicate(case, candidates)
            if finding:
                failures.append(REJECTED_DUPLICATE, f"{finding.verdict} of {finding.existing_case_id}")

        if failures: rejections += failures
        else:        accepted.append(case); remember(seen_in_batch, case)

    if rejections:
        return report_all(rejections)          # nothing stored, nothing allocated

    for case in accepted:
        case.automatability = D6.classify(gather_signals(...))
        case.id = D5.allocate(...)             # only now
    uow.cases.upsert_many(accepted, feature_slug)
    record_gaps(duplicates, manual_only)
    return report(accepted, planned_vs_generated, emit_views(feature_slug))
```

### 2.3 Identifier stability (BR-6.2)

```
resolve_id(payload, existing_cases, state):
    stable = stable_id_for(payload.coverage_item_id, payload.title, existing_cases)
    if stable:
        return stable, state                   # regeneration keeps its id
    return allocate(TEST_CASE, feature_slug, state)
```

A case matching an existing non-obsolete case on coverage item and title keeps its
identifier. Obsolete cases are skipped, so a retired case cannot reclaim its number.

### 2.4 View emission with hand-edit detection (BR-U4-5)

```
emit_views(feature_slug):
    manifest = ViewManifest()
    for path, content in (markdown_view(...), yaml_view(...)):
        digest = sha256(content)
        recorded = uow.views.get(path)

        if path.exists() and recorded and sha256(path.read()) != recorded.content_hash:
            manifest.hand_edited.append(path)   # skipped, not overwritten
            continue
        if recorded and recorded.content_hash == digest:
            manifest.unchanged.append(path)     # nothing to do
            continue

        path.write(content)
        uow.views.upsert(path, feature_slug, digest, case_count)
        manifest.written.append(path)
    return manifest
```

**Three outcomes, not two.** `unchanged` is separate from `written` for the same
reason U2's ingestion report separates skipped from succeeded: a re-emission that
writes nothing is exactly right, and indistinguishable from a broken one unless the
report says so.

### 2.5 Matrix construction (BR-U4-6)

```
build_matrix(fmt):
    links        = uow.traces.all_links()
    requirements = [r.id for r in uow.requirements.query(limit=MAX)]

    matrix = D3.build_matrix(
        [MatrixEdge("requirement", l.source_id, "target", l.target_ref) for l in links],
        all_sources=requirements,               # so uncovered requirements appear
    )
    return TraceMatrixView(
        forward=matrix.forward, reverse=matrix.reverse,
        uncovered=matrix.uncovered(requirements),
        counts_by_link_type=D3.link_counts_by_type(links),
        format=fmt,
    )
```

---

## 3. Interaction with Other Units

| Unit | Use |
|---|---|
| U1 | D1, D3, D4, D5, D6, D7; repositories; `unit_of_work` |
| U2 | The UI model, for locator signals |
| U3 | The approved coverage model, and `coverage_item` for planned counts |
| U7 | `is_gate_open` before the batch; `stage_approve` for the operator's review |
| U5 | Reads automatable cases. U4 writes nothing U5 owns |
| U8 | Reads the corpus and the gaps U4 records |

**U4 registers 2 write tools**: `testcases_upsert` and `views_emit`. Both are already
named in U7's `cases` chat mode.

The traceability matrix is served by U1's existing `trace_matrix` read tool, which U4
now has data for. No new read tool is needed — the tool was written against the shape
U4 produces, which is what registering it in U1 anticipated.

---

## 4. Property Surface

| Component | Property | Category |
|---|---|---|
| Signals | Omitting a judgement signal never yields `manual-only` | PBT-03 |
| Signals | Derived signals depend only on the models, not the payload | PBT-03 |
| Batch | Accepted plus rejected equals submitted | PBT-03 |
| Batch | A batch with any rejection accepts none | PBT-03 |
| Batch | Nothing is allocated when a batch is rejected | PBT-03 |
| Identity | Regeneration of an unchanged case keeps its id | PBT-03 |
| Identity | An obsolete case never yields its id to a replacement | PBT-03 |
| Views | Re-emission of unchanged content writes nothing | PBT-03 |
| Views | A hand-edited file is never overwritten | PBT-03 |
| Matrix | Every requirement appears, covered or not | PBT-03 |

**"Nothing is allocated when a batch is rejected"** is the one worth having. An
identifier allocated and then released could be reissued, and BR-6.2 forbids that —
but the forbidding is easy to break by moving allocation earlier for convenience.

---

## 5. Story Coverage

| Story | Where served |
|---|---|
| US-TCG-01 Structured cases with mandatory steps | BR-U4-1, BR-U4-8, §2.2 |
| US-TCG-02 Synthetic test data with classes | BR-U4-8 stage B; D1 construction |
| US-TCG-03 Duplicate detection | BR-U4-4, §2.2 |
| US-TCG-04 Automatability classification | BR-U4-2, §2.1 |
| US-TCG-05 Derived volume without padding | BR-U4-7 |
| US-TCG-06 Sharded views with tags | BR-U4-5, §2.4 |
| US-TRC-04 Bidirectional matrix | BR-U4-6, §2.5 |

**All 7 U4 stories served.**
