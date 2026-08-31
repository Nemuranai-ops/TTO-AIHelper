# Tech Stack Decisions — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-30

---

## Summary

**U6 adds nothing.** Fourth consecutive unit to add no dependency.

| Concern | Decision | Source |
|---|---|---|
| Everything inherited | Python 3.11+, `uv`, Pydantic v2, stdlib `sqlite3` | U1 |
| Running external commands | `subprocess.run` | stdlib |
| Detecting a toolchain | `shutil.which` | stdlib |
| Import extraction | `re` | stdlib |
| Atomic file write | `os.replace` after a temporary write | stdlib |
| Manifest JSON | `json` | stdlib |

**Verified, not assumed**: nothing in `mcp`, `pydantic`, `pyyaml` or `jinja2` is
needed here, and no package was added. The U2 episode — PyYAML documented as
transitive when it is not — is why every unit since states the check.

---

## Running External Commands

### `subprocess.run` with a literal argv

```python
subprocess.run(
    ["npm", "ci", "--ignore-scripts"],
    cwd=project_root, shell=False, capture_output=True,
    text=True, timeout=timeout_s, check=False,
)
```

Every element is a literal. **No project value — no feature slug, no path from the
corpus — is ever interpolated into an argv**, so nothing agent-supplied can become a
flag. With `shell=False` there is no shell to interpret a metacharacter even if one
arrived, which makes the guarantee structural rather than dependent on the argument
list being right.

`check=False` because a non-zero exit is an expected outcome here: a compilation
failure is information the report carries, not an exception to propagate.

### What was declined

| Considered | Why not |
|---|---|
| A shell string (`shell=True`) | The one form where a metacharacter in a path becomes executable. No benefit that a literal argv does not provide |
| `os.system` | Same problem, plus it discards output |
| A Node binding for Python (`nodejs-bin`, `pyexecjs`) | It would vendor a Node runtime into a Python dependency tree to avoid asking whether Node is installed — a large dependency to answer a question `shutil.which` answers for free |
| Docker, to run verification in a container | Reproducible, and it requires Docker on the operator's workstation to check a project the user explicitly chose not to containerise |
| A TypeScript parser in Python | It would reimplement TypeScript's module resolution, which could disagree with the real one. The structural check asks whether a file exists, which needs no parser |

**The Node-binding option is the one worth stating plainly.** Embedding a runtime would
remove the skipped tier and make verification always available — at the cost of a
tens-of-megabytes dependency, a second Node version diverging from the operator's, and
a Python package that ships a JavaScript engine. The skipped tier is a smaller and more
honest answer to the same problem.

---

## Detecting the Toolchain

`shutil.which("npm")` before invoking, rather than attempting the command and catching
`FileNotFoundError`.

Both work. The difference is that catching the exception conflates "not installed" with
a permissions error, a broken symlink, and a dozen other `OSError`s — which is how a
`skipped` status ends up hiding a real fault the operator needed to know about.

---

## Atomic Write

`Path.write_text` to a temporary file in the same directory, then `os.replace`.

`os.replace` is atomic on POSIX and on Windows, and same-directory keeps it on one
filesystem so the rename cannot become a copy. **The manifest is read by
reconciliation**, so a truncated one from a crashed run would be read as authoritative
by the next run — producing a failure with no cause the engineer can find.

---

## Dependency Count

Unchanged: **4 runtime, 5 development.** Four units in a row have added nothing, which
is what choosing the stack once at U1 was meant to achieve.
