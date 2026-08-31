# NFR Requirements — U7 Orchestration and Agent Layer

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-29

---

## 1. Inherited from U1, Unchanged

U1's NFR Requirements stage settled the cross-cutting qualities once for every unit.
**Nothing below is re-opened.** Recording the inheritance explicitly matters: a
per-unit stage that silently re-decided a settled question would leave two answers in
the documentation and no way to tell which is current.

| Decision | Status | Applies to U7 |
|---|---|---|
| OD-01 corpus recovery point | Closed at U1 | Yes — U7 writes only `unit_state` rows, covered by the same backup and export |
| OD-02 toolchain distribution and rollback | Closed at U1 | Yes — U7 ships in the same package |
| OD-03 recovery rehearsal | Closed at U1 | Yes, with one addition: see U7-NFR-REL-04 |
| OD-04 encryption at rest | Closed at U1 (AS-02) | Yes |
| 8 Resiliency decision points | Answered at U1 | Yes |
| Tech stack | Fixed at U1 | Yes — U7 adds no dependency |
| 37 project NFRs | Owned by U1 | Inherited |

**One addition to OD-03.** The rehearsal scenarios in `docs/restore-procedure.md`
cover database loss, corruption and rollback across a migration. Migration 002 adds
lease columns, so Scenario C must be executed again after it — which the existing
trigger ("after every schema migration") already requires. No new decision, just a
scheduled occurrence of an existing one.

---

## 2. Reliability

| ID | Requirement | Measurement |
|---|---|---|
| U7-NFR-REL-01 | A lease is reported stale when its heartbeat exceeds **30 minutes**, configurable via `TAAS_LEASE_STALE_MINUTES` | Asserted in tests at the boundary |
| U7-NFR-REL-02 | The service never clears a lease. No code path removes or expires one automatically. | Property test: lease classification never returns a clearing instruction |
| U7-NFR-REL-03 | Only the BR-U7-7 state transitions are accepted | Property test over every state pair |
| U7-NFR-REL-04 | Migration 002 ships a tested reverse, and rollback across it is rehearsed | `verify_reversibility`; restore-procedure Scenario C |
| U7-NFR-REL-05 | Gate evaluation is read-only and side-effect free | No write in any gate path |

**Why 30 minutes.** A unit is one feature's work. A session that has produced nothing
for half an hour has almost certainly stopped — long enough not to mislabel a working
session waiting on a slow Jira query, short enough that a crash is noticed within the
same working session rather than the next day.

**U7-NFR-REL-02 is the unusual one.** It requires the *absence* of behaviour, so it
is verified by a property over generated inputs rather than by example: the guarantee
is that no input produces a clearing instruction, and enumerating a few inputs would
not establish that.

---

## 3. Performance

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| U7-NFR-PRF-01 | Gate evaluation for one unit and stage | < 20 ms | Benchmark |
| U7-NFR-PRF-02 | Full unfiltered status report at 8 units x 7 stages | < 500 ms | Benchmark |
| U7-NFR-PRF-03 | The coverage content hash is computed at most once per report | — | Call counting in tests |
| U7-NFR-PRF-04 | Gates are evaluated only for units the report includes | — | Filtered call does no work for excluded units |

**The hash is the expensive part.** Fifty-six gate evaluations that each re-hash the
same coverage content would dominate the report. It cannot change during a single
read, so caching it for the report's duration is free correctness-wise and removes
the cost entirely.

---

## 4. Usability

| ID | Requirement | Measurement |
|---|---|---|
| U7-NFR-USA-01 | The operator runs any stage for a named feature with one instruction, without recalling tool names | Chat modes state what they need; asserted structurally |
| U7-NFR-USA-02 | Every refusal names the gate, the failed condition, the remedy, and the permitted role where restricted | Asserted for every refusal path |
| U7-NFR-USA-03 | A refusal fits in two to three sentences | Length asserted in tests |
| U7-NFR-USA-04 | The agent states what it could not determine rather than filling the gap | Repository instructions; remediation text at the tool boundary |
| U7-NFR-USA-05 | A mode asked to work outside its stage declines and names the correct mode | Asserted per mode |

**Serves**: NFR-USA-01 and NFR-USA-03, the two project NFRs U7 owns.

---

## 5. Maintainability

| ID | Requirement | Measurement |
|---|---|---|
| U7-NFR-MNT-01 | Every tool named in a chat mode exists in the registry | Build-time test |
| U7-NFR-MNT-02 | Every registered tool appears in at least one chat mode | Build-time test |
| U7-NFR-MNT-03 | Every chat mode includes the universal read tools | Build-time test |
| U7-NFR-MNT-04 | No chat mode grants a file-write tool | Build-time test |
| U7-NFR-MNT-05 | Every chat mode names a stage that exists in `StageName` | Build-time test |
| U7-NFR-MNT-06 | The repository instructions state all four standing rules | Build-time test |
| U7-NFR-MNT-07 | Every path-scoped instruction file declares an `applyTo` glob | Build-time test |

### Why these are machine checks

The seven chat modes list the tools their stage may use. U2 through U8 will register
seventeen more write tools over the coming units. A mode naming a tool that does not
exist, or omitting one that does, fails **mid-run in front of the operator** — the
most expensive moment for it to surface.

This is the same class of problem the import contracts solve, and it takes the same
answer. A review checklist depends on eight units' worth of authors remembering;
a test does not.

**U7-NFR-MNT-04 deserves separate mention.** It is how FR-AGT-06 stops being an
instruction the model may drift from over a long session and becomes a capability
that is simply absent. The check is what keeps it absent as modes are edited.

---

## 6. Security

| ID | Requirement | Source | Measurement |
|---|---|---|---|
| U7-NFR-SEC-01 | Every approval records actor, role, timestamp and content hash | NFR-SEC-13 | Asserted in tests |
| U7-NFR-SEC-02 | An approval attempt by an impermissible role is refused **and recorded** | FR-COV-06 | Log assertion |
| U7-NFR-SEC-03 | `Role` is a closed enumeration; an unrecognised value is refused as invalid, not treated as unauthorised | — | Asserted in tests |
| U7-NFR-SEC-04 | `.vscode/mcp.json` contains no secret and is safe to commit | NFR-SEC-01 | Secret scan |
| U7-NFR-SEC-05 | Refusal messages carry no path outside the workspace and no stack detail | NFR-SEC-08 | Inherited from X1 `sanitise` |

**U7-NFR-SEC-02: recording the attempt, not just refusing it.** An approval attempted
by the wrong role is a process signal — someone believed they had authority they do
not. Refusing silently loses that.

**U7-NFR-SEC-03: an invalid role and an unauthorised one are different.** U1 accepted
`role` as a free string, which was adequate for a thin wrapper. But `testlead`
instead of `test-lead` would fail the coverage restriction *closed* — the right
outcome for the wrong reason, and the operator would be told they lack authority
rather than that they made a typo.

---

## 7. Project NFR Ownership

| Project NFR | Owner | How U7 serves it |
|---|---|---|
| NFR-USA-01 One instruction per stage | **U7** | Chat modes with scoped tools; the operator names a feature, not a sequence |
| NFR-USA-03 Say what could not be determined | **U7** | Repository instructions; remediation on every refusal |
| NFR-MNT-08 Maintainable generated artefacts | Shared with U5 | The Agent Layer's own consistency checks |

All other project NFRs are owned by U1 or another unit and are inherited unchanged.

---

## 8. Extension Compliance

**Security Baseline**: SECURITY-06 (least privilege) served by mode tool scoping and
the role restriction; SECURITY-13 (auditable changes) by U7-NFR-SEC-01 and -02;
SECURITY-12 (credentials) by U7-NFR-SEC-04. All others inherited from U1. **No
blocking findings.**

**Resiliency Baseline**: RESILIENCY-10 (dependency isolation) inherited;
RESILIENCY-12 (backup) inherited, with migration 002 triggering an existing rehearsal
requirement. All eight decision points remain answered at U1. **No blocking findings.**

**Property-Based Testing (partial)**: PBT-03 invariants extended with the nine U7
properties, two of which assert forbidden behaviour. **No blocking findings.**

---

## 9. Open Items

**None.** U7 opens no decision and re-opens none. Assumption AS-02 (full-disk
encryption) remains outstanding from U1 and is unaffected by anything in this unit.
