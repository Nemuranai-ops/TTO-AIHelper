"""L15 StructuralVerifier.

The check that matters most is the broken import: US-HND-02 AC4's exact failure, the
one the engineer would otherwise find in Jenkins.
"""

from __future__ import annotations

import pytest

from tto_testgen.adapters.structural_verifier import REQUIRED_FILES, StructuralVerifier


@pytest.fixture()
def project(tmp_path):
    """A minimal but complete generated project."""
    root = tmp_path / "automation"
    (root / "tests").mkdir(parents=True)
    (root / "pages").mkdir()
    (root / "fixtures").mkdir()
    for relative in REQUIRED_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// generated\n", encoding="utf-8")
    (root / ".env.example").write_text("TAAS_BASE_URL=\nTAAS_AUTH_PASSWORD=\n", encoding="utf-8")
    (root / "pages" / "checkout.page.ts").write_text("export class CheckoutPage {}\n",
                                                     encoding="utf-8")
    (root / "tests" / "checkout.spec.ts").write_text(
        "import { test } from '../fixtures/auth';\n"
        "import { CheckoutPage } from '../pages/checkout.page';\n",
        encoding="utf-8",
    )
    return root


def failures(checks):
    return [c for c in checks if not c.passed]


def test_a_complete_project_passes_every_check(project):
    assert failures(StructuralVerifier().verify(project)) == []


# --- required files ----------------------------------------------------------------

@pytest.mark.parametrize("missing", REQUIRED_FILES)
def test_each_required_file_is_checked(project, missing):
    (project / missing).unlink()
    bad = failures(StructuralVerifier().verify(project))
    assert any(missing in c.name for c in bad)


def test_a_missing_file_names_itself(project):
    (project / "tsconfig.json").unlink()
    bad = failures(StructuralVerifier().verify(project))
    finding = next(c for c in bad if "tsconfig" in c.name)
    assert finding.location == "tsconfig.json"
    assert "missing" in finding.detail


# --- imports -------------------------------------------------------------------------

def test_a_spec_importing_a_missing_page_object_fails(project):
    """US-HND-02 AC4. The common failure, caught without a compiler."""
    (project / "tests" / "basket.spec.ts").write_text(
        "import { BasketPage } from '../pages/basket.page';\n", encoding="utf-8"
    )
    bad = failures(StructuralVerifier().verify(project))
    finding = next(c for c in bad if "basket.page" in c.name)
    assert finding.location == "tests/basket.spec.ts"
    assert "does not exist" in finding.detail


def test_a_resolvable_import_passes(project):
    checks = StructuralVerifier().verify(project)
    assert any("checkout.page" in c.name and c.passed for c in checks)


def test_a_missing_fixture_import_fails(project):
    (project / "fixtures" / "auth.ts").unlink()
    bad = failures(StructuralVerifier().verify(project))
    assert any("fixtures/auth" in c.name for c in bad)


def test_package_imports_are_not_treated_as_files(project):
    """Only relative imports name project files. `@playwright/test` is a package."""
    (project / "tests" / "api.spec.ts").write_text(
        "import { test } from '@playwright/test';\n", encoding="utf-8"
    )
    assert failures(StructuralVerifier().verify(project)) == []


# --- absolute paths ---------------------------------------------------------------------

def test_an_absolute_path_in_a_generated_file_fails(project):
    (project / "playwright.config.ts").write_text(
        "const root = '/Users/someone/projects/app';\n", encoding="utf-8"
    )
    bad = failures(StructuralVerifier().verify(project))
    finding = next(c for c in bad if "absolute path" in c.name)
    assert finding.location == "playwright.config.ts"


def test_a_relative_path_is_fine(project):
    (project / "playwright.config.ts").write_text(
        "testDir: './tests',\n", encoding="utf-8"
    )
    assert failures(StructuralVerifier().verify(project)) == []


# --- credentials ---------------------------------------------------------------------------

def test_a_credential_literal_added_by_hand_is_caught(project):
    """U5 refuses one before rendering; a hand-edit is the only remaining path, and
    this is the last point before the operator pushes."""
    (project / "fixtures" / "auth.ts").write_text(
        "const dsn = 'postgres://user:pa55w0rd@db.internal:5432/app';\n", encoding="utf-8"
    )
    bad = failures(StructuralVerifier().verify(project))
    finding = next(c for c in bad if "credential" in c.name)
    assert "fixtures/auth.ts:1" == finding.location


def test_a_property_named_password_reading_from_env_is_not_a_leak(project):
    """A TypeScript property called `password` is correct code, not a credential.

    Only value shapes apply to generated code; the field-name rule would refuse the
    fixture that does the right thing.
    """
    (project / "fixtures" / "auth.ts").write_text(
        "const password = () => process.env.TAAS_AUTH_PASSWORD ?? '';\n", encoding="utf-8"
    )
    assert failures(StructuralVerifier().verify(project)) == []


def test_env_example_carrying_a_value_fails(project):
    (project / ".env.example").write_text(
        "TAAS_BASE_URL=https://staging.acme.co.uk\n", encoding="utf-8"
    )
    bad = failures(StructuralVerifier().verify(project))
    assert any("values in .env.example" in c.name for c in bad)


def test_env_example_with_empty_values_passes(project):
    assert failures(StructuralVerifier().verify(project)) == []


def test_comments_in_env_example_are_ignored(project):
    (project / ".env.example").write_text(
        "# Base URL, e.g. https://app.example.com\nTAAS_BASE_URL=\n", encoding="utf-8"
    )
    assert failures(StructuralVerifier().verify(project)) == []


# --- containment -------------------------------------------------------------------------------

def test_node_modules_is_never_read(project):
    """Otherwise verification would read a dependency tree of tens of thousands of
    files, and report on code that is not ours."""
    junk = project / "node_modules" / "pkg"
    junk.mkdir(parents=True)
    (junk / "index.ts").write_text("const k = 'postgres://u:p@host/db';\n", encoding="utf-8")
    assert failures(StructuralVerifier().verify(project)) == []
