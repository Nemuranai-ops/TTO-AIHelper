---
applyTo: 'generated/views/**/*.{md,yaml,yml}'
---

# Generated Test Case Views

**These files are views, not the record.** The corpus lives in SQLite; these are
rendered from it for review and version control.

## Editing

Do not edit these files to change a test case. The edit will be detected on the next
emission and reported, and the corpus will be unchanged — so the file and the truth
will disagree until someone notices.

To change a case, use `testcases_upsert`. To see the current state, use
`testcase_get` or regenerate the views with `views_emit`.

## Reviewing

These files exist to be read. A case that is hard to follow here is hard to follow
anywhere, and that is worth reporting even though the fix belongs in the generator.

Check that steps are ordered and executable, that expected results are specific, that
test data names the equivalence class it represents, and that the Jira link points
somewhere real.
