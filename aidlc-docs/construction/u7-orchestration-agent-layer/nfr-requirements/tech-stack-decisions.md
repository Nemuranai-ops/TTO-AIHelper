# Tech Stack Decisions — U7 Orchestration and Agent Layer

**Phase**: CONSTRUCTION | **Unit**: U7 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-29

---

## Summary

**U7 adds no dependency.** The stack fixed at U1 covers this unit entirely.

| Concern | Decision | Source |
|---|---|---|
| Language | Python 3.11+ | U1 |
| Dependency management | `uv` with `uv.lock` | U1 |
| Validation | Pydantic v2 | U1 |
| Database | stdlib `sqlite3` | U1 |
| Testing | pytest, Hypothesis | U1 |
| Agent Layer format | Markdown with YAML front-matter | This unit |
| MCP registration format | JSON | VS Code convention |

Adding nothing is the right outcome and worth stating plainly rather than leaving to
inference. U7 is service logic plus configuration files; neither needs a library the
foundation does not already carry.

---

## Agent Layer Formats

These are the only formats this unit introduces, and both are dictated by the tools
that consume them.

### Chat modes and instructions: Markdown with YAML front-matter

```markdown
---
description: Generate test cases for one feature
tools: ['tto-testgen/testcases_upsert', 'tto-testgen/views_emit', ...]
---

# Cases Mode
...
```

**Parsing**: front-matter is read with the standard-library-safe YAML loader already
required by NFR-SEC-05. The consistency checks in U7-NFR-MNT-01 to -07 parse these
files, so they must be machine-readable as well as human-editable — which is exactly
what front-matter plus prose gives.

**Constraint**: the `tools` list is the machine-checked surface. The prose beneath it
is for the model and the reader, and is not asserted beyond the four standing rules
in the repository instructions.

### Path-scoped instructions: `applyTo` glob

```markdown
---
applyTo: 'generated/playwright-suite/**/*.ts'
---
```

Every such file must declare a glob (U7-NFR-MNT-07). A file without one applies
nowhere and is silently inert — precisely the failure a build-time check should
catch, since nothing at runtime would report it.

### MCP registration: JSON

`.vscode/mcp.json`, per VS Code's format. Credentials are referenced by environment
variable name, never by value, which is what makes the file safe to commit — and
committing it is the point, since every operator needs the same registration.

---

## Testing the Agent Layer

The consistency checks are ordinary pytest tests in `tests/unit/`, not a bespoke
linter. They import the tool registry and parse the mode files, so they fail in the
same run and the same way as everything else.

| Check | Failure mode it prevents |
|---|---|
| Tool exists in registry | A mode offers a tool that was renamed or never registered |
| Tool appears in some mode | A tool is registered but unreachable by the operator |
| Universal reads present | A mode cannot check its own gate |
| No file-write tool | FR-AGT-06 erodes silently as modes are edited |
| Stage name valid | A mode serves a stage that does not exist |
| Standing rules present | An edit removes a rule the whole design depends on |

**Choosing pytest over a separate linter** keeps one command and one report. A
check that needs remembering to run is a check that stops being run.

---

## Rejected Alternatives

| Alternative | Why rejected |
|---|---|
| Generating chat modes from the registry | Removes drift entirely, but the modes lose their hand-written prose — and that prose is what tells the model how to behave in that stage, which is most of their value |
| A YAML schema validator for mode files | Another dependency and another format to learn, for checks that are seven assertions in pytest |
| Storing mode definitions in the database | They are version-controlled configuration that must be readable in a diff; a database would make review harder for no gain |
| A dedicated Agent Layer linter binary | One more thing to install, and one more thing to forget to run |
