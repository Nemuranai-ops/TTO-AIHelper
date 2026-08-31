"""L6 McpClientSession - the toolchain acting as an MCP client.

Application Design Q3 put bulk ingestion in the toolchain rather than the agent: at
100-500 Jira stories, routing every issue body through a context window is slow,
expensive, and inserts a transcription step between source and storage.

That makes `tto-testgen` both an MCP server (to the agent) and an MCP client (to
Atlassian and Bitbucket). This does not weaken NFR-SEC-02: the prohibition is on
accepting connections, not on making them.

Requirements: U2-NFR-REL-01, U2-NFR-REL-02, U2-NFR-SEC-02. Pattern: P-U2-01.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from tto_testgen.platform.config import Config
from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import ErrorCode, Result, err, ok

DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True, slots=True)
class ServerSpec:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def servers_from_config(config: Config) -> list[ServerSpec]:
    """The two servers the toolchain drives. Playwright stays with the agent.

    Deciding what matters on a screen is a judgement, so live UI exploration belongs
    to the model. Fetching 500 issue bodies is not, so it belongs here.

    Neither server takes a credential from TAAS. `tt-bitbucket-mcp` never contacts
    Bitbucket - it reads git clones already on disk. `tt-atlassian-mcp` does call
    Jira and Confluence, but authenticates from its own `.env` file next to the
    script; that file holds the real token, and TAAS never reads it. TAAS's only
    job is to point each server at itself.
    """
    atlassian_env = {}
    if config.atlassian_env_file is not None:
        atlassian_env["ATLASSIAN_ENV_FILE"] = str(config.atlassian_env_file)
    bitbucket_env = {}
    if config.bitbucket_env_file is not None:
        bitbucket_env["BITBUCKET_ENV_FILE"] = str(config.bitbucket_env_file)

    return [
        ServerSpec(
            name="tto-atlassian",
            command=config.atlassian_mcp_command,
            args=[str(config.atlassian_mcp_script)],
            env=atlassian_env,
        ),
        ServerSpec(
            name="tto-bitbucket",
            command=config.bitbucket_mcp_command,
            args=[str(config.bitbucket_mcp_script)],
            env=bitbucket_env,
        ),
    ]


class McpClientSession:
    """One session per ingestion run.

    Opened before any resource is attempted, so a spawn failure, a missing binary or a
    bad credential surfaces once - rather than as ten resource failures that each look
    like an unrelated network problem. The operator debugs one cause, not nine
    symptoms.
    """

    __slots__ = ("_specs", "_logger", "_timeout", "_processes", "_unavailable", "_request_id")

    def __init__(
        self,
        specs: list[ServerSpec],
        logger: Logger,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._specs = {spec.name: spec for spec in specs}
        self._logger = logger
        self._timeout = timeout_seconds
        self._processes: dict[str, subprocess.Popen] = {}
        self._unavailable: dict[str, str] = {}
        self._request_id = 0

    # --- lifecycle --------------------------------------------------------

    def __enter__(self) -> "McpClientSession":
        for name, spec in self._specs.items():
            try:
                self._processes[name] = self._spawn(spec)
                self._logger.info("mcp server started", server=name)
            except (OSError, subprocess.SubprocessError) as exc:
                # Recorded rather than raised: one unreachable server should not
                # stop ingestion of the sources the other can still reach.
                self._unavailable[name] = str(exc)
                self._logger.warning("mcp server unavailable", server=name, error=str(exc)[:120])
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def _spawn(self, spec: ServerSpec) -> subprocess.Popen:
        # Neither server takes a credential in its environment any more - each
        # reads its own .env file - but the shape is kept: nothing is ever placed
        # in argv, where process arguments would be visible in `ps` to any user on
        # the machine, and that cannot be corrected retrospectively once a run has
        # happened.
        environment = dict(os.environ)
        environment.update(spec.env)
        return subprocess.Popen(
            [spec.command, *spec.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            text=True,
            bufsize=1,
        )

    def close(self) -> None:
        for name, process in self._processes.items():
            try:
                if process.stdin:
                    process.stdin.close()
                process.terminate()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
            self._logger.info("mcp server stopped", server=name)
        self._processes.clear()

    # --- calls ------------------------------------------------------------

    def is_available(self, server: str) -> bool:
        return server in self._processes and self._processes[server].poll() is None

    def unavailable_reason(self, server: str) -> str | None:
        return self._unavailable.get(server)

    def call(self, server: str, tool: str, arguments: dict[str, Any]) -> Result[Any]:
        """Invoke a tool on a spawned server.

        A general method by necessity - a transport that cannot name a tool cannot be
        a transport. The read-only posture is contained above this, at the P2 source
        protocols, which declare no write operation. A test asserts that A3 and A4
        name no write tool anywhere in their source.
        """
        if not self.is_available(server):
            reason = self._unavailable.get(server, "server is not running")
            return err(
                ErrorCode.FAILED_MCP_UNREACHABLE,
                f"{server} is unavailable: {reason}",
                remediation=(
                    f"Check the TAAS_*_MCP_SCRIPT path for {server} in .env, and that "
                    "its own .env file has the values it needs."
                ),
                server=server,
            )

        process = self._processes[server]
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }

        try:
            assert process.stdin and process.stdout
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            line = self._read_with_timeout(process)
        except (OSError, BrokenPipeError) as exc:
            return err(
                ErrorCode.FAILED_MCP_UNREACHABLE, f"{server} transport failed: {exc}",
                server=server, tool=tool,
            )
        except TimeoutError:
            return err(
                ErrorCode.FAILED_TIMEOUT,
                f"{server}/{tool} exceeded {self._timeout}s",
                remediation="Narrow the request, or raise TAAS_MCP_TIMEOUT_SECONDS.",
                server=server, tool=tool,
            )

        if not line:
            return err(ErrorCode.FAILED_MCP_UNREACHABLE, f"{server} closed the connection",
                       server=server, tool=tool)
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            return err(ErrorCode.FAILED_MCP_UNREACHABLE, f"{server} returned malformed JSON",
                       server=server, tool=tool)

        if "error" in response:
            # JSON-RPC-level failure: the transport or the method itself is wrong
            # (unknown method, bad params). Distinct from a tool reporting its own
            # failure below - this is the protocol refusing the call outright.
            detail = response["error"].get("message", "unknown error")
            return err(ErrorCode.FAILED_MCP_UNREACHABLE, f"{server}/{tool}: {detail}",
                       server=server, tool=tool)

        result = response.get("result", {})
        if result.get("isError"):
            # An MCP tool call that runs and then reports its own failure - "repo
            # not found", a bad path - carries no structuredContent at all, only
            # a text explanation in content[0]. Nothing checked this before, so a
            # failed call was silently treated as ok({}) - a not-found repository
            # read as zero commits rather than as the failure it was.
            blocks = result.get("content") or []
            detail = blocks[0].get("text", "") if blocks else ""
            return err(
                ErrorCode.FAILED_INTERNAL,
                f"{server}/{tool}: {detail or 'the tool reported a failure'}",
                server=server, tool=tool,
            )

        # The MCP result envelope is {content, structuredContent, isError} - not
        # the tool's own payload. Every adapter (Atlassian and Bitbucket alike)
        # is written against the structured payload directly ("commits", "repos",
        # "issues", ...), so unwrapping happens once, here, rather than in every
        # adapter method that calls this transport.
        return ok(result.get("structuredContent") or {})

    def _read_with_timeout(self, process: subprocess.Popen) -> str:
        """Read one line, bounded by the timeout.

        `select` is used rather than a thread because the timeout must classify the
        failure as transient for U1's retry policy, and a thread that outlives the
        call would leak across the retry attempts.
        """
        import select

        assert process.stdout
        ready, _, _ = select.select([process.stdout], [], [], self._timeout)
        if not ready:
            raise TimeoutError
        return process.stdout.readline()
