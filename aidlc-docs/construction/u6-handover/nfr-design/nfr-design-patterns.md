# NFR Design Patterns — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

Four patterns specific to U6, on top of the 45 inherited from U1, U7, U2, U3, U4 and
U5.

U6 is the only unit that starts a process. Three of the four patterns below exist
because of that, and the fourth exists because U6 is the last thing that runs before
work leaves the workspace.

---

## 1. Inherited

| Pattern | Use in U6 |
|---|---|
| P-SEC-03 Message sanitisation | Every line of subprocess output before it reaches a report |
| P-U7-02 Read-only gate evaluation | Before assembly |
| P-U5-03 Deterministic rendering | The manifest — committed, so churn in a diff matters |
| P-U4-04 Three-outcome emission | The shape `skipped` follows |
| P-MNT-01 Dependency inversion | S7 depends on a port, never on `subprocess` |
| P-RES-02 Bounded external call | The per-command timeout |
| P-MNT-02 Import contracts | Assert `subprocess` appears in exactly one module |

**P-SEC-03 is doing unusual work here.** In every prior unit it sanitised messages the
system composed. Here it sanitises output the system did not write — `npm` reporting a
registry URL, `tsc` reporting an absolute path that names the operator's home
directory. The helper is the same; the input is foreign for the first time.

---

## 2. P-U6-01: Argv-Only Command Port

**Delivers**: U6-NFR-SEC-01, -02, U6-NFR-MNT-01

One port, one method, one adapter, and it is the only module in the system that
imports `subprocess`.

```python
class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], *, cwd: Path,
            timeout_s: int) -> CommandResult: ...
```

### The type is the enforcement

`argv` is a sequence of strings, never a string. A caller cannot pass
`"npm ci && rm -rf /"` because the parameter would then be a string where a sequence
is required — and if it slipped through as a one-element list, `shell=False` means
there is no shell to interpret it.

| Approach | "No shell" is enforced by |
|---|---|
| Direct `subprocess.run` in S7 | Every call site remembering `shell=False` |
| A shell helper taking a string | Nothing |
| **An argv-only port** | **The signature, plus one adapter** |

**And the import contract closes it.** A new contract asserts `subprocess` is imported
by exactly one module, so a future unit reaching for it fails the build rather than
quietly acquiring the capability. That is the same mechanism that keeps the domain pure.

### Testability follows from the same shape

S7 takes the port, so verification is testable against a fake runner that returns
canned results. Without it, testing "a compilation failure blocks readiness" would
require breaking a real TypeScript project and having Node installed — which would make
the U6 suite depend on the toolchain the unit was designed to work without.

---

## 3. P-U6-02: Three-Valued Check Status

**Delivers**: U6-NFR-REL-04, -05, -06

```python
class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

Readiness names all three explicitly:

```python
is_ready = (
    structural.status is CheckStatus.PASSED
    and reconciliation.status is CheckStatus.PASSED
    and toolchain.status is not CheckStatus.FAILED   # SKIPPED does not block
)
```

### Why not a boolean and a flag

`None` for skipped in an `bool | None` is the compact option and it is a trap: **`None`
is falsy**, so the first `if not result:` anyone writes treats a skipped tier as a
failure. BR-U6-2.4 — the rule that a missing toolchain does not block handover — would
be undone by a type choice rather than by a decision.

A boolean plus `was_run` carries the same information in a shape where a caller can
read one field and get the wrong answer. The enum makes the omission a syntax error
rather than a silent misreading.

### The comment in the expression is load-bearing

`# SKIPPED does not block` sits on the line that implements the least obvious rule in
the unit. Two property tests pin both directions — a skipped tier never makes
`is_ready` false on its own, a failed one always does — because this is the rule most
likely to be "corrected" by someone being careful.

---

## 4. P-U6-03: Degrade and Report

**Delivers**: U6-NFR-REL-04, and RESILIENCY-07

When a capability is unavailable, U6 does the part it can, states plainly what it did
not do, and lets the operator decide.

| Missing | Done | Reported |
|---|---|---|
| Node | Structural checks, reconciliation, manifest | "Compilation not verified: npm not found on PATH" |
| Node | — | The one command to produce the lockfile |

### Why this is the honest option and the other two are not

| Option | What the engineer gets |
|---|---|
| Refuse to run | Nothing, on a machine that has Python and not Node |
| Report a pass | A false assurance they act on — they push, and Jenkins finds it |
| **Degrade and report** | **A structurally complete project, honestly labelled** |

This is the clearest instance of graceful degradation in the system, and it is worth
naming as a pattern because U8 will face the same shape: a report that cannot compute
one section should render the rest and say which is missing, not fail whole.

### The distinction a timeout makes

A tool that was absent is `skipped`. A tool that ran and did not finish is `failed` —
a broken lockfile or an unreachable registry is a real problem, and folding it into
`skipped` would tell the operator their machine lacks Node when it does not.

---

## 5. P-U6-04: Atomic Artefact Write

**Delivers**: U6-NFR-REL-03, -07

```python
temp = path.with_suffix(path.suffix + ".tmp")
temp.write_text(content, encoding="utf-8")
os.replace(temp, path)          # atomic on POSIX and Windows
```

Same directory, so the rename stays on one filesystem and cannot degrade into a copy.

### Why the manifest specifically

**Reconciliation reads the manifest.** A crash midway through writing it leaves a
truncated file that the *next* run reads as authoritative — producing a reconciliation
failure listing entries that were never missing, with no cause the engineer can find
by looking at the corpus.

Every other file U6 writes is small and independent. The manifest is the one that feeds
back into a check, and that is what makes the atomicity worth the two extra lines.

---

## 6. Patterns Considered and Declined

| Pattern | Why not |
|---|---|
| **Retrying a failed toolchain command** | U1's retry is for transient network faults. A compilation failure is deterministic, and retrying it would take three times as long to report the same result |
| **Caching verification results between runs** | The operator re-runs after every fix, and the file most likely to have changed is the one they just fixed. A stale pass is the one outcome this report must never produce |
| **Running the three toolchain commands in parallel** | They are ordered by dependency: `tsc` needs `node_modules`, which `npm ci` installs. Parallelism would fail on the second command for a reason unrelated to the project |
| **Streaming subprocess output to the operator** | stdout carries MCP protocol traffic; a log line written there corrupts the transport. The same constraint that put logging on stderr in U1 |
| **A `ManifestBuilder` component** | A sorted list of rows and two totals. Ceremony, not structure — the same judgement that declined `SpecBuilder` in U5 |
| **Verifying inside a container** | Reproducible, and it requires Docker to check a project the user explicitly chose not to containerise |

**The parallel-commands decline is the one that looks like a missed optimisation.** It
is not: the ordering is a real dependency, and the sequential run is bounded by the
timeout rather than by a budget, so there is no target it is failing to meet.

---

## 7. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U6-NFR-PRF-01 to -03 | Streamed file reads, set arithmetic |
| U6-NFR-PRF-04 | **P-U6-01** timeout parameter, P-RES-02 |
| U6-NFR-PRF-05 | `shutil.which`, one call |
| U6-NFR-SCL-01 to -03 | L15 streamed reads |
| U6-NFR-SCL-04 | **P-U6-01** output bound |
| U6-NFR-REL-01, -02 | **P-U5-03** determinism, no caching |
| U6-NFR-REL-03, -07 | **P-U6-04** |
| U6-NFR-REL-04, -05, -06 | **P-U6-02**, **P-U6-03** |
| U6-NFR-SEC-01, -02 | **P-U6-01** |
| U6-NFR-SEC-03 | Literal argv includes `--ignore-scripts` |
| U6-NFR-SEC-04 | P-SEC-03, L14 truncation |
| U6-NFR-SEC-05 | L15, re-running L13 |
| U6-NFR-SEC-06 | L15 path assertions |
| U6-NFR-SEC-07 | **No such method exists** on S7 |
| U6-NFR-MNT-01 | **P-MNT-02**, the new `subprocess` contract |
| U6-NFR-MNT-02 to -04 | L15's check set, structure over parsing |

**All 29 U6 NFR requirements have a delivering pattern or component.**
