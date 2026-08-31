# Logical Components — U4 Test Case Generation

**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

Two components: **L9 PersonalDataDetector** and **L10 ViewRenderer**.

---

## Why Two

| Considered | Decision |
|---|---|
| **L9 PersonalDataDetector** | **Added** — holds the pattern set and the allow-list, which is policy |
| **L10 ViewRenderer** | **Added** — holds format decisions and the emitted-hash comparison, which is state |
| `BatchValidator` | Declined — the sequence is S5's, the checks are D7's; the wrapper would hold neither |
| `SignalGatherer` | Declined — a service method reading two repositories |
| `MatrixBuilder` | Declined — D3 already builds matrices; U4 supplies the edges |
| `IdentifierResolver` | Declined — D5 owns allocation and the stable-id rule is four lines of lookup |

The test each candidate faced is the one U3 settled on: **a component earns its place
by holding state, enforcing a boundary, or having a lifetime.** A pure function in a
class has none of the three, and the wrapper makes it harder to test rather than
easier.

L9 passes on the second — it is the single place that decides what counts as personal
data, and that boundary is the whole point of U4-NFR-SEC-01. L10 passes on the first:
it compares against recorded hashes and reports what it did.

**The four declined candidates would each have been a place for a domain algorithm to
be quietly reimplemented.** U4-NFR-MNT-03 forbids exactly that, and the cheapest way
to comply is to leave no plausible home for the copy.

---

## L9: PersonalDataDetector

**Ring**: Domain | **Delivers**: U4-NFR-SEC-01, -02 | **Pattern**: P-U4-03

### Responsibility

Decide whether a test data value matches a personal-data pattern, and whether it is
nonetheless drawn from a documented synthetic set. Nothing else — no logging, no
storage, no configuration lookup.

### Interface

```
screen_value(field: str, value: str) -> PrivacyFinding | None
screen_case(case: TestCase)          -> list[PrivacyFinding]
```

`None` means the value is acceptable. A finding means it is refused.

### `PrivacyFinding`

| Field | Meaning |
|---|---|
| `field` | Where the value was found — step ordinal and data key |
| `pattern` | Which pattern matched: `email`, `phone`, `nino`, `ssn`, `card` |
| `permitted_form` | What an acceptable synthetic value looks like |

`permitted_form` is the field that makes the rejection actionable. Without it the
agent knows only that its value was wrong, and its next attempt is a guess.

### The pattern set

| Pattern | Detects | Permits |
|---|---|---|
| `email` | RFC-shaped addresses | RFC 2606 — `example.com`, `example.org`, `example.net`, `.test`, `.invalid`, `.example` |
| `phone` | E.164 and common national formats | `555-01xx`, and the reserved ranges for the locales in use |
| `nino` | UK National Insurance format | Prefixes never issued by HMRC |
| `ssn` | US SSN format | `000-`, `666-`, `900-999` — ranges never issued |
| `card` | 13-19 digits **passing Luhn** | Published network test numbers |

### Why the Luhn check is part of detection, not a refinement of it

A 16-digit order reference, a batch id, a correlation token — all are plausible test
data and none are card numbers. A detector that flags every 16-digit string would fire
constantly on legitimate values, and a check that fires constantly gets disabled.

The Luhn check costs a dozen lines and removes almost every false positive in the one
pattern where false positives would otherwise be common. It does not weaken detection:
a real card number passes Luhn by construction.

### Where it is called from

D7's validation stage B, alongside the structural case rules. Not at the MCP boundary
— see P-U4-03 for why the pattern set must be able to change without moving the wire
contract.

### Property surface

| Property | Statement |
|---|---|
| PBT-U4-1 | Any value from the synthetic allow-list screens clean, for every pattern |
| PBT-U4-2 | Any generated value matching a pattern and outside the allow-list is refused |
| PBT-U4-3 | Screening is pure — the same value screens identically every time |
| PBT-U4-4 | A finding always names a field that exists on the case |

**PBT-U4-2 is the property that would have caught a class of bug that testing by
example would not**: a pattern written to catch `user@customer.co.uk` that happens not
to catch `user+tag@customer.co.uk`. Hypothesis generates the plus-tag; a hand-written
test case does not, because the person writing it is thinking about the pattern they
just wrote.

---

## L10: ViewRenderer

**Ring**: Adapter | **Delivers**: U4-NFR-PRF-03, -04, -06, U4-NFR-REL-04, U4-NFR-SEC-03, -05, U4-NFR-MNT-01, -02 | **Pattern**: P-U4-04

### Responsibility

Render one feature's cases to Markdown and YAML, decide per file whether to write,
skip as unchanged, or skip as hand-edited, and report all three.

### Interface

```
render_markdown(feature: Feature, cases: Sequence[TestCase]) -> str
render_yaml(feature: Feature, cases: Sequence[TestCase])     -> str
emit(feature_slug: str) -> ViewManifest
```

`render_*` are deterministic and take no I/O; `emit` is where the file system and the
`emitted_view` table are touched. The split exists so the format can be property-
tested without a disk.

### The three-way comparison

```
recorded = views.get(path)              # hash at last emission
on_disk  = sha256(path.read()) if path.exists() else None
fresh    = sha256(rendered)

hand_edited  = on_disk is not None and recorded is not None and on_disk != recorded.content_hash
unchanged    = recorded is not None and recorded.content_hash == fresh
```

Order matters: `hand_edited` is evaluated first. A file the operator edited and that
the corpus also changed is still a hand-edit, and overwriting it because the corpus
moved would lose the edit for a reason the operator would find arbitrary.

### Byte-stability

U4-NFR-MNT-01 requires that unchanged content re-renders byte-identically. Three
things are therefore excluded from every rendered view:

| Excluded | Because |
|---|---|
| Timestamps | Every emission would differ, and every file would look hand-edited on the next run |
| Run identifiers | Same |
| Absolute paths | They differ per operator workstation, so two people's emissions would conflict |

Ordering is by case identifier, and YAML is emitted with explicit key order rather
than dictionary insertion order. **Without this the hand-edit detector is worse than
useless** — it would report every file as hand-edited on every run, and the operator
would learn to ignore the one report that protects their work.

### Confidentiality in the rendered view

U4-NFR-SEC-03 requires views to carry behaviour and expectations, not verbatim source
documentation. L10 renders the case's own fields — title, steps, expected results,
test data, links by identifier. It does not render Jira descriptions, Confluence page
bodies, or comment text.

**The views are pushed to a separate Bitbucket repository**, which is where the
distinction stops being abstract. A generated view quoting three paragraphs of an
internal Confluence page has moved that page into a repository with a different access
list, and nobody involved would have described that as the intent.

### Paths

`generated/testcases/<feature-slug>.md` and `.yaml`, under the workspace root.
`generated/` is gitignored, satisfying U4-NFR-SEC-05. The slug is validated against
`^[a-z0-9-]+$` before it reaches a path — a feature slug is agent-supplied, and an
agent-supplied path segment is a traversal waiting to happen.

### The generated-file banner

Every view opens with a line stating that it is generated, that SQLite is the system
of record, and that edits do not change the corpus (U4-NFR-MNT-02). The banner is
inside the hashed content, so removing it is itself a hand-edit and is reported.

---

## Placement

```
domain/     privacy.py           <- L9   (pure; no imports outside the domain)
adapters/   view_renderer.py     <- L10  (file system + emitted_view table)
services/   generation.py        <- S5   (orchestration only)
```

L9 sits in the domain ring and imports nothing from adapters or services. L10 sits in
the adapter ring and is reached through an emitter port, so S5 depends on the port
rather than on the renderer.

**Both placements are enforced, not documented.** `.importlinter`'s `domain-is-pure`
contract fails the build if `privacy.py` acquires an adapter import; `services-no-
adapters` fails it if `generation.py` imports `view_renderer` directly. This is the
mechanism that gives U4-NFR-MNT-03 teeth — a convenience copy of a domain algorithm in
the wrong ring stops the build rather than being caught in review.

---

## Configuration Additions

| Key | Default | Purpose |
|---|---|---|
| `generation.max_batch_cases` | 200 | BR-U4-3.1 batch cap |
| `generation.views_root` | `generated/testcases` | L10 output root |
| `privacy.enabled_patterns` | all five | Allows a locale-irrelevant pattern to be disabled |
| `privacy.extra_synthetic_domains` | empty | Site-specific reserved domains |

`privacy.enabled_patterns` can weaken a security control, so it is logged at startup
whenever it differs from the default. A control that can be silently narrowed is a
control nobody can rely on.

---

## Verification

| Check | Result |
|---|---|
| Every U4 NFR requirement has a delivering pattern or component | 25 of 25 |
| No new component violates the dependency rule | Verified against the four import contracts |
| U4 holds no copy of a domain algorithm | L9 is new policy, not a copy; L10 renders only |
| Security Baseline | SECURITY-11 via L9; SECURITY-12 via L10 paths. No blocking findings |
| Resiliency Baseline | RESILIENCY-12 via migration 005 reversibility. No blocking findings |
| Property-Based Testing (partial) | PBT-U4-1 to -4 on L9; format round-trip on L10 |
