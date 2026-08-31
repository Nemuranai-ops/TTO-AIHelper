# Logical Components — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

Three components: **L11 TemplateEnvironment**, **L12 LocatorResolver**, **L13
SecretScanner**.

---

## Why Three

| Considered | Decision |
|---|---|
| **L11 TemplateEnvironment** | **Added** — configuration that must be identical everywhere, and the home of the `ts` filter |
| **L12 LocatorResolver** | **Added** — the ranked ladder and the at-risk marks, both policy |
| **L13 SecretScanner** | **Added** — a pattern set that will change as the team learns |
| `ProjectScaffold` | Declined — nine templates and a destination path, which A7 already holds |
| `SpecBuilder` | Declined — the templates build the spec; a builder would duplicate them in Python |
| `AnnotationFormatter` | Declined — three fields into a template |

The test is the one U3 settled on and every unit since has applied: **a component earns
its place by holding state, enforcing a boundary, or having a lifetime.**

L11 has a lifetime — built once, compiled templates cached inside it. L12 and L13 each
enforce a boundary: one decides what a locator may be, the other what a value may
contain. The three declined candidates hold none of the three, and each would have been
a place for template logic to be quietly reimplemented in Python.

**`SpecBuilder` is the one that would have done real damage.** A builder assembling
spec structure in Python would put half the generated coding standard outside the
templates — and the templates are what the Automation Engineer reviews. The standard
would then live in two places, one of them unreviewed.

---

## L11: TemplateEnvironment

**Ring**: Adapter | **Delivers**: U5-NFR-REL-01, -02, U5-NFR-SEC-06, U5-NFR-MNT-01 to -04
**Patterns**: P-U5-01, P-U5-02

### Responsibility

Own the single configured Jinja2 environment, register the `ts` filter, and render a
named template against a context. Nothing else — no file writing, no decisions about
what to render.

### Interface

```
render(template_name: str, **context) -> str
template_names() -> list[str]
```

### Configuration, and why each setting

| Setting | Value | Reason |
|---|---|---|
| `loader` | `PackageLoader` | A filesystem path resolves differently by working directory |
| `autoescape` | `False` | HTML escaping corrupts TypeScript |
| `undefined` | `StrictUndefined` | **A typo renders empty and still compiles** |
| `trim_blocks` | `True` | Fixes block whitespace, so a reformatted template renders identically |
| `lstrip_blocks` | `True` | Same |
| `keep_trailing_newline` | `True` | An editor stripping a final newline would otherwise change every hash |

`StrictUndefined` is the one worth defending. Jinja2's default renders a missing
variable as the empty string, so `getByRole('button', { name: '{{ nmae }}' })` produces
a locator matching nothing — **that compiles and passes review**, and fails as a
confusing CI error weeks later. Strict mode turns it into a render-time exception
naming the template and the variable.

### The `ts` filter

```
ts(value) -> str        # json.dumps(str(value), ensure_ascii=False)
```

Registered here rather than defined per template, so there is one implementation and
one place to fix it. Applied at every interpolation point in the templates, where a
reviewer can see it (P-U5-01).

### Property surface

| Property | Statement |
|---|---|
| PBT-U5-A | `ts` produces a valid JS string literal for any string, including quotes, newlines and backslashes |
| PBT-U5-B | A template referencing an undefined variable raises rather than rendering empty |
| PBT-U5-C | Rendering the same template with the same context twice produces identical bytes |

---

## L12: LocatorResolver

**Ring**: Domain | **Delivers**: U5-NFR-PRF-04, U5-NFR-MNT-02, -04 | **Pattern**: P-U5-04

### Responsibility

Turn a UI element into the highest-ranked Playwright locator it supports, and say
whether the result is verified and whether it is fragile.

### Interface

```
resolve(element) -> ResolvedLocator | None
rank_of(element) -> int
```

`None` means no locator is available — the page object omits the element and the case
is marked at risk. Pure: an element in, a value out, no I/O.

### `ResolvedLocator`

| Field | Meaning |
|---|---|
| `expression` | The Playwright call, e.g. `getByRole('button', { name: 'Place order' })` |
| `rank` | 1–5, for reporting which strategies the suite rests on |
| `is_verified` | Carried from the UI model, never inferred |
| `is_fragile` | True for rank 5, or where U2 flagged it |
| `annotations` | `UNVERIFIED`, `FRAGILE` — rendered as comments inside the hashed content |

### The ladder

| Rank | Form | Condition |
|---|---|---|
| 1 | `getByRole(role, { name })` | Accessible role and name present |
| 2 | `getByLabel(label)` | A labelled form control |
| 3 | `getByPlaceholder` / `getByText` | Either uniquely identifies the element |
| 4 | `getByTestId(id)` | A test id exists and no semantic locator does |
| 5 | CSS | Last resort, always fragile |
| — | XPath | **Not in the ladder** |

**XPath's absence is the enforcement.** Ranking it sixth would still generate it
whenever nothing else existed. Omitting it means the element is dropped and the case
marked at risk, which is the honest signal: an element with no role, no label, no text
and no test id is one the application should expose better, and a generated XPath would
hide that behind a selector that breaks on the first refactor.

### Placement in the domain

`resolve` takes an element record and returns a value. It holds the ranking policy,
which is a rule about what makes a good locator — not a rendering concern. Keeping it in
the domain makes PBT-U5-10 testable without a template or a database.

### Property surface

| Property | Statement |
|---|---|
| PBT-U5-10 | A locator is always the highest-ranked form the element supports |
| PBT-U5-4 | No resolved locator is an XPath expression |
| PBT-U5-8 | Every locator from an unverified element carries its annotation |

---

## L13: SecretScanner

**Ring**: Domain | **Delivers**: U5-NFR-SEC-01, -02 | **Pattern**: P-U4-03 (the shape)

### Responsibility

Decide whether a value that is about to be rendered into TypeScript is a credential or
an environment-specific URL. Pure, like L9 before it.

### Interface

```
scan_value(field: str, value: str) -> SecretFinding | None
scan_case(case) -> list[SecretFinding]
```

### `SecretFinding`

| Field | Meaning |
|---|---|
| `field` | Where — step ordinal and data key |
| `kind` | `credential-field`, `token-shape`, `private-key`, `connection-string`, `environment-url` |
| `remedy` | The environment variable to use instead |

**The value is never in the finding.** A refusal that quotes the offending secret
copies it into the log, and the log may be shipped with the handover — so the control
that keeps credentials out of the repository would put them into the audit trail
instead. L9 established this; L13 inherits it (P-SEC-03).

### Two signals

| Signal | Catches |
|---|---|
| **Field name** — `password`, `passwd`, `token`, `secret`, `apikey`, `api_key`, `authorization`, `credential`, `private_key` | `password: "hunter2"` — the most likely literal to appear |
| **Value shape** — `Bearer <token>`, `-----BEGIN * KEY-----`, `<scheme>://user:pass@host`, an absolute URL whose host is not `localhost` or a reserved example domain | The case where the field is called something else |

### Why not an entropy threshold

It catches novel formats and fires on hashes, ids, UUIDs and base64 fixtures — all
ordinary test data. **U4 already paid this lesson**: a Luhn-only card check flagged
batch ids until the issuer range was added, and a control that fires on legitimate
input is a control somebody turns off.

### Distinct from L9, deliberately

| | L9 `PersonalDataDetector` | L13 `SecretScanner` |
|---|---|---|
| Asks | Is this a real person's data? | Is this a secret or environment-specific? |
| Runs at | U4, before storage | U5, before rendering |
| `Passw0rd!` | Passes — nobody's real data | **Refused** |
| `alice@customer.co.uk` | **Refused** | Passes — not a credential |

Neither subsumes the other, and merging them would produce one component answering two
questions with one pattern set — which is how a check ends up too broad for one purpose
and too narrow for the other.

---

## Placement

```
domain/     locators.py        <- L12   (pure; ranking policy)
domain/     secrets.py         <- L13   (pure; pattern set)
adapters/   templates.py       <- L11   (Jinja2 environment)
adapters/   playwright_emitter.py <- A7 (rendering + three-outcome emission)
services/   automation.py      <- S6    (orchestration only)
templates/playwright/*.j2      <- the generated coding standard
```

Both domain components import nothing outside the domain, so `domain-is-pure` holds.
L11 and A7 sit in the adapter ring; S6 reaches A7 through the `AutomationEmitter` port
already defined in `ports/emitters.py` since U1.

**The placement is enforced by `.importlinter`, not by review.** A convenience copy of
the locator ladder inside a template helper would break `domain-is-pure` or leave the
domain version unused — and U5-NFR-MNT-05 exists precisely because U5 is the second
unit with a strong temptation to reimplement something U1 owns.

---

## Configuration Additions

| Key | Default | Purpose |
|---|---|---|
| `automation.destination` | `generated/automation` | Project root |
| `automation.playwright_version` | Pinned exact | Emitted into `package.json` |
| `automation.typescript_version` | Pinned exact | Same |
| `automation.max_spec_lines` | 5000 | U5-NFR-SCL-04 warning threshold |
| `secrets.extra_field_names` | empty | Site-specific credential field names |

The two version pins are configuration rather than template literals, so raising
Playwright is a config change and a regeneration — not a template edit that would need
reviewing as a standard change.

---

## Verification

| Check | Result |
|---|---|
| Every U5 NFR requirement has a delivering pattern or component | 28 of 28 |
| No new component violates the dependency rule | Verified against the four import contracts |
| U5 holds no copy of a domain algorithm | L12 and L13 are new policy; A7 renders only |
| Security Baseline | SECURITY-10 via pinned versions; -11 via L13 and P-U5-01; -12 via destination handling. No blocking findings |
| Resiliency Baseline | RESILIENCY-12 via migration 006 reversibility. No blocking findings |
| Property-Based Testing (partial) | 10 U5 properties plus 3 on L11 |
