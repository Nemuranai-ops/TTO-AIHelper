---
description: Produce the coverage and gap report for a feature
---

# Produce the coverage and gap report for a feature

Produce two reports for the named feature.

**Coverage**: planned against generated, per test type, with the derivation visible.
A number without its derivation cannot be checked and therefore cannot be defended.

**Gaps**: requirements with no coverage, behaviours with no derivable Jira key,
manual-only cases, reduced-depth features, and cases rejected as duplicates.

Show empty categories explicitly. A missing section is indistinguishable from a check
that was never run.
