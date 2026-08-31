# End-to-End Test Instructions

**Project**: TTO Test Analyst Agent System (TAAS)
**Version**: 1.0 | **Date**: 2026-08-31

---

## What "end to end" means for this system

TAAS is not an application with a user journey. It is a **VS Code Copilot workspace
plus a local MCP toolchain**, and the end-to-end path runs through a human operator at
seven gates.

That has one consequence worth stating plainly: **the full path cannot be automated,
because approving a gate is the operator's judgement.** What follows is a manual
rehearsal, not a test script.

---

## Prerequisites

| Needed | For |
|---|---|
| VS Code with the GitHub Copilot Agent extension | The agent layer |
| The four MCP servers registered in `.vscode/mcp.json` | TTO-Atlasian, TTO-bitbucket, Playwright, tto-testgen |
| Atlassian and Bitbucket read tokens | Ingestion |
| A `resources.md` with real Jira and Confluence links | Something to ingest |
| A reachable application under test | Live locator verification (optional) |
| Node.js | The final compile check (optional — U6 reports `skipped` without it) |

---

## The Rehearsal

Each step is a chat mode, a tool call, and a gate. **Approve nothing you have not
read** — that is the point of the gates, and a rehearsal that rubber-stamps them proves
nothing.

### 1. Ingest

Mode: `ingest`. Call `resources_list`, then `ingest_run`.

**Check**: unclassified references are listed rather than guessed at. Not-found and
not-authorised failures are distinguished — they call for different fixes.

### 2. Analyse

Mode: `analyse`. The agent proposes features, business rules and the UI model.

**Check**: every feature cites at least one ingested artefact. An artefact mapping to no
feature is listed rather than forced into the nearest one.

### 3. Requirements

Mode: `requirements`. Call `requirements_upsert`.

**Check**: a requirement stating two behaviours is rejected with the suggested split.
Behaviour with no Jira link becomes a gap, not a silent omission.

### 4. Coverage — **the first binding gate**

Mode: `coverage`. Call `coverage_build`, review, then `coverage_approve`.

**Check**: the planned yield states its derivation. The approval binds to a content
hash — rebuild without changing anything and confirm the approval survives; change one
requirement and confirm it is invalidated and says so.

### 5. Cases

Mode: `cases`. Call `testcases_upsert` in batches of up to 200.

**Check**: every case has steps with expected results. Try a case whose test data
contains a real-looking email — it must be refused, naming the field and the permitted
form, and **nothing** from that batch stored.

### 6. Automation

Mode: `automation`. Call `automation_emit`.

**Check**: only `automatable` cases produce tests. Edit `playwright.config.ts` by hand,
re-emit, and confirm the file is reported as hand-edited and **not overwritten**.

### 7. Handover

Mode: `handover`. Call `handover_assemble`, then `reports_generate`.

**Check**: structural verification passes and the toolchain tier is either `passed` or
honestly `skipped`. The manifest reconciles three ways. Then push the project to
Bitbucket and configure Jenkins **manually** — TAAS has no method that does either.

### 8. Re-baseline

Later, after the application has moved: `delta_detect`.

**Check**: obsolete cases are retired with reasons and **nothing is deleted**.
`requires-update` cases are reported and untouched. If a source was unreachable, the
baseline did **not** advance.

---

## The Five Things Worth Deliberately Breaking

A rehearsal that only follows the happy path proves the easy half. Each of these has a
defined correct behaviour:

| Break | Correct behaviour |
|---|---|
| Put a real email in a case's test data | Batch refused entirely; field and pattern named; nothing stored |
| Hand-edit a generated spec, then re-emit | Reported as hand-edited; file untouched |
| Delete a page object, then run `handover_assemble` | Structural check fails naming the file; handover not ready |
| Revoke the Bitbucket token, then `delta_detect` | Jira changes reported; Bitbucket named unavailable; **baseline not advanced** |
| Run `reports_generate` before approving any coverage | Report renders with sections marked `not available`, each naming its stage |

**The fourth is the one to be most careful about.** Its failure mode is silent: if the
baseline advances anyway, every change in the missed window is skipped for ever and
nothing later will reveal it. Check `delta_status` before and after.

---

## What a Rehearsal Cannot Prove

| Not provable this way | Why |
|---|---|
| That the agent reasons well | The gates exist because it might not |
| That 6,000 cases are the right 6,000 | Coverage is a model, and the model is reviewed by a human |
| That the generated tests pass against the real application | They are a starting point; the engineer supplies the interactions |

The system's claim is narrower and checkable: **every figure is traceable to the corpus,
every case to a Jira key, and every decision to a human who approved it.**
