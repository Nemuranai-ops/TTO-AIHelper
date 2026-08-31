# Agent Layer — The Operator Interface

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-29

The AI-DLC artefact for UI design. TAAS has no conventional frontend — its interface
is the VS Code Copilot chat surface, shaped entirely by the configuration files this
unit owns. Chat modes are the screens, instructions are the standing behaviour, and
prompt files are the reusable actions.

---

## 1. Repository Instructions

**Path**: `.github/copilot-instructions.md` | **Serves**: FR-AGT-01, FR-AGT-06, NFR-USA-03

Always in force. Establishes what the agent is and what it must never do.

### Content

| Section | Substance |
|---|---|
| Role | A test analysis assistant operating a seven-stage pipeline. It reasons about meaning; the toolchain owns every fact that must stay true. |
| Pipeline model | The seven stages, their order, and that each ends at a human gate |
| Traceability rule | Every test case carries ordered steps and a Jira key. The toolchain refuses otherwise — do not attempt to work around a refusal. |
| State rule | All durable state goes through `tto-testgen-mcp`. Never write a test case, requirement or coverage item to a file. |
| Honesty rule | Say what could not be determined. Never fill a gap with plausible content. |
| Scope rule | The operator names the unit and stage. Never propose the next one. |
| Error handling | `REJECTED_*` means fix the input; `FAILED_*` means the system had a problem. Do not retry a rejection unchanged. |

### The rule that needs the most care

**"Never fill a gap with plausible content."** It runs against the grain of what a
language model does well. Stated once it will drift over a long session, which is why
the traceability rule is enforced by the schema and not by this file. This instruction
reduces how often the refusal is met; the constraint is what makes it hold.

---

## 2. Chat Modes

**Path**: `.github/chatmodes/*.chatmode.md` | **Serves**: FR-AGT-03, NFR-USA-01

Seven modes, one per pipeline stage. These are the screens of the interface.

| Mode | Purpose | Stage tools (plus universal reads) |
|---|---|---|
| `ingest` | Resolve and ingest declared inputs | `ingest_resources`, `resources_list`, `artefacts_query` |
| `analyse` | Build the application model | `analysis_upsert`, `api_model_derive`, `ui_model_upsert`, `artefacts_query`, `feature_get` |
| `requirements` | Derive atomic testable requirements | `requirements_upsert`, `requirements_query`, `feature_get`, `trace_query` |
| `coverage` | Build and approve the baseline | `coverage_build`, `coverage_approve`, `coverage_reduce`, `coverage_get`, `coverage_forecast`, `requirements_query` |
| `cases` | Generate the corpus | `testcases_upsert`, `views_emit`, `testcases_query`, `testcase_get`, `duplicates_check`, `coverage_get` |
| `automation` | Emit Playwright TypeScript | `automation_emit`, `testcases_query`, `testcase_get` |
| `handover` | Assemble and verify the project | `handover_assemble`, `handover_verify`, `reports_generate` |

**Universal in every mode**: `run_status`, `unit_state_get`, `health_check`,
`features_list`, `unit_begin`, `unit_complete`, `stage_approve`.

**Absent from every mode**: file-write tools. FR-AGT-06 becomes structural rather
than remembered — the agent cannot write a test case to a file because no mode offers
the capability.

### Mode opening behaviour

Each mode states which stage it serves and what it needs from the operator, then
stops. It does not begin work, and it does not suggest a feature.

> **Cases mode.** I generate test cases for one feature at a time. The coverage
> baseline must be approved for that feature before I can start. Name the feature.

### What a mode does when asked to work outside its stage

Declines, names the correct mode, and does not attempt a workaround.

> That is automation generation, which the Automation mode handles. Switch to it and
> name the feature.

---

## 3. Path-Scoped Instructions

**Path**: `.github/instructions/*.instructions.md` | **Serves**: FR-AGT-02

Applied automatically by `applyTo` glob, so guidance arrives without being fetched.

| File | `applyTo` | Content |
|---|---|---|
| `playwright.instructions.md` | `generated/playwright-suite/**/*.ts` | Page Object Model, role and label locators, no fixed waits, tag and traceability annotations, no literal credentials |
| `testcase-views.instructions.md` | `generated/views/**/*.{md,yaml}` | These are generated views, not the record. Edit the corpus through the toolchain; hand-edits are detected and reported. |
| `toolchain.instructions.md` | `src/tto_testgen/**/*.py` | Hexagonal boundaries, parameterised SQL only, `Result` rather than exceptions, no secret in a log line |

A file matching no glob gets the repository instructions alone. That is the normal
case, not an error.

---

## 4. Prompt Files

**Path**: `.github/prompts/*.prompt.md` | **Serves**: FR-AGT-04

Six recurring tasks, so their structure is consistent rather than re-improvised.

| Prompt | Task |
|---|---|
| `analyse-story.prompt.md` | Read one Jira story and extract features, rules and edge cases |
| `generate-cases.prompt.md` | Produce a case batch for one feature from its approved coverage |
| `review-batch.prompt.md` | Summarise a generated batch for operator review — counts, types, rejections |
| `generate-page-object.prompt.md` | Produce one page object from the UI model |
| `coverage-report.prompt.md` | Produce the coverage and gap report for a feature |
| `resume-run.prompt.md` | Show what is interrupted, what it produced, and what the operator's options are |

`resume-run` earns its place: it is the first thing an operator needs after any
interruption, and reconstructing that view by hand each time is exactly the friction
the persona's "losing the thread" pain point describes.

---

## 5. MCP Registration

**Path**: `.vscode/mcp.json` | **Serves**: FR-AGT-05, NFR-SEC-01

Four servers.

| Server | Transport | Access |
|---|---|---|
| `tto-testgen` | stdio, `uv run tto-testgen-mcp` | Local, read and write |
| `tto-atlassian` | Per existing TTO-Atlassian-MCP config | **Read-only** |
| `tto-bitbucket` | Per existing TTO-Bitbucket-MCP config | **Read-only** |
| `playwright` | Per Microsoft Playwright MCP config | Read-only against the AUT |

Credentials come from the environment or the OS credential store. No secret appears
in this file, and it is committed to the repository — which is precisely why.

### Note on the read-only servers

The toolchain also acts as an MCP client to Atlassian and Bitbucket for bulk
ingestion (Application Design Q3), so those two are reachable by both the agent and
the toolchain. The agent uses them for targeted lookups during analysis; the
toolchain uses them for volume. Neither path can write: the source protocols declare
no write method.

---

## 6. Operator Journeys

### Starting a run

```
Operator opens the workspace
      |
      v
Copilot loads .github/copilot-instructions.md automatically
      |
      v
Operator selects the Ingest chat mode
      |
      v
Mode states its purpose and asks what to ingest
      |
      v
Operator: "Ingest everything in resources.md"
      |
      v
Agent calls ingest_resources, reports the inventory, and STOPS
      |
      v
Operator reviews, then approves the ingest stage
```

### Meeting a closed gate

```
Operator (Cases mode): "Generate cases for checkout"
      |
      v
unit_begin -> REJECTED_GATE_CLOSED
      |
      v
"The coverage baseline for checkout is complete but not approved.
 Approve the coverage stage for checkout - the Test Lead must do this."
      |
      v
Operator knows exactly what is needed and who must do it
```

### Returning after an interruption

```
Operator (any mode): "Where did we get to?"
      |
      v
run_status -> facts, sorted by unit and stage, no suggestion
      |
      v
"checkout/cases has been in progress for 3 days with no activity.
 It had produced 40 cases before stopping. Nothing was lost - unit work
 is transactional, so restarting re-runs it from the beginning.
 payments/coverage is complete and approved."
      |
      v
Operator decides what to work on. The agent does not.
```

---

## 7. Design Rules for the Interface

| Rule | Reason |
|---|---|
| A mode states its purpose and stops | The operator drives; C-12 |
| No mode proposes a feature or unit | C-12, enforced by there being no tool that could |
| Every refusal names the remedy | A refusal without one sends the operator to documentation for something the system knows |
| Status is facts, never a ranking | A report surfacing one candidate is a proposal in disguise |
| Modes decline out-of-stage work by name | Switching mode is one action; a workaround is a defect |
| No file-write tool in any pipeline mode | FR-AGT-06 made structural |
| Generated views say they are generated | Prevents editing a view and expecting the corpus to change |

---

## 8. Requirement Coverage

| Requirement | Where |
|---|---|
| FR-AGT-01 Repository instructions | §1 |
| FR-AGT-02 Path-scoped instructions | §3 |
| FR-AGT-03 Per-stage chat modes | §2 |
| FR-AGT-04 Prompt files | §4 |
| FR-AGT-05 MCP registration | §5 |
| FR-AGT-06 State through the toolchain | §1 state rule, §2 absent file-write tools |
| NFR-USA-01 One instruction per stage | §2 — the operator names a feature, not a tool sequence |
| NFR-USA-03 Say what could not be determined | §1 honesty rule |
| C-12 Operator names the scope | §2, §6, §7 |
