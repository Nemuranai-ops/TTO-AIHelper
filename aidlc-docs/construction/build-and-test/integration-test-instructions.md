# Integration Test Instructions

**Project**: TTO Test Analyst Agent System (TAAS)
**Version**: 1.0 | **Date**: 2026-08-31

---

## Purpose

Test the interactions between units. **263 tests**, all against a real SQLite database
created per test from the migration chain — never a mock of one.

---

## No Test Environment To Stand Up

There is no `docker-compose up`, no test database to provision, and no service to start.

| Dependency | How the tests handle it |
|---|---|
| SQLite | Created per test in `tmp_path` from migrations 001–007 |
| Atlassian, Bitbucket | Fake source adapters in `tests/fakes/sources.py` |
| Node, npm, npx | `FakeCommandRunner` in `tests/fakes/commands.py` |
| The file system | `tmp_path`, per test |

```bash
uv run pytest tests/integration
```

**Expected**: `263 passed` in about 1.3 seconds.

**Nothing is left behind.** Every test writes into `tmp_path`; no cleanup step is
needed, and a failing test does not poison the next one.

---

## Why the Fakes Are Shared, Not Per-Unit

`tests/fakes/` holds **one fake per port**, used by every unit. Eight independent
in-memory repositories would drift, and the drift would surface only at integration —
which is exactly what contract-first fakes exist to prevent.

**This is not theoretical.** A fake written to match a caller rather than its port hid a
real defect through two full unit approvals: `FakeGapRepository.add` took
`(category, subject, **fields)` while `SqliteGapRepository.add` takes a dict, so U4's
service passed against the fake and raised `TypeError` against SQLite. The docstring
now says: *a fake written to fit its caller is not a stand-in for anything.*

When you add a method to a port, add it to the fake **from the port's signature**, not
from the call site you happen to be writing.

---

## The Unit Interaction Map

| Test file | Interaction proven |
|---|---|
| `test_sqlite_integration.py` | U1: schema, migrations, transactions, triggers |
| `test_agent_layer.py` (unit) | U7: every registered tool is reachable from a chat mode |
| `test_ingestion.py` | U2 → U1: resources to artefacts, partial ingestion |
| `test_u3_services.py` | U3 → U1: requirements, coverage, approval binding |
| `test_u4_generation.py` | U4 → U1, U3, U7: the batch, gates, gaps, views |
| `test_u5_automation.py` | U5 → U4, U2: emission, refusals, hand-edits |
| `test_u6_handover.py` | U6 → U5: assembly, both verification tiers, reconciliation |
| `test_u8_reporting.py` | U8 → all: reports over a real corpus, empty and populated |
| `test_u8_delta.py` | U8 → U1 D8: detection, classification, retirement |
| `test_composition.py` | Every unit: the whole application builds and registers 35 tools |

---

## Key Scenarios, and What They Guard

### The batch is all-or-nothing

`test_a_rejected_batch_stores_nothing_and_allocates_nothing`

A rejected batch must leave the corpus and the identifier sequence untouched. The test
asserts the *next* accepted batch starts at `TC-…-00001`, because a transaction
rollback alone would not prove the sequence had not moved.

### A hand-edited file survives

`test_a_hand_edited_config_survives_regeneration`

Tuning `playwright.config.ts` is the first thing an automation engineer does. A
regeneration that reverted it would surface as a mysterious CI failure rather than as a
lost edit.

### A partial delta run does not advance the baseline

`test_a_partial_detection_does_not_advance_the_baseline`

**The most consequential test in the suite.** Its failure would be permanent and silent:
the next run would compare from the newer head, so every change in the window the failed
source covered would be skipped for ever, and nothing downstream would reveal it.

### A report renders when a section cannot be computed

`test_a_report_on_an_empty_corpus_renders_rather_than_failing`

The period a report is most useful is the one where it has least data.

---

## Running a Single Scenario

```bash
uv run pytest tests/integration/test_u8_delta.py::test_a_partial_detection_does_not_advance_the_baseline -v
```

---

## What Is Not Covered Here

| Not tested | Where it is | Why |
|---|---|---|
| Live Atlassian or Bitbucket | Manual, against a real instance | Credentials and rate limits |
| A real `npm ci` | Manual, or CI with Node | U6 reports `skipped` without Node by design |
| The generated Playwright project executing | Jenkins | Explicitly outside this system's scope |
| The Copilot agent's own behaviour | The chat modes are configuration, not code | `test_agent_layer.py` checks the surface, not the model |

**The last row is the honest limitation.** This suite proves the toolchain is correct.
It cannot prove the agent uses it well — that is what the human gate at each stage is
for.
