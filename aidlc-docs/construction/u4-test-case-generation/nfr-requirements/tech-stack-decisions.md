# Tech Stack Decisions — U4 Test Case Generation

**Phase**: CONSTRUCTION | **Unit**: U4 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## Summary

**U4 adds nothing.** Checked, not assumed — the U2 episode where PyYAML was claimed to
arrive transitively and did not is why that distinction is now stated each time.

| Concern | Decision | Source |
|---|---|---|
| Everything inherited | Python 3.11+, `uv`, Pydantic v2, stdlib `sqlite3`, pytest, Hypothesis | U1 |
| Markdown view rendering | Plain string building | stdlib |
| YAML view rendering | `yaml.safe_dump` | PyYAML, already a dependency from U2 |
| Personal-data patterns | `re` | stdlib |
| View content hashing | `hashlib.sha256` | stdlib |

---

## View Rendering

### Markdown: plain string building, not Jinja2

Jinja2 is already a dependency — U5 needs it for the Playwright emitter, where
FR-AUT-11 demands byte-identical regeneration and a template is the only thing that
guarantees it.

The case views have a different requirement. They are read by humans in an editor, the
format is a dozen lines of structure, and the content is domain data rather than code.
A template would add a file to maintain alongside the code that fills it, for output
that a function produces more legibly.

**The distinction is worth stating** because "we already have Jinja2" is a reasonable
argument that happens to be wrong here: the reason U5 needs templates is
reproducibility of *generated code*, and that reason does not transfer to a Markdown
summary.

Determinism is still required (U4-NFR-MNT-01) and is achieved the same way as
elsewhere: sorted iteration, no timestamps in the body, fixed field order.

### YAML: `yaml.safe_dump`

`sort_keys=True`, `default_flow_style=False`, `allow_unicode=True`.

`safe_dump` rather than `dump` for symmetry with `safe_load`: these files are read back
by the hand-edit check, and a view that could serialise an arbitrary Python object
would be a file the check then has to parse safely anyway.

---

## Personal-Data Patterns

Plain `re`, five patterns:

| Pattern | Shape |
|---|---|
| Email | `local@domain.tld` |
| Phone | International and national forms, 9-15 digits with common separators |
| National insurance | Two letters, six digits, one letter |
| Social security | Three-two-four digits |
| Card number | 13-19 digits passing a Luhn check |

**Luhn is checked for card numbers specifically**, because a 16-digit order reference
is common in test data and a bare digit-count rule would reject it. The check turns a
noisy pattern into a precise one, and a rule that fires on legitimate data is a rule
that gets disabled.

### The documented synthetic set

Values from a known synthetic set are permitted: `example.com` and `example.org`
email domains (RFC 2606), the `555-01xx` phone range (reserved for fiction), and the
standard test card numbers published by payment processors.

**Reserved ranges exist precisely for this**, and permitting them means the agent has
an obvious correct answer rather than only a prohibition.

---

## Rejected Alternatives

| Alternative | Why rejected |
|---|---|
| Jinja2 for the case views | See above: U5's reason does not transfer |
| A PII detection library | Adds a dependency and a model download to improve a five-pattern check whose false-positive cost is one substitution |
| Storing views as blobs in the database | They exist to be read in an editor and diffed in git |
| An ORM for the batch insert | The all-or-nothing guarantee depends on explicit transaction control, which is what U1 chose `sqlite3` for |
