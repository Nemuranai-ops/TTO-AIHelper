# Business Logic Model — U2 Ingestion and Analysis

**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

---

## 1. The Split, at Method Level

Application Design Q3 put bulk ingestion in the toolchain. This is where that lands.

| Method | Who reasons | Why |
|---|---|---|
| `S1.ingest_resources` | Toolchain | Fetching and hashing needs no judgement, and 500 issue bodies through a context window is expensive for nothing |
| `S2.derive_api_model` | Toolchain | Endpoint extraction is mechanical |
| `S2.upsert_feature_model` | Agent supplies | What constitutes a feature is a judgement |
| `S2.upsert_business_rules` | Agent supplies | Reading a rule out of prose is a judgement |
| `S2.upsert_ui_model` | Agent supplies | Deciding what a screen's states mean is a judgement |
| `S2.record_discrepancy` | Either | Detection is mechanical; resolution is not, and neither does it |

---

## 2. Algorithms

### 2.1 Resource classification (BR-U2-1)

```
classify(raw_ref):
    for rule in RULES:                      # ordered, 1..9
        if rule.pattern.match(raw_ref):
            return ResourceClassification(raw_ref, rule.type, rule.number, rule.pattern)
    return ResourceClassification(raw_ref, UNCLASSIFIED, 9, "no rule matched")
```

Order matters and is fixed. Rule 2 (a bare `PROJ-123` token) would swallow a JQL
string containing one, so rule 3 cannot precede it — the ordering is a design
decision, not an accident of authorship.

### 2.2 Ingestion (BR-U2-8)

```
ingest_resources(manifest_path):
    entries, unclassifiable = manifest_adapter.parse(manifest_path)
    report = IngestionReport(unclassified=unclassifiable)

    results = isolate(entries, lambda entry: ingest_one(entry), logger)

    for entry, artefacts in results.succeeded:
        report.succeeded.append((entry, len(artefacts)))
    for entry, failure in results.failed:
        report.failed.append((entry, failure.code, classify_failure(failure)))
    return report


ingest_one(entry):                          # one transaction per resource
    with unit_of_work() as uow:
        uow.resources.upsert(Resource(entry.raw_ref, entry.type, entry.inferred_from))
        records = with_retry(lambda: source_for(entry.type).fetch(entry), policy)
        stored = []
        for record in records:
            digest = content_hash(hashable_content(record))       # BR-U2-3.1
            if uow.artefacts.get_by_hash(digest):
                continue                                          # skip unchanged
            stored.append(uow.artefacts.upsert(Artefact.of(..., content_hash=digest)))
        return stored
```

**One transaction per resource, not per run.** This is the one place U1's
all-or-nothing rule is deliberately relaxed, and only here: at 3-10 repositories and
hundreds of issues, one unreachable source must not discard an hour of successful
retrieval.

### 2.3 API model merge (BR-U2-5)

```
derive_api_model(repo_ids):
    from_code = bitbucket.endpoints(repo)               # method, route, file, line, symbol
    from_spec = parse_openapi(bitbucket.find_spec(repo))

    endpoints, discrepancies = [], []

    for endpoint in from_code:
        spec = from_spec.get((endpoint.method, endpoint.route))
        if spec:
            endpoints.append(endpoint.with_shapes(spec, source=SPECIFIED))
            if shapes_differ(endpoint.inferred_shapes, spec.shapes):
                discrepancies.append(shape_mismatch(endpoint, spec))
            if spec.auth != endpoint.auth and endpoint.auth != UNKNOWN:
                discrepancies.append(auth_mismatch(endpoint, spec))
        else:
            endpoints.append(endpoint.with_shapes(inferred_from_handler, source=INFERRED))

    for key, spec in from_spec.items():
        if key not in {(e.method, e.route) for e in from_code}:
            # In the spec, not in the code. Not an endpoint.
            discrepancies.append(endpoint_not_implemented(key, spec))

    return ApiMergeResult(endpoints, discrepancies, inferred_count=...)
```

**The last loop is the load-bearing one.** A spec entry with no implementation is
recorded as a discrepancy and produces no endpoint. Treating it as real would generate
tests for something that returns 404 — failures unrelated to any defect, which erode
trust in the whole suite faster than missing coverage does.

### 2.4 Design asset parsing (BR-U2-4)

```
parse_assets(folder):
    manifest = safe_load_yaml(folder / "screens.manifest.yaml") or {}
    associated, unassociated = [], []

    for path in folder.glob("*.png"):
        segments = path.stem.split("__")
        if len(segments) == 2:
            parsed = {"feature": slug(segments[0]), "screen": slug(segments[1]),
                      "state": "default"}
        elif len(segments) == 3:
            parsed = {"feature": slug(segments[0]), "screen": slug(segments[1]),
                      "state": slug(segments[2])}
        else:
            unassociated.append(path.name)
            continue

        origin = {k: "filename" for k in parsed}
        for field, value in manifest.get(path.name, {}).items():
            parsed[field] = value                     # field-by-field override
            origin[field] = "manifest"
        associated.append((path.name, parsed, origin))

    return DesignAssetParse(associated, unassociated)
```

`origin` records where each value came from. Field-by-field override is only
auditable if you can see which fields were overridden.

### 2.5 Discrepancy detection (BR-U2-6)

```
would_a_tester_write_a_different_test(claim_a, claim_b) -> bool
```

Not a function in the code — the test in BR-U2-6.1 is a rule for deciding what to
detect, applied when writing each detector. The detectors themselves are specific:
`endpoint_not_implemented`, `shape_mismatch`, `status_code_undocumented`,
`auth_requirement_mismatch`, `screen_not_in_live`, `screen_differs_from_design`,
`rule_contradiction`.

Adding a detector means answering the question first. That is the point of stating it.

---

## 3. Payload Validation

The agent's payloads are validated before storage. Rejections use U1's taxonomy.

```
validate_feature_model(payload, known_artefact_ids):
    failures = []
    for feature in payload.features:
        if not feature.source_artefact_ids:
            failures.append(REJECTED_NO_JIRA_KEY,
                            f"feature {feature.slug} cites no source artefact")
        unknown = set(feature.source_artefact_ids) - known_artefact_ids
        if unknown:
            failures.append(REJECTED_UNKNOWN_JIRA_KEY, f"unknown artefacts: {unknown}")
    if has_cycle(payload.features):
        failures.append(REJECTED_INVALID_STEPS, "feature hierarchy contains a cycle")
    return failures
```

**A feature grounded in no artefact is rejected.** It is an invention, and inventions
are exactly what the traceability rule exists to stop — catching them at the feature
level is cheaper than catching them 200 test cases later.

---

## 4. Interaction with U1 and U7

| Dependency | Use |
|---|---|
| U1 `unit_of_work` | One transaction per resource during ingestion; one per payload for analysis |
| U1 `isolate` | Per-resource failure isolation |
| U1 `with_retry` | Transient external failures only |
| U1 `Result` | Every method returns one |
| U1 P2 source protocols | A3-A6 implement them; no write method exists to call |
| U7 `is_gate_open` | Checked before `analyse` work begins |
| U7 `unit_begin`/`complete` | Both stages are units |

**U2 registers 4 write tools**: `ingest_resources`, `analysis_upsert`,
`api_model_derive`, `ui_model_upsert`. All four are already named in U7's chat modes,
and U7's consistency check will confirm they exist once registered.

---

## 5. Property-Based Test Surface

| Component | Property | Category |
|---|---|---|
| Classification | Every raw reference yields exactly one type | PBT-03 invariant |
| Classification | The same reference always yields the same rule number | PBT-03 determinism |
| Classification | An unmatched reference is `unclassified`, never another type | PBT-03 invariant |
| Content hashing | Identical content yields an identical hash regardless of metadata | PBT-03 invariant |
| Content hashing | Different content yields a different hash | PBT-03 invariant |
| Asset parsing | Every filename is either associated or reported, never both and never neither | PBT-03 invariant |
| Asset parsing | Manifest override never changes a field the manifest does not name | PBT-03 invariant |
| API merge | Every returned endpoint exists in the code input | PBT-03 invariant |
| API merge | Every spec-only entry appears as a discrepancy | PBT-03 invariant |
| Ingestion | Successes plus failures plus skips equals the input count | PBT-03 invariant |

The last one is worth stating: it is how "one failure did not silently swallow three
others" gets verified.

---

## 6. Story Coverage

| Story | Where served |
|---|---|
| US-ING-01 Declare inputs | BR-U2-1, §2.1 |
| US-ING-02 Ingest Jira and Confluence | BR-U2-2, BR-U2-8, §2.2 |
| US-ING-03 Ingest Bitbucket and the API surface | BR-U2-5, §2.3 |
| US-ING-04 Ingest UI designs | BR-U2-4, §2.4 |
| US-ANA-01 Feature model and journeys | BR-U2-7.1, §3 |
| US-ANA-02 Business rules and integration points | BR-U2-7.2, BR-U2-6 |
| US-ANA-03 API model | BR-U2-5, §2.3 |
| US-ANA-04 UI model with verified selectors | BR-U2-7.3, BR-U2-6 |

**All 8 U2 stories served.**
