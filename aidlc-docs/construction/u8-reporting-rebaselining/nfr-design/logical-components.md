# Logical Components — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-31

Two components: **L16 ReportRenderer** and **L17 ChangeDetector**.

---

## Why Two

| Considered | Decision |
|---|---|
| **L16 ReportRenderer** | **Added** — format decisions and byte-stability |
| **L17 ChangeDetector** | **Added** — per-source outcome, which the baseline guard reads |
| `EdgeBuilder` | Declined — a query and four boolean lookups S9 already has |
| `SectionRegistry` as a class | Declined — it is a tuple of dataclasses |
| `BaselineManager` | Declined — one guarded function, not a lifetime |

The test is the one applied since U3: **a component earns its place by holding state,
enforcing a boundary, or having a lifetime.**

L16 holds format decisions that must not vary. L17 enforces a boundary — it is where
external sources are reached, and its result is what P-U8-01's guard depends on.

**Seventeen components across eight units**, and the three declined here follow the same
judgement that declined `SpecBuilder` at U5, `ManifestBuilder` at U6 and
`IdentifierResolver` at U4. A wrapper around a function is a name with nothing behind
it, and by the last unit that has become the default answer rather than a debate.

---

## L16: ReportRenderer

**Ring**: Adapter | **Delivers**: U8-NFR-PRF-01, -02, U8-NFR-SCL-04, U8-NFR-REL-07,
U8-NFR-SEC-01 to -03, U8-NFR-MNT-03 | **Patterns**: P-U5-03, P-U8-02

### Responsibility

Turn computed sections into Markdown and CSV, deterministically, writing under the
configured report root. It decides nothing about *what* to compute.

### Interface

```
render_markdown(report: Report) -> str
render_csv(section: ReportSection) -> str
emit(report: Report) -> list[Path]
```

### Determinism

The same three exclusions as U5 and U6 — no timestamps, no run identifiers, no absolute
paths — plus explicit ordering on every collection.

**Reports are committed and diffed.** A report that reorders itself between identical
runs produces a diff full of movement and no information, and a reader learns to skip
the diff — which is the report's only mechanism for showing what changed.

### CSV

`csv.writer` with `lineterminator="\n"` pinned. A requirement statement can contain a
comma, a quote or a newline; joining with commas would shift the columns **for exactly
the rows whose text is most interesting**, and a shifted traceability matrix is worse
than none because it looks right.

The default `"\r\n"` would make the bytes depend on nothing observable and break
byte-stability on a platform change.

### The confidentiality rule

Sections carry behaviour, identifiers and figures — not verbatim source documentation.
A statement is included; the Confluence page it came from is referenced by identifier,
not quoted.

**A report is the artefact most likely to be forwarded**: a coverage report goes to a
Test Lead, who sends it to a programme manager, who attaches it to a status pack. A
generated view stays in a repository; a report travels.

### The last-line scan

L9 and L13 run over the rendered text before it is written — personal data and
credentials respectively. Both refused their content upstream; this catches anything
that arrived by a path neither covers, such as a requirement statement ingested before
L9 existed. One pass over text already in memory, and the same reasoning as U6's
re-scan.

### Property surface

| Property | Statement |
|---|---|
| PBT-U8-8 | Rendering is byte-stable for an unchanged report |
| PBT-U8-9 | Every rendered figure carries a derivation string |
| PBT-U8-11 | CSV round-trips through `csv.reader` with fields intact |

---

## L17: ChangeDetector

**Ring**: Adapter | **Delivers**: U8-NFR-REL-03, U8-NFR-PRF-05, U8-NFR-SEC-04
**Patterns**: P-U8-03, P-RES-03

### Responsibility

Detect changes since a baseline, per source, under isolation — and report which sources
were reached.

### Interface

```
detect(baseline: DeltaBaseline) -> DetectionResult
```

### `DetectionResult`

| Field | Meaning |
|---|---|
| `changes` | Everything detected, from every source that answered |
| `head_commits` | Current head per repository — **only for sources that answered** |
| `jira_watermark` | Latest `updated` seen, or None |
| `unavailable_sources` | `(source, reason)` for each that did not |

### Why `unavailable_sources` is a field

P-U8-01's guard depends on knowing whether every source was reached. If that fact lived
only in a log, the guard would have to infer it — most likely from an empty change list,
which is ambiguous: **no changes and no connection look identical from outside.**

Making it data means the guard reads a fact rather than deducing one. The same reasoning
that made U6's `skipped` a status and U2's not-found distinct from not-authorised.

### Read-only, structurally

L17 reaches Bitbucket and Jira through P2's source protocols, which **declare no write
method**. C-05 and C-06 — read-only against both — hold because the capability is
absent, not because L17 declines to use it.

That was decided at U1 and has now been relied on by U2 and U8 without either needing to
restate it as a rule.

### Isolation

Each source runs under U1's `isolate`. A Bitbucket outage yields a `DetectionResult`
carrying Jira's changes and naming Bitbucket as unavailable — and P-U8-01 then refuses
to advance the baseline, which is the whole point of the pair.

### Property surface

| Property | Statement |
|---|---|
| PBT-U8-6 | Every change reaching no trace edge appears in `unmapped` |
| PBT-U8-10 | The baseline advances only when `unavailable_sources` is empty |
| PBT-U8-12 | A source that failed contributes no head commit and no watermark |

**PBT-U8-12 closes the gap PBT-U8-10 leaves.** The guard refuses to advance when a
source failed; this asserts that a failed source could not have contributed a value to
advance *with*, so the two together make a partial advance unreachable rather than
merely refused.

---

## Placement

```
adapters/   report_renderer.py    <- L16
adapters/   change_detector.py    <- L17
services/   reporting.py          <- S8, the section registry lives here
services/   delta.py              <- S9, and advance_baseline
```

Both services depend on ports. `advance_baseline` sits in `delta.py` as a module-level
function rather than a method, so it can be property-tested without constructing a
service — which matters, because it is the function whose failure would be invisible.

**S9 has no `create_case`, no `create_requirement`, and no `regenerate`.** FR-DLT-06's
gates hold because there is nothing to bypass them with. Fourth and final use of
enforcement-by-absence, after P2's source protocols, `next_unit()` and S7's missing
`push`.

---

## Configuration Additions

| Key | Default | Purpose |
|---|---|---|
| `reports.root` | `generated/reports` | Where reports are written |
| `reports.formats` | `markdown,csv` | Which to emit |
| `delta.max_changes` | 500 | Bound on changes processed in one run |

`delta.max_changes` reaching its limit is reported, not silently truncated — the same
rule as U3's commit-index bounds. A run that processed the first 500 of 900 changes and
said nothing would look complete.

---

## Verification

| Check | Result |
|---|---|
| Every U8 NFR requirement has a delivering pattern or component | 28 of 28 |
| No new component violates the dependency rule | Verified against five import contracts |
| U8 holds no copy of D8's classification logic | S9 builds edges; D8 classifies |
| Security Baseline | SECURITY-11 via L16's scan; SECURITY-12 via the report root. No blocking findings |
| Resiliency Baseline | RESILIENCY-07 via P-U6-03's third use; RESILIENCY-12 via migration 007. No blocking findings |
| Property-Based Testing (partial) | 12 U8 properties, three of them on the baseline guard |
