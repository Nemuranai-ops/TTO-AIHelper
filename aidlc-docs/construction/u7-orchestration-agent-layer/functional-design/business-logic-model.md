# Business Logic Model — U7 Orchestration and Agent Layer

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

---

## 1. What S10 Does

S10 RunStateService answers three questions and nothing else:

1. **May this work proceed?** — gate evaluation
2. **Who holds this unit, and is that claim still alive?** — lease management
3. **Where does the run stand?** — status composition

It touches no other service. S4, S5, S6 and S7 call into it for gate checks; it calls
back into nothing. That is what keeps the single service-to-service edge acyclic.

**There is no method that selects the next unit.** C-12 reserves that to the
operator, and the absence is the enforcement.

---

## 2. Algorithms

### 2.1 Gate evaluation (BR-U7-3)

```
evaluate_gate(unit_ref, stage, coverage_hash_fn):
    prior = prior_stage(stage)
    if prior is None:
        return GateEvaluation(is_open=True)          # ingest has no predecessor

    record = run_state.get(unit_ref, prior)
    if record is None or record.state != COMPLETED:
        return closed(NOT_COMPLETED,
                      f"{prior} is not complete for {unit_ref}",
                      f"Complete {prior} first")

    if record.approved_by is None:
        role = " (Test Lead only)" if prior is COVERAGE else ""
        return closed(NOT_APPROVED,
                      f"{prior} is complete but not approved",
                      f"Approve {prior} for {unit_ref}{role}")

    current = coverage_hash_fn(unit_ref, prior)
    if record.approved_content_hash is not None and current != record.approved_content_hash:
        return closed(CONTENT_CHANGED,
                      f"{prior} was approved on {record.approved_at}, "
                      f"but its content has changed since",
                      f"Re-approve {prior}; the prior approval no longer applies")

    return GateEvaluation(is_open=True, approved_by=record.approved_by,
                          approved_at=record.approved_at)
```

**The hash comparison is skipped when no hash was recorded.** An approval given
without one is honoured rather than permanently blocking — but the report says so, so
the weaker guarantee is visible rather than assumed.

### 2.2 Lease classification (BR-U7-2)

```
classify_lease(record, now, stale_after_minutes=30):
    reference = record.last_heartbeat or record.leased_at
    age = minutes_between(reference, now)

    if age <= stale_after_minutes:
        return LeaseStatus(ACTIVE, age,
            guidance=f"Another session claimed this {age}m ago and appears active.")

    return LeaseStatus(STALE, age, produced_so_far=record.metrics,
        guidance=(f"Claimed {age}m ago with no sign of life since. "
                  f"If that session has ended, restart with regenerate=true. "
                  f"It had produced: {summarise(record.metrics)}."))
```

**No branch clears the lease.** The function returns a classification and guidance.
Clearing a lock another process still holds is how databases get corrupted, and the
service cannot know whether the other session is dead or merely slow.

### 2.3 Status composition (BR-U7-4)

```
compose_status(scope=None):
    rows = []
    for record in run_state.all(scope):                    # already sorted by (unit_ref, stage)
        rows.append(UnitStatusRow(
            unit_ref=record.unit_ref, stage=record.stage, state=record.state,
            changed_at=record.changed_at,
            approved_by=record.approved_by, approved_at=record.approved_at,
            gate_open=evaluate_gate(record.unit_ref, record.stage).is_open,
            lease_status=classify_lease(record) if record.state is IN_PROGRESS else None,
            metrics=record.metrics))

    return StatusReport(units=rows, corpus=corpus_totals(),
                        business_rules=config.business_rule_fingerprint())
```

Sorted by `(unit_ref, stage_order)` — stable and semantically neutral. **No sort by
readiness, no `next` field, no filtering to open gates.** Each would turn a report
into a proposal.

### 2.4 Resume presentation (BR-U7-5)

```
resume_view():
    interrupted = [r for r in run_state.all() if r.state is IN_PROGRESS]
    return {
        "interrupted": [{"unit": r.unit_ref, "stage": r.stage,
                         "lease": classify_lease(r),
                         "produced": r.metrics} for r in interrupted],
        "completed":   count_by_state(COMPLETED),
        "note": "Nothing was lost. Unit work is transactional: an interrupted unit "
                "committed nothing, so restarting it re-runs it from the beginning.",
    }
```

The note matters. An operator returning after a crash needs to know whether partial
output is lurking. It is not — and saying so removes the impulse to go looking.

---

## 3. Interaction with U1

U1 built three thin tool wrappers over `RunStateRepository`. This stage decides their
fate.

**Decision: the wrappers are retained and rewired, not replaced.**

| Tool | U1 behaviour | U7 behaviour |
|---|---|---|
| `unit_begin` | Direct repository write; refuses `in-progress` and `completed` | Delegates to S10: issues a lease with `leased_at` and `lease_holder`, and returns a `LeaseStatus` assessment on refusal |
| `unit_complete` | Direct write; lease match | Delegates to S10: validates the transition per BR-U7-7 and commits metrics |
| `stage_approve` | Direct write; string role check | Delegates to S10: `Role` enum, content hash recorded, attempts logged |

**Why retain rather than replace.** The tool names are already registered, and the
agent layer being written in this same unit is authored against them. Renaming would
break nothing today and confuse everything later. The change is behind the surface:
handlers call S10 instead of writing to the repository directly.

The gate check `is_gate_open` that S4, S5, S6 and S7 will call is new — U1 had no
service to host it.

---

## 4. Operator Interaction, End to End

One unit through one stage, as the operator experiences it:

```
1. Operator selects the Cases chat mode and names the feature.
      "Generate test cases for checkout."

2. Agent calls unit_begin(unit_ref="checkout", stage="cases").
      -> S10 evaluates the gate: is coverage complete, approved, unchanged?
      -> Closed: the refusal names which condition failed and what opens it.
      -> Open: a lease is issued.

3. Agent reads what it needs (coverage_get, requirements_query) and reasons out
   the batch.

4. Agent calls testcases_upsert with the whole batch.
      -> One transaction. Validated, de-duplicated, identified, committed - or
         none of it, with every failure named.

5. Agent calls unit_complete(lease_id, metrics).
      -> State and metrics commit together.

6. Agent presents the outcome and STOPS.
      -> It does not announce the next unit. There is no tool that would tell it.

7. Operator reviews, then approves:
      stage_approve(unit_ref="checkout", stage="cases", approver, role)
      -> Recorded with the content hash. The next stage's gate now opens.
```

**Step 6 is the whole of C-12 in practice.** The agent stops because the surface
offers nothing else to do.

---

## 5. Property-Based Test Surface

| Component | Property | Category |
|---|---|---|
| Stage ordering | `prior_stage(next_stage(s)) == s` for every non-terminal stage | PBT-02 round-trip |
| Stage ordering | `prior_stage(ingest)` is None; every other stage has exactly one prior | PBT-03 invariant |
| Gate evaluation | A gate is open only when all three conditions hold — for every generated combination | PBT-03 invariant |
| Gate evaluation | A closed gate always names exactly one failed condition | PBT-03 invariant |
| Lease classification | Age is monotonic in elapsed time | PBT-03 invariant |
| Lease classification | Never returns an instruction to clear the lease | PBT-03 invariant |
| Status composition | Output is sorted by `(unit_ref, stage_order)` for any input order | PBT-03 invariant |
| Status composition | Contains no field named `next`, `recommended` or `ready` | PBT-03 invariant |
| Transitions | Only the BR-U7-7 transitions are accepted, for every state pair | PBT-03 invariant |

The last two are unusual as properties, and deliberate: **C-12 is a constraint on
what the system must never do**, and a property test over all generated inputs is a
stronger guard than an example test over the three someone thought of.

---

## 6. Story Coverage

| Story | Where served |
|---|---|
| US-BAT-01 Name the batch scope | BR-U7-7 transition validity; §4 step 2 |
| US-BAT-02 Durable transactional unit state | BR-U7-1 lease lifecycle; §2.3 |
| US-BAT-03 Resume after interruption | BR-U7-2, BR-U7-5; §2.2, §2.4 |
| US-BAT-04 Stop at every stage gate | BR-U7-3; §2.1 |
| US-AGT-01 Repository instructions | frontend-components.md §1 |
| US-AGT-02 Per-stage chat modes | BR-U7-6; frontend-components.md §2 |
| US-AGT-03 Register the MCP servers | frontend-components.md §5 |
| US-AGT-04 Path-scoped instructions and prompts | frontend-components.md §3, §4 |

**All 8 U7 stories served.**
