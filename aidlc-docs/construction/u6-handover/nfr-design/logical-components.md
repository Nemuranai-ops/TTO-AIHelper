# Logical Components — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

Two components: **L14 CommandRunner** and **L15 StructuralVerifier**.

---

## Why Two

| Considered | Decision |
|---|---|
| **L14 CommandRunner** | **Added** — isolates the only place external code executes |
| **L15 StructuralVerifier** | **Added** — holds the check set, which will grow |
| `ManifestBuilder` | Declined — a sorted list of rows and two totals |
| `LockfileGenerator` | Declined — one `CommandRunner` call and a file check |
| `Reconciler` | Declined — three set differences over data S7 already holds |

The test each faced is the one applied since U3: **a component earns its place by
holding state, enforcing a boundary, or having a lifetime.**

L14 enforces the sharpest boundary in the system — it is the only module that may
import `subprocess`, and an import contract says so. L15 holds a check set that will
grow every time the team discovers a new way an assembled project can be broken.

The three declined candidates hold none of the three. `Reconciler` is the closest call
and still wrong: three set differences do not become clearer for having a class around
them, and the sets themselves are the interesting part.

---

## L14: CommandRunner

**Ring**: Adapter (with its port in `ports/`) | **Delivers**: U6-NFR-SEC-01 to -04,
U6-NFR-PRF-04, U6-NFR-SCL-04 | **Pattern**: P-U6-01

### Responsibility

Run one external command with a literal argument list, bound its runtime and its
output, and report what happened. It decides nothing about *which* commands to run.

### Interface

```
run(argv: Sequence[str], *, cwd: Path, timeout_s: int) -> CommandResult
is_available(executable: str) -> bool
```

`is_available` wraps `shutil.which`. It sits here rather than in S7 so the whole of the
"can we run external things" question lives behind one port — which is what lets the
verification tests use a fake runner that reports Node absent without touching the
machine's PATH.

### `CommandResult`

| Field | Meaning |
|---|---|
| `argv` | What was run, for the report |
| `exit_code` | `None` when the command timed out |
| `stdout`, `stderr` | Truncated and sanitised |
| `timed_out` | True when the timeout fired |
| `duration_ms` | The toolchain tier is the slow one |

### The four guarantees

| Guarantee | Mechanism |
|---|---|
| No shell | `shell=False`, always, in one place |
| No interpolation | The signature takes a sequence; callers pass literals |
| Bounded runtime | `timeout=timeout_s`, `timed_out` distinguished from a non-zero exit |
| Bounded output | Truncated to a configured size **before** it is stored |

**The output bound is applied at capture, not after.** A failing `npm ci` against a
broken lockfile emits tens of megabytes, and `capture_output=True` holds all of it —
truncating afterwards would mean the memory was already spent.

Sanitisation runs through U1's existing `sanitise` on the truncated text. `npm` reports
registry URLs, and a proxy failure can carry an `Authorization` header in its error
body; `tsc` reports absolute paths naming the operator's home directory. Neither is
catastrophic and both are avoidable for the cost of one call.

### The import contract

A fifth contract is added:

```ini
[importlinter:contract:subprocess-is-isolated]
name = Only the command runner imports subprocess
type = forbidden
source_modules = tto_testgen.domain, tto_testgen.services, tto_testgen.mcp,
                 tto_testgen.platform
forbidden_modules = subprocess
```

**This is the first contract that names a stdlib module**, and it is worth the
asymmetry: the capability to start a process is the single most consequential thing
this codebase can acquire, and a future unit reaching for it should fail the build
rather than quietly gain it.

### Property surface

| Property | Statement |
|---|---|
| PBT-U6-7 | Every argv passed to the runner is a list of literals with no interpolated project value |
| PBT-U6-8 | Output longer than the bound is truncated, and the truncation is stated |

---

## L15: StructuralVerifier

**Ring**: Adapter | **Delivers**: U6-NFR-PRF-01, U6-NFR-SCL-01 to -03, U6-NFR-SEC-05,
-06, U6-NFR-MNT-03, -04

### Responsibility

Run the checks that need no toolchain: required files present, imports resolve, no
absolute path, no credential literal. Report each with a name and a location.

### Interface

```
verify(project_root: Path) -> TierResult
```

One method. The check set is internal because it is a list, not a configuration
surface — a caller choosing which structural checks to skip is a caller producing a
verification report that means something different each time.

### The check set

| Check | Method | Catches |
|---|---|---|
| Required files present | `Path.exists` over the eleven FR-HND-01 names | U5 never ran, or ran partially |
| Import targets resolve | Regex for `from '...'`, then `exists` | **US-HND-02 AC4's failure** |
| No absolute path | Regex per file | A path naming the generating workstation |
| No credential literal | L13's `scan_value` over the bytes | A credential added by hand-edit |

### Why a regex and not a TypeScript parse

The question is *whether a referenced file exists*, which needs no parser. Adding one
would introduce a second implementation of TypeScript's module resolution that could
disagree with the real one — and a verification step that disagrees with the compiler
is worse than one that checks less.

The same judgement as U6-NFR-MNT-03, and the same shape as U6's reconciliation finding
case identifiers by pattern rather than by parsing the annotation array.

### Why L13 runs again here

U5 refuses a credential *before* rendering. The only remaining path into the assembled
project is a hand-edit, and **U6 is the last point before the operator pushes**. One
extra pass over files already being read closes it.

### Streaming

Files are read one at a time and released. At ~300 files the whole project would fit in
memory comfortably; reading one at a time costs nothing and keeps U6-NFR-SCL-03 true
rather than incidentally satisfied.

### Property surface

| Property | Statement |
|---|---|
| PBT-U6-2 | A failed structural check always makes `is_ready` false |
| PBT-U6-6 | No blocking finding is reported without naming a file |

---

## Placement

```
ports/      commands.py            <- the CommandRunner protocol
adapters/   command_runner.py      <- L14, the only importer of subprocess
adapters/   structural_verifier.py <- L15
services/   handover.py            <- S7, orchestration only
```

S7 depends on the port, so the whole unit is testable without Node — which is the
point, since U6 exists partly to work on a machine that lacks it.

**S7 has no `push`, no `branch`, no `git`, and no `subprocess` import.** FR-HND-04 is
a capability it does not have rather than a rule it follows, and the fifth import
contract now enforces the last of those structurally.

---

## Configuration Additions

| Key | Default | Purpose |
|---|---|---|
| `handover.command_timeout_s` | 300 | Per toolchain command |
| `handover.output_limit_bytes` | 65536 | Truncation bound |
| `handover.skip_toolchain` | false | Explicitly skip the tier even when Node is present |

`handover.skip_toolchain` exists for the case where Node is present but the registry is
unreachable — an air-gapped workstation, a VPN that is down. Setting it produces the
same honest `skipped` result rather than a five-minute wait for a timeout, and it is
logged at startup like every other narrowed control.

---

## Verification

| Check | Result |
|---|---|
| Every U6 NFR requirement has a delivering pattern or component | 29 of 29 |
| No new component violates the dependency rule | Verified against five import contracts |
| U6 holds no emission logic and no domain algorithm | L15 re-uses L13; nothing is reimplemented |
| Security Baseline | SECURITY-13 via L14's four guarantees and the new contract. No blocking findings |
| Resiliency Baseline | RESILIENCY-04 via the timeout, RESILIENCY-07 via P-U6-03. No blocking findings |
| Property-Based Testing (partial) | 7 U6 properties, plus 2 on L14 |
