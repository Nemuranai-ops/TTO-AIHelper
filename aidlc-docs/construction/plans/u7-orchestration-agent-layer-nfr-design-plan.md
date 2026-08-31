# NFR Design Plan — U7 Orchestration and Agent Layer

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: NFR Design
**Created**: 2026-08-29T14:56:00Z
**Status**: APPROVED 2026-08-29T15:05:00Z - all recommendations accepted

---

## What U7 inherits

U1's NFR Design established 20 patterns and 4 logical components. U7 uses them and
adds nothing to the resilience, security or observability sets:

| Inherited pattern | How U7 uses it |
|---|---|
| P-RES-01 Unit of Work | Every state transition is one transaction |
| P-RES-02 Bounded retry | Not exercised — U7 makes no external call |
| P-RES-04 Lease-based unit state | U7 *is* the lease logic; U1 built its storage |
| P-SCL-01 Capped pagination | Status reports inherit the 200-record cap |
| P-SEC-01 Two-level validation | Pydantic at the boundary, domain invariants beneath |
| P-SEC-03 Message sanitisation | Every refusal passes through it |
| P-OBS-01 Correlation propagation | Approval and transition logging |
| P-MNT-01 Dependency inversion | S10 depends on `RunStateRepository`, not SQLite |

Also inherited: the nine patterns **deliberately not used** at U1 — circuit breaker,
bulkhead, connection pool, rate limiter, in-memory cache, pre-computed summaries,
event sourcing, async, retry-on-4xx. None becomes applicable here.

**Four questions, all U7-specific.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Performance: scoping the coverage-hash cache

U7-NFR-PRF-03 requires the coverage content hash to be computed at most once per
report. Where should that memory live?

A) **A request-scoped context object**, created when a report begins and discarded
when it ends. Nothing survives the call. **(Recommended — a cache that cannot outlive
the read it serves cannot go stale, which removes invalidation as a concern entirely)**

B) **A module-level cache keyed by feature**, with explicit invalidation on coverage
write. Faster across reports, and it introduces a consistency obligation on every
write path — the reason U1 declined pre-computed summaries.

C) **`functools.lru_cache`** on the hash function. Terse, and it persists across
reports with no invalidation at all, so a stale hash could keep a revoked approval
looking valid.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 2 — Maintainability: where the Agent Layer checks read the tool registry

U7-NFR-MNT-01 and -02 compare chat mode files against the registered tool set. The
registry is populated by `register_read_tools` and `register_write_tools`, which need
a database connection.

A) **Build an empty in-memory registry for the check**, using a throwaway SQLite
connection. The check asserts names and tiers, which do not depend on data.
**(Recommended — the check is about the tool surface's shape, and coupling it to a
populated database would make a schema problem look like a documentation problem)**

B) **Export a static manifest** of tool names at build time and compare against that.
No database, and one more artefact to keep current.

C) **Run the check against a live application** built by `composition.build`. Most
realistic, and it makes a documentation check fail when credentials are missing.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 3 — Logical Components: does U7 need any?

U1 added four supporting components, each because an NFR would otherwise have no
owner. Does U7 need the same?

A) **One: a `GateEvaluator`**, separate from `RunStateService`. Gate logic is called
by four other units' services, is the most heavily tested logic in the unit, and has
no dependency on lease management. Separating it keeps `RunStateService` about state
and `GateEvaluator` about policy. **(Recommended)**

B) **None.** Fold gate evaluation into `RunStateService`. Fewer moving parts, and one
service carrying two unrelated responsibilities.

C) **Two**: `GateEvaluator` plus a `LeaseManager` split out from `RunStateService`.

D) **Three**: the above plus an `AgentLayerValidator` as a runtime component rather
than a test.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

## Question 4 — Usability: how a refusal reaches the operator

U7-NFR-USA-02 requires every refusal to name the gate, the condition, the remedy and
the permitted role. The `Result` type carries `message` and `remediation` separately.

A) **Structured fields the agent composes into prose.** `failed_condition`, `detail`,
`remediation` and `permitted_role` travel as data; the chat mode's instructions tell
the agent how to present them. **(Recommended — the agent already renders everything
else it says, and structured fields let it adapt phrasing to context without the
toolchain guessing at tone)**

B) **A fully-formed sentence in `message`**, which the agent relays verbatim.
Predictable wording, and the toolchain ends up owning conversational tone.

C) **Both** — structured fields plus a pre-composed fallback sentence.

X) Other (please describe after [Answer]: tag below)

[Answer]: A  (accepted recommendation)

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Record which U1 patterns U7 uses, and which are not exercised
- [x] 1.2 Specify the request-scoped caching pattern per Question 1
- [x] 1.3 Specify the gate evaluation pattern and its read-only guarantee
- [x] 1.4 Specify the lease classification pattern and its no-clearing guarantee
- [x] 1.5 Specify the status composition pattern and its neutrality guarantee
- [x] 1.6 Specify the Agent Layer consistency check pattern per Question 2
- [x] 1.7 Record any pattern deliberately not used in U7, with reasons
- [x] 1.8 Map every pattern to the U7 NFR it delivers
- [x] 1.9 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the components chosen in Question 3
- [x] 2.2 Define responsibilities and interfaces
- [x] 2.3 Place them within the hexagonal rings
- [x] 2.4 Define their interaction with U1 components and with the four calling services
- [x] 2.5 Define the configuration surface additions
- [x] 2.6 Verify no new component violates the dependency rule
- [x] 2.7 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 26 U7 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify C-12 neutrality is structurally guaranteed, not merely intended
- [x] 3.3 Verify Security and Resiliency compliance at design level
- [x] 3.4 Verify the U7 property surface is unaffected by the patterns chosen
- [x] 3.5 Validate content per `common/content-validation.md`
- [x] 3.6 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/nfr-design/nfr-design-patterns.md`
- [x] `aidlc-docs/construction/u7-orchestration-agent-layer/nfr-design/logical-components.md`
