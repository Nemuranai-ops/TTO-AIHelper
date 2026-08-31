"""X3 ConfigAndSecrets. Requirements: NFR-SEC-01, U1-NFR-SEC-01. Pattern: P-SEC-02."""

from pathlib import Path

import pytest

from tto_testgen.platform.config import REQUIRED, Config, SecretStr, load

def complete_env(tmp_path: Path) -> dict:
    """Two dummy scripts, so load()'s existence check passes.

    load() checks that both *_MCP_SCRIPT paths are real files - a wrong path should
    fail at startup, not as the first ingestion call's mysterious "server
    unavailable". Real (empty) files exercise that check the same way a real
    deployment does, rather than special-casing it away.
    """
    atlassian = tmp_path / "atlassian_mcp_server.py"
    bitbucket = tmp_path / "bitbucket_mcp_server.py"
    atlassian.write_text("")
    bitbucket.write_text("")
    return {
        "TAAS_ATLASSIAN_MCP_SCRIPT": str(atlassian),
        "TAAS_BITBUCKET_MCP_SCRIPT": str(bitbucket),
    }


class TestSecretStr:
    def test_repr_does_not_leak(self):
        assert "hunter2" not in repr(SecretStr("hunter2"))

    def test_str_does_not_leak(self):
        assert "hunter2" not in str(SecretStr("hunter2"))

    def test_fstring_does_not_leak(self):
        # The realistic accident: an f-string in a log line.
        assert "hunter2" not in f"token is {SecretStr('hunter2')}"

    def test_reveal_returns_the_value(self):
        assert SecretStr("hunter2").reveal() == "hunter2"

    def test_equality_and_hash_by_value(self):
        assert SecretStr("a") == SecretStr("a")
        assert SecretStr("a") != SecretStr("b")
        assert len({SecretStr("a"), SecretStr("a")}) == 1


class TestLoad:
    def test_nothing_is_required_any_more(self, tmp_path):
        """Both MCP scripts are vendored inside the repo at a fixed path, so
        REQUIRED is empty - there is no environment variable an operator must set
        before anything else works."""
        assert REQUIRED == ()

    def test_an_empty_environment_still_fails_on_a_workspace_with_no_vendored_scripts(
        self, tmp_path
    ):
        """load({}) still fails on a bare tmp_path, but for a different and more
        honest reason than before: the default script paths resolve relative to
        the workspace root, and a fake workspace in a test doesn't have them."""
        result = load(tmp_path, {})
        assert not result.ok
        assert "TAAS_ATLASSIAN_MCP_SCRIPT" in result.message

    def test_the_vendored_scripts_are_found_without_any_configuration(self, tmp_path):
        """The real point of vendoring them: pointed at the actual repo root (not
        a fake tmp_path), the defaults resolve to real files with zero env vars
        set."""
        repo_root = Path(__file__).resolve().parents[2]
        result = load(repo_root, {})
        assert result.ok, getattr(result, "message", "")
        assert result.value.atlassian_mcp_script.name == "atlassian_mcp_server.py"
        assert result.value.atlassian_mcp_script.exists()
        assert result.value.bitbucket_mcp_script.exists()

    def test_succeeds_with_required_variables(self, tmp_path):
        result = load(tmp_path, complete_env(tmp_path))
        assert result.ok
        assert isinstance(result.value, Config)

    def test_applies_documented_defaults(self, tmp_path):
        cfg = load(tmp_path, complete_env(tmp_path)).value
        assert cfg.similarity_threshold == 0.90  # BR-1.3
        assert cfg.commit_lookback_days == 180  # BR-3.1
        assert cfg.page_size == 200  # P-SCL-01
        assert cfg.retry_attempts == 3  # P-RES-02
        assert cfg.backup_keep == 10  # U1-NFR-REC-04

    def test_relative_paths_resolve_inside_the_workspace(self, tmp_path):
        cfg = load(tmp_path, complete_env(tmp_path)).value
        assert cfg.db_path.is_relative_to(tmp_path)  # U1-NFR-ENC-01

    def test_absolute_path_is_respected(self, tmp_path):
        env = {**complete_env(tmp_path), "TAAS_DB_PATH": str(tmp_path / "elsewhere" / "x.db")}
        cfg = load(tmp_path, env).value
        assert cfg.db_path == tmp_path / "elsewhere" / "x.db"

    @pytest.mark.parametrize("bad", ["1.5", "-0.1"])
    def test_rejects_out_of_range_threshold(self, tmp_path, bad):
        result = load(tmp_path, {**complete_env(tmp_path), "TAAS_SIMILARITY_THRESHOLD": bad})
        assert not result.ok

    def test_rejects_non_numeric_setting(self, tmp_path):
        result = load(tmp_path, {**complete_env(tmp_path), "TAAS_PAGE_SIZE": "many"})
        assert not result.ok

    def test_rejects_zero_page_size(self, tmp_path):
        assert not load(tmp_path, {**complete_env(tmp_path), "TAAS_PAGE_SIZE": "0"}).ok

    def test_config_is_frozen(self, tmp_path):
        cfg = load(tmp_path, complete_env(tmp_path)).value
        with pytest.raises(Exception):
            cfg.page_size = 5  # type: ignore[misc]

    def test_business_rule_fingerprint_captures_corpus_tunables(self, tmp_path):
        cfg = load(tmp_path, complete_env(tmp_path)).value
        assert cfg.business_rule_fingerprint() == {
            "similarity_threshold": 0.90,
            "commit_lookback_days": 180,
            "max_batch_cases": 200,
            # U4: a narrowed pattern set weakens a security control, so it belongs
            # beside the rules that change the corpus rather than out of sight.
            "privacy_patterns": ["card", "email", "nino", "phone", "ssn"],
            # U5: two runs on different Playwright versions are not comparable
            # artefacts, so the emitted version belongs in the fingerprint.
            "playwright_version": "1.49.1",
        }


class TestU4Configuration:
    @staticmethod
    def _env(tmp_path, **overrides):
        return {**complete_env(tmp_path), **overrides}

    def test_the_privacy_pattern_names_match_the_domain(self):
        """config.py restates them because platform may not import domain.

        The layering contract forbids the import, so the list is duplicated - and a
        duplicated list that nothing checks is a list that drifts. This is the check.
        """
        from tto_testgen.domain.privacy import PATTERN_NAMES as domain_names
        from tto_testgen.platform.config import PATTERN_NAMES as config_names

        assert set(config_names) == set(domain_names)

    def test_an_unknown_privacy_pattern_is_refused(self, tmp_path):
        result = load(tmp_path, self._env(tmp_path, TAAS_PRIVACY_PATTERNS="email,postcode"))
        assert not result.ok
        assert "postcode" in result.message

    def test_a_narrowed_pattern_set_appears_in_the_fingerprint(self, tmp_path):
        """Narrowing weakens a security control, so it is recorded with the run.

        A control that can be quietly narrowed is a control nobody can rely on.
        """
        result = load(tmp_path, self._env(tmp_path, TAAS_PRIVACY_PATTERNS="email,card"))
        assert result.ok
        assert result.value.business_rule_fingerprint()["privacy_patterns"] == [
            "card", "email"
        ]

    def test_the_batch_cap_must_be_positive(self, tmp_path):
        result = load(tmp_path, self._env(tmp_path, TAAS_MAX_BATCH_CASES="0"))
        assert not result.ok
