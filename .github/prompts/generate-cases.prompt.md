---
description: Generate the case batch for one feature
---

# Generate the case batch for one feature

Read the approved coverage model for the named feature with `coverage_get`, then
produce one case per planned coverage item.

Each case needs:
- **Ordered steps**, each with a specific expected result
- **Test data** where the case depends on values, labelled with its equivalence class
- **A trace link** resolving to a Jira key that exists in the ingested set

Submit the whole batch in one `testcases_upsert` call. It is atomic and reports every
failure at once — one correction pass fixes them all. Submitting cases one at a time
to avoid rejections wastes both your effort and the operator's.

If a coverage item cannot be turned into a traceable case, report it rather than
producing an untraceable one.
