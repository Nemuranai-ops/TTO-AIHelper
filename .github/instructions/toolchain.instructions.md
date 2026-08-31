---
applyTo: 'src/tto_testgen/**/*.py'
---

# TAAS Toolchain

## Hexagonal boundaries

`domain/` imports nothing outside the standard library and `domain`. Services depend
on protocols in `ports/`, never on a concrete adapter. `composition.py` is the only
module permitted to know both sides.

`lint-imports` fails the build on a violation. That contract is what keeps the
property suite runnable without a database — the moment the domain needs one, the
invariants stop being cheap to verify and quietly stop being verified.

## SQL

Parameterised only. No f-string, no concatenation, no `.format()` in any query path.
All statements live in `adapters/sqlite/queries/`.

No `DELETE` against a business entity. Deletion is soft: mark obsolete with a reason
and the change event that caused it.

## Errors

Return `Result`, do not raise across a boundary. `REJECTED_*` means the caller must
fix its input; `FAILED_*` means the system had a problem. Every failure carries
remediation text the agent can act on.

## Secrets

Credentials are `SecretStr`. Never log one, never serialise one, never put one in an
error message. Every message crossing the MCP boundary passes through `sanitise`.

## Tests

Domain logic gets property tests, not only examples. Assert mechanisms, not just
outcomes: `EXPLAIN QUERY PLAN` catches a bad index at its cause, where a timing test
would pass on a small corpus and fail mysteriously at volume.
