# Business Logic Model — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

Algorithms, flow and semantics for the domain kernel. Technology-agnostic: no framework, no
transport, no persistence mechanics beyond where an integrity rule is enforced.

---

## 1. The Domain Kernel

U1's domain answers four questions, and nothing else:

1. **Is this valid?** (D7 IntegrityValidator, with D1 construction invariants)
2. **Have we seen it before?** (D4 SimilarityAnalyzer)
3. **What does it trace to?** (D3 TraceabilityResolver)
4. **How much of it do we need?** (D2 CoverageModeller)

D5 allocates, D6 rates and classifies, D8 assesses change. None of the eight performs I/O. Every one
is a function of its inputs, which is what makes the property suite possible.

---

## 2. Algorithms

### 2.1 Similarity comparison (D4)

```
normalise(case):
    segments = [step.action + " || " + step.expected for step in case.steps]   # ordinal order
    text     = join(segments, " >> ")
    text     = lowercase(text)
    text     = collapse_whitespace(text)
    text     = strip_terminal_punctuation_per_segment(text)
    return NormalisedCase(text, hash=sha256(text), classes=set(case.equivalence_classes))

bucket_key(case):
    return feature_slug + "|" + test_type + "|" + str(len(case.steps))

similarity(a, b):
    if a.hash == b.hash: return 1.0
    sa, sb = shingles(a.text, 3), shingles(b.text, 3)
    return |sa & sb| / |sa | sb|                      # Jaccard

classify(candidate, existing, threshold=0.90):
    if candidate.classes != existing.classes: return DISTINCT     # BR-1.4 override, checked first
    s = similarity(candidate, existing)
    if s == 1.0: return IDENTICAL
    if s >= threshold: return NEAR_DUPLICATE
    return DISTINCT
```

**Candidate selection is by `bucket_key`**, never a full scan. At 10,000 cases a full pairwise
comparison is 50 million operations; bucketing reduces the comparison set to cases that could
plausibly match, which is what makes NFR-PRF-01's 200 ms budget reachable rather than aspirational.

**The equivalence-class check runs before the threshold**, so a differing class short-circuits to
DISTINCT without computing similarity at all — cheaper, and it makes the override unconditional
rather than a post-hoc correction.

### 2.2 Coverage derivation (D2)

```
derive_coverage(requirement, rules, ui_model, api_model):
    items = []
    for test_type in applicable_types(requirement.category):
        if not adds_value(test_type, requirement):
            items.append(CoverageItem(type, is_required=False, rationale=why_not))
            continue
        technique = select_technique(requirement, rules)
        count     = planned_count(technique, requirement)
        items.append(CoverageItem(type, technique, count, rationale))
    if total(items) > 50:
        items = apply_reduction(items, select_reduction(requirement))
    return items

planned_count(technique, req):
    EQUIVALENCE_PARTITIONING -> len(valid_classes) + len(invalid_classes)
    BOUNDARY_VALUE_ANALYSIS  -> 3 * len(boundaries)          # below, at, above
    DECISION_TABLE           -> len(rules)
    STATE_TRANSITION         -> len(valid_transitions) + len(forbidden_transitions)
    DIRECT                   -> 1
```

**`adds_value` returning false produces a row, not a silence** (BR-2.6). The distinction between
"we considered this and it adds nothing" and "nobody looked" is the difference between a coverage
model and a coverage claim.

### 2.3 Jira key resolution (D3)

```
resolve_key(entity, links, known_keys, commits):
    direct = [l for l in links if l.type == DIRECT_STORY and l.key in known_keys]
    if direct: return Ok(strongest(direct))

    candidates = []
    for commit in commits within lookback_window(180 days):
        for key in extract_keys(commit.message):
            if key in known_keys:
                candidates.append((key, commit))

    if not candidates:
        return Gap(entity, attempted=["direct-story", "commit-derivation"])

    chosen = select(candidates)      # BR-3.2: recency, then lines changed, then recency, then lexical
    return Ok(DerivedLink(chosen.key,
                          type=DERIVED_FROM_COMMIT,
                          evidence=chosen.commit.sha,
                          selection_basis=describe_rule_used(),
                          alternatives=candidates - chosen))
```

**Every path is explicit.** A key resolves directly, resolves by derivation with its basis recorded,
or does not resolve and becomes a gap. There is no fourth path in which something plausible is
attached.

### 2.4 Risk rating (D6)

```
rate(requirement, signals):
    available = [f for f in FACTORS if signals.has(f)]
    if not available: return Rating(score=None, band=None, partial=True, reason="no signals")

    weighted = sum(signals[f] * WEIGHT[f] for f in available)
    maximum  = sum(5 * WEIGHT[f] for f in available)
    score    = round(weighted / maximum * 100)
    return Rating(score, band_for(score),
                  partial=len(available) < len(FACTORS),
                  factors={f: signals.get(f, "unavailable") for f in FACTORS})
```

Missing factors leave both numerator and denominator, preserving the ratio among known signals
rather than diluting it toward zero.

### 2.5 Automatability (D6)

```
classify(case, ui_model, api_model):
    for rule in DECISION_LIST:               # BR-5.1, order significant
        if rule.matches(case, ui_model, api_model):
            return Verdict(rule.verdict, reason=f"rule {rule.n}: {rule.text}",
                           annotation=rule.annotation)
    return Verdict(NEEDS_REVIEW, reason="rule 10: no rule matched")
```

### 2.6 Identifier allocation (D5)

```
allocate(kind, feature_slug, sequence_state):
    if supplied_id_present: return Err(REJECTED_SELF_SUPPLIED_ID)
    n = sequence_state.next(kind, feature_slug)
    if n > 99999: return Err(FAILED_INTERNAL, "sequence exhausted")
    return Ok(f"{PREFIX[kind]}-{feature_slug.upper()}-{n:05d}"), sequence_state.advance()

stable_id_for(candidate, existing_cases):
    match = find(existing_cases, coverage_item_id == candidate.coverage_item_id
                                 and title == candidate.title
                                 and not is_obsolete)
    return match.id if match else None       # None means allocate fresh
```

---

## 3. The Validation Pipeline

Ordering is a design decision, not an accident: cheap structural checks precede expensive lookups,
so a malformed batch fails before touching the database.

```
validate_batch(cases, links, known_keys, gate_state):

  Stage A - gate (once per batch)
    coverage baseline approved for this feature?          -> REJECTED_GATE_CLOSED, stop
    approved_content_hash still matches?                  -> REJECTED_GATE_CLOSED, stop

  Stage B - structural (per case, no I/O)
    identifier not supplied                               -> REJECTED_SELF_SUPPLIED_ID
    at least one step                                     -> REJECTED_NO_STEPS
    every step has non-blank expected                     -> REJECTED_NO_STEPS
    ordinals unique and gapless from 1                    -> REJECTED_INVALID_STEPS
    data-dependent steps carry an equivalence class       -> REJECTED_MISSING_EQUIVALENCE_CLASS

  Stage C - traceability (per case, requires known_keys)
    at least one trace link                               -> REJECTED_NO_JIRA_KEY
    at least one resolves to a Jira key                   -> REJECTED_NO_JIRA_KEY
    every referenced key exists in the ingested set       -> REJECTED_UNKNOWN_JIRA_KEY

  Stage D - corpus (per case, indexed lookup)
    not a duplicate of an existing case                   -> REJECTED_DUPLICATE
    not a duplicate of another case in this batch         -> REJECTED_DUPLICATE

  Collect every failure across B, C and D.
  If any failed: roll back, return BatchValidation with all failures.
  If none failed: proceed to allocation and commit.
```

**Stage A stops the batch; stages B, C and D collect.** A closed gate makes every case in the batch
moot, so continuing wastes work. A malformed case does not invalidate its neighbours, so every fault
is reported together and one correction pass can fix them all.

---

## 4. Error Taxonomy

Two families, fifteen codes. The family is the actionable part: `REJECTED_*` means the agent must
change its input; `FAILED_*` means the system had a problem and blind retry is inappropriate.

### 4.1 `REJECTED_*` — agent-fixable

| Code | Meaning | Remediation given to the agent |
|---|---|---|
| `REJECTED_NO_STEPS` | Case has no steps, or a step lacks an expected result | Add ordered steps, each with an expected result |
| `REJECTED_INVALID_STEPS` | Ordinals duplicated or gapped | Number steps consecutively from 1 |
| `REJECTED_NO_JIRA_KEY` | No link resolves to a Jira key | Add a link, or route the behaviour to the gap report |
| `REJECTED_UNKNOWN_JIRA_KEY` | Key not in the ingested set | Ingest the issue, or use a key that exists |
| `REJECTED_DUPLICATE` | Identical or near-duplicate | Named existing case shown; differentiate or drop |
| `REJECTED_MISSING_EQUIVALENCE_CLASS` | Data without a class label | State the class or boundary the value represents |
| `REJECTED_SELF_SUPPLIED_ID` | Caller supplied an identifier | Omit it; the toolchain allocates |
| `REJECTED_GATE_CLOSED` | Prior stage unapproved, or approved content changed | Obtain approval for the named stage |
| `REJECTED_ALREADY_COMPLETE` | Unit and stage already completed | Pass the regenerate flag if re-running is intended |
| `REJECTED_ROLE_NOT_PERMITTED` | Role may not perform this approval | Only the Test Lead approves the coverage baseline |

### 4.2 `FAILED_*` — system problems

| Code | Meaning |
|---|---|
| `FAILED_DB_UNAVAILABLE` | Database unreachable or corrupt |
| `FAILED_MCP_UNREACHABLE` | External MCP server unreachable after retries |
| `FAILED_MIGRATION` | Schema migration failed and was rolled back |
| `FAILED_TIMEOUT` | Operation exceeded its budget |
| `FAILED_LOCKED` | Database locked, possibly by a killed process |
| `FAILED_INTERNAL` | Unexpected condition; the operation rolled back |

### 4.3 Result semantics

- Every tool returns `Result`. **No exception crosses the MCP boundary.**
- Every failure carries a code, a message, and remediation text
- Messages are sanitised: no path outside the workspace, no stack detail, no credential
- `is_rejection(result)` lets the agent branch without parsing prose

---

## 5. Transaction and Unit-of-Work Semantics

| Property | Rule |
|---|---|
| Boundary ownership | The service opens and closes the transaction; repositories never open one |
| Granularity | One write-tier tool call, one transaction |
| Atomicity | Full application or full rollback; no partial batch |
| Ingestion exception | Per resource, not per run, so one unreachable source does not discard successful retrieval (NFR-REL-04) |
| Lease | `unit_begin` issues a lease; `unit_complete` requires it; an uncompleted lease leaves the unit `in-progress` |
| Interruption | A killed process leaves the unit `in-progress` and produces no partial output; the operator decides on resume (US-BAT-03 AC3) |
| Stale lock | Detected and reported with recovery guidance, never silently cleared |

### Retry policy (X4)

| Setting | Value |
|---|---|
| Attempts | 3 |
| Backoff | 1s, 2s, 4s, with jitter |
| Retryable | Connection error, timeout, HTTP 429, HTTP 5xx |
| Never retried | HTTP 4xx authentication and validation failures |
| On exhaustion | Fail the unit, log the reason, continue the run |

**Jitter matters here specifically.** Ingestion issues many requests in a burst; without jitter,
three synchronised retries against a rate-limited Jira make the situation worse rather than better.

---

## 6. Data Flow Through the Kernel

```
   agent-supplied payload
            |
            v
   +--------------------+
   |  D1 construction   |  invalid shapes cannot be constructed at all
   +--------------------+
            |
            v
   +--------------------+
   |  D7 validation     |  gate, structure, traceability, duplication
   +--------------------+
            |
      +-----+-----+
      |           |
   failures     all pass
      |           |
      v           v
  rollback   +--------------------+
  report all |  D3 resolve keys   |
  failures   +--------------------+
                     |
                     v
             +--------------------+
             |  D6 classify       |  risk, automatability
             +--------------------+
                     |
                     v
             +--------------------+
             |  D5 allocate ids   |
             +--------------------+
                     |
                     v
             +--------------------+
             |  repository commit |
             +--------------------+
```

**Text alternative**: an agent payload is constructed into domain records, which rejects malformed
shapes immediately. D7 validates in four stages. Failures roll back the whole batch and report
together. On success, D3 resolves traceability keys, D6 classifies risk and automatability, D5
allocates identifiers, and the batch commits in one transaction.

---

## 7. Property-Based Test Surface

Partial PBT mode enforces PBT-02, PBT-03, PBT-07, PBT-08, PBT-09. Every property below targets a
domain component and needs no database, network, or fixture.

| Component | Property | Category |
|---|---|---|
| D1 | `from_dict(to_dict(x)) == x` for every entity | PBT-02 round-trip |
| D1 | A `TestCase` cannot be constructed with an empty step list | PBT-03 invariant |
| D5 | `decode(encode(id)) == id` | PBT-02 round-trip |
| D5 | Allocation is strictly monotonic within (kind, feature) | PBT-03 invariant |
| D5 | No identifier is issued twice | PBT-03 invariant |
| D4 | `similarity(a, a) == 1.0` | PBT-03 reflexive |
| D4 | `similarity(a, b) == similarity(b, a)` | PBT-03 symmetric |
| D4 | `0.0 <= similarity(a, b) <= 1.0` | PBT-03 bounded |
| D4 | Differing equivalence class always yields DISTINCT | PBT-03 invariant |
| D2 | Total yield equals the sum of per-feature yields | PBT-03 invariant |
| D2 | Reduction never increases planned count | PBT-03 invariant |
| D2 | Every requirement has at least one coverage item | PBT-03 invariant |
| D3 | Every forward matrix edge has a reverse edge | PBT-03 invariant |
| D3 | Every non-obsolete case reaches at least one Jira key | PBT-03 invariant |
| D6 | An unavailable factor never lowers the score relative to omitting it | PBT-03 invariant |
| D6 | The same case always yields the same verdict | PBT-03 determinism |

### Generators (PBT-07)

Domain-specific, not primitives: realistic `JiraKey` (2-10 uppercase letters, hyphen, positive
integer), `FeatureSlug` (lowercase hyphenated), `TestCase` (1-20 ordered steps with non-empty
actions and expectations, and coherent equivalence classes), `CoverageModel` (consistent
requirement-to-item relationships).

**Unconstrained primitives would produce meaningless counterexamples.** A random byte string as a
Jira key tests the parser, not the rule.

### Reproducibility (PBT-08)

Hypothesis default shrinking; failing seeds recorded in the test report for deterministic replay.

---

## 8. Story Coverage

| Story | Where served |
|---|---|
| US-ENB-01 Schema and durability | `domain-entities.md` entities, integrity rules, indexes; §5 transaction semantics |
| US-ENB-02 MCP server with typed tools | §4 error taxonomy and Result semantics |
| US-ENB-03 Observability and failure isolation | §5 retry policy and transaction semantics |
| US-ENB-04 Secrets and confidentiality | §4.3 message sanitisation; `domain-entities.md` synthetic-data rule on `test_data` |
| US-ENB-05 Scale and performance | §2.1 bucketing; `domain-entities.md` indexes |
| US-ENB-06 Test suite including PBT | §7 property surface and generators |
| US-TRC-01 Mandatory Jira key | §3 validation stage C; `business-rules.md` BR-7, BR-8; dual enforcement in `domain-entities.md` |

**All 7 U1 stories served.**

---

## 9. Technology Independence

This model names no framework, no library, and no storage engine. Two places reference SQLite
constraints — the integrity rule table in `domain-entities.md` and the index list — and both are
deliberate: *where* an integrity rule is enforced is a business decision about how unbreakable the
rule must be, not an implementation detail. The dual enforcement of the Jira key rule and the
mandatory-steps rule is the clearest example: it exists because those two rules must survive a
future code path that forgets to call the validator.
