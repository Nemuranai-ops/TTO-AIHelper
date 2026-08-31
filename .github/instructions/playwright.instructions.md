---
applyTo: 'generated/playwright-suite/**/*.ts'
---

# Generated Playwright Automation

This project is generated from the test corpus. Regeneration is byte-identical for
identical input, so hand-edits are detected and reported before being overwritten —
but the corpus, not this code, is the source of truth.

## Locators

Prefer `getByRole`, then `getByLabel`, then `getByTestId`. Reach for CSS or XPath only
when nothing semantic exists, and when you do, say why in a comment.

A locator built from the DOM's accidents breaks on the first refactor. One built from
the interface's meaning survives it.

## Waiting

Never `waitForTimeout`. Use Playwright's auto-waiting and expectation-based waits.

A fixed wait is slow when it passes and flaky when it does not — it trades both speed
and reliability for the appearance of stability.

## Structure

Page Object Model. Locators live in the page object, never inline in a spec. A spec
interacts with the application only through page objects.

## Traceability

Every test carries its case identifier and Jira key as annotations. They survive into
the JUnit XML, which is what lets a red test in Jenkins be traced back to what it was
meant to prove.

## Configuration

Base URL, credentials and timeouts come from environment variables. Never a literal.
`.env.example` documents every variable the suite needs.
