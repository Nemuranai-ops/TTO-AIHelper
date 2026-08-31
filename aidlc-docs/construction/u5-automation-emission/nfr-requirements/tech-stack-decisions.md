# Tech Stack Decisions — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## Summary

**U5 adds no new Python dependency.** Jinja2 has been declared since U1 and is used for
the first time here.

| Concern | Decision | Source |
|---|---|---|
| Everything inherited | Python 3.11+, `uv`, Pydantic v2, stdlib `sqlite3`, pytest, Hypothesis | U1 |
| TypeScript rendering | **Jinja2 3.1.5** | Already declared |
| JS string escaping | `json.dumps` on the string | stdlib |
| Credential patterns | `re` | stdlib |
| Content hashing | `hashlib.sha256` | stdlib |
| Generated project runtime | `@playwright/test` — **not a Python dependency** | The emitted `package.json` |

---

## Jinja2 Is a Direct Dependency — Verified

Checked rather than assumed. `mcp`, `pydantic` and `pyyaml` were each inspected and
none of them requires Jinja2:

```
mcp      -> no jinja2
pydantic -> no jinja2
pyyaml   -> no jinja2
```

It is declared explicitly in `pyproject.toml` and resolves to 3.1.5, bringing
MarkupSafe 3.0.3 with it.

**This check exists because of U2.** PyYAML was documented as arriving transitively
through the MCP SDK; it does not, and the claim went into an approved document before
anyone ran the command. Every unit since has verified the dependency graph rather than
reasoning about it, and this is that verification for U5.

---

## Why Jinja2 Here, When U4 Declined It

U4 rendered its Markdown and YAML views with plain string building and recorded the
reasoning. The requirement is genuinely different:

| | U4 views | U5 TypeScript |
|---|---|---|
| Read by | A person, in an editor | A person **and** a compiler |
| Correctness | Legible and complete | **Byte-identical across runs** |
| Structure | A dozen lines | Nine distinct file shapes |
| Reviewed as | Documentation | **A coding standard in its own right** |

The last row is the deciding one. The Automation Engineer reviewing this unit reviews
the templates, not the Python that drives them — and a standard expressed as string
concatenation inside a service is a standard nobody will read.

**Autoescape is off, deliberately.** Jinja2's HTML escaping would corrupt TypeScript.
Escaping is applied per value through `json.dumps`, which produces a correctly quoted
JS string literal for any Python string, including one containing quotes, newlines or
backslashes. That is a narrower and more accurate tool than a template-wide HTML
escaper, and U5-NFR-SEC-06 depends on it being the right one.

---

## The Pinned Playwright Version

The generated `package.json` pins `@playwright/test` to an exact version. It is not a
range.

**Version drift between the generator and the Jenkins agent is the classic source of
"passes locally, fails in CI"** — and it was the argument that shaped the packaging
decision at requirements time (Clarification Question 2). The user chose a pure
Playwright project pushed to Bitbucket rather than a Docker image, which means the
browser binaries are the agent's responsibility rather than the artefact's. Pinning the
library version is the part U5 can control, and stating the version in the README is
how the agent's browser install can be matched to it.

| Emitted | Value | Why exact |
|---|---|---|
| `@playwright/test` | Pinned, stated in the README | Browser API changes between minors |
| `typescript` | Pinned | Compiler strictness changes between minors |
| `@types/node` | Pinned | Matches the Node the agent runs |

The version is configuration, not a literal in a template, so raising it is a config
change and a regeneration rather than a template edit.

---

## What U5 Does Not Add

| Considered | Why not |
|---|---|
| A TypeScript formatter (Prettier) as a Python dependency | It is a Node tool. The templates emit already-formatted code, and determinism requires the formatting to be ours rather than a tool's version-dependent output |
| A JS/TS parser to validate generated syntax | It would validate the output against a second implementation of TypeScript. The properties in `nfr-requirements.md` assert the specific things that matter; syntactic validity is caught the first time anyone runs the project |
| `black`/`ruff` for the Python | Not introduced here. It is a project-wide decision, and U5 is not the place to make it unilaterally |
| Docker, for reproducible browsers | Explicitly declined by the user at requirements time in favour of a pure Playwright project |

---

## Dependency Count

Unchanged: **4 runtime, 5 development.** U5 is the third consecutive unit to add
nothing, which is the intended outcome of having chosen the stack once at U1 rather
than per unit.
