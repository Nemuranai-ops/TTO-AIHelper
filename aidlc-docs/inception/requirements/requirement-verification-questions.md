# Requirements Verification Questions

**Project**: TTO Test Analyst Agent System
**Stage**: INCEPTION - Requirements Analysis
**Created**: 2026-08-28T08:12:30Z

---

## How to Answer

Fill in the letter choice after each `[Answer]:` tag. If none of the options match, choose
`X) Other` and describe your preference after the tag.

Options marked **(Recommended)** carry my analysis of the best fit given your stated constraints
(no LLM API keys, Copilot-only models, ~6,000 test cases, Jenkins handover). You are free to
override any of them.

**Tell me when you are done** and I will validate the answers, resolve any contradictions, and
produce `requirements.md`.

---

# Section A: Scope and Boundaries

## Question 1
What exactly is the deliverable of this AI-DLC engagement?

A) **The agent system only** — the VS Code Copilot agent workspace, its instructions/chat modes/prompts, the deterministic supporting toolchain, MCP wiring, SQLite schema, and generator templates. It is then pointed at a real application by your team. **(Recommended)**

B) The agent system **plus a worked end-to-end demonstration** against one real application (real Bitbucket repo + real Jira project), producing an actual partial test suite as proof.

C) The agent system plus **synthetic sample fixtures** (a fake app's requirements/code/screenshots) so the pipeline can be exercised and regression-tested without touching real corporate data.

D) Agent system + synthetic fixtures + demonstration against a real application (A + B + C).

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2
Is a running/deployed instance of the application under test available for the agent to explore live with Playwright MCP?

A) **Yes** — a stable test/QA environment with a URL and test credentials is reachable from the developer's machine. Playwright MCP can navigate it, snapshot the accessibility tree, and derive real selectors. **(Recommended if true — it dramatically improves selector quality)**

B) **No** — the application is not deployed yet. UI understanding must be derived from Figma screenshots plus front-end source code in Bitbucket, and Playwright tests must be generated against inferred/`data-testid` selectors that are validated later.

C) **Partially** — some modules are deployed, others are not. The system must handle both paths.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 3
After the initial baseline of ~6,000 test cases is established, does the system need to keep the baseline in sync as the application evolves?

A) **Yes — incremental re-baselining is in scope.** Using `bitbucket_changes` / `bitbucket_diff` / `bitbucket_log` and Jira deltas, the system detects what changed since the last run and adds, updates, or retires affected test cases and automation. **(Recommended — the Bitbucket MCP tool set is clearly built for this, and a 6,000-case suite decays fast without it)**

B) **No — one-shot baseline only.** The system produces the initial suite; ongoing maintenance is manual.

C) Yes, but as a **later phase** — design the schema and traceability to support it, but do not implement the delta pipeline now.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4
Should the agent system write anything back to Jira/Confluence (the Atlassian MCP exposes write tools)?

A) **Read-only for now.** The system consumes Jira/Confluence but never writes. All outputs land in the repo and SQLite. **(Recommended for a first release — avoids blast radius while the pipeline is being tuned)**

B) **Write coverage reports to Confluence** — publish the coverage baseline, traceability matrix, and gap analysis as Confluence pages, updated on each run.

C) **Write test cases to Jira** — create Jira test issues (or Xray/Zephyr test objects) for the generated cases.

D) Both B and C.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

# Section B: Technology Choices

## Question 5
What language and framework should the **generated UI automation** target?

A) **TypeScript + `@playwright/test`** — the reference Playwright stack, best MCP/codegen alignment, best Jenkins reporting support. **(Recommended unless your QA team standardises elsewhere)**

B) **Python + `pytest-playwright`** — good if your QA team is Python-first.

C) **Java + Playwright for Java** — good if the AUT and your Jenkins tooling are Java/Maven based.

D) **C# + Playwright for .NET** — good if the AUT is .NET.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 6
What should the **generated API automation** target?

A) **Same language/runner as the UI tests** (e.g. Playwright's `APIRequestContext` in the same TypeScript project) — one repo, one runner, one report, shared fixtures and auth. **(Recommended)**

B) **A separate stack** — e.g. Java + REST Assured, or Python + pytest/requests — kept independent from UI tests.

C) **Postman collections + Newman**, so non-coders can maintain them.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 7
The agent system needs deterministic, non-LLM tooling to do the heavy lifting (SQLite persistence, ID allocation, de-duplication, coverage maths, traceability, sharding, exports, batch orchestration of ~6,000 cases). What language should this toolchain be written in?

A) **Python 3.11+** — strongest fit for data/CLI work, first-class `sqlite3`, easy Pydantic schemas, trivially packaged as an MCP server via the official Python SDK. **(Recommended)**

B) **TypeScript / Node** — keeps the whole repository in one language if the generated tests are also TypeScript.

C) Whatever matches the answer to Question 5.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 8
How should that deterministic toolchain be exposed to the GitHub Copilot agent?

A) **As a local MCP server** (`tto-testgen-mcp`) registered in `.vscode/mcp.json` alongside TTO-Atlassian-MCP, TTO-Bitbucket-MCP, and Playwright MCP — the agent calls typed tools such as `coverage_plan`, `testcase_upsert`, `traceability_link`, `batch_next`. **(Recommended — typed, discoverable, no shell-quoting fragility, and it lets the agent stay in one modality)**

B) **As a CLI** the agent invokes through the VS Code terminal tool (`tto-testgen coverage-plan ...`).

C) **Both** — one core library, exposed as both an MCP server and a CLI, so Jenkins/humans can run it headlessly too.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

# Section C: Test Artefacts and Traceability

## Question 9
What is the authoritative store and format for the ~6,000 generated test cases?

A) **SQLite is the system of record; Markdown/YAML files are generated views** sharded per feature and committed to git. Gives queryable coverage maths plus human-reviewable, diff-able files. **(Recommended)**

B) **Files are the system of record** (YAML/Markdown per feature); SQLite is a rebuildable index only.

C) **SQLite only** — humans read the data through generated reports, not raw files.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 10
What structure should individual test cases take?

A) **Structured test cases** — id, title, feature, type, priority, preconditions, ordered steps, expected results, test data, requirement links, automatability flag. Rendered to Markdown for review. **(Recommended — richest input for automation generation and clearest for manual review)**

B) **Gherkin `.feature` files** — Given/When/Then scenarios with Scenario Outlines and Examples tables.

C) **Both** — structured records as the canonical form, with Gherkin rendered from them for BDD-oriented stakeholders.

X) Other (please describe after [Answer]: tag below)

[Answer]: A, Test step is must. each test cases must have proper test steps with test data if applicable.

## Question 11
How strictly must every test case trace back to a source artefact?

A) **Strict — every test case must carry at least one link** to a Jira key, Confluence page, code symbol/endpoint, or screenshot region. Untraceable cases are rejected by the toolchain. **(Recommended — it is the only mechanical defence against LLM-invented tests at 6,000 scale)**

B) **Best-effort** — trace where possible; allow untraced exploratory/heuristic cases, flagged as such.

C) Strict for functional/API cases, best-effort for negative/boundary/exploratory cases.

X) Other (please describe after [Answer]: tag below)

[Answer]: every test case must carry at least one link  to a Jira key.

## Question 12
Of the ~6,000 test cases, what proportion is expected to be automated by the system?

A) **The system decides per case** using an automatability classifier (API and deterministic UI flows automated; visual/UX/exploratory/manual-data cases marked manual-only). Expect roughly 60-80% automated. **(Recommended)**

B) **All 6,000** must be converted to automated tests.

C) **A defined subset only** — e.g. all API cases plus a prioritised set of critical UI journeys (roughly 1,000-2,000 automated).

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 13
How should the "~6,000 test cases" figure be treated?

A) **As an expected outcome, not a quota.** The count falls out of a documented coverage model (features x test types x equivalence classes x boundaries). If the model yields 4,800 or 7,300, that is the honest answer and the gap is explained. **(Recommended — forcing a number is how suites fill with padding)**

B) **As a hard target.** The system must generate approximately 6,000 (+/-10%), expanding depth of boundary/combinatorial coverage until the number is reached.

C) As a **capacity-planning figure only** — used to size batching, storage, and runtime, with no bearing on generation.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

# Section D: Input Sources

## Question 14
What form should the `resources.md` input manifest take?

A) **Structured Markdown with YAML front-matter per entry** — each resource declares type (jira-epic, jira-story, confluence-page, bitbucket-repo, figma-folder, openapi-spec), identifier, scope hints, and priority. Machine-parseable and human-editable. **(Recommended)**

B) **Plain list of links** — the agent infers type from the URL pattern.

C) **A YAML/JSON file instead of Markdown** (`resources.yaml`).

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 15
How will Figma screenshots in the predefined folder be associated with features and screens?

A) **Filename convention plus an optional sidecar manifest** — e.g. `<feature>__<screen>__<state>.png`, with `screens.manifest.yaml` for anything the filename cannot express (linked Jira key, route, notes). **(Recommended — works with zero extra effort for well-named files, degrades gracefully otherwise)**

B) **Folder structure only** — `figma/<feature>/<screen>.png`.

C) **Vision analysis** — the Copilot model reads each screenshot and infers the feature itself, with no naming requirement.

D) Filename convention + sidecar manifest + vision analysis to enrich each screen's components and states (A + C).

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 16
Roughly what scale of input should the system be designed for?

A) **Small** — 1-3 Bitbucket repos, under 100 Jira stories, under 30 screens.

B) **Medium** — 3-10 repos, 100-500 Jira stories, 30-150 screens.

C) **Large** — 10+ repos, 500+ Jira stories, 150+ screens.

D) Unknown at this point — design for Medium and make the batching configurable so it scales up.

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

# Section E: Jenkins Handover

## Question 17
What is the handover contract with the existing Jenkins pipeline?

A) **A self-contained test repository/branch** — standard layout, lockfile-pinned dependencies, config-driven environments, npm/pytest scripts, tags for suite selection, and JUnit XML + HTML reporting already configured. The agent commits to a branch and opens a PR; Jenkins picks it up. **(Recommended)**

B) The above, **plus a generated `Jenkinsfile`** as a reference the pipeline team can adopt or ignore.

C) **A packaged artefact** (zip/tarball or Docker image) dropped in a known location for Jenkins to consume.

D) **Just the test source files** in an agreed directory layout — all packaging, dependency, and reporting concerns stay with the pipeline team.

X) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 18
How should the generated suite be organised for selective execution in Jenkins?

A) **Tag/annotation-driven** — every test carries tags for suite (smoke/regression/full), type (ui/api), feature, and priority, so Jenkins selects by grep/tag expression. **(Recommended)**

B) **Directory-driven** — separate top-level folders per suite; Jenkins selects by path.

C) **Manifest-driven** — the toolchain emits suite manifests (JSON lists of test ids) that Jenkins consumes.

D) Tags plus generated manifests (A + C).

X) Other (please describe after [Answer]: tag below)

[Answer]: A

---

# Section F: Operating Model

## Question 19
Generating ~6,000 traceable test cases far exceeds a single Copilot chat session's context and output budget. How should the run be structured?

A) **Resumable batch pipeline with checkpointing.** The toolchain slices work into feature-sized units, tracks per-unit status in SQLite, and the agent processes one unit per turn — stopping, resuming, and retrying without losing or duplicating work. Progress is visible and the run can span days. **(Recommended — this is the single most important design decision for reaching 6,000 reliably)**

B) **Human-driven batches** — the operator explicitly tells the agent which feature to work on next.

C) **Fully autonomous long-running loop** with minimal human checkpoints.

X) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 20
How much human review is required before generated artefacts are accepted?

A) **Gate at each pipeline stage** — a human approves the coverage baseline before test-case generation, and approves test cases before automation generation. **(Recommended — a wrong coverage model multiplied by 6,000 is expensive to unwind)**

B) **Gate only at the coverage baseline**; test cases and automation flow through automatically once the baseline is approved.

C) **Post-hoc review** — generate everything, review afterwards in the PR.

X) Other (please describe after [Answer]: tag below)

[Answer]: A, based on the input it can be ~6000. its not fixed. but make it reliable to large number. sube story might have only 10 test cases. but it up to input sources.

---

# Section G: Extension Opt-Ins

## Question 21: Security Extensions
Should security extension rules be enforced for this project?

A) Yes — enforce all SECURITY rules as blocking constraints (recommended for production-grade applications)

B) No — skip all SECURITY rules (suitable for PoCs, prototypes, and experimental projects)

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 22: Resiliency Extensions
Should the resiliency baseline be applied to this project?

**What this extension is.** Enabling it applies a set of **directional, design-time best practices** for building resilient systems, derived from the **AWS Well-Architected Framework (Reliability Pillar)** and resilience-review guidance. It steers requirements, design, and code toward fault tolerance, high availability, observability, and recoverability — covering 15 practice areas across business goals, change management, observability, high availability, disaster recovery, and continuous improvement.

**What this extension is NOT.** Enabling it does **not** make your workload production-ready, nor does it certify or guarantee any availability, RTO, or RPO target. It is a **starting point** that scaffolds good resiliency decisions early — it is not a substitute for a formal **AWS Well-Architected Review** of the built system.

Treat the output as a well-grounded **first draft of your resiliency posture** to build on and validate — not a finished, production-certified result.

A) Yes — apply the resiliency baseline as directional best practices and design-time guidance (recommended for business-critical workloads, as an informed starting point that you can validate and harden before go-live)

B) No — skip the resiliency baseline (suitable for PoCs, prototypes, and experimental projects where rapid iteration matters more than reliability)

X) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 23: Property-Based Testing Extension
Should property-based testing (PBT) rules be enforced for this project?

A) Yes — enforce all PBT rules as blocking constraints (recommended for projects with business logic, data transformations, serialization, or stateful components)

B) Partial — enforce PBT rules only for pure functions and serialization round-trips (suitable for projects with limited algorithmic complexity)

C) No — skip all PBT rules (suitable for simple CRUD applications, UI-only projects, or thin integration layers with no significant business logic)

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Note on Question 23

This question is about testing **the agent system you are building**, not about the ~6,000 test
cases it generates. The toolchain contains exactly the kind of logic PBT is good at — coverage
maths, de-duplication, ID allocation, traceability graph integrity, batch resumption invariants —
so it is worth a deliberate answer rather than a reflex one.
