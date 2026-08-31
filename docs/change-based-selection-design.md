# Change-based test selection — design note

**Status:** proposal, awaiting approval. Nothing in this note is implemented.
**Date:** 2026-08-31 · **Against:** `ae2f5ca`
**Decision needed from:** Test Lead / architecture owner

---

## What this note is for

Two statements of intent, which pull in opposite directions and therefore need to be
reconciled deliberately rather than by accident:

1. **Repository code is not a requirement source.** What a test case *exists to
   verify* comes from stories, business rules and design — never from reading the
   implementation. A corpus derived from code tests what was built, not what was
   asked for, and can never find a missing feature.
2. **Repository code *is* the authority on what to re-run.** Given a diff between two
   versions, the system should select the subset of the existing corpus that covers
   what moved, so a regression run is proportionate to the change. Test smarter, not
   harder.

These are compatible if and only if the code→case relationship is treated as an
**index, not a source**: built after cases exist, from artefacts already in the
corpus, and used only to *select* among cases, never to decide which cases exist.
That single sentence is the architectural constraint this note is built around.

This note answers three questions:

- **A.** How does a changed file path map to a test case?
- **B.** What classification should a *modified* file produce?
- **C.** Where does selection get entered, and what does it return?

---

## Where the code stands today

### Principle 1 already holds, structurally

| Guard | Where |
|---|---|
| The requirements stage cannot reach Bitbucket — no Bitbucket tool is in its tool list | `.github/chatmodes/requirements.chatmode.md` |
| Code enters only as an **API model** (endpoints), at the analyse stage | `services/analysis.py::derive_api_model` |
| Commit history is used only to derive a **Jira key** for a requirement no story names — provenance, not content | `domain/traceability.py` (`DERIVED_FROM_COMMIT`) |
| Every case must still resolve to a story-backed key; a code link cannot satisfy the rule | `domain/traceability.py:75` (`require_jira_key` accepts only `DIRECT_STORY` / `DERIVED_FROM_COMMIT`) |

No change is proposed to any of these, and each should be treated as a regression
guard on the work below.

### Principle 2 is provided for but does not work end to end

**Detection is real and correct.** `ChangeDetector._detect_bitbucket`
(`adapters/change_detector.py:132`) diffs the baseline head against the current head
per repository via `git diff --name-status`, producing
`ChangedRef(ref=<repo-relative path>, source="bitbucket", kind=modified|added|removed)`.
That is exactly the version-to-version input required.

**But nothing maps a changed path to a case.** `DeltaService._edges_for`
(`services/delta.py:224`) resolves impact through `uow.traces.for_target(change.ref)`
— it needs a case carrying a trace link whose `target_ref` *is* that file path.
`LinkType.CODE_SYMBOL` exists for exactly this purpose (`domain/model.py:33`, and it
is in the `trace_link` `CHECK` constraint), but **nothing ever writes one**:
`code-symbol` appears nowhere under `.github/`, and `testcases_upsert` accepts such a
link without requiring it. Every changed file therefore falls through to `unmapped`.

**And a modified file would classify as unchanged anyway.** `services/delta.py:247`:

```python
target_removed   = change.kind == "removed",
statement_changed = (change.kind == "modified" and change.source == "jira"),
rule_changed      = False,
```

A modified Bitbucket path sets none of the four booleans, so `classify_edge` returns
`UNCHANGED` — *"source changed but the verified behaviour did not"*. Only a deleted
path yields `OBSOLETE`.

**No entity in the corpus points at code.** `TestCase` has no target endpoint or
screen field; it reaches a requirement through `coverage_item_id`. `TestableRequirement`
carries `feature_id` and `source_artefact_ids`, not endpoints. (The reason string
*"the endpoint or screen it targets was removed"* in `classify_edge` is aspirational —
`target_removed` is set purely from the change kind.)

---

## A. How a changed path maps to a case

### Option A1 — the agent attaches `code-symbol` links at generation time

The cases chat mode instructs the model to add
`{type: "code-symbol", target_ref: "<repo>:<path>"}` when a case targets a known
endpoint.

**Rejected.** Three reasons, in increasing order of seriousness:

- It puts implementation code in front of the model during the *cases* stage, which
  is precisely where principle 1 says it must not be.
- It is a model-authored fact that must stay true across thousands of cases and many
  sessions — the category this repository's whole design says deterministic code
  should own.
- It goes stale silently. A file rename breaks the link with no error, and a broken
  selection index fails safe-looking: it under-selects, and an under-selection is
  indistinguishable from a small change.

### Option A2 — derive the index deterministically, at selection time ✅ **recommended**

The join already exists in the schema, with **no migration required**:

```
changed file_path
   → api_endpoint.file_path          (already stored, repo-relative — same shape as git diff)
   → api_endpoint.feature_id         (already stored by derive_api_model)
   → testable_requirement.feature_id
   → coverage_item.requirement_id
   → test_case.coverage_item_id      (WHERE is_obsolete = 0)
```

`api_endpoint` (migration `m001_initial.py:74`) carries both `feature_id` and
`file_path`. `screen` carries `feature_id` too, so UI cases join by the same route.

**Granularity is the feature, not the individual case.** That is coarser than ideal
and it is the honest ceiling of what today's data supports. It is still a large win:
*"this release's diff touches 3 of 22 features — run their 780 cases, not all 6,140"*
is the whole point of the exercise. It is also fully deterministic, needs no agent,
and cannot go stale independently of the API model it is derived from.

Two caveats to carry into implementation:

- `api_endpoint.feature_id` is **nullable** — it is `NULL` whenever `api_model_derive`
  ran without a `feature_slug`. An endpoint with no feature cannot be resolved and
  must be **reported as unresolvable**, never silently skipped.
- The index is only as current as the last `api_model_derive`. Selection must report
  the head commit the API model was derived at, so a stale index is visible rather
  than assumed.

Implementation cost: one query (`endpoints by file_path`) beside the existing
`list_endpoints()`. No schema change, no new agent instruction.

### Option A3 — case granularity later, by diffing API models

Once A2 is in place, re-deriving the API model at the new head and comparing endpoint
sets gives case-level precision *and* answers questions A2 cannot:

| Observed | Means | Output |
|---|---|---|
| Endpoint disappeared | Cases targeting it may be dead | `OBSOLETE` **candidates**, for human confirmation — never auto-retired on a feature-level join |
| Route or method changed | The contract moved | `REQUIRES_UPDATE` candidates |
| **Endpoint appeared** | New behaviour with no requirement behind it | **Coverage gap — untested new behaviour** |

The third row is arguably the most valuable output in this whole note, and it is the
existing "unmapped is loud" discipline applied to code rather than to Jira.

**Recommendation: A2 now, A3 as a named follow-up.** A3 should not gate A2.

---

## B. What classification a modified file should get

**Recommendation: none. Do not change `ChangeClassification`.**

The enum answers *"is this case still valid?"* — and for a modified implementation
file, `UNCHANGED` is the **correct** answer. The code moved; what the case verifies
did not. Promoting these to `REQUIRES_UPDATE` would flood the human-revision list
with hundreds of cases that need no revision at all, which is the exact opposite of
testing smarter.

The mistake to avoid is overloading one enum with two different questions:

| Question | Answered by | Output |
|---|---|---|
| Is this case still valid? | `ChangeClassification` (unchanged) | retire / revise / keep |
| Should this case be re-run? | **new, orthogonal** | an ordered run list |

So: add a **selection axis** alongside the existing classification, rather than a
fourth enum value. Existing classification semantics, their tests and their property
suite do not move.

The one case where modified code genuinely *does* imply `REQUIRES_UPDATE` — the
contract itself changed — is not knowable from `--name-status` alone. It needs the
API-model comparison in A3, and should be introduced there with that evidence, not
guessed at here.

---

## C. Where selection is entered, and what it returns

### It must not be `delta_detect`

`delta_detect` has side effects by design: it starts a run, writes a `change_event`,
retires obsolete cases, and — when detection was complete — **advances the baseline
and completes the run** (`services/delta.py`, `advance_baseline`). Asking *"what
should I run for this release?"* must not consume the delta, and must be repeatable.

### It must take an explicit version pair

The requirement is *"changes done to code from one version to another"* — an
arbitrary pair of refs (`v1.4.0..v1.5.0`), not "since the last completed run". The
existing delta machinery is baseline-relative and cannot answer that. A separate
entry point taking explicit `base` and `head` also makes the answer reproducible,
which a baseline-relative one is not.

**Proposal:** a new read-only tool, `selection_for_change`, on the read tier
(`mcp/tools_read.py`), taking `{repo_slug, base, head, feature_slug?}` and writing
nothing.

### Output shape

```jsonc
{
  "base": "v1.4.0", "head": "v1.5.0",
  "api_model_derived_at": "<commit>",        // so a stale index is visible
  "selected": [                               // ordered; see below
    { "case_id": "TC-CHECKOUT-00012", "feature": "checkout",
      "risk_band": "high", "test_type": "api-contract",
      "why": ["src/Checkout/CartController.cs → POST /cart/items"] }
  ],
  "selected_count": 780, "active_corpus": 6140, "selection_scale": 0.127,
  "not_selected_count": 5360,                 // stated, so the risk is accepted knowingly

  "changed_paths_defining_endpoints_with_no_case": [...],  // HIGH — untested change
  "changed_paths_with_unresolvable_feature": [...],        // HIGH — index incomplete
  "changed_paths_not_indexed": { "count": 48, "sample": [...] },  // low — .csproj, README

  "derivation": "..."
}
```

**Ordering** — deterministic, no model involved: `risk_band` descending, then the
number of changed paths reaching the case, then `case_id` as a stable tiebreak.
Risk bands already exist on `TestableRequirement`.

**Scale guard** — reuse the existing `LARGE_IMPACT_THRESHOLD` (0.20,
`domain/impact.py`). Above it, say so plainly: selecting 30% of the corpus saves
little and carries selection risk, so run the full suite.

**What stays loud.** The existing discipline is that *"we found no link"* and
*"there is no impact"* are different statements. Applied here, changed paths must be
partitioned by severity rather than lumped into one `unmapped` list — a changed
`.csproj` is noise, a changed controller that reaches no case is an **untested
change** and the single most important line in the output.

**Selection is a report, not an action.** `DeltaService` creates nothing, and that
invariant holds here: this returns a list. Executing it is out of scope for this
system (README, *Not in scope*).

---

## What would change, by layer

| Layer | Change | Notes |
|---|---|---|
| `domain/selection.py` | **New.** Pure function: (changed paths, path→feature index, feature→cases index, risk bands) → ordered selection + severity-partitioned residue | No I/O; keeps `domain-is-pure`; Hypothesis-testable |
| `adapters/sqlite/queries` | One query: endpoints by file path | No migration |
| `services/` | Build the indexes, call the domain function | Creates nothing |
| `mcp/tools_read.py` | `selection_for_change` (read tier) | Read-only, no run, no baseline move |
| `.github/chatmodes/` | Nothing at generation time. Possibly a new selection mode later | **Deliberately untouched** — principle 1 |
| Schema | **None** | The join already exists |

---

## Non-goals

- Deriving requirements or cases from code. Unchanged, and guarded by the four rows
  in *Principle 1 already holds*.
- Auto-retiring cases on a feature-level join. Too coarse to be safe; obsolescence
  stays with A3's endpoint evidence and human confirmation.
- Executing the selected tests. Out of scope for this system.
- Fetching or parsing OpenAPI spec content — a separate, already-documented limit
  (see `architecture.html`, Plate 2).

---

## Open questions

1. **Is feature-granularity selection acceptable for the first version?** It is what
   the schema supports today without a migration. Case granularity needs A3.
2. **Should an unresolvable feature (`api_endpoint.feature_id IS NULL`) block a
   selection, or degrade it with a warning?** Blocking is safer; degrading is more
   usable. My inclination is to degrade loudly, and let the Test Lead decide whether
   to proceed — consistent with how coverage gaps are handled elsewhere.
3. **Should selection require an approved coverage baseline for the features it
   touches?** Selecting from an unapproved corpus may be legitimate for a smoke run,
   but it should probably be stated in the output rather than silently allowed.
4. **Does A3 land in this piece of work or a later one?** It is where the real value
   is — especially *new endpoint with no requirement* — but it is materially larger.
