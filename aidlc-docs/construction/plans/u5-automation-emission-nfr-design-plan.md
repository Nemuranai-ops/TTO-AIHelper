# NFR Design Plan — U5 Automation Emission

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: NFR Design
**Created**: 2026-08-30T14:12:00Z
**Status**: APPROVED 2026-08-30 — all recommendations accepted

---

## What U5 inherits

41 patterns across five units. U5 leans hardest on U4's, because U4 solved the same
problem one layer up.

| Inherited | Use in U5 |
|---|---|
| P-U4-04 Three-outcome emission | Every generated file, through the same table |
| P-U4-01 Deferred allocation | `AT-` identifiers, allocated after every refusal |
| P-RES-01 Unit of Work | One transaction per emission |
| P-SEC-01 Two-level validation | Pydantic at the boundary, refusals beneath |
| P-SEC-03 Message sanitisation | A refusal names a field, never a secret's value |
| P-U7-02 Read-only gate evaluation | Before emission |
| P-MNT-02 Import contracts | Enforce that U5 holds no classification logic |

**Three questions.**

---

# Questions

Fill in each `[Answer]:` tag. Options marked **(Recommended)** carry my analysis.
Tell me when done.

## Question 1 — Security: where the TypeScript escaping lives

U5-NFR-SEC-06 requires every interpolated value to be a correctly quoted JS literal.

A) **A Jinja2 filter, registered once on the environment and applied in the templates
at every interpolation point** — `{{ case.title | ts }}`. **(Recommended — the escape
is then visible at the point of use, so a reviewer reading a template can see which
values are escaped and a missing filter is a visible omission rather than an invisible
one)**

B) **Escape in the service** before values reach the template. The templates stay
plain, and a value can be escaped twice or not at all with nothing in the template
showing which.

C) **A wrapper type** that renders escaped. Impossible to misuse, and it puts a custom
type between the domain objects and the templates that every template author must know
about.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — a `ts` Jinja2 filter applied at every interpolation point (accepted via "Accept all recommendations")

## Question 2 — Reliability: how the template environment is configured

Jinja2's defaults are tuned for HTML and for convenience, neither of which suits
generated code.

A) **A single explicitly-configured environment**: `autoescape=False`,
`undefined=StrictUndefined`, `trim_blocks` and `lstrip_blocks` on, `keep_trailing_newline`
on, templates loaded from package data. **(Recommended — `StrictUndefined` is the
important one: a typo in a template name silently renders empty by default, producing
a spec missing a locator that still compiles)**

B) **Jinja2 defaults** with autoescape off. Fewer decisions, and an undefined variable
renders as nothing.

C) **Pre-render validation** of the context against a schema per template. Catches the
same class earlier, and it means maintaining a schema per template alongside the
template.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — one explicitly-configured environment with `StrictUndefined` (accepted via "Accept all recommendations")

## Question 3 — Logical Components: what U5 needs

A) **Three: `LocatorResolver`** (the ranked ladder, the unverified and fragile marks),
**`SecretScanner`** (field names and value shapes), and **`TemplateEnvironment`** (the
configured Jinja2 environment and the `ts` filter). **(Recommended — the first two hold
policy that will change as the team learns; the third holds configuration that must be
identical everywhere and is the natural home for the escape filter)**

B) **Two** — fold `TemplateEnvironment` into the emitter, since only the emitter
renders.

C) **Four** — add a `ProjectScaffold`, though the scaffold is nine templates and a
destination path, which the emitter already has.

X) Other (please describe after [Answer]: tag below)

[Answer]: A — three components: L11 TemplateEnvironment, L12 LocatorResolver, L13 SecretScanner (accepted via "Accept all recommendations")

---

# Execution Checklist

## Phase 1: Pattern Selection

- [x] 1.1 Record which inherited patterns U5 uses
- [x] 1.2 Specify the escaping pattern per Question 1
- [x] 1.3 Specify the template environment pattern per Question 2
- [x] 1.4 Specify the determinism pattern and its three exclusions
- [x] 1.5 Specify the ranked-resolution pattern
- [x] 1.6 Record patterns considered and declined
- [x] 1.7 Map every pattern to the U5 NFR it delivers
- [x] 1.8 Write `nfr-design-patterns.md`

## Phase 2: Logical Components

- [x] 2.1 Define the components chosen in Question 3
- [x] 2.2 Define responsibilities, interfaces and the pattern set
- [x] 2.3 Place them within the hexagonal rings
- [x] 2.4 Define configuration additions
- [x] 2.5 Verify no new component violates the dependency rule
- [x] 2.6 Write `logical-components.md`

## Phase 3: Validation

- [x] 3.1 Verify all 28 U5 NFR requirements have a delivering pattern or component
- [x] 3.2 Verify U5 holds no copy of a domain algorithm
- [x] 3.3 Verify Security and Resiliency compliance at design level
- [x] 3.4 Validate content per `common/content-validation.md`
- [x] 3.5 Update `aidlc-state.md` and log in `audit.md`

---

# Mandatory Artifacts

- [x] `.../u5-automation-emission/nfr-design/nfr-design-patterns.md`
- [x] `.../u5-automation-emission/nfr-design/logical-components.md`
