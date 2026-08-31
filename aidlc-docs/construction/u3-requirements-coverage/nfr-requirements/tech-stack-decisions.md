# Tech Stack Decisions — U3 Requirements and Coverage

**Phase**: CONSTRUCTION | **Unit**: U3 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## Summary

**U3 adds nothing.** The U1 stack covers this unit entirely, and unlike U2 — which
needed PyYAML and where the claim that it arrived transitively turned out to be false
— this has been checked rather than assumed.

| Concern | Decision | Source |
|---|---|---|
| Language, packaging, validation, database, testing | Inherited | U1 |
| Coverage content hashing | `hashlib.sha256` over a canonical JSON form | stdlib |
| Atomicity detection | `re` over a small pattern set | stdlib |
| Risk banding | Plain arithmetic | — |

---

## Coverage Content Hashing

The approval binds to this hash, so its determinism is load-bearing.

```
payload = [(item.id, item.requirement_id, item.test_type, item.technique,
            item.planned_count, item.is_required)
           for item in sorted(items, key=lambda i: i.id)]
digest  = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))
```

| Property | How it is guaranteed |
|---|---|
| Order-independent | Items sorted by id before serialising |
| Stable across runs | `sort_keys=True`, fixed separators, no timestamps |
| Sensitive to substance | The six fields in BR-U3-4.2 |
| Insensitive to prose | Rationale is not in the payload |

**`separators=(",", ":")` matters.** Python's default JSON separators include a space
after each comma, which is stable within a version but is not a guarantee. Pinning
them makes the hash a function of the data alone.

---

## Atomicity Detection

Plain `re`, not a parser.

| Considered | Outcome |
|---|---|
| **`re` over a verb-conjunction pattern** | **Chosen** — a dozen lines, no dependency, and the heuristic is deliberately conservative so precision beyond this is not useful |
| `spacy` or `nltk` for POS tagging | Rejected — a large model dependency and a download step, to improve a heuristic that already errs toward acceptance by design |
| An LLM call to judge atomicity | Rejected — no API key exists (C-01), and routing it through the agent would put a judgement inside a validator that must be deterministic |

**The last rejection is the interesting one.** Atomicity *is* a judgement, and the
agent is where judgement belongs. But this check runs inside `requirements_upsert`,
which must be deterministic: the same payload must be accepted or rejected identically
every time, or a retry could succeed where the first attempt failed and the operator
would have no idea why.

The judgement stays with the agent — it writes the requirement. The validator only
catches the obvious cases, and `force_atomic` exists for when it is wrong.

---

## Rejected Alternatives

| Alternative | Why rejected |
|---|---|
| Caching the coverage derivation | U3-NFR-PRF-01's 5-second budget is met without it, and a cache would need invalidating on every requirement change |
| A rules engine for coverage depth | The depth rules are BR-2's four techniques. A rules engine would add configuration surface for logic that is already declarative |
| Storing the coverage model as a JSON blob | Loses the ability to query by test type or requirement, which the reports need |
| A separate table for not-required items | Splits one concept across two places to save rows nothing needs saving |
