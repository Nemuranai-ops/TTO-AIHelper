# Logical Components — U3 Requirements and Coverage

**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

One component.

---

## Why One

| Considered | Decision |
|---|---|
| **L8 CommitIndex** | **Added** — holds state, enforces bounds, has a lifetime |
| `CoverageHasher` | Declined — eight lines, no state, rules live in BR-U3-4.2 |
| `AtomicityChecker` | Declined — a pure function over a pattern set |
| `RiskSignalGatherer` | Declined — a service method reading three repositories |

**Three units each added two to four components. U3 adds one**, and that is the right
answer rather than an oversight. A component earns its place by holding state,
enforcing a boundary, or having a lifetime. A pure function wrapped in a class has
none of those, and the wrapper makes it harder to test rather than easier.

---

## L8: CommitIndex

**Ring**: Adapter | **Delivers**: U3-NFR-PRF-05, U3-NFR-IDX-01 to -04

### Responsibility

Fetch commit history once per distinct file for the duration of one requirement batch,
enforce the bounds, and report when either is reached.

### Interface

```
__enter__() -> CommitIndex
__exit__(...) -> None                       # discards the cache
commits_for(file_path) -> list[CommitRecord]
bounds_report() -> BoundsReport
```

### `BoundsReport`

| Field | Meaning |
|---|---|
| `files_indexed` | Distinct files fetched |
| `file_limit_reached` | True when the 200-file bound stopped further fetching |
| `truncated_files` | Files where history was cut at 500 commits |
| `skipped_files` | Files never fetched because the file bound was already reached |
| `guidance` | Present when either bound was hit |

**`skipped_files` is separate from `truncated_files`** because they produce different
gaps. A truncated file may still have yielded a key from its recent history; a skipped
file yielded nothing and its behaviours are untraceable for a reason that has nothing
to do with the repository's Jira discipline.

Conflating them would put "we ran out of budget" and "this file has no keys" in the
same bucket, and the operator's response to each is different.

### Bounds

| Bound | Default | Setting |
|---|---|---|
| Distinct files per batch | 200 | `TAAS_COMMIT_INDEX_MAX_FILES` |
| Commits per file | 500 | `TAAS_COMMIT_INDEX_MAX_COMMITS` |
| Lookback | 180 days | `TAAS_COMMIT_LOOKBACK_DAYS` (existing, U1) |

The lookback reuses U1's existing setting rather than introducing a second one. Two
settings for one window is how they end up disagreeing.

### Lifetime

Created on entering `requirements_upsert`, discarded on exit. Nothing survives the
call.

**A session-scoped index would serve history that changed since it was built**, and
there is no event to invalidate it on — the repository moves independently of the run.
Rebuilding per batch costs one round of fetches for the guarantee that derived
provenance reflects what the repository said when the batch was processed.

### Dependencies

`BitbucketSourceAdapter` (U2, via the P2 protocol), `platform.logging`. No service, no
domain component.

---

## Placement

```
        +-------------------------------------------+
        |   APPLICATION SERVICES  S3, S4            |
        +-------------------------------------------+
              |                        |
   +---------------------+   +---------------------+
   |  DOMAIN             |   |   PORTS  P1, P2     |
   |  D2 D3 D6 D7 (U1)   |   |                     |
   +---------------------+   +---------------------+
                                       ^
        +-------------------------------------------+
        |   ADAPTERS                                |
        |   A2 (U1)   A4 (U2)   + L8 CommitIndex    |
        +-------------------------------------------+
```

**Text alternative**: S3 and S4 depend on U1's domain components and on the port
protocols. L8 sits in the adapter ring beside U2's Bitbucket adapter, which it wraps.
No new domain component and no new port.

---

## Dependency Verification

| Component | Imports | Violates? |
|---|---|---|
| L8 CommitIndex | `ports.sources`, `domain.traceability` (for `CommitRecord`), `platform` | No |

L8 imports a domain *type* but no domain logic, and no service. The import contracts
hold unchanged.

---

## What U3 Does Not Add

Worth stating, because their absence is a decision:

- **No domain component.** The coverage arithmetic is D2's, the risk formula is D6's,
  the traceability rules are D3's. U3-NFR-MNT-04 asserts this, and the import contract
  enforces it — a copy here would drift, and the drift would be silent because both
  copies would produce plausible numbers.
- **No new port.** U3 reads through P1 and P2 as they stand.
- **No new emitter.** U3 stores; U8 reports.

---

## Configuration Additions

| Setting | Default | Component |
|---|---|---|
| `TAAS_COMMIT_INDEX_MAX_FILES` | 200 | L8 |
| `TAAS_COMMIT_INDEX_MAX_COMMITS` | 500 | L8 |
| `TAAS_ATOMICITY_ENFORCED` | true | S3 — allows the heuristic to be disabled wholesale if it proves more trouble than help |

`TAAS_ATOMICITY_ENFORCED` is a wholesale escape distinct from `force_atomic`'s
per-requirement one. If overrides cluster to the point that the heuristic is costing
more than it catches, turning it off is a configuration change rather than a code
change — and the clustering is visible because every override is recorded.

---

## Requirement Coverage

All 24 U3 NFR requirements have a delivering pattern (in
[nfr-design-patterns.md](nfr-design-patterns.md) §7) or this component.
