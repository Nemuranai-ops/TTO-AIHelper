# NFR Requirements — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## 1. Inherited, Unchanged

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, and the project
NFRs owned by U1, U2, U3, U4 and U7. **Nothing re-opened.**

**U5 shares two project NFRs with U4**: NFR-SEC-10 (confidentiality) and NFR-SEC-11
(synthetic test data). The division is clean — U4 keeps real data out of the corpus;
U5 keeps it out of the TypeScript, **which is the copy that leaves the workspace**.

That last clause is the reason U5's security requirements are not a duplicate of U4's.
The corpus lives in a gitignored SQLite file on one workstation. The generated project
is pushed to Bitbucket and read by Jenkins.

---

## 2. Performance

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U5-NFR-PRF-01 | Emit one feature's specs and page objects at 100 cases | < 5 s | Benchmark |
| U5-NFR-PRF-02 | Emit the whole project at 6,000 cases and 150 features | < 60 s | Benchmark |
| U5-NFR-PRF-03 | A second whole-project emission with no corpus change | < 30 s | Benchmark |
| U5-NFR-PRF-04 | Locator resolution per case | < 20 ms | Benchmark |
| U5-NFR-PRF-05 | Only the features named are re-emitted | Call counting |

**Five seconds on the frequent operation, sixty on the rare one.** Per-feature emission
follows every batch; whole-project emission happens before a handover. Putting the
tight budget on the frequent path is the same split U3 used for coverage builds.

**U5-NFR-PRF-03 is not a duplicate of -02.** The second emission writes nothing — every
file hashes identically — so it measures the cost of *deciding* not to write, which is
the whole corpus read plus 300 hashes. If that cost approached the write path, the
three-way comparison would be a false economy.

**Ten seconds for the whole project was rejected.** Reaching it would mean rendering
features in parallel, and parallel rendering introduces non-deterministic file ordering
— the one property this unit cannot trade.

---

## 3. Scalability

| ID | Requirement | Measurement |
|---|---|---|
| U5-NFR-SCL-01 | 6,000 cases across 150 features, ~300 generated files | Benchmark |
| U5-NFR-SCL-02 | Remain within budget at 10,000 cases | Benchmark headroom |
| U5-NFR-SCL-03 | One feature is rendered at a time; the corpus is never wholly in memory | Streamed queries |
| U5-NFR-SCL-04 | A single spec file stays under 5,000 lines at 200 cases | Asserted |

**U5-NFR-SCL-04 is the one that could force a design change.** Per-feature scoping is
right for 40 cases and questionable for 400. The requirement makes the threshold
visible rather than letting one enormous file appear unremarked at handover — if a
feature exceeds it, the answer is a sub-file split, and this is where that gets
noticed.

---

## 4. Reliability

| ID | Requirement | Measurement |
|---|---|---|
| U5-NFR-REL-01 | Rendering the same corpus twice produces identical bytes | Property + benchmark |
| U5-NFR-REL-02 | Output is independent of input and iteration order | Property |
| U5-NFR-REL-03 | A hand-edited file is never overwritten | Asserted |
| U5-NFR-REL-04 | `input_hash` is stored per test, so a drift is detectable in production | Asserted |
| U5-NFR-REL-05 | A second emission with no change writes zero files | Benchmark assertion |
| U5-NFR-REL-06 | A refused emission writes no file at all, not a partial project | Asserted |
| U5-NFR-REL-07 | Migration 006 ships a tested reverse | `verify_reversibility` |

### Determinism is verified three ways, not one

| Mechanism | Catches |
|---|---|
| Property test: render twice, compare bytes | Non-determinism in development, over generated shapes |
| `input_hash` stored per test | A drift that only appears against the real corpus |
| Benchmark: second emission writes zero files | The whole path end to end, and an operator can run it |

**One mechanism would not be enough.** The property test exercises the shapes Hypothesis
generates, which are not the shapes a real Jira backlog produces. The stored hash
catches a divergence at scale but only after it has happened. The zero-write assertion
is the one that gives an operator a direct answer to "is regeneration safe?" — and it
is the one that would fail loudly if any of the three exclusions in BR-U5-7.1 were
forgotten.

**A golden-file comparison was rejected.** It catches everything and makes every
legitimate template change require regenerating hundreds of fixtures — which in
practice means people regenerate them without reading the diff, at which point the
fixtures assert nothing.

---

## 5. Security

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U5-NFR-SEC-01 | An emission carrying a literal credential is **refused**, naming the case and field | NFR-SEC-10 | Asserted per pattern |
| U5-NFR-SEC-02 | An emission carrying an environment-specific URL is refused | NFR-SEC-10 | Asserted |
| U5-NFR-SEC-03 | `.env.example` documents every variable and carries no values | FR-AUT-07 | Asserted |
| U5-NFR-SEC-04 | Generated code contains no `eval`, `Function` constructor, or shell invocation | NFR-SEC-13 | Property |
| U5-NFR-SEC-05 | The project is written under the configured destination only | NFR-SEC-12 | Path assertion |
| U5-NFR-SEC-06 | Case content reaches the templates as data, never as a code fragment | NFR-SEC-13 | Autoescape and quoting |

### What the credential check looks for

Two signals, because either alone misses the common case:

| Signal | Catches |
|---|---|
| **Field name** — `password`, `token`, `secret`, `apikey`, `authorization`, `credential` | `password: "hunter2"`, the single most likely literal |
| **Value shape** — bearer tokens, `-----BEGIN * KEY-----`, connection strings, absolute URLs with a real host | The case where the field is called something else |

An entropy threshold was rejected. It catches novel formats and fires on hashes, ids
and base64 fixtures — all ordinary test data. **The same failure mode as a Luhn-only
card check**: a control that fires on legitimate input is a control somebody turns off,
and U4 already paid that lesson once.

### U5-NFR-SEC-06 is the injection surface

Case titles, step actions and expected results are agent-supplied text that ends up
inside TypeScript string literals. A title containing `'; await page.goto('http://…
would be a code-injection path if the template interpolated it raw.

Every value is quoted through a JS-string escaper before interpolation, and the
templates never place case content outside a string literal. This is the one place in
the system where untrusted text becomes executable code, and it is worth naming as such.

---

## 6. Maintainability

| ID | Requirement | Measurement |
|---|---|---|
| U5-NFR-MNT-01 | No generated file contains a fixed wait | Property over rendered output |
| U5-NFR-MNT-02 | No generated file contains an XPath locator | Property over rendered output |
| U5-NFR-MNT-03 | Every generated test carries its tags, case id and Jira key | Property |
| U5-NFR-MNT-04 | Every unverified locator carries its annotation | Property |
| U5-NFR-MNT-05 | U5 contains no automatability logic and no similarity logic | Import contracts |
| U5-NFR-MNT-06 | The `@playwright/test` version the templates emit is pinned and stated | Asserted |

### The standard is asserted over output, not over templates

The templates *are* the generated coding standard, so something must stop a template
change from quietly degrading it. Three options; the properties above take the third:

| | Checks | Weakness |
|---|---|---|
| Lint the templates | The source | A forbidden fragment assembled from two harmless halves passes |
| Run the project's own linter in CI | The result, faithfully | Makes the Python suite depend on a Node toolchain |
| **Properties over rendered output** | **The result** | **Only asserts properties someone thought to write** |

The third's weakness is real and the least damaging: a template can be rewritten freely
as long as what comes out still holds, and adding a property is cheaper than
maintaining a Node toolchain inside a Python test run.

---

## 7. Project NFR Ownership

| Project NFR | Owner | How U5 serves it |
|---|---|---|
| NFR-SEC-10 Confidentiality | **U5**, with U4 | U5-NFR-SEC-01, -02, -05 |
| NFR-SEC-11 Synthetic test data | U4 | Inherited — U4 refuses it before U5 can render it |
| NFR-SEC-13 No generated code executed | **U5** | U5-NFR-SEC-04, -06 |

---

## 8. Extension Compliance

**Security Baseline**: SECURITY-10 (pinned versions) served by U5-NFR-MNT-06;
SECURITY-11 by -SEC-01 and -06; SECURITY-12 by -SEC-05. **No blocking findings.**

**Resiliency Baseline**: RESILIENCY-12 inherited; migration 006 triggers the existing
rehearsal requirement. **No blocking findings.**

**Property-Based Testing (partial)**: PBT-03 extended with the 10 U5 properties. This
unit is the strongest fit for the extension so far — six of the ten properties are
statements about generated text that example tests would exercise only along the paths
someone already thought about. **No blocking findings.**

---

## 9. Open Items

**None.** AS-02 remains outstanding from U1 and is unaffected.
