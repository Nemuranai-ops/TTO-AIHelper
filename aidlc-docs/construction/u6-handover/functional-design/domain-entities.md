# Domain Entities — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

U6 adds **no table**. It reads what U5 wrote, checks it, and produces two documents.

---

## Why No New Table

A handover is an event, not an entity. What it produces — a manifest and a
verification report — are files the operator reads and pushes, and the facts they
contain already live in `automated_test`, `test_case` and `gap`.

Storing the manifest would create a second copy of the corpus that goes stale the
moment a case changes. **The same reasoning that keeps the traceability matrix
unstored in U4**: the links are the truth, and the document is a view of them at a
moment.

What *is* recorded is the handover's outcome, and `unit_state` already holds it:
`unit_ref='<project>'`, `stage='handover'`, with `metrics` carrying the counts. U7
built that column for exactly this.

---

## Computed Types

### `HandoverManifest`

Written to `handover-manifest.md` and `handover-manifest.json` in the project root.

| Field | Meaning |
|---|---|
| `generated_at_version` | The coverage model version and its content hash |
| `entries` | One per automated test |
| `totals` | Automated, manual-only, needs-review, corpus total |
| `at_risk` | Tests resting on unverified or fragile locators |
| `reconciliation` | The three-way result — see `VerificationReport` |

### `ManifestEntry`

| Field | Source |
|---|---|
| `test_id` | `automated_test.id` |
| `case_id` | `automated_test.case_id` |
| `test_name` | `automated_test.test_name` |
| `spec_path` | Relative to the project root, **never absolute** |
| `jira_key` | The case's resolved trace link |
| `tags` | The case's own tags |
| `is_at_risk`, `at_risk_reason` | `automated_test` |

`spec_path` is relative because the manifest is committed and read on other machines.
An absolute path would name the generating workstation, which is both useless to the
reader and a small disclosure about the operator's environment.

### `VerificationReport`

Two tiers, reported separately and never merged.

| Field | Meaning |
|---|---|
| `structural` | The Python-only checks, always run |
| `toolchain` | `npm ci`, `tsc --noEmit`, `playwright test --list` |
| `reconciliation` | The three-way manifest check |
| `is_ready` | True only when `structural` and `reconciliation` both pass |
| `blocking` | Every failure, each naming what and where |

### `TierResult`

| Field | Meaning |
|---|---|
| `status` | `passed`, `failed`, or **`skipped`** |
| `skipped_reason` | Why — e.g. "node not found on PATH" |
| `checks` | Per-check outcome |
| `duration_ms` | For the toolchain tier, which is the slow one |

**`skipped` is a first-class status, not a kind of pass.** A report saying
"compilation not verified: Node not found" is honest; folding it into `passed` would
be a false assurance the engineer acts on — they would push, and find in Jenkins the
failure U6 exists to catch first.

This is the same three-outcome instinct as U4's `unchanged` and U5's manifest: the
middle state is the one that carries information, and collapsing it loses exactly what
the reader needs.

---

## What U6 Adds to the Project

U5 writes a complete project. U6 supplies the three things it cannot.

| File | Why U5 cannot produce it |
|---|---|
| `package-lock.json` | Records a resolved dependency graph; only `npm` can write it |
| `.gitignore` | Concerns the repository the project is pushed to, not the code |
| `handover-manifest.md` / `.json` | Describes the finished project, which does not exist until assembly |

The `.gitignore` excludes `node_modules/`, `test-results/`, `playwright-report/`,
`.env` and `blob-report/`. **`.env` is the important entry**: `.env.example` is
committed and `.env` holds the credentials the engineer fills in, and a project that
invites them to create the second without excluding it is a project that invites a
credential into the repository.

---

## Entities U6 Reads

| Entity | Used for |
|---|---|
| `automated_test` | Manifest entries, the at-risk count, reconciliation |
| `test_case` | Jira keys, tags, the corpus totals |
| `emitted_view` (`kind='automation'`) | Which files U5 believes it wrote |
| `gap` | Manual-only and needs-review totals |
| `unit_state` | The gate, and where the outcome is recorded |

**U6 writes to none of them except `unit_state`.** Assembly and verification are
read-only against the corpus: a handover that adjusted what it was describing would
make the manifest a record of itself rather than of the delivery.

---

## Integrity Rules

| Rule | Enforcement | New? |
|---|---|---|
| Handover is ready only when structural checks and reconciliation pass | S7, BR-U6-5 | **Yes** |
| A skipped tier never counts as passed | `TierResult.status`, three-valued | **Yes** |
| Every manifest entry names an existing spec file | BR-U6-4 | **Yes** |
| Every spec file on disk appears in the manifest | BR-U6-4 | **Yes** |
| U6 never pushes, branches, or writes Jenkins configuration | **No such method exists** | **Yes** |

The last is structural, following U7's `next_unit()` and P2's write-free source
protocols. FR-HND-04 is not a rule S7 follows — it is a capability S7 does not have,
so it cannot be violated by a future change that forgets the rule.
