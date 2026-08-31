# TTO Test Analyst Agent System — `tto-testgen`

The deterministic toolchain behind TAAS, exposed to the GitHub Copilot agent as a
local MCP server.

**What this is.** TAAS is two halves. The *agent layer* is Copilot configuration —
instructions, chat modes, prompt files — where reasoning about requirements happens.
This repository is the other half: the code that owns every fact which must stay
true across thousands of test cases. Identifier allocation, de-duplication, coverage
arithmetic, traceability enforcement, resumable run state.

The split is the design. The model reasons about meaning; deterministic code
guarantees the rest. A rule the model is merely asked to follow erodes over 6,000
cases and many sessions; a rule the storage layer enforces does not.

---

## Requirements

- Python 3.11 or later
- [`uv`](https://docs.astral.sh/uv/)
- VS Code with the GitHub Copilot Agent extension

Runs on macOS, Windows and Linux. No cloud service, no hosted component: all state
is a local SQLite file.

## Install

```bash
git clone <your-bitbucket-url>/tto-testgen.git
cd tto-testgen
uv sync
```

`uv sync` installs from the committed `uv.lock`, so every workstation resolves to an
identical dependency set.

## Configure

```bash
cp .env.example .env
```

Nothing is required by default. TAAS drives two other MCP servers itself for bulk
reads (fetching hundreds of Jira issues through the model's context would be slow
and expensive) — they're vendored inside this repo at `src/tt-atlassian-mcp` and
`src/tt-bitbucket-mcp`, and `.env.example` already points at them.

Neither takes a credential from TAAS:

| Server | How it authenticates |
|---|---|
| `tt-bitbucket-mcp` | It doesn't — it reads git clones already on disk and never contacts Bitbucket's network API at all |
| `tt-atlassian-mcp` | From its own `.env` next to its script, which TAAS never reads |

One-time setup for the Atlassian side only:

```bash
cd src/tt-atlassian-mcp
python3 -m pip install -r requirements.txt
cp .env.example .env   # fill in ATLASSIAN_BASE_URL, ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN
```

See `src/tt-atlassian-mcp/README.md` for the full setup, including corporate proxy
and TLS handling. `ATLASSIAN_READ_ONLY` defaults to `true`; leave it that way.

Everything else has a documented default. Two are business rules rather than
settings:

| Variable | Default | Effect |
|---|---|---|
| `TAAS_SIMILARITY_THRESHOLD` | `0.90` | What counts as a near-duplicate |
| `TAAS_COMMIT_LOOKBACK_DAYS` | `180` | How far back a Jira key may be derived from commits |

Changing either changes the corpus, so the effective values are recorded in run
metadata alongside the results they produced.

## Run

```bash
uv run tto-testgen-mcp
```

The server communicates over stdio and opens no network listener. Register it in
`.vscode/mcp.json` alongside TTO-Atlassian-MCP, TTO-Bitbucket-MCP and Playwright MCP.

## Verify

```bash
uv run pytest                    # full suite
uv run pytest -m benchmark       # performance budgets at 10,000 cases
uv run lint-imports              # hexagonal boundary contracts
```

---

## What the toolchain enforces

These are refusals, not warnings. Each exists because the alternative is a corpus
nobody can trust.

| Rule | Enforced by |
|---|---|
| Every test case has at least one ordered step with an expected result | Domain construction, D7 validation, and a database trigger |
| Every test case resolves to a Jira key that was actually ingested | D3, D7, and a database trigger |
| Identifiers are allocated by the toolchain, never supplied | D5, plus an immutability trigger |
| Near-duplicates are refused | D4, using indexed bucket selection |
| Test data names the equivalence class it represents | Domain construction and a `NOT NULL` constraint |
| Nothing is hard-deleted | No `DELETE` against a business entity exists in any query module |
| Only the Test Lead approves a coverage baseline | `stage_approve` |
| A completed unit is not re-run without an explicit instruction | `unit_begin` |

The two most important rules are enforced twice, in the domain and in the schema.
The validator produces an error the agent can act on; the constraint makes the rule
unbreakable even if a future code path bypasses the validator. Neither alone is
enough: a constraint gives an unhelpful error, and a validator can be forgotten.

---

## Rollback

```bash
git checkout <previous-tag>
uv sync
```

Every release is a git tag. If a schema migration ran since that tag, revert it
first — every forward migration ships a tested reverse, so this is safe:

```bash
uv run python -c "
from tto_testgen.composition import build
from tto_testgen.adapters.sqlite.schema import migrate_down
app = build().value
print(migrate_down(app.connection, target=<version>))
"
```

A backup is taken automatically before any migration.

## Recovery

Backups live in `.taas/backups/` (the newest 10 are retained). Portable exports live
in `generated/exports/`.

Two mechanisms, because they cover different failures. A backup restores
byte-identically but is only readable by a compatible schema version. An export is
JSON Lines per table and survives a database the current code can no longer open.

See [`docs/restore-procedure.md`](docs/restore-procedure.md) for the full procedure
and the rehearsal scenario.

---

## Layout

```
src/tto_testgen/
  domain/        pure logic - no I/O, no dependencies outside stdlib
  ports/         protocol definitions only
  platform/      result types, logging, config, resilience, health
  adapters/      SQLite schema, migrations, repositories, backup
  mcp/           stdio server and the two-tier tool surface
  composition.py the only module that knows both a protocol and its implementation
src/tt-atlassian-mcp/  vendored - the MCP server TAAS drives for Jira and Confluence
src/tt-bitbucket-mcp/  vendored - the MCP server TAAS drives for repository reads
tests/
  unit/          example-based
  properties/    Hypothesis, targets domain/ only
  integration/   adapters against a real SQLite file
  benchmark/     performance budgets, run on demand
  fakes/         in-memory ports, shared by every unit
```

Dependencies point inward. `lint-imports` fails the build if a domain module imports
an adapter — that boundary is what keeps the property suite runnable without a
database, and it erodes silently without a contract to hold it.

## Not in scope

Test execution and Jenkins orchestration. This system generates tests and packages
them; the pipeline runs them. It never pushes to a repository and never writes
Jenkins configuration.
