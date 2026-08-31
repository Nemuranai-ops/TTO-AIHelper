# Security Test Instructions

**Project**: TTO Test Analyst Agent System (TAAS)
**Version**: 1.0 | **Date**: 2026-08-31

The Security Baseline extension is **enabled with blocking constraints**, so this is a
gate rather than a report.

---

## 1. Dependency Vulnerability Scan

```bash
uv run pip-audit
```

**Expected**: `No known vulnerabilities found`.

### This gate caught seven vulnerabilities at first run

The pins were chosen at U1 against knowledge current then. By the Build and Test stage,
advisories had accumulated:

| Package | Was | Advisories | Now |
|---|---|---|---|
| `mcp` | 1.2.1 | **5** | **1.28.1** |
| `jinja2` | 3.1.5 | 1 | **3.1.6** |
| `pytest` | 8.3.4 | 1 | **9.0.3** |

`mcp` is the runtime dependency carrying the entire agent interface, which makes five
advisories there the most serious finding of the build.

Upgrading `mcp` required raising `pydantic` from 2.10.4 to **2.13.5**, because
`mcp>=1.28` bounds pydantic from below on Python 3.14+. All 951 tests pass on the new
set, and no source change was needed.

**Re-run this scan before every handover.** Pins that were clean when written do not
stay clean.

### When a vulnerability is found

1. Read the advisory. Not every one is reachable from this codebase.
2. Upgrade to the stated fix version, exactly pinned.
3. If an exact pin will not resolve, relax it to a range, let `uv sync` choose, then
   **pin that version back**. A range left in place reintroduces the drift the pins
   exist to prevent.
4. Run the full suite. A dependency upgrade that breaks a test is information.

---

## 2. Secrets and Personal Data

Three layers, each in the codebase rather than in a checklist.

### L9 `PersonalDataDetector` — before a case is stored

```bash
uv run pytest tests/unit/test_domain_privacy.py tests/properties/test_u4_properties.py
```

Five patterns: email, phone, national insurance, social security, card number. A card
check requires **both** a Luhn-valid number and an issuer digit of 2–6, because roughly
one arbitrary digit string in ten passes Luhn and a 15-digit batch id is not a card.

### L13 `SecretScanner` — before TypeScript is written

```bash
uv run pytest tests/unit/test_domain_secrets.py
```

Field-name signals plus value shapes. **Distinct from L9 and deliberately so**: a
password field holding `Passw0rd!` passes L9 correctly — it is nobody's real data — and
must still never be committed.

### The last-line scans — before anything leaves

| Where | Runs |
|---|---|
| U6 structural verification | L13 over the assembled project |
| U8 report emission | L9 **and** L13 over rendered reports |

Both catch what arrived by a path the upstream check does not cover, which after U5 is
only a hand-edit.

---

## 3. No Untrusted Execution

```bash
uv run lint-imports
grep -rn "eval(\|exec(\|__import__" src/tto_testgen/ | grep -v "^Binary"
```

**Expected**: 5 contracts kept, and no `eval`/`exec` in application code.

| Control | Enforced by |
|---|---|
| `subprocess` in exactly one module | **Import contract**, verified by breaking it |
| No shell | `shell=False` in that one module; the port takes a sequence, not a string |
| No interpolation into an argv | Every argument is a literal; property-asserted |
| Dependency lifecycle scripts do not run | `npm ci --ignore-scripts` |
| Case content is data, never code | `json.dumps` escaping at every template interpolation |

**The `subprocess` contract was verified by violating it**, not by observing it pass. A
probe module importing `subprocess` was added, the linter reported
`4 kept, 1 broken`, and the probe was removed. A contract that passes because nothing
violates it would also pass if misconfigured.

---

## 4. Read-Only Posture Against External Systems

```bash
uv run pytest tests/unit/test_ports_readonly.py
```

C-05 and C-06 — read-only against Atlassian and Bitbucket — hold because **the source
protocols in `ports/sources.py` declare no write method**. The capability is absent, so
it cannot be misused by a later change that forgets the rule.

The same pattern appears four times: source protocols, `RunStateService` without
`next_unit()`, `HandoverService` without `push`, and `DeltaService` without any method
that creates a requirement or a case.

---

## 5. Workspace Containment

```bash
uv run pytest tests/integration/test_composition.py -k workspace
```

Everything written stays under the workspace root: `.taas/` for the database and
backups, `generated/` for views, automation and reports. Both are gitignored.

Feature and screen slugs are validated against `^[a-z0-9][a-z0-9-]*$` before reaching a
path and **refused rather than sanitised** — rewriting `../etc` to `etc` writes a file
nobody asked for, which is a different wrong answer rather than a right one.

---

## 6. Secret Handling

```bash
uv run pytest tests/unit/test_platform_config.py
```

Credentials are held in `SecretStr`, whose `__repr__`, `__str__` and f-string forms all
redact — the realistic accident being an f-string in a log line. Error messages pass
through `sanitise`, which strips paths outside the workspace, stack-trace lines and
secret-shaped text.

**Subprocess output is sanitised too**, which is the one place foreign text enters:
`npm` reports registry URLs, a proxy failure can carry an `Authorization` header, and
`tsc` reports absolute paths naming the operator's home directory.

---

## Standing Assumption

**AS-02**, open since U1 and unchanged: full-disk encryption is assumed to be enforced
on operator workstations. The corpus is a plain SQLite file, and the assumption is
recorded rather than verified because it is an estate control this system cannot check.

If it does not hold, remediation is contained to the storage adapters — the corpus is
the only thing at rest.

---

## Not Covered

| Not done | Why |
|---|---|
| Penetration testing | There is no network service to test |
| Authentication testing | TAAS has no users; it runs as the operator |
| SAST beyond the import contracts | Available and not currently configured |
| Scanning the *generated* Playwright project's dependencies | It has its own lockfile; the receiving team's CI should audit it |

**The last row is a real handover boundary.** TAAS pins the Playwright version it emits
and cannot audit the tree that resolves from it on the Jenkins agent.
