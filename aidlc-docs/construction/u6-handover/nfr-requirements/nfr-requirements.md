# NFR Requirements — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## 1. Inherited, Unchanged

OD-01 to OD-04, the eight Resiliency decision points, the tech stack, and the project
NFRs owned by U1, U2, U3, U4, U5 and U7. **Nothing re-opened.**

**U6 owns NFR-SEC-13 jointly with U5.** U5 guarantees that generated content is never
executed as code; U6 guarantees that the code it *does* execute — `npm`, `tsc`,
`playwright` — runs under containment it controls. The two halves are different
problems with the same requirement behind them.

---

## 2. Performance

Two tiers, two shapes of budget.

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U6-NFR-PRF-01 | Structural verification at 6,000 cases and ~300 files | < 10 s | Benchmark |
| U6-NFR-PRF-02 | Three-way reconciliation at 6,000 cases | < 10 s | Benchmark |
| U6-NFR-PRF-03 | Manifest construction at 6,000 cases | < 5 s | Benchmark |
| U6-NFR-PRF-04 | Each toolchain command is **bounded**, not fast | 300 s timeout, configurable | Asserted |
| U6-NFR-PRF-05 | Node detection adds no measurable cost when absent | Single `shutil.which` | Asserted |

**The toolchain tier has a timeout, not a budget.** A performance budget on `npm ci`
would be measuring the operator's network and the registry's mood, neither of which is
a property of this system. What U6 owes is an upper bound: an unresponsive registry
must not hang the handover indefinitely.

**Ten seconds on the structural tier** because it always runs, it is the tier readiness
depends on, and it is what the operator waits for interactively. At 300 files and 6,000
case identifiers it is file reads and set arithmetic, so the budget is generous — which
is the point: it should never be the reason a handover feels slow.

---

## 3. Scalability

| ID | Requirement | Measurement |
|---|---|---|
| U6-NFR-SCL-01 | 6,000 cases, ~300 generated files, 150 features | Benchmark |
| U6-NFR-SCL-02 | Remain within budget at 10,000 cases | Benchmark headroom |
| U6-NFR-SCL-03 | Files are read one at a time; the project is never wholly in memory | Streamed reads |
| U6-NFR-SCL-04 | Subprocess output is bounded before it reaches memory | Asserted |

**U6-NFR-SCL-04 is not theoretical.** A failing `npm ci` against a broken lockfile
produces tens of megabytes of output, and `capture_output=True` holds all of it. The
bound is applied at read time rather than after.

---

## 4. Reliability

| ID | Requirement | Measurement |
|---|---|---|
| U6-NFR-REL-01 | Handover is fully idempotent: a re-run over an unchanged corpus produces byte-identical artefacts | Property |
| U6-NFR-REL-02 | Every check re-runs; no result is cached between runs | Asserted |
| U6-NFR-REL-03 | The manifest is written whole or not at all | Asserted |
| U6-NFR-REL-04 | A skipped tier never blocks readiness | Property |
| U6-NFR-REL-05 | A failed tier always blocks readiness | Property |
| U6-NFR-REL-06 | A subprocess timeout is reported as a **failure**, never a skip | Asserted |
| U6-NFR-REL-07 | A crashed run leaves no partial manifest for the next to read | Atomic write |

### Why nothing is cached between runs

**The operator re-runs this after every fix**, which is the whole usage pattern. A
resumed run that skipped previously-passing checks would report a stale pass for a file
changed since — and the file most likely to have changed is the one they just fixed.

Re-running everything costs ten seconds. Reporting one stale pass costs a failed
Jenkins build and the trust in this report.

### Why the manifest is written atomically

Reconciliation reads the manifest. A crash midway through writing it would leave a
truncated file that the *next* run reads as authoritative, producing a reconciliation
failure with no cause the engineer can find. Written to a temporary file and renamed,
which is atomic on every filesystem TAAS supports.

---

## 5. Security

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U6-NFR-SEC-01 | Subprocesses run with `shell=False` and a literal argv | NFR-SEC-13 | Property |
| U6-NFR-SEC-02 | No project value is interpolated into any argv | NFR-SEC-13 | Property |
| U6-NFR-SEC-03 | `npm ci` runs with `--ignore-scripts` | NFR-SEC-13 | Asserted |
| U6-NFR-SEC-04 | Subprocess output is truncated, sanitised, and included only for a failed check | NFR-SEC-01 | Asserted |
| U6-NFR-SEC-05 | Verification re-scans assembled files for credential literals | NFR-SEC-10 | Asserted |
| U6-NFR-SEC-06 | U6 writes only within the project directory | NFR-SEC-12 | Path assertion |
| U6-NFR-SEC-07 | No method exists that pushes, branches, or writes CI configuration | FR-HND-04 | **Source inspection** |

### `--ignore-scripts` is the requirement most likely to be removed by someone helpful

`npm ci` runs `preinstall`, `install` and `postinstall` from **every transitive
dependency** by default. The generated project is ours; its dependency tree is not.
Verification must not be the path through which a compromised transitive package
executes on the operator's workstation.

It will occasionally break a package that needs a build step, and the temptation will be
to drop the flag. The requirement exists so that decision is a documented change rather
than a quick fix.

### Why output is sanitised even though it is our own tooling

`npm` reports registry URLs, and a proxy failure can include an `Authorization` header
in the error body. `tsc` reports absolute paths that name the operator's home
directory. Neither is catastrophic and both are avoidable — U1's `sanitise` already
handles the patterns, so applying it costs one call.

### U6-NFR-SEC-05 catches the one remaining path

U5 refuses a credential *before* rendering. The only way one reaches the assembled
project after that is a hand-edit, and U6 is the last point before the operator pushes.
Re-running L13 over the assembled bytes closes it.

---

## 6. Maintainability

| ID | Requirement | Measurement |
|---|---|---|
| U6-NFR-MNT-01 | U6 contains no emission logic and no template | Import contracts |
| U6-NFR-MNT-02 | U6 never repairs what it finds; it reports | Source inspection |
| U6-NFR-MNT-03 | Structural checks use file existence, not a TypeScript parse | Source inspection |
| U6-NFR-MNT-04 | Every blocking finding names a file, and a line where applicable | Property |

**U6-NFR-MNT-02 is a real temptation.** Finding a missing page object and generating it
would look like helpfulness and would mean verification verifies its own repair — at
which point the check can never fail, and the gate it guards is theatre. Regeneration
is the operator's decision through `automation_emit`.

---

## 7. Project NFR Ownership

| Project NFR | Owner | How U6 serves it |
|---|---|---|
| NFR-SEC-13 No untrusted execution | **U6**, with U5 | U6-NFR-SEC-01 to -03 |
| NFR-SEC-12 Workspace containment | Inherited | U6-NFR-SEC-06 |
| NFR-SEC-10 Confidentiality | Shared with U4, U5 | U6-NFR-SEC-04, -05 |

---

## 8. Extension Compliance

**Security Baseline**: SECURITY-13 (no untrusted execution) served by U6-NFR-SEC-01
to -03 — the most direct application of that rule in the project, since U6 is the only
unit that starts a process. SECURITY-11 by -SEC-05. **No blocking findings.**

**Resiliency Baseline**: RESILIENCY-04 (bounded external calls) served by the
per-command timeout; RESILIENCY-07 (degrade rather than fail) served by the skipped
tier, which is the clearest instance of graceful degradation in the system. **No
blocking findings.**

**Property-Based Testing (partial)**: PBT-03 extended with the 7 U6 properties, two of
which pin down the skipped-versus-failed distinction. **No blocking findings.**

---

## 9. Open Items

**None.** AS-02 remains outstanding from U1 and is unaffected.
