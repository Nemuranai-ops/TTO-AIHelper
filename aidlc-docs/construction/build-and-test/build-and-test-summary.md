# Build and Test Summary

**Project**: TTO Test Analyst Agent System (TAAS)
**Phase**: CONSTRUCTION | **Stage**: Build and Test
**Version**: 1.0 | **Date**: 2026-08-31

---

## Build Status

| | |
|---|---|
| **Build tool** | `uv` with a committed `uv.lock` |
| **Command** | `uv sync --extra dev` |
| **Status** | ✅ **Success** |
| **Artifacts** | None — editable install; there is no compilation step |
| **Architecture check** | ✅ **5 import contracts kept, 0 broken** |

---

## Test Execution

| Suite | Tests | Result | Time |
|---|---|---|---|
| Unit | 559 | ✅ Pass | ~1.5 s |
| Integration | 263 | ✅ Pass | ~1.3 s |
| Properties | 106 | ✅ Pass | ~30 s warm / ~5 min cold |
| Benchmarks | 23 | ✅ Pass | ~1.5 s |
| **Total** | **951** | ✅ **951 passed, 0 failed, 0 skipped** | **~35 s** |

Coverage percentage is not measured, deliberately — see `unit-test-instructions.md`.
Assurance rests on the import contracts, the properties, and the benchmarks, and the
defects this project actually shipped past review were all in fully covered lines.

---

## Performance

All 23 budgets met. The three that matter most:

| Budget | Target | Measured |
|---|---|---|
| **Full report set, end to end** (NFR-PRF-02) | 30 s | **0.23 s** at 10,000 cases |
| Duplicate selection, crowded bucket | 50 ms | **3.7 ms** against 2,000 candidates |
| Second automation emission | writes zero files | **zero written** |

**NFR-PRF-02 was provisioned at U1 and unexercised for seven units.** U8 is where a
whole report is assembled over a real corpus for the first time.

---

## Security — and the finding this gate produced

| Check | Result |
|---|---|
| Dependency vulnerabilities | ✅ **No known vulnerabilities** *(after remediation)* |
| No untrusted execution | ✅ `subprocess` isolated, contract verified by breaking it |
| Read-only against Atlassian and Bitbucket | ✅ Enforced by absent write methods |
| Personal data and credential screening | ✅ L9, L13, plus two last-line scans |
| Workspace containment | ✅ All output under `.taas/` and `generated/`, both gitignored |

### Seven vulnerabilities were found, in three packages

The pins were chosen at U1 against knowledge current then. By this stage, advisories had
accumulated:

| Package | Was | Advisories | Upgraded to |
|---|---|---|---|
| **`mcp`** | 1.2.1 | **5** | **1.28.1** |
| `jinja2` | 3.1.5 | 1 | 3.1.6 |
| `pytest` | 8.3.4 | 1 | 9.0.3 |

`mcp` is the runtime dependency carrying the entire agent interface, which makes five
advisories there the most serious finding of the build.

Raising `mcp` required raising `pydantic` from 2.10.4 to **2.13.5**, because
`mcp>=1.28` bounds pydantic from below on Python 3.14+. **All 951 tests pass on the new
set and no source change was needed** — which is the useful signal: the pins were stale,
not the code.

**This is what the gate is for.** The scan is documented as a pre-handover step in
`security-test-instructions.md`, because pins that were clean when written do not stay
clean.

---

## Additional Test Categories

| Category | Status | Notes |
|---|---|---|
| Contract tests | **N/A** | Single deployable, not microservices. The import contracts serve the equivalent purpose internally |
| Security tests | ✅ Pass | `security-test-instructions.md` |
| End-to-end tests | **Manual** | `e2e-test-instructions.md` — the path runs through seven human gates and cannot be fully automated |
| Load / stress tests | **N/A** | No server, no concurrent users. Single-writer by design |

---

## Defects Found During Construction

Recorded because the pattern matters more than the individual faults. **Six were found
by property tests and would not have been found by example tests.**

| Defect | Unit | Found by |
|---|---|---|
| `İ` lowercases to `i` + combining dot → uncompilable TypeScript | U5 | Property |
| A bare `\r` splits a Markdown table row | U8 | Property |
| A plus-tagged address escaping the email pattern | U4 | Property |
| Luhn-only card check flagging batch ids | U4 | Example, then hardened by property |
| `with_suffix('.ts')` on `checkout.page` → `checkout.ts` | U6 | A fixture with a realistic filename |
| `executescript()` discarding the enclosing transaction | U1 | Integration |
| SQLite choosing an unselective index | U1 | `EXPLAIN QUERY PLAN` assertion |
| A fake written to match its caller, hiding a signature mismatch | U4 | Reading the port during U8 planning |
| Seven dependency vulnerabilities | Build | `pip-audit` at this gate |

**The last two are the instructive ones.** Both survived a full stage approval, and
neither was found by running tests — one by reading a port, the other by running a scan
that had not been run since U1.

---

## Overall Status

| | |
|---|---|
| **Build** | ✅ Success |
| **All tests** | ✅ 951 passed |
| **Import contracts** | ✅ 5 kept, 0 broken |
| **Performance budgets** | ✅ 23 of 23 met |
| **Security scan** | ✅ Clean after remediation |
| **Ready for Operations** | ✅ **Yes** |

---

## Standing Items Carried Forward

| Item | Status |
|---|---|
| **AS-02** — full-disk encryption assumed on operator workstations | Open since U1. An estate control this system cannot verify; remediation contained to the storage adapters if it does not hold |
| Live locator verification through Playwright MCP | Deferred from U2; locators are emitted unverified and annotated as such |
| Dependency re-scan before each handover | Documented in `security-test-instructions.md` |

---

## Next Steps

**Ready to proceed to the Operations phase.**

The Operations stage is a placeholder in this workflow. For this system it would cover
the operator's own runbook — restoring from `.taas/backups`, rehearsing a migration
rollback, and the pre-handover checklist — of which the first two already exist as
`docs/restore-procedure.md` and `docs/release-checklist.md`.
