---
description: Produce one page object from the UI model
---

# Produce one page object from the UI model

Generate a page object for the named screen.

- Locators defined centrally in the object, never inline in a spec
- `getByRole` and `getByLabel` before `getByTestId`; CSS or XPath only where nothing
  semantic exists, with a comment saying why
- Methods express intent (`submitOrder`), not mechanics (`clickButton3`)
- No fixed waits

If an element has only a fragile locator, say so. A test built on one will break on
the first refactor, and the operator should know before it is written rather than
after it fails.
