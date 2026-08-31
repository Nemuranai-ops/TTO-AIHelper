# Tech Stack Decisions — U8 Reporting and Re-baselining

**Phase**: CONSTRUCTION | **Unit**: U8 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-31

---

## Summary

**U8 adds nothing.** Fifth consecutive unit, and the last one.

| Concern | Decision | Source |
|---|---|---|
| Everything inherited | Python 3.11+, `uv`, Pydantic v2, stdlib `sqlite3` | U1 |
| Report aggregation | SQL | stdlib `sqlite3` |
| Markdown rendering | Plain string building | stdlib |
| CSV rendering | `csv` | stdlib |
| Impact classification | **D8**, unchanged | U1 |
| Change detection | The Bitbucket and Jira adapters | U2 |

**Verified, not assumed**: no package was added, and nothing U8 needs is missing from
the four runtime dependencies chosen at U1. The U2 episode — PyYAML documented as
transitive when it is not — is why every unit since has stated the check rather than
reasoning about it.

---

## Final Dependency Position

| | Count | Since |
|---|---|---|
| Runtime | **4** — `mcp`, `pydantic`, `jinja2`, `pyyaml` | U2 |
| Development | **5** — `pytest`, `pytest-benchmark`, `hypothesis`, `import-linter`, `pip-audit` | U1 |

**Five units in a row added nothing.** The stack was chosen once at U1 against the whole
requirement set, and the only additions since were PyYAML at U2 — which was needed and
was initially mis-documented as transitive.

---

## CSV: `csv`, Not String Joining

The traceability matrix is emitted as CSV (FR-RPT-03), and a requirement statement or
case title can contain a comma, a quote or a newline.

`csv.writer` handles all three correctly. Joining with commas would produce a file that
opens in a spreadsheet with the columns silently shifted for exactly the rows whose text
is most interesting — and a shifted traceability matrix is worse than none, because it
looks right.

`lineterminator="\n"` is set explicitly. The default is `"\r\n"`, which would make the
file's bytes depend on nothing observable and break U8-NFR-REL-07's byte-stability on a
platform change.

---

## Markdown: Plain String Building, Not Jinja2

Jinja2 is a dependency and is deliberately not used here, for the same reason U4 gave
for its views.

| | U5 TypeScript | U8 reports |
|---|---|---|
| Read by | A person **and** a compiler | A person |
| Correctness | Byte-identical, or hand-edit detection collapses | Legible and complete |
| Reviewed as | A coding standard | A document |

Reports are byte-stable because nothing time-varying goes into them, not because a
template guarantees it. A template would add nine files to maintain alongside the code
that fills them, for output a function produces more legibly.

**"We already have Jinja2" is a reasonable argument that is wrong twice now**, and the
reason is the same both times: U5 needs templates for *reproducibility of generated
code*, and that requirement does not transfer to a document.

---

## What U8 Does Not Add

| Considered | Why not |
|---|---|
| A charting library | A coverage report is a table. An image cannot be diffed, searched, or read in a terminal |
| A PDF renderer | The reports are pushed to a repository and read in a browser or an editor. PDF would add a dependency and remove diffability |
| An HTML report template | Markdown renders in Bitbucket, in VS Code and in a terminal. HTML renders in one of those |
| A templating pass for CSV | `csv.writer` is correct and complete |
| Caching report output | The corpus changes constantly during a baseline, and a cached coverage figure is the one number that must never be stale |

**The last one is the same objection made at U1, U3 and U4**, and it has hardened each
time. Here it is at its sharpest: a stale coverage figure in a report the Test Lead
signs off is precisely the false confidence this whole system was commissioned to
remove.
