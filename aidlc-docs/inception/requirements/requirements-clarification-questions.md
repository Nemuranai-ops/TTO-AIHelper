# Requirements Clarification Questions

**Project**: TTO Test Analyst Agent System
**Stage**: INCEPTION - Requirements Analysis (answer validation)
**Created**: 2026-08-28T08:31:30Z

All 23 answers were read and validated. Twenty of them are internally consistent and need no
further discussion. Three items cannot be resolved by assumption, because guessing wrong on any
of them changes what gets built. Please answer the three questions below.

---

## Contradiction 1: Mandatory Jira key vs. code-derived and design-derived tests

You answered:

- **Q11**: "every test case must carry at least one link to a Jira key." — stricter than the option
  I offered, which would have accepted a Confluence page, code symbol, or screenshot as the link.
- **Q4**: **A** — the system is **read-only** against Atlassian. It may not create Jira issues.
- **Q14 / Q15**: Bitbucket repositories and a Figma screenshot folder are first-class input sources.

These pull against each other. `bitbucket_endpoints` will find API routes, and Figma screenshots
will show UI states, that no Jira story describes — undocumented endpoints, error states, admin
screens, legacy behaviour. Under a hard Jira-key rule, those behaviours can be neither tested nor
recorded, and the system cannot create a Jira issue to cover them either.

There is a useful fact here: `bitbucket_log` and `bitbucket_changes` both report **Jira keys per
commit** and a **key-coverage percentage**. So a source file can often be traced to a Jira key
through the commits that touched it, even when no story names it directly. That gives a middle
path, but it is not free — the key it yields is the story that last touched the file, which is
evidence of provenance rather than of specification.

### Clarification Question 1
How should the system handle a testable behaviour it finds in code or Figma that maps to no Jira story?

A) **Derive the Jira key from commit history.** Use `bitbucket_log` / `bitbucket_changes` to find
the Jira keys of commits touching the relevant file, and attach the best match. Record the link
type as `derived-from-commit` so reviewers can tell it apart from a direct story link. Where no
commit carries a key either, the behaviour goes to the gap report instead of becoming a test case.
**(Recommended — keeps your rule intact, exploits a capability your Bitbucket MCP already provides, and stays honest about link strength)**

B) **Report only, never generate.** Any behaviour without a direct Jira story link is excluded from
the test suite and listed in an "untraceable behaviour" gap report for a human to triage. The
6,000 cases are then strictly story-derived.

C) **Relax the rule to a documented hierarchy.** Prefer a Jira key; fall back to a Confluence page,
then a code symbol, then a screenshot. Every case still carries a link, but not necessarily a Jira
one, and the link type is recorded.

D) **Generate with a placeholder.** Create the test case linked to a synthetic key
(e.g. `UNTRACED-001`), and emit a report the operator uses to raise the real Jira stories manually.

X) Other (please describe after [Answer]: tag below)

[Answer]: A. bitbucket is read only. we are test team that building this system to make our life easier.

---

## Ambiguity 2: Jenkins packaging target

You answered **Q17: C** — "a packaged artefact (zip/tarball or Docker image) dropped in a known
location for Jenkins to consume." That option deliberately spanned two choices, and they are
substantially different pieces of work.

Playwright needs browser binaries — roughly 500 MB for Chromium, Firefox, and WebKit. A zip of
test sources assumes Jenkins agents already have a matching Node version and the exact matching
browser build installed; a version drift between the generator and the agent is the classic
source of "passes locally, fails in CI." A Docker image built from
`mcr.microsoft.com/playwright:v<version>-jammy` pins the browsers to the same version as the
Playwright library and makes the artefact genuinely self-contained.

### Clarification Question 2
What should the packaged artefact be?

A) **Docker image**, built from the official pinned Playwright base image, containing the test
sources and dependencies, published to your registry. Jenkins runs a container and mounts a
results volume. **(Recommended — the only form that makes browser versions reproducible, and it satisfies SECURITY-10's pinned-base-image requirement cleanly)**

B) **Tarball/zip** of the test project with a lockfile, plus a documented setup script Jenkins runs
to install Node dependencies and browsers before executing.

C) **Both** — a tarball for teams that want to run natively, and a Docker image for reproducible
CI runs.

X) Other (please describe after [Answer]: tag below)

[Answer]: X. need as a pure playwrite project. we have test team accessible bitbucket repository. so we can push it and configure new jobs in Jenkins manually.

---

## Ambiguity 3: Human-driven batching at medium scale

You answered:

- **Q19**: **B** — human-driven batches: the operator explicitly tells the agent which feature to
  work on next.
- **Q16**: **B** — medium scale: 3-10 repos, 100-500 Jira stories, 30-150 screens.
- **Q20**: **A** — a human gate at each pipeline stage.

Taken literally, that combination means an operator issues a prompt per feature per stage. At the
upper end of medium scale that is on the order of a few hundred interactions to reach a full
baseline. That may be exactly what you want — it is the highest-control option, and for a first
run against a real application there is a real argument for watching every step. But I want to be
sure it is a deliberate choice rather than a side effect of the option wording, because it sets
the pace of the entire engagement.

Note that resumable checkpointing gets built regardless: Q3 (incremental re-baselining) requires
durable per-unit state in SQLite anyway. The question is purely **who decides what runs next**.

### Clarification Question 3
How should batch initiation work in practice?

A) **Agent proposes, operator confirms.** The toolchain maintains the work queue and the agent
says "next up: Checkout / boundary cases, 40 estimated — proceed?" The operator approves, redirects
to a different feature, or skips. One short confirmation per unit rather than a specification per
unit. **(Recommended — preserves your control, removes the burden of remembering what is left)**

B) **Strictly operator-specified**, as literally described in Q19 B — the operator names the
feature and stage each time; the agent never proposes.

C) **Operator-approved run blocks.** The operator approves a block of work up front ("generate test
cases for all 12 features in the Payments epic"), the agent runs the whole block autonomously with
checkpointing, and returns for approval at the next pipeline stage gate.

X) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Answers accepted without change

For the record, these twenty answers are consistent and are now fixed as requirements. No action
needed on this list.

| Area | Decision |
|---|---|
| Deliverable | Agent system only (Q1: A) |
| Live AUT for Playwright MCP | Available — live selector derivation is viable (Q2: A) |
| Incremental re-baselining | In scope (Q3: A) |
| Atlassian access | Read-only (Q4: A) |
| UI automation | TypeScript + `@playwright/test` (Q5: A) |
| API automation | Same project, Playwright `APIRequestContext` (Q6: A) |
| Toolchain language | Python 3.11+ (Q7: A) |
| Toolchain exposure | Local MCP server `tto-testgen-mcp` (Q8: A) |
| Test case store | SQLite is system of record; MD/YAML are generated views (Q9: A) |
| Test case structure | Structured records; **steps mandatory**, test data where applicable (Q10: A+) |
| Automation proportion | Automatability classifier decides per case (Q12: A) |
| The 6,000 figure | An outcome of the coverage model, not a quota; scale must be reliable at large volume, and a small sub-story may legitimately yield ~10 cases (Q13: A, Q20 note) |
| `resources.md` | Plain link list, type inferred from URL/path pattern (Q14: B) |
| Figma association | Filename convention + optional sidecar manifest (Q15: A) |
| Scale target | Medium: 3-10 repos, 100-500 stories, 30-150 screens (Q16: B) |
| Suite selection | Tag/annotation-driven (Q18: A) |
| Review gates | Human gate at each pipeline stage (Q20: A) |
| Security Baseline extension | **ENABLED** — blocking constraints (Q21: A) |
| Resiliency Baseline extension | **ENABLED** — design-time guidance (Q22: A) |
| Property-Based Testing extension | **PARTIAL** — pure functions and serialization round-trips (Q23: B) |
