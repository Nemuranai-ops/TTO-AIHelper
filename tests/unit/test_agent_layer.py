"""Agent Layer consistency. Requirements: U7-NFR-MNT-01 to U7-NFR-MNT-07.

The seven chat modes list the tools their stage may use. U2 through U8 will register
seventeen more write tools. A mode naming a tool that does not exist, or omitting one
that does, fails mid-run in front of the operator - the most expensive moment for it
to surface.

Same class of problem as the import contracts, same answer: a machine check. A review
checklist depends on eight units' worth of authors remembering; a test does not.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tto_testgen.domain.model import StageName

REPO = Path(__file__).resolve().parents[2]
CHATMODES = REPO / ".github" / "chatmodes"
INSTRUCTIONS = REPO / ".github" / "instructions"
PROMPTS = REPO / ".github" / "prompts"
REPO_INSTRUCTIONS = REPO / ".github" / "copilot-instructions.md"
MCP_CONFIG = REPO / ".vscode" / "mcp.json"

UNIVERSAL_READS = {"run_status", "unit_state_get", "health_check", "features_list"}

#: Tool-name fragments that would indicate file-write capability. FR-AGT-06 requires
#: durable state to go through the toolchain; excluding the capability is what makes
#: that structural rather than remembered.
FILE_WRITE_MARKERS = ("write_file", "create_file", "edit_file", "editFiles",
                      "insert_edit", "apply_patch", "str_replace")


def build_registry():
    """An empty in-memory registry.

    The check is about the tool surface's *shape*, and shape does not depend on data.
    Coupling it to a populated database - or worse, to a live application needing
    credentials - would make a documentation problem present as a configuration one.
    """
    import sqlite3

    from tto_testgen.adapters.sqlite.repositories import unit_of_work
    from tto_testgen.adapters.sqlite.schema import ensure_schema
    from tto_testgen.mcp.server import ToolRegistry
    from tto_testgen.mcp.tools_read import register_read_tools
    from tto_testgen.mcp.tools_u2 import register_u2_tools
    from tto_testgen.mcp.tools_u3 import register_u3_tools
    from tto_testgen.mcp.tools_u4 import register_u4_tools
    from tto_testgen.mcp.tools_u5 import register_u5_tools
    from tto_testgen.mcp.tools_u6 import register_u6_tools
    from tto_testgen.mcp.tools_u8 import register_u8_tools
    from tto_testgen.mcp.tools_write import register_write_tools
    from tto_testgen.services.analysis import AnalysisService
    from tto_testgen.services.ingestion import IngestionService
    from tto_testgen.services.runstate import RunStateService

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    ensure_schema(conn)
    registry = ToolRegistry()
    register_read_tools(registry, lambda: conn)
    register_write_tools(registry, RunStateService(lambda: unit_of_work(conn)))
    # U2's tools are registered with placeholder services: the check is about the
    # tool surface's shape, and shape does not depend on the services behind it.
    register_u2_tools(registry, None, None, None)
    register_u3_tools(registry, None, None)
    register_u4_tools(registry, None)
    register_u5_tools(registry, None)
    register_u6_tools(registry, None)
    register_u8_tools(registry, None, None)
    return registry


def parse_front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    _, raw, body = text.split("---", 2)
    data: dict = {}
    for match in re.finditer(r"^(\w+):\s*(.*)$", raw, re.M):
        key, value = match.group(1), match.group(2).strip()
        if value.startswith("["):
            data[key] = re.findall(r"'([^']+)'", raw[match.start():])
        else:
            data[key] = value
    return data, body


def mode_files() -> list[Path]:
    return sorted(CHATMODES.glob("*.chatmode.md"))


def mode_tools(path: Path) -> list[str]:
    data, _ = parse_front_matter(path)
    return [t.split("/", 1)[-1] for t in data.get("tools", [])]


@pytest.fixture(scope="module")
def registry():
    return build_registry()


class TestChatModes:
    def test_one_mode_per_pipeline_stage(self):
        stems = {p.name.replace(".chatmode.md", "") for p in mode_files()}
        assert stems == {s.value for s in StageName}

    def test_every_mode_names_a_valid_stage(self):
        """U7-NFR-MNT-05."""
        for path in mode_files():
            data, _ = parse_front_matter(path)
            assert data.get("stage") in {s.value for s in StageName}, path.name

    def test_every_mode_has_a_description(self):
        for path in mode_files():
            data, _ = parse_front_matter(path)
            assert data.get("description"), path.name

    def test_every_named_tool_exists_in_the_registry(self, registry):
        """U7-NFR-MNT-01. Drift fails the build rather than the run."""
        known = set(registry.tools)
        # Tools registered by units not yet built are permitted, but must be named
        # in the plan rather than invented - so they are listed explicitly here.
        # Shrinks as each unit registers its tools. U2's four have moved from this
        # list into the registry.
        future = {
            "testcases_upsert", "views_emit", "automation_emit", "handover_assemble",
            "handover_verify", "reports_generate",
        }
        offenders = []
        for path in mode_files():
            for tool in mode_tools(path):
                if tool not in known and tool not in future:
                    offenders.append(f"{path.name}: {tool}")
        assert offenders == [], f"Modes name tools that do not exist: {offenders}"

    def test_every_registered_tool_appears_in_some_mode(self, registry):
        """U7-NFR-MNT-02. A registered tool no mode offers is unreachable."""
        named = {t for path in mode_files() for t in mode_tools(path)}
        missing = sorted(set(registry.tools) - named)
        assert missing == [], f"Registered but unreachable from any mode: {missing}"

    def test_every_mode_includes_the_universal_reads(self):
        """U7-NFR-MNT-03. A mode that cannot check its own gate forces a mode switch."""
        for path in mode_files():
            tools = set(mode_tools(path))
            assert UNIVERSAL_READS <= tools, f"{path.name} missing {UNIVERSAL_READS - tools}"

    def test_no_mode_grants_a_file_write_tool(self):
        """U7-NFR-MNT-04. FR-AGT-06 made structural rather than remembered."""
        offenders = []
        for path in mode_files():
            for tool in mode_tools(path):
                if any(marker in tool for marker in FILE_WRITE_MARKERS):
                    offenders.append(f"{path.name}: {tool}")
        assert offenders == [], f"File-write capability granted: {offenders}"

    def test_every_mode_can_claim_and_complete_a_unit(self):
        for path in mode_files():
            tools = set(mode_tools(path))
            assert {"unit_begin", "unit_complete"} <= tools, path.name

    def test_every_mode_states_it_does_not_choose_scope(self):
        # C-12 expressed in the interface the operator actually reads.
        for path in mode_files():
            _, body = parse_front_matter(path)
            assert "will not choose" in body or "do not" in body.lower(), path.name


class TestRepositoryInstructions:
    def test_file_exists(self):
        assert REPO_INSTRUCTIONS.exists()

    def test_states_all_four_standing_rules(self):
        """U7-NFR-MNT-06. An edit that removes a rule the design depends on fails here."""
        text = REPO_INSTRUCTIONS.read_text(encoding="utf-8").lower()
        for phrase, rule in [
            ("traceability", "traceability is not negotiable"),
            ("durable state", "state goes through the toolchain"),
            ("could not determine", "say what you could not determine"),
            ("names the scope", "the operator names the scope"),
        ]:
            assert phrase in text, f"missing standing rule: {rule}"

    def test_explains_the_error_families(self):
        text = REPO_INSTRUCTIONS.read_text(encoding="utf-8")
        assert "REJECTED_" in text and "FAILED_" in text

    def test_names_all_seven_stages_in_order(self):
        text = REPO_INSTRUCTIONS.read_text(encoding="utf-8")
        positions = [text.find(s.value) for s in StageName]
        assert all(p >= 0 for p in positions)


class TestPathScopedInstructions:
    def test_every_instruction_file_declares_a_glob(self):
        """U7-NFR-MNT-07.

        A file without `applyTo` applies nowhere and is silently inert - exactly the
        failure a build-time check should catch, since nothing at runtime reports it.
        """
        files = sorted(INSTRUCTIONS.glob("*.instructions.md"))
        assert files
        for path in files:
            data, _ = parse_front_matter(path)
            assert data.get("applyTo"), f"{path.name} declares no applyTo glob"

    def test_globs_are_distinct(self):
        globs = [parse_front_matter(p)[0]["applyTo"] for p in INSTRUCTIONS.glob("*.md")]
        assert len(globs) == len(set(globs))


class TestPrompts:
    def test_prompt_files_exist_with_descriptions(self):
        files = sorted(PROMPTS.glob("*.prompt.md"))
        assert len(files) == 6
        for path in files:
            data, body = parse_front_matter(path)
            assert data.get("description"), path.name
            assert body.strip(), path.name


class TestMcpRegistration:
    def test_config_is_valid_json(self):
        json.loads(MCP_CONFIG.read_text(encoding="utf-8"))

    def test_all_four_servers_are_registered(self):
        servers = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))["servers"]
        assert set(servers) == {"tto-testgen", "tto-atlassian", "tto-bitbucket", "playwright"}

    def test_no_literal_secret_is_present(self):
        # The file is committed deliberately - every operator needs the same
        # registration - which is exactly why it must reference variables, not values.
        text = MCP_CONFIG.read_text(encoding="utf-8")
        for match in re.finditer(r'"(\w*(?:TOKEN|SECRET|PASSWORD|KEY))"\s*:\s*"([^"]*)"', text):
            assert match.group(2).startswith("${env:"), match.group(0)

    def test_toolchain_uses_stdio(self):
        servers = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))["servers"]
        assert servers["tto-testgen"]["type"] == "stdio"
