# Business Rules — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

U5 turns approved cases into TypeScript. Every rule here is either a deterministic
transformation or a refusal — there is no judgement left in this unit, because the
judgement was made in U4 when the case was classified.

---

# BR-U5-1: Spec Scoping and File Layout

**Decision**: one spec per feature, one page object per screen.

## BR-U5-1.1 The layout

```
<destination>/
  package.json            pinned @playwright/test version
  playwright.config.ts    HTML + JUnit reporters, env-driven baseURL
  tsconfig.json
  .env.example            every variable the project reads
  README.md               what is generated, what is safe to edit
  fixtures/
    auth.ts               one authentication path, shared by UI and API
  pages/
    <screen-slug>.page.ts one page object per screen
  tests/
    <feature-slug>.spec.ts one spec per feature
```

## BR-U5-1.2 Inside a spec

`test.describe` per coverage item, `test` per case. The describe title names the
coverage item and its technique, so a Jenkins failure report groups by the reason the
cases exist rather than by an arbitrary boundary.

## BR-U5-1.3 Why per feature

| Scoping | Files at 6,000 cases | Problem |
|---|---|---|
| Per case | 6,000 | Unnavigable, and a Jenkins run spends its time on process startup |
| Per coverage item | ~1,200 | Splits a feature across many files for no reviewer benefit |
| **Per feature** | **~150** | **Matches U4's view sharding** |

Matching U4 is the substantive reason rather than a tidiness one: a reviewer opens
`checkout.md` and `checkout.spec.ts` and sees the same cases in the same order, so
comparing what was specified against what was generated is reading, not searching.

## BR-U5-1.4 Slug validation

Feature and screen slugs are validated against `^[a-z0-9][a-z0-9-]*$` before reaching a
path, and refused rather than sanitised — the same rule and the same reasoning as U4's
`ViewRenderer`. Rewriting `../etc` to `etc` writes a file nobody asked for, which is a
different wrong answer rather than a right one.

This also reserves `<project>`, which BR-U5-7 uses for scaffold files: the angle
brackets cannot appear in a real slug.

---

# BR-U5-2: What Is Emitted

**Decision**: `automatable` only. Everything else is reported.

## BR-U5-2.1 The three classifications

| D6 verdict | Test emitted? | Reported? |
|---|---|---|
| `automatable` | Yes | In the manifest |
| `needs-review` | **No** | Yes, with D6's reason |
| `manual-only` | **No** | Yes, with D6's reason |

## BR-U5-2.2 Why `needs-review` produces nothing

`needs-review` means D6 could not decide. Generating a test from an undecided
classification produces a spec the engineer must audit before trusting — and an
unaudited spec that passes is worse than no spec, because it reports coverage that
nobody has confirmed exists.

The alternative considered was `test.fixme()`, which would put the skeleton in front of
the engineer. It was declined because a suite of 6,000 tests containing several hundred
`fixme` entries trains people to filter them out, and the filtered-out set is exactly
the set that needed attention.

## BR-U5-2.3 The two are reported apart

`manual-only` is a decision; `needs-review` is the absence of one. The second is the
actionable half — a case D6 could not judge is usually one missing signal away from
being judged, and merging the lists hides which cases those are (FR-AUT-10).

## BR-U5-2.4 Gaps

Both classes are written to the `gap` table, in the categories U3's migration 004
already declared. U5 introduces no new gap category.

---

# BR-U5-3: Locator Strategy

**Decision**: best available locator, with every unverified one annotated in the code.

## BR-U5-3.1 Order of preference

| Rank | Locator | Condition |
|---|---|---|
| 1 | `getByRole(role, { name })` | The element has an accessible role and name |
| 2 | `getByLabel(label)` | A form control with an associated label |
| 3 | `getByPlaceholder`, `getByText` | Where either uniquely identifies the element |
| 4 | `getByTestId(id)` | A test identifier exists and no semantic locator does |
| 5 | CSS | Last resort, and annotated as fragile |
| — | XPath | **Never generated** |

XPath is excluded rather than ranked last. It is the locator form most sensitive to
structural change, and generating it would guarantee the failure mode R-04 names:
selectors that break on the first UI change, and automation that gets abandoned.

## BR-U5-3.2 Unverified locators are annotated, not withheld

The live-exploration work was deferred from U2, so most locators in the first run carry
`is_verified = false`. Each generated locator built from an unverified element carries a
comment naming it:

```typescript
// UNVERIFIED: derived from the design model, not confirmed against a running
// application. Confirm before relying on this test's result.
readonly submitButton = this.page.getByRole('button', { name: 'Place order' });
```

**Refusing to emit would produce almost nothing on the first run**, which is the run
the baseline exists to produce. Emitting without the distinction would present a guess
as a confirmed fact — which is what `is_verified` was created to prevent (US-ANA-04
AC5). The comment sits where the engineer is actually looking when the test fails.

## BR-U5-3.3 The test is marked at risk

A test whose locators are wholly unverified is stored with `is_at_risk = 1` and the
reason recorded, so the automation report can state how much of the suite rests on
underived evidence without anyone reading the code to find out.

## BR-U5-3.4 Fragile locators

An element flagged `is_fragile` with no alternative recorded produces a CSS locator, an
annotation, and an at-risk mark. U5 does not invent an alternative — deriving a better
locator requires seeing the application, and that is U2's job through Playwright MCP.

---

# BR-U5-4: No Fixed Waits

**Decision**: refuse to generate any fixed delay; use expectations.

## BR-U5-4.1 What is never generated

`page.waitForTimeout`, `setTimeout`, `sleep`, and any hard-coded millisecond delay in a
test body.

## BR-U5-4.2 What replaces them

Playwright's auto-waiting for actions, and `expect(locator).toBeVisible()` /
`toHaveText()` / `toHaveURL()` for state. A step's expected result becomes an
assertion, which is where the wait belongs: the test proceeds when the expected thing
is true, not when a guessed interval has elapsed.

## BR-U5-4.3 Why this is a refusal rather than a preference

A fixed wait is the single most common cause of a suite that is both slow and flaky —
too short and it fails randomly, too long and the suite takes hours. Both failures
erode trust, and a suite nobody trusts gets ignored rather than fixed (FR-AUT-09).

The templates make it structural: there is no template fragment that emits a delay, so
one cannot appear without someone adding it to a reviewed artefact.

---

# BR-U5-5: No Literal Secrets or Environment URLs

**Decision**: refuse the emission, naming the value's location.

## BR-U5-5.1 What is refused

| Refused | Instead |
|---|---|
| A credential, token or API key as a literal | `process.env.TAAS_*`, documented in `.env.example` |
| An environment-specific base URL | `baseURL` from config, from the environment |
| A personal email or phone in test data | Already refused upstream by U4's L9 |

## BR-U5-5.2 Refusal, not redaction

An emission carrying a literal secret is rejected and the file is not written
(US-AUT-05 AC2). Redacting it would produce a project that does not run and does not
say why; rejecting it names the case and the field.

**The generated project is pushed to a Bitbucket repository**, which is where a literal
credential stops being a code-quality problem and becomes a disclosure — the same
reasoning that made U4's personal-data check a rejection rather than a warning.

## BR-U5-5.3 `.env.example` documents every variable

Every variable the generated project reads appears there with a description and no
value. A project whose configuration is discoverable only by running it and reading the
crash is a project the engineer has to reverse-engineer before using.

---

# BR-U5-6: Annotations and Traceability

**Decision**: annotations that survive into JUnit XML.

## BR-U5-6.1 What each test carries

```typescript
test('TC-CHECKOUT-00042 Reject an empty basket', {
  tag: ['@checkout', '@boundary'],
  annotation: [
    { type: 'case', description: 'TC-CHECKOUT-00042' },
    { type: 'jira', description: 'PAY-12' },
    { type: 'coverage', description: 'CI-CHECKOUT-00003' },
  ],
}, async ({ page }) => { ... });
```

## BR-U5-6.2 Tags match the case exactly

Tag annotations are the case's own tags, prefixed with `@`. They are not derived,
extended or tidied: Jenkins selects suites by tag expression, and a tag the generator
invented is one the operator cannot predict (FR-AUT-05, US-AUT-04 AC1).

## BR-U5-6.3 The identifier is in the test title as well as the annotation

Belt and braces, deliberately. Annotations reach the JUnit XML; the title reaches
every report format, including ones nobody has configured yet. **A red test in Jenkins
must carry its own provenance** — the engineer seeing it should not have to query the
database to learn which story it came from (FR-AUT-06, US-AUT-04 AC3).

---

# BR-U5-7: Deterministic Regeneration

**Decision**: byte-identical output, and hand-edits are skipped.

## BR-U5-7.1 What is excluded from generated code

| Excluded | Because |
|---|---|
| Timestamps | Every regeneration would differ, and every file would look hand-edited |
| Run identifiers | Same |
| Absolute paths | They differ per workstation, so two engineers' output would conflict |
| Iteration order that is not explicitly sorted | Dictionary order is not a contract |

Cases are emitted in identifier order, page objects in screen-slug order, and imports
sorted. **Without this the hand-edit detector is worse than useless**, reporting every
file on every run — the same failure U4 designed around, and the same fix.

## BR-U5-7.2 Hand-edit detection

Three outcomes, using U4's mechanism through the generalised `emitted_view` table:

| Outcome | Condition | Action |
|---|---|---|
| `written` | New, or content changed | Written, hash recorded |
| `unchanged` | Recorded hash equals fresh hash | Nothing done |
| `hand_edited` | File on disk differs from its recorded hash | **Skipped**, reported |

Hand-edit is evaluated first, exactly as in U4: a file the engineer edited and that the
corpus also changed is still a hand-edit. **The point of this unit is that the
generated suite is a starting point rather than something the engineer cannot touch**
(US-AUT-06 AC3), and overwriting their work would make it the latter.

## BR-U5-7.3 Scaffold files

`package.json`, `playwright.config.ts`, `tsconfig.json`, `.env.example` and `README.md`
are recorded under the reserved `<project>` slug. They are written once and then behave
exactly like any other generated file — including being skipped once edited, which is
the common case, because tuning `playwright.config.ts` is the first thing an engineer
does.

## BR-U5-7.4 The input hash

Each `automated_test` stores the hash of what it was generated from: the case, its
steps and data, and the locators it used. Two runs producing the same input hash and
different output hashes means the generator is non-deterministic — a fault no amount of
reading the output would reveal, and one FR-AUT-11 forbids.

---

# BR-U5-8: The Emission Sequence

Cheap refusals first, file writes last.

| Stage | Check | Component |
|---|---|---|
| A | Cases gate approved for the feature | U7 L5 |
| A | The feature exists and has cases | S6 |
| B | Per case: classification is `automatable` | S6, BR-U5-2 |
| B | Per case: no literal secret in the rendered values | S6, BR-U5-5 |
| C | Locators resolved and ranked; unverified ones marked | A7, BR-U5-3 |
| D | Render specs, page objects and scaffold | A7 |
| E | Three-way comparison per file | A7, BR-U5-7 |
| F | Record `automated_test` rows and gaps | S6 |

**Stage A stops; B through E collect.** A closed gate makes the whole emission moot. A
single case with a literal secret does not invalidate its neighbours, so every fault is
reported together and one correction pass fixes them — the same shape as U4's batch,
for the same reason.

**Stage F runs last** because a recorded `automated_test` row asserting a spec that was
never written would make the next run believe the file exists.

---

# Rule-to-Requirement Traceability

| Rule | Requirements | Stories |
|---|---|---|
| BR-U5-1 Spec scoping | FR-AUT-01, FR-AUT-02 | US-AUT-01 |
| BR-U5-2 What is emitted | FR-AUT-10 | US-AUT-06 |
| BR-U5-3 Locator strategy | FR-AUT-03 | US-AUT-02 |
| BR-U5-4 No fixed waits | FR-AUT-09 | US-AUT-02 |
| BR-U5-5 No literal secrets | FR-AUT-07, NFR-SEC-10 | US-AUT-05 |
| BR-U5-6 Annotations | FR-AUT-05, FR-AUT-06 | US-AUT-04 |
| BR-U5-7 Deterministic regeneration | FR-AUT-11 | US-AUT-06 |
| BR-U5-8 Emission sequence | FR-AUT-04, FR-AUT-08 | US-AUT-03, US-AUT-05 |
