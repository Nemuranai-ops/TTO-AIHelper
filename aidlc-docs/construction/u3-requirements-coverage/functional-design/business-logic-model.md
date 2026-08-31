# Business Logic Model — U3 Requirements and Coverage

**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

---

## 1. What U3 Adds

U1 built the logic; U3 supplies its inputs and stores its output.

| U1 domain component | What U3 feeds it | What U3 does with the result |
|---|---|---|
| D6 `rate_risk` | Four signals from three sources | Stores rating, band and factors |
| D3 `derive_key_from_commits` | Commit history from A4 | Stores the link, or routes a gap |
| D2 `derive_coverage` | Requirement specs with technique inputs | Stores items, computes the hash, forecasts |
| D2 `apply_reduction` | The operator's decision | Stores both yields and a gap |
| D7 validation | Requirement batches | All-or-nothing acceptance |

**U3 contains no coverage arithmetic and no risk formula.** Those are U1's, and
duplicating either here would create two implementations that drift.

---

## 2. Algorithms

### 2.1 Risk signal gathering (BR-U3-1)

```
gather_signals(requirement, payload, uow, commit_index):
    rules       = uow.features.rules_for_feature(requirement.feature_id)
    endpoints   = [e for e in uow.features.list_endpoints()
                   if e.feature_id == requirement.feature_id]

    complexity  = band(len(rules), [1, 3, 6, 10])
    integration = band(len(endpoints), [0, 1, 3, 6])

    files = source_files_for(requirement, uow)
    if not files or not commit_index.available:
        change_frequency = None          # unavailable, NOT zero
    else:
        recent = count_commits_within(files, days=90, index=commit_index)
        change_frequency = band(recent, [0, 2, 5, 10])

    criticality = payload.get("business_criticality")        # None if not supplied
    evidence    = payload.get("criticality_evidence", "")

    return RiskSignals(criticality, evidence, complexity, integration, change_frequency)
```

`band(value, thresholds)` maps a count to 1-5. The thresholds are stated in
`business-rules.md` rather than tuned here, so they are reviewable in one place.

**`None` propagates to D6 as `unavailable`.** BR-4.4 then removes the factor from both
numerator and denominator, preserving the ratio among what is known.

### 2.2 Requirement derivation (BR-U3-2, BR-U3-6)

```
upsert_requirements(feature_slug, payload):
    if not gate_open(feature_slug, REQUIREMENTS):
        return REJECTED_GATE_CLOSED

    known_keys   = uow.artefacts.known_jira_keys()
    commit_index = CommitIndex(bitbucket, lookback_days=180)   # fetched lazily, once per file
    accepted, rejections, gaps = [], [], []

    for candidate in payload.requirements:
        failures = []
        if not is_atomic(candidate.statement):
            failures.append(REJECTED_INVALID_STEPS, suspected_split(candidate.statement))
        if candidate.category not in CATEGORIES:
            failures.append(REJECTED_INVALID_STEPS, "unknown category")
        if not candidate.source_artefact_ids:
            failures.append(REJECTED_NO_JIRA_KEY, "cites no source artefact")

        key = resolve_key(candidate, known_keys, commit_index)   # BR-U3-7
        if key is Gap:
            gaps.append(key)                                     # not a rejection
            continue
        if key is None:
            failures.append(REJECTED_NO_JIRA_KEY, "no resolvable Jira key")

        (rejections if failures else accepted).append(...)

    if rejections:
        return all_failures(rejections)          # nothing stored
    store(accepted, gaps)
```

**A gap is not a rejection.** A rejected requirement is the agent's mistake and must be
fixed. A gapped behaviour is a fact about the sources — nothing the agent can correct —
and failing the batch for it would leave the agent retrying forever.

### 2.3 Key resolution with a shared commit index (BR-U3-7)

```
class CommitIndex:
    """History fetched once per file, per run.

    At 500 requirements over 50 files, per-requirement fetching would make 490
    redundant calls to Bitbucket.
    """
    def commits_for(self, file_path):
        if file_path not in self._cache:
            self._cache[file_path] = bitbucket.log(repo, path=file_path,
                                                   since=now - lookback)
        return self._cache[file_path]


resolve_key(candidate, known_keys, index):
    direct = [l for l in candidate.links if l.type is DIRECT_STORY
              and l.key in known_keys]
    if direct:
        return direct[0]

    for path in source_files_of(candidate):
        outcome = derive_key_from_commits(path, index.commits_for(path), known_keys)
        if isinstance(outcome, KeyResolution):
            return outcome
    return Gap(candidate.statement, attempted=["direct-story", "commit-derivation"])
```

### 2.4 Coverage build and approval binding (BR-U3-4)

```
build_coverage(feature_slug):
    requirements = uow.requirements.query(feature_id=...)
    specs        = [to_spec(r, technique_inputs_for(r)) for r in requirements]

    model = derive_coverage(specs)                 # U1 D2
    digest = coverage_hash(model.items)            # BR-U3-4.2

    previous = uow.coverage.latest_for(feature_id)
    if previous and previous.content_hash == digest:
        version = previous.version                 # unchanged rebuild keeps approval
        invalidated = False
    else:
        version = (previous.version + 1) if previous else 1
        invalidated = bool(previous and previous.approved_by)

    store(model.items, version, digest)
    for requirement_id in model.undetermined_boundaries:
        record_gap("boundaries-undetermined", requirement_id)
    for uncovered in find_uncovered(model, [r.id for r in requirements]):
        record_gap("uncovered-requirement", uncovered)

    return CoverageBuildResult(version, digest, model.items, forecast(model),
                               approval_invalidated=invalidated)


coverage_hash(items):
    payload = [(i.id, i.requirement_id, i.test_type, i.technique,
                i.planned_count, i.is_required) for i in sorted(items, key=id)]
    return sha256(json(payload))
```

**`approval_invalidated` is returned, not merely implied.** The operator rebuilding
coverage needs to be told the Test Lead's approval no longer stands — discovering it
later, when the cases gate refuses, wastes a round trip and looks like a bug.

### 2.5 Reduction (BR-U3-5)

```
apply_reduction(feature_slug, reason, actor, override=False):
    model = current_model(feature_slug)
    band  = aggregate_risk_band(feature_slug)

    if band in (HIGH, CRITICAL) and not override:
        return REJECTED_ROLE_NOT_PERMITTED(
            f"{feature_slug} is rated {band}. Pass override=true to reduce it anyway; "
            f"the contradiction will be recorded.")

    technique = select_reduction(spec_for(feature_slug))       # U1 D2
    reduced   = D2.apply_reduction(model, technique)

    store_reduction(full_yield=model.planned_total,
                    reduced_yield=reduced.planned_total,
                    technique, reason, actor, band, was_override=override)
    record_gap("reduced-depth", feature_slug,
               detail=f"{model.planned_total} -> {reduced.planned_total} via {technique}")
    return rebuild(feature_slug)          # new hash, so approval invalidates itself
```

---

## 3. Interaction with Other Units

| Unit | Use |
|---|---|
| U1 | D2, D3, D6, D7; repositories; `unit_of_work`; `Result` |
| U2 | A4 for commit history; the artefacts, features, rules and endpoints it stored |
| U7 | `is_gate_open` before each stage; `stage_approve` for the Test Lead approval |
| U4 | Reads the approved model. U3 writes nothing U4 owns |
| U8 | Reads `gap` and `coverage_reduction` for its reports |

**U3 registers 4 write tools**: `requirements_upsert`, `coverage_build`,
`coverage_approve`, `coverage_reduce` — all four already named in U7's chat modes.

`coverage_approve` delegates to U7's `stage_approve` rather than re-implementing the
role restriction. One place decides who may approve what, so four services cannot
disagree.

---

## 4. Property Surface

| Component | Property | Category |
|---|---|---|
| Risk banding | `band` is monotonic non-decreasing in its input | PBT-03 |
| Risk banding | Output is always 1-5 for any non-negative count | PBT-03 |
| Signal gathering | An unavailable factor is never rendered as 0 | PBT-03 |
| Coverage hash | Identical item sets hash identically regardless of order | PBT-03 |
| Coverage hash | Changing `is_required` changes the hash | PBT-03 |
| Coverage hash | Changing rationale text does not | PBT-03 |
| Versioning | Version increments only when the hash changes | PBT-03 |
| Atomicity | A statement with no verb conjunction is never rejected as non-atomic | PBT-03 |
| Batch | Accepted plus rejected equals submitted | PBT-03 |
| Reduction | Reduced yield never exceeds full yield | PBT-03 |

The three hash properties are the ones worth having: they pin down exactly what
"modifying an approved model" means, and that definition is what the Test Lead's
approval rests on.

---

## 5. Story Coverage

| Story | Where served |
|---|---|
| US-TRQ-01 Atomic requirements | BR-U3-2, §2.2 |
| US-TRQ-02 Risk rating | BR-U3-1, §2.1 |
| US-TRQ-03 Edge cases | BR-U3-3 (`boundaries-undetermined`) |
| US-COV-01 Coverage model | §2.4, U1 D2 |
| US-COV-02 Depth from techniques | U1 D2, fed by §2.4 |
| US-COV-03 Yield forecast | §2.4 |
| US-COV-04 Approval gate | BR-U3-4.3, delegated to U7 |
| US-COV-05 Risk-based reduction | BR-U3-5, §2.5 |
| US-TRC-02 Commit-derived keys | BR-U3-7, §2.3 |
| US-TRC-03 Gap routing | BR-U3-3, §2.2 |

**All 10 U3 stories served.**
