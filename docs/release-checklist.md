# Release Checklist

**Satisfies**: NFR-SEC-09, SECURITY-10, OD-02, U1-NFR-DIST-01 to -04

Every step is a gate. A release is a git tag, and the tag is what a rollback returns
to — so a tag that does not pass this list is a rollback target that does not work.

## 1. Supply chain

```bash
uv lock --check                                    # lockfile matches pyproject
uv run pip-audit                                   # vulnerability scan
uv run pip-audit --format cyclonedx-json -o sbom.json   # SBOM
```

- [ ] Lockfile is current and committed
- [ ] No known vulnerabilities, or each is documented with a reason to accept
- [ ] SBOM generated and attached to the release
- [ ] No unused dependencies (`pyproject.toml` reviewed against actual imports)
- [ ] Every version is exact — no ranges, no `latest`, anywhere

## 2. Correctness

```bash
uv run pytest
uv run pytest -m benchmark
uv run lint-imports
```

- [ ] Full suite passes
- [ ] All 16 property tests present and passing
- [ ] Performance budgets met at 10,000 cases
- [ ] `idx_case_bucket` confirmed in the de-duplication query plan
- [ ] All 3 import contracts kept

## 3. Migrations

- [ ] Every new forward migration has a reverse
- [ ] Reverse migrations tested (`verify_reversibility`)
- [ ] Rollback across the migration rehearsed per `restore-procedure.md` Scenario C

## 4. Secrets

```bash
git grep -nE '(token|secret|password|api[_-]?key)\s*=\s*["'"'"'][^"'"'"']+' -- ':!*.example' ':!docs/*'
```

- [ ] No credential in source, config, tests or documentation
- [ ] `.env` is gitignored and absent from the tree
- [ ] `.gitignore` still excludes `.taas/` and `generated/`
- [ ] A clean clone contains no ingested corporate content

## 5. Cross-platform

- [ ] Installs and runs on macOS, Windows and Linux with Python 3.11+
- [ ] No shell invocation; `pathlib` throughout

## 6. Tag

```bash
git tag -a v<x.y.z> -m "<summary>"
git push origin v<x.y.z>
```

- [ ] Tag pushed
- [ ] Rollback verified: `git checkout <previous-tag> && uv sync` starts cleanly
