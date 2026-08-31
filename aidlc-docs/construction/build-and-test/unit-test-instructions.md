# Unit Test Execution

**Project**: TTO Test Analyst Agent System (TAAS)
**Version**: 1.0 | **Date**: 2026-08-31

---

## Run Everything

```bash
uv run pytest tests/
```

**Expected**: `951 passed`. There are no skipped tests and no expected failures.

---

## The Four Suites

| Suite | Tests | Time | What it proves |
|---|---|---|---|
| `tests/unit` | **559** | ~1.5 s | Domain rules and adapters in isolation |
| `tests/integration` | **263** | ~1.3 s | Services against a real SQLite database |
| `tests/properties` | **106** | ~30 s warm, **~5 min cold** | The invariants, over generated input |
| `tests/benchmark` | **23** | ~1.5 s | Every performance budget |

### Run one suite

```bash
uv run pytest tests/unit          # fastest feedback while editing
uv run pytest tests/integration
uv run pytest tests/properties
uv run pytest tests/benchmark -m benchmark
```

### The fast loop

```bash
uv run pytest tests/ -m "not benchmark"
```

**928 passed, 23 deselected.** Use this while working; run the benchmarks before a
commit that touches a query, a renderer or a batch path.

---

## Why the property suite is slow on a first run

Hypothesis keeps an example database under `.hypothesis/`. A **cold** run explores from
scratch and takes around five minutes; a warm one reuses known-interesting examples and
takes about thirty seconds.

**Do not treat the cold run as a hang.** During U6's build a five-minute shrink of a
counterexample was mistaken for one — Hypothesis was working, and the counterexample it
produced (`"\\"`) was a genuine finding.

`.hypothesis/` is gitignored, so CI always runs cold. Budget five minutes there.

---

## What the Property Suite Is For

106 properties, and six of them found defects no example test would have:

| Found | Where | Why an example would have missed it |
|---|---|---|
| `İ` lowercases to `i` + a combining dot, producing uncompilable TypeScript | U5 L12 | Nobody puts a Turkish dotted capital I in a fixture |
| A bare `\r` splits a Markdown table row | U8 L16 | Nobody puts a carriage return in a fixture |
| A plus-tagged address escaping the email pattern | U4 L9 | The author tests the pattern they just wrote |
| `"\\"` breaking a quote-counting heuristic | U5 L11 | The heuristic looked obviously right |

**Run them before believing a change is safe.** They are the slowest part of the suite
and the part that finds what review does not.

---

## Coverage

Line coverage is **not** measured, and that is deliberate.

The project's assurance comes from three things a coverage percentage does not capture:

| Mechanism | What it guarantees |
|---|---|
| **5 import contracts** | The architecture cannot drift |
| **106 properties** | Invariants hold over generated input, not chosen input |
| **23 benchmarks** | Every stated budget is measured, not assumed |

A line-coverage target would be met by exercising lines, and the defects this project
actually shipped past review — a `with_suffix` that replaced instead of appending, a
fake written to match its caller — were all in fully covered lines.

Add coverage measurement if a stakeholder requires the number; do not expect it to
change what the suite finds.

---

## Reading a Failure

### A domain test fails

The rule is in `aidlc-docs/construction/u*/functional-design/business-rules.md`, keyed
by the `BR-` reference in the test's docstring. **Read the rule before changing the
test**: most of these tests encode a decision with a recorded reason, and the reason is
usually the thing that has been forgotten.

### A property fails

Hypothesis prints the falsifying example and a `@seed` to replay it:

```bash
uv run pytest tests/properties/test_u8_properties.py --hypothesis-seed=<seed>
```

`print_blob = true` is set in `pyproject.toml` so the counterexample is reproducible
rather than merely reported.

**Check whether the property or the code is wrong.** Twice in this project the property
was the faulty one, and both times the fix was to assert the real invariant rather than
a heuristic that approximated it.

### An import contract fails

```bash
uv run lint-imports
```

The output names the module and the forbidden import. Do not relax the contract — each
carries a comment saying why it exists.

### A benchmark fails

The assertion message carries the measured figure and the budget. Budgets have wide
margins (the tightest is ~13× headroom), so a failure means something changed
structurally — a query that stopped using an index, or an aggregation moved into Python.

Check `EXPLAIN QUERY PLAN` first: two budget failures in this project were the optimiser
choosing a different index, not the code being slower.
