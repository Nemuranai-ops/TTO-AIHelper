# Business Logic Model — U6 Handover

**Phase**: CONSTRUCTION | **Unit**: U6 | **Stage**: Functional Design
**Version**: 1.0 | **Date**: 2026-08-30

---

## 1. The Sequence

```
handover_assemble()
        |
   [A] gate: automation approved?  ---- closed ----> REJECTED_GATE_CLOSED
        |
   [B] add what U5 cannot produce: .gitignore, lockfile (if npm), manifest
        |
   [C] structural verification (Python, always)
        |
   [D] toolchain verification (npm ci, tsc, playwright --list) if node present
        |                                                  else skipped, with reason
   [E] three-way reconciliation: automated_test <-> disk <-> manifest
        |
   [F] is_ready = structural.passed and reconciliation.passed
        |
   record the outcome in unit_state; report
```

**No stage writes to the corpus.** A handover that adjusted what it was describing
would make the manifest a record of itself rather than of the delivery.

---

## 2. Algorithms

### 2.1 Structural verification (BR-U6-2.1)

```
verify_structure(project_root):
    checks = []
    for required in REQUIRED_FILES:
        checks.append(Check(required, (project_root / required).exists()))

    for spec in sorted(project_root.glob("tests/*.ts")):
        for target in imports_of(spec):              # ../pages/x, ../fixtures/y
            resolved = (spec.parent / target).with_suffix(".ts")
            checks.append(Check(f"{spec.name} -> {target}", resolved.exists()))

    for path in sorted(all_generated_files(project_root)):
        text = path.read_text()
        checks.append(Check(f"{path} has no absolute path", not ABSOLUTE.search(text)))
        checks.append(Check(f"{path} has no credential", scan_value(str(path), text) is None))
    return TierResult(checks)
```

`imports_of` is a regular expression over `from '...'`, not a TypeScript parse. **The
question is whether a referenced file exists**, which does not need a parser — and
adding one would introduce a second implementation of TypeScript's module resolution
that could disagree with the real one.

L13's `scan_value` runs again here, over the assembled bytes rather than the case
values. U5 refused a credential *before* rendering; this catches one that arrived by
hand-edit afterwards, which is the only remaining path.

### 2.2 Toolchain verification (BR-U6-2.2, BR-U6-7)

```
verify_toolchain(project_root, timeout_s):
    if shutil.which("npm") is None:
        return TierResult(status=SKIPPED, reason="npm not found on PATH")

    for name, argv in (
        ("install",  ["npm", "ci", "--ignore-scripts"]),
        ("compile",  ["npx", "tsc", "--noEmit"]),
        ("enumerate",["npx", "playwright", "test", "--list"]),
    ):
        result = run(argv, cwd=project_root, timeout=timeout_s,
                     shell=False, capture_output=True)
        ...
```

Every argument is a literal. **No project value is interpolated into an argv**, so a
feature slug cannot become a flag — and with `shell=False` there is no shell to
interpret a metacharacter even if one arrived.

`npm ci` rather than `npm install`: it installs exactly the lockfile and fails if
`package.json` and the lockfile disagree, which is precisely the drift FR-HND-02 exists
to catch. It also refuses to run without a lockfile, so a skipped BR-U6-3 makes this
check fail honestly rather than silently resolving fresh versions.

### 2.3 Three-way reconciliation (BR-U6-4)

```
reconcile(project_root, automated_tests):
    in_db   = {t.case_id: t for t in automated_tests}
    on_disk = {}
    for spec in sorted(project_root.glob("tests/*.spec.ts")):
        for case_id in CASE_ID.findall(spec.read_text()):     # TC-<SLUG>-<NNNNN>
            on_disk[case_id] = spec
    in_manifest = {e.case_id: e for e in manifest.entries}

    return Reconciliation(
        missing_from_disk     = sorted(in_db.keys()      - on_disk.keys()),
        missing_from_db       = sorted(on_disk.keys()    - in_db.keys()),
        missing_from_manifest = sorted(on_disk.keys()    - in_manifest.keys()),
        orphan_manifest       = sorted(in_manifest.keys()- on_disk.keys()),
    )
```

The disk side finds identifiers by pattern rather than by parsing, which is why U5 put
the case identifier in the test **title** as well as the annotation. A structured parse
of the annotation array would be more precise and would make this check depend on the
template's shape — so a template change would break verification for a reason unrelated
to correctness.

### 2.4 The manifest (US-HND-03)

```
build_manifest(automated_tests, cases, gaps):
    entries = [ManifestEntry(...) for t in sorted(automated_tests, key=id)]
    return HandoverManifest(
        entries=entries,
        totals={
            "automated":    len(entries),
            "manual_only":  count_by_class(cases, "manual-only"),
            "needs_review": count_by_class(cases, "needs-review"),
            "corpus_total": count_active(cases),
        },
        at_risk=[e for e in entries if e.is_at_risk],
        ...
    )
```

Sorted by identifier and carrying no timestamp, for the same reason U5's output does:
the manifest is committed, and one that reorders itself between identical runs reads as
churn in every diff.

**The totals answer the Test Lead's actual question** — not "how many tests are there"
but "what proportion of the corpus is this, and what is not here" (US-HND-03 AC2).

### 2.5 Readiness (BR-U6-5)

```
is_ready = structural.passed and reconciliation.passed and toolchain.status is not FAILED
```

Written as three terms rather than two so the skipped case is visible in the
expression: `SKIPPED is not FAILED` is true, and a reader can see that is intended
rather than inferring it from an omission.

---

## 3. What Happens When Node Is Absent

The realistic case, and worth tracing end to end:

| Stage | Outcome |
|---|---|
| Lockfile | Not written. Report names `npm install --package-lock-only` |
| Structural tier | Runs. Catches missing files and broken imports |
| Toolchain tier | `skipped`, reason recorded |
| Reconciliation | Runs — it is Python and file reads |
| `is_ready` | **True**, if structural and reconciliation pass |
| The report says | "Compilation not verified: npm not found on PATH" |

The engineer receives a project that is structurally complete and honestly labelled as
uncompiled. **That is materially better than both alternatives**: refusing to run leaves
them with nothing, and claiming verification would send them to Jenkins believing
something that was never checked.

---

## 4. Interaction with Other Units

| Unit | Use |
|---|---|
| U1 | Repositories, `unit_of_work`, L13 for the re-scan |
| U5 | The generated project. **Read only** — U6 adds files, never rewrites them |
| U7 | `is_gate_open` before assembly; `stage_approve` for the operator's decision |
| U8 | Reads the manifest and the corpus for its reports |

**U6 does not call U5.** If the project is incomplete, U6 reports it; regenerating is
the operator's decision through `automation_emit`. A verification step that repaired
what it found would be verifying its own repair.

---

## 5. Property Surface

| Property | Statement |
|---|---|
| PBT-U6-1 | A skipped tier never makes `is_ready` false on its own |
| PBT-U6-2 | A failed structural check always makes `is_ready` false |
| PBT-U6-3 | Reconciliation is symmetric: a mismatch appears in exactly one direction list |
| PBT-U6-4 | The manifest is byte-stable for an unchanged corpus |
| PBT-U6-5 | Every manifest entry's `spec_path` is relative |
| PBT-U6-6 | No blocking finding is reported without naming a file |
| PBT-U6-7 | Every subprocess argv is a list of literals with no interpolated value |

**PBT-U6-1 and -2 are the pair that pins down BR-U6-2.4**, which is the unit's least
obvious rule and the one most likely to be broken by a later change that treats
`skipped` as a failure "to be safe".

---

## 6. Story Coverage

| Story | Rules | Algorithms |
|---|---|---|
| US-HND-01 | BR-U6-1, BR-U6-3, BR-U6-6 | §2.1, §3 |
| US-HND-02 | BR-U6-2, BR-U6-5, BR-U6-7 | §2.1, §2.2, §2.5 |
| US-HND-03 | BR-U6-4 | §2.3, §2.4 |

**All 3 U6 stories are covered.**
