# Business Rules — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

U6 assembles, verifies, and stops. Every rule is either a check or a refusal.

---

# BR-U6-1: Assembly

**Decision**: verify in place; add only what U5 cannot produce.

## BR-U6-1.1 `generated/automation` is the handover directory

No copy is made. U5's output **is** what the operator pushes.

**A copy would create two projects that can disagree**, and the one pushed would be
the one nothing verified. It would also break U5's hand-edit protection: the recorded
hash names a path, and a copied file at a different path is a file the protection does
not cover — so an engineer's tuned `playwright.config.ts` would be silently reverted in
the copy they actually deliver.

## BR-U6-1.2 What U6 adds

`package-lock.json` (BR-U6-3), `.gitignore`, and the handover manifest. Nothing else.

## BR-U6-1.3 Completeness is checked, not assumed

FR-HND-01 lists eleven required files. Each is checked for presence, and a missing one
is a structural failure naming the file. **U5 might not have run**, or might have run
for one feature and not the rest, and "the directory looks like a project" is not the
same as "the project is complete".

## BR-U6-1.4 A hand-edited file is never modified

U6 inherits U5's rule through the same table. Assembly adds files; it does not rewrite
existing ones. The one exception is the manifest, which U6 owns outright and which is
rewritten on every handover — stated in its own header so the engineer knows not to
edit it.

---

# BR-U6-2: Two Verification Tiers

**Decision**: structural checks always run; toolchain checks run when Node is present
and are reported as `skipped` when it is not.

## BR-U6-2.1 The structural tier — always, in Python

| Check | Fails when |
|---|---|
| Required files present | Any of the eleven is missing |
| Every `import` from `../pages/` resolves | A spec references a page object U5 never generated |
| Every `import` from `../fixtures/` resolves | Same, for fixtures |
| Every referenced data file exists | Same, for test data |
| No absolute path appears in any generated file | A path names the generating workstation |
| No file contains a literal credential | L13, re-run over the assembled bytes |

**This tier catches US-HND-02 AC4's failure**, which is the common one: a spec importing
a page object that does not exist. It needs no compiler — a missing file is a missing
file — and it runs in milliseconds.

## BR-U6-2.2 The toolchain tier — when Node is present

| Check | Command |
|---|---|
| Dependencies install from the lockfile | `npm ci --ignore-scripts` |
| TypeScript compiles | `npx tsc --noEmit` |
| Playwright enumerates the tests | `npx playwright test --list` |

## BR-U6-2.3 Absent Node is `skipped`, never `passed`

The report states which tier ran. **"Compilation not verified: node not found on
PATH" is honest; recording it as a pass is a false assurance the engineer acts on** —
they push, and find in Jenkins the failure U6 exists to catch first.

Requiring Node was the alternative and would make the unit unusable on a machine with
Python and no Node — quite possibly the operator's, since TAAS runs inside VS Code
beside the Copilot agent rather than on a build agent.

## BR-U6-2.4 Readiness depends on the structural tier only

`is_ready` is true when the structural tier and reconciliation pass. A **failed**
toolchain tier blocks readiness; a **skipped** one does not.

The distinction matters: a compilation error is a real defect and must block. An
unavailable compiler is a fact about the machine, and blocking on it would mean the
system can never declare a handover ready in the environment it was built for.

## BR-U6-2.5 `--ignore-scripts` is not optional

`npm ci` runs lifecycle scripts from every transitive dependency by default. The
generated project is ours, but its dependency tree is not, and verification must not be
a path through which arbitrary code executes on the operator's workstation
(NFR-SEC-13).

---

# BR-U6-3: The Lockfile

**Decision**: generated with `npm install --package-lock-only`; absent and reported
when Node is not available.

## BR-U6-3.1 Why that flag

It resolves the dependency graph and writes the lockfile **without downloading
packages or running scripts**. Fast, and it needs only registry metadata.

## BR-U6-3.2 When Node is absent

The handover report names the single command the operator must run before pushing:

```
npm install --package-lock-only
```

**A missing file with the exact command beside it is a two-second fix.** A missing file
with no explanation is a puzzle, and the operator's first guess — `npm install` — also
creates `node_modules/`, which is 500 MB they then have to notice is gitignored.

## BR-U6-3.3 A lockfile is never hand-written

It records resolved integrity hashes. Synthesising one would produce a file that looks
authoritative and is wrong, and `npm ci` would fail against it in CI — the exact class
of failure U6 exists to prevent.

## BR-U6-3.4 Exact versions are re-checked

`package.json` is parsed and every version asserted to be exact. U5 pins them and
config refuses a range, but the file is editable and this is the last point before it
is pushed (FR-HND-02).

---

# BR-U6-4: Three-Way Reconciliation

**Decision**: the `automated_test` table, the spec files on disk, and the manifest must
agree.

## BR-U6-4.1 The three sources

| Source | Says |
|---|---|
| `automated_test` | What the corpus believes was generated |
| Spec files on disk | What is actually being handed over |
| The manifest | What the operator is told they are receiving |

## BR-U6-4.2 Why two-way is not enough

| Comparison | Misses |
|---|---|
| Database ↔ manifest | A spec file deleted or renamed by hand |
| Disk ↔ manifest | A test the database believes exists but was never written |

**Both failures are reachable**, because the design explicitly permits the engineer to
edit the project. Only the three-way check catches both.

## BR-U6-4.3 A mismatch blocks readiness

Named in both directions: tests present on disk but absent from the manifest, and
manifest entries with no corresponding test (US-HND-03 AC3). Neither is guessed at or
quietly reconciled.

## BR-U6-4.4 Test identity across the three

A test is matched by its case identifier, which appears in `automated_test.case_id`, in
the manifest entry, and in the spec file's test title and annotation. **U5 put it in
the title as well as the annotation for this reason**: the disk side of the check needs
to find it without parsing TypeScript.

---

# BR-U6-5: What "Ready" Means

## BR-U6-5.1 The conditions

| Condition | Required for ready |
|---|---|
| Structural tier passes | **Yes** |
| Reconciliation passes | **Yes** |
| Toolchain tier passes | Only if it ran |
| Toolchain tier skipped | Does not block |
| Lockfile present | **No** — reported, with the command |

## BR-U6-5.2 Ready is not approved

`is_ready` is U6's assessment. The handover gate is the operator's, through U7's
`stage_approve`. **The system reports; the human decides** — the same division as every
other stage gate, and the reason U6 has no method that pushes.

## BR-U6-5.3 Every blocking finding names what and where

File, line where applicable, and what was expected. A verification report that says
"structural check failed" without saying which file is a report that sends the engineer
looking, which is the work U6 was supposed to save.

---

# BR-U6-6: The Boundary

**Decision**: enforced by absence.

## BR-U6-6.1 What U6 cannot do

S7 has **no method** that pushes to a repository, creates or switches a branch, writes
Jenkins configuration, or invokes `git`. FR-HND-04 is therefore not a rule S7 follows —
it is a capability S7 does not have.

This is the third time the pattern has been used: P2's source protocols declare no
write method, `RunStateService` has no `next_unit()`, and now S7 has no `push()`. In
each case the alternative was a rule someone could forget.

## BR-U6-6.2 Why the constraint exists

The operator pushes and configures Jenkins manually, by their own decision
(Clarification Question 2). A system that could push would eventually push to the wrong
branch of a repository the test team shares, and no amount of care in the calling code
would make that impossible while the method existed.

---

# BR-U6-7: Subprocess Invocation

**Decision**: fixed argument lists, bounded, never a shell.

## BR-U6-7.1 The rules

| Rule | Why |
|---|---|
| `shell=False`, argument list never a string | No shell metacharacter can be interpreted |
| Arguments are literals; no project value is interpolated | A feature slug cannot become an argument |
| `cwd` is the project directory | No `cd`, no relative escape |
| Timeout per command, default 300 s | A hung `npm ci` must not hang the handover |
| `--ignore-scripts` on `npm ci` | Dependency lifecycle scripts do not run |
| Output captured, not streamed to stdout | stdout carries MCP protocol traffic |

## BR-U6-7.2 A timeout is a failure, not a skip

`skipped` means the tool was absent. A tool that ran and did not finish is a real
problem — a broken lockfile, an unreachable registry — and the report says which.

## BR-U6-7.3 Node detection is by resolution, not by trying

`shutil.which("npm")` before invoking. Attempting the command and catching
`FileNotFoundError` would work and would conflate "not installed" with a dozen other
`OSError`s, which is how a skip ends up hiding a real fault.

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-U6-1 Assembly | FR-HND-01, FR-HND-03 | US-HND-01 |
| BR-U6-2 Two tiers | FR-HND-05 | US-HND-02 |
| BR-U6-3 Lockfile | FR-HND-02 | US-HND-01 |
| BR-U6-4 Reconciliation | FR-HND-06 | US-HND-03 |
| BR-U6-5 Readiness | FR-HND-05, FR-HND-06 | US-HND-02, US-HND-03 |
| BR-U6-6 The boundary | FR-HND-04 | US-HND-01 |
| BR-U6-7 Subprocess | NFR-SEC-13 | US-HND-02 |
