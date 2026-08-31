---
description: Extract features, rules and edge cases from one Jira story
---

# Extract features, rules and edge cases from one Jira story

Read the named Jira story and extract:

1. **Features** it belongs to or introduces
2. **Business rules** — validation, state transitions, calculations, permissions
3. **Edge cases and boundaries** it implies
4. **Failure scenarios** it describes or leaves unstated

For each, note whether it is stated explicitly or inferred. An inferred rule is worth
recording, but it must be labelled as inferred.

If the story has no acceptance criteria, say so plainly. Do not construct criteria
that look reasonable — a requirement derived from an invented criterion produces
tests that assert a fiction.

Store the result with `analysis_upsert`.
