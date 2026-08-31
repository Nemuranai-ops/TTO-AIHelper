"""M1 McpServer.serve_stdio() against a REAL subprocess speaking real MCP.

Before this, serve_stdio() was a hand-rolled line protocol - no initialize
handshake, tools/list and tools/call in shapes the real protocol never uses, no
`id` ever echoed back - marked `# pragma: no cover - transport wiring` and never
exercised by anything, including a real client. Every other test in this suite
calls McpServer.call()/.list_tools() directly as plain Python methods, which is
exactly why a wire-level defect this fundamental went unnoticed: the object-level
logic underneath was always correct, only the protocol bridge to a real MCP
client (Copilot) was not. These tests replace the pragma with the genuine article.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def server(tmp_path):
    env = dict(os.environ)
    env["TAAS_DB_PATH"] = str(tmp_path / "taas.db")
    proc = subprocess.Popen(
        [sys.executable, "-c", "from tto_testgen.composition import main; main()"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, cwd=REPO_ROOT, env=env,
    )
    yield proc
    proc.stdin.close()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)


def _send(proc, request):
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()


def _recv(proc):
    line = proc.stdout.readline()
    assert line, f"no response - stderr:\n{proc.stderr.read()}"
    return json.loads(line)


def _initialize(proc):
    _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1"}}})
    response = _recv(proc)
    _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    return response


class TestHandshake:
    def test_initialize_returns_a_real_jsonrpc_result(self, server):
        response = _initialize(server)
        assert "result" in response
        assert response["result"]["serverInfo"]["name"] == "tto-testgen"

    def test_the_response_id_matches_the_request_id(self, server):
        _send(server, {"jsonrpc": "2.0", "id": 42, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "test", "version": "1"}}})
        response = _recv(server)
        assert response["id"] == 42


class TestToolsList:
    def test_every_registered_tool_is_visible_with_a_valid_schema(self, server):
        _initialize(server)
        _send(server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        response = _recv(server)
        tools = response["result"]["tools"]
        names = {t["name"] for t in tools}
        assert "delta_detect" in names
        assert "requirements_upsert" in names
        assert "ingest_resources" in names
        for tool in tools:
            assert isinstance(tool["inputSchema"], dict)
            assert tool["inputSchema"].get("type") == "object"


class TestToolsCall:
    def test_a_successful_call_carries_the_agents_existing_ok_value_contract(self, server):
        """structuredContent is the same {"ok", "value"} shape _result_payload has
        always produced - the transport rewrite changes the wire, not the contract
        every tool handler and every existing test already agrees on."""
        _initialize(server)
        _send(server, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "delta_status", "arguments": {}}})
        response = _recv(server)
        assert response["id"] == 3
        result = response["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["ok"] is True
        assert result["structuredContent"]["value"]["has_baseline"] is False

    def test_an_unknown_tool_is_reported_as_isError_not_a_crash(self, server):
        _initialize(server)
        _send(server, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "not_a_real_tool", "arguments": {}}})
        response = _recv(server)
        result = response["result"]
        assert result["isError"] is True
        assert result["structuredContent"]["ok"] is False

    def test_invalid_arguments_fail_without_reaching_the_handler(self, server):
        """artefacts_query's limit is an int - a non-numeric string must fail
        validation before any query runs."""
        _initialize(server)
        _send(server, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                       "params": {"name": "artefacts_query", "arguments": {"limit": "not-a-number"}}})
        response = _recv(server)
        result = response["result"]
        assert result["isError"] is True
        assert "Invalid arguments" in result["structuredContent"]["message"]
