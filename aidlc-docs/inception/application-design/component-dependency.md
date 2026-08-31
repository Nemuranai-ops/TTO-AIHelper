# Component Dependencies

**Project**: TTO Test Analyst Agent System (TAAS)
**Stage**: INCEPTION - Application Design
**Version**: 1.0
**Date**: 2026-08-28

---

## The Dependency Rule

Dependencies point inward, always:

```
MCP Surface  -->  Services  -->  Domain Core
                     |
                     +-------->  Ports  <--------  Adapters
```

- The **domain core** imports nothing from any other ring
- **Services** import domain and ports, never adapters
- **Adapters** import ports and domain types, never services
- **Platform** components are importable from any ring; they import nothing but standard library

Concrete adapters are supplied to services at composition time. A service holds a `TestCaseRepository`
protocol, never a `SqliteTestCaseRepository`. This is what allows the domain and service logic to be
tested without a database, which the property-based tests require.

---

## Dependency Matrix

`W` = writes through, `R` = reads through, `U` = uses (pure call), `-` = no dependency.

| From \ To | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | P1 | P2 | P3 | X1 | X2 | X4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **S1 Ingestion** | U | - | - | - | - | - | - | - | W | R | - | U | U | U |
| **S2 Analysis** | U | - | - | - | U | - | U | - | W | R | - | U | U | U |
| **S3 Requirements** | U | - | U | - | U | U | U | - | W | - | - | U | U | - |
| **S4 Coverage** | U | U | - | - | U | - | U | - | W | - | - | U | U | - |
| **S5 TestCase** | U | - | U | U | U | U | U | - | W | - | W | U | U | - |
| **S6 Automation** | U | - | U | - | - | - | - | - | R | - | W | U | U | - |
| **S7 Handover** | U | - | - | - | - | - | - | - | R | - | W | U | U | - |
| **S8 Reporting** | U | U | U | - | - | - | - | - | R | - | W | U | U | - |
| **S9 Delta** | U | - | U | - | - | - | - | U | W | R | - | U | U | U |
| **S10 RunState** | U | - | - | - | - | - | - | - | W | - | - | U | U | - |
| **D1 to D8** | U | - | - | - | - | - | - | - | - | - | - | U | - | - |
| **A1 Schema** | - | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **A2 Repositories** | U | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **A3 Atlassian** | U | - | - | - | - | - | - | - | - | - | - | U | U | U |
| **A4 Bitbucket** | U | - | - | - | - | - | - | - | - | - | - | U | U | U |
| **A5 DesignAsset** | U | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **A6 Manifest** | U | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **A7 Playwright** | U | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **A8 Views** | U | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **A9 Reports** | U | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **M1 McpServer** | - | - | - | - | - | - | - | - | - | - | - | U | U | - |
| **M2 ToolRegistry** | U | - | - | - | - | - | - | - | - | - | - | U | U | - |

**Adapters implement ports** (not shown as dependencies): A2 implements P1; A3, A4, A5, A6 implement
P2; A7, A8, A9 implement P3.

### Acyclicity

The graph is acyclic. Verified by construction: rings are strictly ordered
(MCP → Services → Domain/Ports ← Adapters), no domain component imports a service, no adapter
imports a service, and no service imports another service — **with one exception**.

**The single service-to-service dependency**: S4, S5, S6 and S7 call `S10.is_gate_open()`. This is
deliberate and does not create a cycle, because S10 depends on nothing but its repository and never
calls back. Gate enforcement was placed in a service rather than duplicated into four services
because a gate that four components implement independently is a gate that eventually disagrees
with itself.

---

## Communication Patterns

| Boundary | Pattern | Rationale |
|---|---|---|
| Agent to toolchain | MCP over stdio, typed schemas, structured results | C-10; NFR-SEC-02 forbids a network listener |
| Toolchain to Atlassian/Bitbucket | MCP client, synchronous, read-only, retry-wrapped | Q3 decision; keeps hundreds of issue bodies out of the model's context |
| Agent to Playwright MCP | Direct, agent-driven | UI exploration needs judgement about what is on screen |
| Service to domain | Direct synchronous calls, pure functions | Domain is I/O-free by construction |
| Service to repository | Protocol calls inside a caller-supplied transaction | Services own transaction boundaries; repositories never open one |
| Service to emitter | Protocol call returning a written-file manifest | Emitters do not read repositories, so output is a function of what it was given |
| Any component to platform | Direct calls | Cross-cutting by nature |

---

## External MCP Server Touch Points

| Server | Touched by | Tools used | Direction |
|---|---|---|---|
| **TTO-Atlassian-MCP** | A3 only | `jira_get_issue`, `jira_search_issues`, `confluence_get_page`, `confluence_search` | Read only |
| **TTO-Bitbucket-MCP** | A4 only | `bitbucket_repos`, `bitbucket_endpoints`, `bitbucket_file`, `bitbucket_grep`, `bitbucket_log`, `bitbucket_changes`, `bitbucket_diff`, `bitbucket_tags` | Read only |
| **Playwright MCP** | The agent, not the toolchain | navigation, snapshot, locator inspection | Read only against the AUT |
| **tto-testgen-mcp** | The agent | write tier and read tier | Local |

**Containment is structural.** Exactly one adapter touches each external server, and the P2 source
protocols declare no write operation. The read-only posture required by C-05, C-06 and NFR-SEC-14
therefore cannot be violated by a component that forgets the rule — there is no method to call.

---

## Data Flow: the Seven Pipeline Stages

### Stage 1 — Input Sources

```
resources.md --> A6 --> S1 --> A3 (Jira, Confluence) --------+
                        |                                     |
figma folder ---------> A5 ---------------------------------->+--> P1 --> SQLite
                        |                                     |
                        +--> A4 (repos, endpoints, commits) --+
```

### Stage 2 — Analyse and Understand

```
SQLite --> S2 --> agent reads artefacts via read tier
                        |
                        v
             agent reasons: features, journeys, rules
                        |
                        v
            analysis_upsert  -->  S2  -->  D1 validate  -->  P1
                        ^
Playwright MCP ---------+  (agent explores live AUT, supplies UI model)

A4 endpoints --> S2.derive_api_model --> P1     (toolchain-derived, no agent)
```

### Stage 3 — Identify Testable Requirements

```
SQLite --> agent reasons requirements --> requirements_upsert --> S3
                                                                   |
                                    +------------------------------+
                                    v
                         D7 atomicity --> D6 risk --> D3 Jira key
                                    |                      |
                                    v                      v
                                   P1                  gap set (if unresolvable)
```

### Stage 4 — Establish Coverage Baseline

```
P1 requirements --> S4 --> D2 derive --> D2 depth --> D2 yield --> P1 model
                                                          |
                                                          v
                                              coverage_forecast (read tier)
                                                          |
                                                          v
                                        Test Lead --> coverage_approve --> P1 approval
```

### Stage 5 — Generate Test Cases

```
agent reasons cases for one feature
        |
        v
testcases_upsert --> S5 --> S10.is_gate_open?  --(closed)--> REJECTED_GATE_CLOSED
                             |
                          (open)
                             v
                    D7 --> D3 --> D4 --> D6 --> D5
                             |
                     any failure? --> roll back, report ALL failures
                             |
                          (all pass)
                             v
                          P1 commit --> A8 emit views
```

### Stage 6 — Generate Automation

```
P1 cases (automatable only) + UI model + API model
        |
        v
S6 --> detect hand-edits --(found)--> stop and report
        |
     (none)
        v
     A7 Jinja2 render --> reject fixed waits and literal credentials
        |
        v
   TypeScript project files on disk
```

### Stage 7 — Handover

```
S7 --> assemble project --> verify references
                                |
                                v
                       verify tsc compiles
                                |
                                v
                    verify playwright test --list
                                |
                                v
                       produce and reconcile manifest
                                |
                                v
                    READY  (operator pushes manually; Jenkins out of scope)
```

### Delta Path

```
A4 bitbucket_changes + A3 jira updated-since
        |
        v
S9 --> D8 map impact via trace graph --> classify
        |                                    |
        v                                    v
  unmapped changes reported          unchanged / requires-update / obsolete
                                             |
                                             v
                                   re-enter at S3 for affected scope,
                                   subject to the same gates
```

---

## Composition Root

One module wires concrete adapters to protocols at startup. It is the only place in the codebase
that knows both a protocol and its implementation.

```
main()
  |
  +-- X3 ConfigAndSecrets.load()          (fails fast, naming any missing variable)
  +-- X2 StructuredLogger configure
  +-- A1 SqliteSchemaManager.ensure()     (migrate, back up first)
  +-- construct A2 repositories       --> bind to P1
  +-- construct A3, A4, A5, A6        --> bind to P2
  +-- construct A7, A8, A9            --> bind to P3
  +-- construct S1..S10 with bound ports
  +-- M2 ToolRegistry.register(services)
  +-- M1 McpServer.serve(stdio)
```

**Why this matters for testing**: with composition isolated here, every service can be constructed
in a test with in-memory fakes, and every domain component needs no construction at all. That is the
precondition for the property-based suite required under PBT partial mode.
