# Business Logic Model — U5 Automation Emission

**Phase**: CONSTRUCTION | **Unit**: U5 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

---

## 1. The Orchestration

S6 reads the corpus and hands A7 what to render. It makes no judgement: every decision
about whether a case is automatable was made by D6 in U4.

```
automation_emit(feature_slug, include_scaffold)
        |
   [A] gate: cases approved for this feature? ---- closed ----> REJECTED_GATE_CLOSED
        |                                                       (emission stops)
   [B] partition by classification
        |
        +--> automatable   -> to render
        +--> needs-review  -> not_automated, with D6's reason
        +--> manual-only   -> not_automated, with D6's reason
        |
   [B] per renderable case: no literal secret in any value
        |
   any secret? --- yes ---> refuse, name the case and field, write nothing
        |
       no
        |
   [C] resolve locators per referenced screen, rank, mark unverified
   [D] render: page objects, specs, and scaffold if requested
   [E] per file: written | unchanged | hand_edited
   [F] record automated_test rows, gaps, and the manifest
```

**Why F runs last.** An `automated_test` row asserting a spec that was never written
would make the next run believe the file exists — and the run after that would find a
hash for a file on disk that nobody generated.

---

## 2. Algorithms

### 2.1 Partitioning (BR-U5-2)

```
partition(cases):
    renderable, not_automated = [], []
    for case in cases:
        if case.automatability == AUTOMATABLE:
            renderable.append(case)
        else:
            not_automated.append(
                NotAutomated(case.id, case.automatability, case.automatability_reason)
            )
    return renderable, not_automated
```

D6's reason is carried through unchanged. Rewording it would put a second explanation
of one decision into circulation, and the two would eventually disagree.

### 2.2 Locator selection (BR-U5-3)

```
locator_for(element):
    if element.role and element.accessible_name:
        return Locator(f"getByRole('{element.role}', {{ name: '{name}' }})", rank=1)
    if element.label:
        return Locator(f"getByLabel('{element.label}')", rank=2)
    if element.placeholder or element.text:
        return Locator(..., rank=3)
    if element.test_id:
        return Locator(f"getByTestId('{element.test_id}')", rank=4)
    if element.css:
        return Locator(css, rank=5, fragile=True)
    return None                       # the page object omits it; the case is at risk
```

Ranked, not scored. There is no situation where a CSS selector is preferable to an
accessible role, so a weighting would only obscure a fixed order.

**XPath is absent from the ladder**, not last on it. It is the form most sensitive to
structural change, and generating it would guarantee R-04's failure mode.

### 2.3 The unverified annotation (BR-U5-3.2)

```
render_locator(element):
    locator = locator_for(element)
    if not element.is_verified:
        emit_comment("UNVERIFIED: derived from the design model, not confirmed "
                     "against a running application.")
    if element.is_fragile and not element.alternative_locator:
        emit_comment("FRAGILE: no alternative locator recorded.")
    emit(locator)
```

Both comments are inside the hashed content, so removing one is a hand-edit and is
reported — the same property that protects U4's generated-file banner.

### 2.4 Step rendering (BR-U5-4)

```
render_step(step, page_object):
    action    = action_for(step.action, page_object)     # click, fill, goto
    assertion = expectation_for(step.expected)           # toBeVisible, toHaveText
    return [action, assertion]
```

Every step yields an action and an assertion. **The assertion is the wait**: the test
proceeds when the expected thing is true, not when an interval has elapsed. There is no
template fragment that emits a delay, so a fixed wait cannot appear without someone
adding it to a reviewed artefact.

### 2.5 Secret detection (BR-U5-5)

```
screen_for_secrets(case):
    findings = []
    for datum in case.test_data:
        if looks_like_credential(datum.field_name, datum.value):
            findings.append((datum.field_name, "credential"))
    for value in [case.preconditions, *[s.action for s in case.steps]]:
        if contains_environment_url(value):
            findings.append((value_location, "environment-url"))
    return findings
```

Distinct from U4's L9, and deliberately so. L9 asks *is this a real person's data*;
this asks *is this a secret or an environment-specific value*. A password field with
the value `Passw0rd!` passes L9 correctly — it is nobody's real data — and must still
never be committed as a literal.

### 2.6 Three-way emission (BR-U5-7.2)

Identical in shape to U4's, and reached through the same table:

```
emit_file(path, content, kind, feature_slug):
    fresh    = sha256(content)
    recorded = views.get(path)

    if path.exists() and recorded and sha256(path.read()) != recorded.content_hash:
        return HAND_EDITED
    if recorded and recorded.content_hash == fresh and path.exists():
        return UNCHANGED
    path.write(content)
    views.upsert(path, feature_slug, fresh, kind="automation")
    return WRITTEN
```

**The scaffold is the case that makes this matter.** Tuning `playwright.config.ts` is
the first thing an engineer does to a new project, and a regeneration that reverted it
would be discovered as a mysterious CI failure rather than as a lost edit.

### 2.7 Determinism (BR-U5-7.1)

```
render_spec(feature, cases):
    for case in sorted(cases, key=lambda c: c.id):        # never insertion order
        ...
    imports = sorted(set(collected_imports))              # never set order
```

No timestamps, no run ids, no absolute paths. The regeneration test is direct: render
twice, compare bytes.

---

## 3. The Template Set

A7's templates are a review artefact in their own right — the generated coding standard
lives in them, and an Automation Engineer reviewing this unit reviews these files
rather than the Python that drives them.

| Template | Owns |
|---|---|
| `package.json.j2` | The pinned `@playwright/test` version |
| `playwright.config.ts.j2` | Reporters, env-driven `baseURL`, timeouts, retries |
| `tsconfig.json.j2` | Compiler options |
| `env.example.j2` | Every variable, with a description and no value |
| `README.md.j2` | What is generated, what is safe to edit, how to run |
| `auth.fixture.ts.j2` | **One** authentication path, used by UI and API tests |
| `page-object.ts.j2` | Locators, centrally defined; unverified and fragile comments |
| `spec.ts.j2` | `describe` per coverage item, `test` per case, annotations |
| `api-spec.ts.j2` | `APIRequestContext` tests, same project, same fixture |

**`auth.fixture.ts` is shared rather than duplicated** (US-AUT-03 AC2). Two
authentication paths drift, and the drift surfaces as UI tests passing while API tests
401 — with no obvious cause, because both "work".

---

## 4. Interaction with Other Units

| Unit | Use |
|---|---|
| U1 | `automated_test` and `emitted_view` repositories; `unit_of_work`; identity for `AT-` ids |
| U2 | The UI model — screens, elements, locators, `is_verified`, `is_fragile` |
| U4 | The corpus. **Read only**: U5 writes nothing U4 owns |
| U7 | `is_gate_open` before emission; `stage_approve` for the engineer's review |
| U6 | Reads the generated project and assembles the handover. U5 does not package |

**The one-directional flow is load-bearing here.** If the emitter could adjust a
locator it found inconvenient, the UI model and the generated code would disagree — and
the model is what the next run reads, so the improvement would be silently lost and
then silently re-applied every time.

---

## 5. Property Surface

| Property | Statement |
|---|---|
| PBT-U5-1 | Rendering the same cases twice produces identical bytes |
| PBT-U5-2 | Output is independent of input order |
| PBT-U5-3 | No rendered file contains `waitForTimeout`, `setTimeout` or a literal delay |
| PBT-U5-4 | No rendered file contains an XPath locator |
| PBT-U5-5 | Every emitted test's tags equal its case's tags |
| PBT-U5-6 | Every emitted test names its case id and Jira key |
| PBT-U5-7 | A case that is not `automatable` never produces a test |
| PBT-U5-8 | Every unverified locator carries its annotation |
| PBT-U5-9 | Generated TypeScript contains no literal from the credential pattern set |
| PBT-U5-10 | A locator is always the highest-ranked form the element supports |

**PBT-U5-3 and -4 are the ones example tests would miss.** A fixed wait or an XPath
selector reaching the output would come from a template branch nobody exercised —
precisely the branch a hand-written case does not cover, because the person writing it
is thinking about the path they just built.

---

## 6. Story Coverage

| Story | Rules | Algorithms |
|---|---|---|
| US-AUT-01 | BR-U5-1 | §3 template set |
| US-AUT-02 | BR-U5-3, BR-U5-4 | §2.2, §2.3, §2.4 |
| US-AUT-03 | BR-U5-1, BR-U5-8 | §3 `api-spec`, shared fixture |
| US-AUT-04 | BR-U5-6 | §3 `spec.ts.j2` |
| US-AUT-05 | BR-U5-5 | §2.5, §3 config and env templates |
| US-AUT-06 | BR-U5-2, BR-U5-7 | §2.1, §2.6, §2.7 |

**All 6 U5 stories are covered.**
