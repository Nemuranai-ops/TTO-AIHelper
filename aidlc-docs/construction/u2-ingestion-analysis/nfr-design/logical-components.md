# Logical Components — U2 Ingestion and Analysis

**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-29

Two supporting components.

---

## Why Two

| Considered | Decision |
|---|---|
| **L6 McpClientSession** | **Added** — a resource with a lifetime, and the place transport failure becomes a `Result` |
| **L7 PagedFetcher** | **Added** — four adapters would otherwise each implement paging-with-a-ceiling slightly differently |
| `DiscrepancyDetector` as a component | Declined — the detectors are pure functions over two claims. Wrapping them in a class would add ceremony without state |

---

## L6: McpClientSession

**Ring**: Adapter | **Delivers**: U2-NFR-REL-01, U2-NFR-REL-02, U2-NFR-SEC-02

### Responsibility

Own the lifetime of the child MCP server processes, and turn transport failures into
structured results.

### Interface

```
__enter__() -> McpClientSession        # spawns; fails fast on a bad credential
__exit__(...) -> None                  # terminates cleanly, always
call(server, tool, arguments) -> Result[dict]
is_available(server) -> bool
```

### Behaviour

| Concern | Decision |
|---|---|
| Lifetime | One session per ingestion run |
| Spawn failure | `FAILED_MCP_UNREACHABLE` before any resource is attempted |
| Timeout | 30s per call, configurable, classified transient |
| Credentials | Passed as child-process environment, never as arguments |
| Termination | In `finally`, including on an unhandled exception |

**Credentials go in the environment, not in `args`.** Process arguments are visible in
`ps` output to any user on the machine; the environment of another user's process is
not. It is a small difference that costs nothing to get right and cannot be corrected
retrospectively once a run has happened.

**Failing fast on spawn** is what turns a systemic problem into one message. Without
it, a wrong token produces ten resource failures that each look like a network
problem.

---

## L7: PagedFetcher

**Ring**: Adapter | **Delivers**: U2-NFR-SCL-02 to -05

### Responsibility

Retrieve a paged result set, stop at the ceiling, and report whether more existed.

### Interface

```
fetch(fetch_page, *, page_size=100, ceiling=2000) -> PagedResult
```

`fetch_page(cursor) -> (records, next_cursor)` is supplied by the caller, so the
component knows nothing about Jira, Confluence or Bitbucket.

### `PagedResult`

| Field | Meaning |
|---|---|
| `records` | Up to `ceiling` records |
| `ceiling_reached` | True when stopped early |
| `pages_fetched` | For the report |
| `guidance` | Present when the ceiling was hit: how to narrow the query |

**`guidance` is populated by the component, not the caller.** The fetcher knows the
ceiling and the count; the caller would have to reconstruct both to phrase the advice.
Putting it here means every adapter gives the operator the same actionable message.

### Why not four implementations

Jira search, Confluence search, Bitbucket log and Bitbucket changes all page. Four
hand-rolled loops would drift — one would forget the ceiling, another would count
pages instead of records, and the difference would surface as one source silently
over-ingesting.

---

## Placement

```
        +-------------------------------------------+
        |     APPLICATION SERVICES  S1, S2          |
        +-------------------------------------------+
                            |
        +-------------------------------------------+
        |              PORTS  P2                    |
        |   read-only source protocols              |
        +-------------------------------------------+
                            ^
        +-------------------------------------------+
        |   ADAPTERS  A3  A4  A5  A6                |
        |     + L6 McpClientSession                 |
        |     + L7 PagedFetcher                     |
        +-------------------------------------------+
```

**Text alternative**: both components sit in the adapter ring alongside A3 to A6. They
may depend on ports and domain types, never on a service. The services reach external
sources only through the P2 protocols, which declare no write method.

---

## Read-Only Posture

L6 exposes `call(server, tool, arguments)` — a general method that could, in
principle, invoke a write tool.

**The containment is at the port, not here.** A3 and A4 implement P2 protocols that
declare no write operation, so no service can ask for one. L6 is a transport; the
capability boundary is the protocol above it.

A test asserts that A3 and A4 name no Atlassian or Bitbucket write tool anywhere in
their source (U2-NFR-SEC-03) — because with a general `call`, absence of the
capability is no longer visible from the method signature alone, and it needs
asserting instead.

**This is a genuine weakening compared with U1's design**, where the read-only posture
was enforced purely by absent methods. It is accepted because a transport that cannot
name a tool cannot be a transport, and the compensating check is cheap and specific.

---

## Configuration Additions

| Setting | Default | Component |
|---|---|---|
| `TAAS_INGEST_MAX_PER_RESOURCE` | 2000 | L7 |
| `TAAS_INGEST_PAGE_SIZE` | 100 | L7 |
| `TAAS_MCP_TIMEOUT_SECONDS` | 30 | L6 |

---

## Dependency Verification

| Component | Imports | Violates? |
|---|---|---|
| L6 McpClientSession | `mcp` SDK, `platform` | No |
| L7 PagedFetcher | `platform` only | No |

Neither imports a service. Neither is imported by the domain. The import contracts
hold unchanged.

---

## Requirement Coverage

All 26 U2 NFR requirements have a delivering pattern (in
[nfr-design-patterns.md](nfr-design-patterns.md) §8) or one of these components.
