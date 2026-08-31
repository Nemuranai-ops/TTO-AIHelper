# NFR Design Patterns — U3 Requirements and Coverage

**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

Four patterns specific to U3, on top of the inherited set. The smallest addition of
any unit so far, and the right size: U3 orchestrates logic that already carries its
own patterns.

---

## 1. Inherited

| Pattern | Use in U3 |
|---|---|
| P-RES-01 Unit of Work | One transaction per requirement batch, per coverage build |
| P-SCL-01 Capped pagination | Requirement queries inherit the 200-record cap |
| P-SEC-01 Two-level validation | Pydantic at the boundary, D7 beneath |
| P-SEC-03 Message sanitisation | Every rejection passes through it |
| P-OBS-01 Correlation propagation | Build, approval and reduction all carry the run id |
| P-MNT-01 Dependency inversion | Services depend on ports |
| P-MNT-02 Import contracts | Enforce that U3 holds no coverage arithmetic |
| P-U7-02 Read-only gate evaluation | `is_gate_open` before each stage |
| P-U2-02 Bounded paging | The shape the commit index bound follows |

---

## 2. P-U3-01: Run-Scoped Index

**Delivers**: U3-NFR-PRF-05, U3-NFR-IDX-01 to -04

Commit history is fetched once per distinct file and held for the duration of one
`requirements_upsert` call, then discarded.

```
with CommitIndex(bitbucket, bounds) as index:
    for candidate in batch:
        resolve_key(candidate, known_keys, index)
```

### Why the run, not the session

Three units have now solved a caching problem three ways, and the differences are not
arbitrary:

| Unit | Scope | Because |
|---|---|---|
| U7 `ReportContext` | One report | A stale coverage hash would make a revoked approval look valid |
| U2 hash-skip | Database | The expensive case is *across* runs |
| **U3 `CommitIndex`** | **One batch** | **Every requirement in a batch draws on the same files** |

A session-scoped index would serve history that changed since it was built, and
deciding when it goes stale has no good answer — the repository moves independently of
the run, and there is no event to invalidate on. Rebuilding per batch costs one round
of fetches for a guarantee that the derived provenance reflects what the repository
said when the batch was processed.

### The bounds

200 distinct files, 500 commits per file, both configurable. Reaching either is
reported and the affected files route to gaps with the reason stated.

**Unbounded would fail on the repository that most needs it.** A large monorepo with
deep history would hold the whole thing in memory. A gap saying "commit index limit
reached" is honest; a run that crawls and then succeeds anyway is not.

---

## 3. P-U3-02: Informational Result Field

**Delivers**: U3-NFR-REL-05

A rebuild that changes the content hash returns `approval_invalidated: true` on a
**successful** result, with a log line naming the previous approver and date.

**It is information, not an error.** The rebuild worked; nothing is wrong. Returning
a `REJECTED_*` code would tell the agent to fix its input when there is nothing to
fix, and burying it in a log would leave the operator to discover it later — when the
cases gate refuses, at which point it reads as a bug rather than a consequence.

This is the first place in the system where a successful operation carries a
consequence the caller must act on. The shape is worth naming because U4, U5 and U6
will each have one: a batch that succeeded but produced fewer cases than forecast, an
emission that succeeded but skipped hand-edited files.

---

## 4. P-U3-03: Canonical-Form Hashing

**Delivers**: U3-NFR-PRF-03, and the approval binding in BR-U3-4.3

```
payload = [(i.id, i.requirement_id, i.test_type, i.technique,
            i.planned_count, i.is_required) for i in sorted(items, key=lambda i: i.id)]
digest  = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))
```

| Guarantee | Mechanism |
|---|---|
| Order-independent | Sorted by id before serialising |
| Stable across runs and versions | `sort_keys`, pinned separators, no timestamps |
| Sensitive to substance | The six fields of BR-U3-4.2 |
| Insensitive to prose | Rationale is absent from the payload |

**The pinned separators are not pedantry.** Python's default JSON separators include a
space after each comma — stable within a version, not guaranteed across them. The Test
Lead's approval binds to this digest, so a formatting change in the standard library
must not be able to invalidate every approval in the corpus.

---

## 5. P-U3-04: Delegated Authorisation

**Delivers**: U3-NFR-SEC-01

`coverage_approve` calls U7's `stage_approve`. It does not check the role itself.

**One place decides who may approve what.** U3, U4, U5 and U6 all sit behind gates;
four independent role checks would eventually disagree, and the disagreement would
surface as one service permitting what another refuses — with no obvious wrong answer
to point at.

The same reasoning that put `is_gate_open` in one service rather than four.

---

## 6. Patterns Considered and Declined

| Pattern | Why not |
|---|---|
| **Caching the coverage derivation** | The 5-second budget is met without it, and a cache would need invalidating on every requirement change — the same objection that ruled out pre-computed summaries at U1 |
| **A session-scoped commit index** | No good answer to when it goes stale; see §2 |
| **Incremental coverage rebuild** | Rebuilding only changed requirements would make the content hash depend on build history rather than on content, and the hash is what the approval binds to |
| **A rules engine for depth** | The depth rules are BR-2's four techniques, already declarative. An engine would add configuration surface for logic that has none |
| **Wrapping pure functions in components** | `CoverageHasher` and `AtomicityChecker` would hold no state and no policy. Ceremony, not structure |

**The incremental rebuild is the one worth dwelling on.** It is the obvious
optimisation and it is wrong for a non-obvious reason: if the hash reflects which
requirements were rebuilt rather than what they contain, two identical models could
hash differently depending on the order they were built in — and an approval would
then be invalidated by a rebuild that changed nothing.

---

## 7. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U3-NFR-SCL-01 to -05 | P-SCL-01, indexes from `domain-entities.md` |
| U3-NFR-PRF-01, -02, -04 | Direct SQL aggregation, no caching |
| U3-NFR-PRF-03 | **P-U3-03** |
| U3-NFR-PRF-05 | **P-U3-01** |
| U3-NFR-REL-01 to -03 | P-RES-01 |
| U3-NFR-REL-04 | **P-U3-03** — an unchanged hash means an unchanged version |
| U3-NFR-REL-05 | **P-U3-02** |
| U3-NFR-REL-06 | L2 migration runner |
| U3-NFR-IDX-01 to -04 | **P-U3-01** |
| U3-NFR-SEC-01 | **P-U3-04** |
| U3-NFR-SEC-02 to -04 | P-RES-01, storage constraints |
| U3-NFR-MNT-01 to -03 | The `force_atomic` escape and its audit record |
| U3-NFR-MNT-04, -05 | **P-MNT-02** import contracts |

**All 24 U3 NFR requirements have a delivering pattern or component.**
