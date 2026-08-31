# NFR Design Patterns — U2 Ingestion and Analysis

**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-29

Five patterns specific to U2, on top of those inherited from U1 and U7.

---

## 1. Inherited, and Two Exercised for the First Time

| Pattern | Status in U2 |
|---|---|
| P-RES-01 Unit of Work | One transaction per resource, not per run |
| **P-RES-02 Bounded retry** | **First real exercise** — written for this unit, never reached in U1 or U7 |
| **P-RES-03 Per-resource isolation** | **First real exercise** — same |
| P-SEC-01 Two-level validation | Pydantic on agent payloads, domain invariants beneath |
| P-SEC-03 Message sanitisation | External failures never carry a token-bearing URL |
| P-PRF-02 Content-hash skip | The mechanism is U1's; U2 is where it pays |
| P-OBS-01 Correlation propagation | Every external call carries the run's id |
| P-MNT-01 Dependency inversion | Adapters satisfy P2; services depend on the protocols |

U1 and U7 both declined bounded retry as unexercised. In U2 it meets a network for the
first time — which means U2 is also the first place the policy's correctness matters
rather than merely being defined.

---

## 2. P-U2-01: Run-Scoped Client Session

**Delivers**: U2-NFR-REL-01, U2-NFR-REL-02, U2-NFR-SEC-02

One MCP client session per ingestion run. Opened before any resource is attempted,
closed in a `finally`.

```
with McpClientSession(config) as session:
    for resource in resources:
        isolate(resource, lambda r: ingest_one(r, session))
```

**Opening before the first resource is the point.** A spawn failure, a missing binary
or a bad credential surfaces once, immediately, as `FAILED_MCP_UNREACHABLE` — rather
than as ten separate resource failures that look unrelated. The operator debugs one
cause instead of nine symptoms.

**Not per resource**, which would pay the spawn cost ten times and scatter a systemic
problem. **Not long-lived across runs**, which would leave a broken client after a
server dies between runs, discovered only at the next ingestion.

---

## 3. P-U2-02: Bounded Paging at the Source

**Delivers**: U2-NFR-SCL-02, U2-NFR-SCL-03, U2-NFR-SCL-04, U2-NFR-SCL-05

The adapter pages, counts, and stops at the ceiling.

```
fetch_paged(query, page_size=100, ceiling=2000):
    fetched, cursor = [], None
    while True:
        page, cursor = source.search(query, cursor=cursor)
        fetched.extend(page)
        if len(fetched) >= ceiling:
            return fetched[:ceiling], CeilingReached(ceiling, more_available=True)
        if cursor is None:
            return fetched, Complete()
```

**Enforced at the source, not after.** The adapter is the only place that knows a
further page exists, and stopping there means the excess is never fetched,
transferred, parsed or held. Enforcing in the service would fetch 8,000 issues to
discard 6,000.

**`CeilingReached` is returned, not logged.** It reaches the ingestion report and then
the operator, because a ceiling that is silently applied produces a run that looks
successful and a corpus built on a third of the input.

---

## 4. P-U2-03: Hash-Skip as the Caching Strategy

**Delivers**: U2-NFR-PRF-01, U2-NFR-PRF-02

Before storing, the content hash is compared against what is already held. A match
means no store and no further work.

### Why no response cache, re-examined

U1 declined in-memory caching because an indexed SQLite lookup is sub-millisecond.
That reason does not transfer: here the saving would be a network round trip, three
to four orders of magnitude larger.

The decision holds anyway, for a different reason. **The hash already solves the
expensive case** — re-fetching unchanged artefacts across runs. Within a single run
each artefact is fetched once, so a session cache would have nothing to serve. A
persistent cache would duplicate what the hash does while adding a time-to-live, and a
time-to-live is a way of being wrong on a schedule.

Recording *why* it was re-examined matters as much as the outcome: inheriting a
decision whose original reasoning no longer applies is how a design quietly stops
being justified.

---

## 5. P-U2-04: Safe Parsing of Untrusted Input

**Delivers**: U2-NFR-SEC-04, U2-NFR-SEC-05, U2-NFR-SEC-06

`yaml.safe_load` for the Figma manifest and any OpenAPI spec. No `eval`, no `exec`, no
dynamic import anywhere in U2. Ingested content is stored verbatim and never executed.

**Two inputs, one of them easy to miss.** The Figma manifest is obviously untrusted —
a file in a shared folder. The OpenAPI spec is equally untrusted and arrives through a
path that feels internal, having come from "our own" repository. It is a file anyone
with commit access can change.

Cross-document `$ref` is recorded unresolved rather than fetched. Resolving it would
mean an HTTP request to a URL chosen by the spec's author, which is a capability not
worth having for a field we can mark unknown.

---

## 6. P-U2-05: Symmetric Discrepancy Recording

**Delivers**: FR-ANA-08, U2-NFR-OBS-03

Both claims stored with both sources. Neither marked correct.

**Symmetry is not a formality.** A record holding one claim plus a note about "the
other source" is readable in one direction, and the reader frequently arrives from the
side that was not chosen as primary — the API tester looking at the spec, when the
record was written from the code's perspective.

The one asymmetry is deliberate and lives in BR-U2-5: code decides endpoint
*existence*. That is a rule about what is real, not about which source is right.

---

## 7. Patterns Re-examined and Still Declined

| Pattern | U1's reason | Still holds in U2? |
|---|---|---|
| **In-memory cache** | Indexed lookup already sub-millisecond | **No — but see P-U2-03.** The reason changes; the decision stands |
| **Async / concurrency** | No throughput that matters | Weakest here of anywhere. Held: only the first run is slow, and thread-safety in the isolation boundary is a real cost |
| **Circuit breaker** | No concurrent callers to stampede | Yes. Sequential ingestion with bounded retry covers the failure that can occur |
| **Rate limiter** | The servers enforce their own | Yes, and P-RES-02 handles 429 correctly |
| **Retry on 4xx** | A 401 does not become a 200 | Yes, and more visibly: retrying a bad credential ten times can trip a lockout |

Two of these are close calls in U2 rather than obvious. Recording which ones were
close is worth more than recording the verdict alone — it tells whoever revisits this
where to look first.

---

## 8. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U2-NFR-SCL-01 to -05 | **P-U2-02** |
| U2-NFR-PRF-01, -02 | **P-U2-03** |
| U2-NFR-PRF-03, -04 | Pure functions, no I/O |
| U2-NFR-REL-01, -02 | **P-U2-01**, P-RES-02 |
| U2-NFR-REL-03 to -07 | P-RES-01, P-RES-03 |
| U2-NFR-SEC-01, -02 | P-SEC-02 (inherited), P-U2-01 |
| U2-NFR-SEC-03 | P-SEC-04 capability absence (inherited) |
| U2-NFR-SEC-04 to -06 | **P-U2-04** |
| U2-NFR-SEC-07 | P-SEC-03 sanitisation |
| U2-NFR-OBS-01 to -04 | P-OBS-01, **P-U2-02** ceiling reporting, **P-U2-05** |

**All 26 U2 NFR requirements have a delivering pattern or component.**
