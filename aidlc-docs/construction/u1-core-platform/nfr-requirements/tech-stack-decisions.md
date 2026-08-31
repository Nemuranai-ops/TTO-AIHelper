# Tech Stack Decisions — U1 Core Platform

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U1 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-29

Decisions here bind every unit. U2 through U8 inherit this stack and add nothing to it without
revisiting this document.

---

## Summary

| Concern | Decision | Version | Binding source |
|---|---|---|---|
| Language | Python | >= 3.11 | C-10, NFR-POR-01 |
| Dependency management | `uv` with `uv.lock` | latest, pinned | Q9 |
| MCP server | Official `mcp` Python SDK | pinned exact | C-10, FR-AGT-05 |
| Schema and validation | Pydantic | v2, pinned exact | Q10, NFR-SEC-03 |
| Database | SQLite via stdlib `sqlite3` | stdlib | C-04, Q4 of Application Design |
| Templating | Jinja2 | pinned exact | Q6 of Application Design, FR-AUT-11 |
| Similarity | Standard library only | — | Q11 |
| Testing | pytest | pinned exact | NFR-MNT-02 |
| Property testing | Hypothesis | pinned exact | PBT-09, NFR-MNT-03 |
| Architecture enforcement | import-linter | pinned exact | NFR-MNT-01 |
| Vulnerability scanning | pip-audit | pinned exact | NFR-SEC-09 |
| SBOM | CycloneDX | pinned exact | NFR-SEC-09 |

**Every dependency is pinned to an exact version and recorded in a committed lockfile.** Nothing
floats. This satisfies NFR-SEC-09 and makes `uv sync` reproducible on any workstation, which is what
OD-02's distribution model depends on.

---

## Decisions with Rationale

### Language: Python 3.11+

**Not a choice** — constraint C-10 fixes it. 3.11 is the floor for `tomllib` in the standard library,
exception groups, and the typing features the port protocols use.

**Cross-platform**: `pathlib` throughout, no shell invocation, no platform-specific paths. CI runs
the matrix across macOS, Windows and Linux (U1-NFR-POR-01).

### Dependency management: `uv`

| Considered | Outcome |
|---|---|
| **`uv`** | **Chosen** — fast, produces `uv.lock`, pins the Python version itself, identical behaviour on all three platforms |
| Poetry | Rejected — mature and well known, but substantially slower, and its lockfile format has churned |
| pip-tools | Rejected — workable, but Python version pinning and environment management stay manual |

`uv` also makes the OD-02 rollback path a two-command operation: `git checkout <tag>` then
`uv sync`. Nothing else has to be reasoned about.

### MCP server: official `mcp` Python SDK

The reference implementation, maintained alongside the protocol. Serves over stdio, which is what
NFR-SEC-02 requires — no network listener is opened.

### Validation: Pydantic v2

| Considered | Outcome |
|---|---|
| **Pydantic v2** | **Chosen** — one model definition produces both the MCP tool schema and the runtime validation |
| dataclasses plus manual validation | Rejected — the schema and the checks become two artefacts that drift apart |
| attrs plus cattrs | Rejected — good serialisation, no schema generation, so the drift problem returns |

**The single-definition property is the reason.** NFR-SEC-03 requires every input validated against
a typed schema before any logic runs. If the declared schema and the runtime check are separate
artefacts, they eventually disagree, and the disagreement is invisible until something invalid gets
through. One definition makes that class of bug unreachable.

**Domain independence**: Pydantic models live at the MCP boundary (M1, M2) and in adapters. The
domain core (D1-D8) uses plain dataclasses and imports nothing outside the standard library, which
the import-linter contract enforces. The domain must stay dependency-free for the property tests to
run against it in isolation.

### Database: stdlib `sqlite3`

Constraint C-04 fixes SQLite. Application Design Q4 chose a repository layer over `sqlite3` with
parameterised SQL in dedicated query modules, and no ORM.

| Consideration | Effect |
|---|---|
| Integrity rules stay visible as plain DDL | The §10.3 rules are readable in the schema file rather than inferred from decorators |
| Query plans stay under direct control | `EXPLAIN QUERY PLAN` confirms `idx_case_bucket` is used, which is how NFR-PRF-03 is proven |
| No mapping layer | One less place for the domain to leak into persistence |

**Configuration**: WAL journal mode for concurrent read during write; `foreign_keys = ON` per
connection, since SQLite defaults it off and the referential rules depend on it; `busy_timeout` set
so a brief lock waits rather than failing.

**`foreign_keys = ON` is easy to forget and silent when missed.** It is set in the connection
factory, and a startup assertion verifies it, because a schema whose foreign keys are not enforced
looks identical to one whose are.

### Templating: Jinja2

Required by Application Design Q6. FR-AUT-11 demands byte-identical regeneration, which a language
model cannot guarantee and a template can.

**Determinism measures**: `trim_blocks` and `lstrip_blocks` fixed; every iteration over a collection
explicitly sorted; no reliance on dictionary ordering; no timestamps or random values in output.
U5 owns the templates; U1 owns the rendering contract.

### Similarity: standard library only

BR-1 needs shingle extraction and Jaccard similarity — set arithmetic over string slices, roughly a
dozen lines.

| Considered | Outcome |
|---|---|
| **stdlib** | **Chosen** — no dependency, fully deterministic, trivially property-testable |
| rapidfuzz | Rejected — faster, but adds a compiled dependency for an algorithm that is not the bottleneck. Bucketed candidate selection is what makes the budget, not comparison speed |
| datasketch MinHash/LSH | Rejected — genuinely valuable well beyond 10,000 cases; premature at this scale |

**The bottleneck is candidate selection, not comparison.** With `idx_case_bucket` narrowing the
candidate set, comparison runs over a handful of cases, so a faster comparison would not move the
budget. Adding a compiled dependency to speed up the part that is already fast would be the wrong
trade.

### Testing: pytest and Hypothesis

| Layer | Tool | Target |
|---|---|---|
| Unit | pytest | Documented behaviour across all modules |
| Property | Hypothesis | `domain/` only — the 16-property surface |
| Integration | pytest | Adapters against a temp SQLite file and stubbed MCP servers |
| Benchmark | pytest-benchmark | The NFR-PRF budgets at 10,000 cases |

**Hypothesis targets the domain exclusively.** That is the payoff of the hexagonal decision: no
database, no network, no fixtures, so the properties are cheap enough to run on every commit.

### Architecture enforcement: import-linter

A contract fails the build if `domain` imports anything outside the standard library and `domain`,
or if any adapter imports a service.

**Without this, the hexagonal boundary erodes quietly.** One convenient import from an adapter into
the domain makes the property tests need a database, and by the time anyone notices, the invariants
have stopped being tested. A build-time contract is cheaper than the archaeology.

### Supply chain

| Control | Mechanism | Requirement |
|---|---|---|
| Pinning | `uv.lock`, committed | NFR-SEC-09 |
| Vulnerability scanning | `pip-audit` in the release check | NFR-SEC-09 |
| SBOM | CycloneDX generated per release | NFR-SEC-09 |
| Trusted sources | PyPI only, or a corporate mirror | NFR-SEC-09 |
| No unused dependencies | Reviewed per release | NFR-SEC-09 |

---

## Rejected Alternatives

| Alternative | Why rejected |
|---|---|
| SQLAlchemy ORM | Obscures the integrity constraints, which are the architecture here; less predictable query plans |
| Async everywhere | The toolchain is a local single-operator process; async adds concurrency semantics for no throughput gain |
| A web framework for the MCP server | NFR-SEC-02 forbids a network listener; stdio needs no HTTP stack |
| Alembic for migrations | Built for SQLAlchemy metadata; plain versioned SQL migrations are simpler and keep the DDL readable |
| Separately versioned packages | One process, one version; Q7 of Units Generation settled this |
| SQLCipher | Not required under the OD-04 decision; contained to A1 and A2 if AS-02 proves wrong |
| Docker for the toolchain | NFR-POR-02 requires local operation; OD-02 chose git plus `uv sync` |

---

## Cross-Platform Verification

Every dependency is pure Python or a stdlib module, so all three platforms are supported without a
compiled toolchain on the operator's machine.

| Dependency | Pure Python | Notes |
|---|---|---|
| `mcp` SDK | Yes | |
| Pydantic v2 | No — compiled core | Wheels published for all three platforms and for CPython 3.11-3.13 |
| Jinja2 | Yes | |
| pytest, Hypothesis, import-linter, pip-audit | Yes | |
| `sqlite3` | stdlib | Bundled with CPython on all three |

**Pydantic v2 is the only compiled dependency**, and it ships prebuilt wheels for every platform and
Python version in scope, so no operator needs a C compiler. This is verified by the CI matrix
(U1-NFR-POR-01).

---

## Version Pinning Policy

| Rule | Reason |
|---|---|
| Exact versions in `pyproject.toml`, not ranges | Reproducibility across workstations |
| `uv.lock` committed | The only guarantee that two machines resolve identically |
| Python floor 3.11, ceiling unpinned but CI-tested to 3.13 | Allows newer runtimes without silent breakage |
| Dependency updates are a deliberate change with a rerun of the full suite | Prevents a transitive update from quietly changing behaviour |
| No `latest` anywhere, including CI images | NFR-SEC-09, SECURITY-10 |
