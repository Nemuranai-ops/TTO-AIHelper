# NFR Requirements — U2 Ingestion and Analysis

**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-29

---

## 1. Inherited from U1, Unchanged

OD-01 to OD-04, all eight Resiliency decision points, the tech stack, and 37 of the 47
project NFRs. **Nothing is re-opened.**

**Two inherited patterns become real here for the first time.** U1's bounded retry
(P-RES-02) and per-resource isolation (P-RES-03) were written for this unit and never
exercised in U1 or U7, because neither makes an external call. U2 is where they are
first tested against something that can actually fail.

---

## 2. Scalability

| ID | Requirement | Measurement |
|---|---|---|
| U2-NFR-SCL-01 | Handle 3-10 Bitbucket repositories, 100-500 Jira stories, 30-150 screens | Verified against the stated range |
| U2-NFR-SCL-02 | Jira and Confluence results are paged, 100 per page | Asserted in tests |
| U2-NFR-SCL-03 | A ceiling of **2,000 artefacts per resource**, configurable via `TAAS_INGEST_MAX_PER_RESOURCE` | Asserted in tests |
| U2-NFR-SCL-04 | Reaching the ceiling stops ingestion for that resource and **reports it** | Report contains the ceiling notice |
| U2-NFR-SCL-05 | No operation holds all artefacts of a resource in memory at once | Streamed page by page |

**U2-NFR-SCL-04 is the one that matters.** A ceiling without a report is worse than no
ceiling: the run appears to succeed, the corpus is quietly built on a third of the
input, and nobody finds out until coverage looks inexplicably thin.

The system is designed for 100-500 stories. Silently ingesting 8,000 would push every
downstream stage past the volume its budgets assume. Telling the operator lets them
narrow the JQL in a minute.

---

## 3. Performance

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U2-NFR-PRF-01 | Content-hash skip decides without a network call | < 10 ms | Indexed lookup on `artefact.content_hash` |
| U2-NFR-PRF-02 | A re-run over unchanged sources performs no fetch | 0 external calls | Call counting in tests |
| U2-NFR-PRF-03 | Resource classification for 100 entries | < 100 ms | Pure regex, no I/O |
| U2-NFR-PRF-04 | Figma folder parsing for 150 files | < 2 s | Filesystem plus one YAML load |

**Ingestion is sequential**, one resource at a time. U1 declined concurrency for the
toolchain, and ingestion is the one place that argument is weakest — ten repositories
fetched serially is mostly network wait.

It still stands. The content-hash skip means only the **first** run is slow; every
subsequent run touches what changed. A first run taking minutes rather than seconds is
not worth introducing thread-safety obligations into per-resource isolation, which is
the mechanism that makes partial failure survivable.

If this proves wrong in practice, a bounded thread pool is a contained change: the
isolation boundary already exists, and only its internals would need to become
thread-safe.

---

## 4. Reliability

| ID | Requirement | Measurement |
|---|---|---|
| U2-NFR-REL-01 | 30-second timeout per external call, configurable | Asserted in tests |
| U2-NFR-REL-02 | A timeout is classified transient and retried under U1's policy | Asserted in tests |
| U2-NFR-REL-03 | A resource is the transaction boundary; no sub-resource checkpoint | Interrupted resource stores nothing |
| U2-NFR-REL-04 | One failing resource does not stop the others | Isolation asserted |
| U2-NFR-REL-05 | Re-running after a failure re-fetches the whole resource; the hash skip makes it cheap | Call counting |
| U2-NFR-REL-06 | Not-found and not-authorised are distinguished in the report | Asserted in tests |
| U2-NFR-REL-07 | A partial ingestion completes the unit and reports; it does not refuse | Asserted in tests |

**Why 30 seconds.** Long enough for a large Confluence page or a slow JQL query, short
enough that three retries with backoff stay inside two minutes. Ten seconds would
retry a legitimately slow query three times before failing — slower than waiting once.

**Why no sub-resource checkpointing.** Committing every hundred artefacts would make
recovery faster and correctness worse: a half-ingested repository would be
indistinguishable from a complete one, and every downstream stage would treat it as
whole. The resource is the transaction boundary, and the hash skip already makes a
re-fetch cheap.

---

## 5. Security

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U2-NFR-SEC-01 | One credential per service, shared between the agent's MCP registration and the toolchain | NFR-SEC-01 | Config inspection |
| U2-NFR-SEC-02 | Credentials are `SecretStr` and never logged, serialised or stored | NFR-SEC-01 | Log assertion |
| U2-NFR-SEC-03 | A3 and A4 reference no Atlassian or Bitbucket write tool | NFR-SEC-14 | Source inspection, asserted |
| U2-NFR-SEC-04 | `screens.manifest.yaml` is parsed with a safe loader | NFR-SEC-05 | Asserted in tests |
| U2-NFR-SEC-05 | Any OpenAPI spec fetched from a repository is parsed with a safe loader | NFR-SEC-05 | Asserted in tests |
| U2-NFR-SEC-06 | Ingested content is stored verbatim and never executed or evaluated | NFR-SEC-13 | No `eval`, `exec` or dynamic import in U2 |
| U2-NFR-SEC-07 | External call failures are logged without credentials or full URLs bearing tokens | NFR-SEC-06 | Log assertion |

**One credential per service, not two.** The toolchain and the agent's MCP servers are
the same operator with the same permission set. Two credentials for one person is
bookkeeping without a security benefit — and the second one gets rotated late, which
is a real risk rather than a theoretical one.

**U2-NFR-SEC-05 is the non-obvious one.** The Figma manifest is an obvious untrusted
input. An OpenAPI spec pulled from a repository is equally untrusted and easier to
overlook, because it arrives through a code path that feels internal.

---

## 6. Observability

| ID | Requirement | Source |
|---|---|---|
| U2-NFR-OBS-01 | Every external call logs the service, operation and outcome, with the correlation id | NFR-OBS-01 |
| U2-NFR-OBS-02 | Retries log the attempt number and backoff | NFR-REL-03 |
| U2-NFR-OBS-03 | The ingestion report records per-resource counts and durations | NFR-OBS-03 |
| U2-NFR-OBS-04 | The hash-skip count is reported, so a "nothing happened" run is visibly correct rather than suspicious | NFR-OBS-03 |

**U2-NFR-OBS-04 exists because of how a good outcome looks.** A re-run that fetches
nothing and stores nothing is exactly right, and indistinguishable from a broken run
unless the report says "412 artefacts unchanged".

---

## 7. Project NFR Ownership

| Project NFR | Owner | How U2 serves it |
|---|---|---|
| NFR-SCL-01 Input scale | **U2** | U2-NFR-SCL-01 to -05 |
| NFR-PRF-04 Content-hash caching | **U2** | U2-NFR-PRF-01, -02 (mechanism from U1) |

All others inherited.

---

## 8. Extension Compliance

**Security Baseline**: SECURITY-05 (untrusted input) served by U2-NFR-SEC-04 and -05;
SECURITY-06 (least privilege) by U2-NFR-SEC-03; SECURITY-12 (credentials) by
U2-NFR-SEC-01 and -02. **No blocking findings.**

**Resiliency Baseline**: RESILIENCY-10 (dependency isolation) is genuinely exercised
here for the first time — U2-NFR-REL-01 to -05. **No blocking findings.**

**Property-Based Testing (partial)**: PBT-03 extended with the 10 U2 properties.
**No blocking findings.**

---

## 9. Open Items

**None.** AS-02 remains outstanding from U1 and is unaffected.
