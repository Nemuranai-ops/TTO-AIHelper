# Tech Stack Decisions — U2 Ingestion and Analysis

**Phase**: CONSTRUCTION | **Unit**: U2 | **Stage**: NFR Requirements
**Version**: 1.0 | **Date**: 2026-08-29

---

## Summary

U2 adds **one** dependency to the U1 stack: the MCP SDK's client side, which is part
of the `mcp` package already pinned.

| Concern | Decision | New? |
|---|---|---|
| MCP client | `mcp` SDK client, stdio transport to the existing servers | No — same package |
| YAML parsing | `yaml.safe_load` from PyYAML | **Yes** — one addition |
| OpenAPI parsing | Plain dict traversal of the parsed YAML or JSON | No |
| Everything else | Inherited from U1 | No |

**PyYAML is the only addition**, and it is a **direct** dependency.

An earlier draft of this document claimed it arrived transitively via the MCP SDK.
That was wrong: `mcp` requires anyio, httpx, httpx-sse, pydantic, pydantic-settings,
sse-starlette, starlette and uvicorn — no YAML parser among them. The error surfaced
at the first import during code generation, which is the cheap place for it to
surface; asserting a dependency graph without checking it is how a lockfile ends up
disagreeing with the documentation that explains it.

---

## The Toolchain as an MCP Client

Application Design Q3 put bulk ingestion in the toolchain. That means `tto-testgen` is
both an MCP **server** (to the agent) and an MCP **client** (to Atlassian and
Bitbucket).

| Aspect | Decision |
|---|---|
| Transport | stdio, launching the same server binaries the agent's `mcp.json` registers |
| Lifetime | One client session per ingestion run, closed on completion |
| Credentials | From `Config`, passed as environment to the child process |
| Failure | Connection or spawn failure becomes `FAILED_MCP_UNREACHABLE`, retried under U1's policy |

**One session per run, not per call.** Spawning a server process per Jira issue would
dominate the runtime of a 500-issue ingestion. One session per run is the natural
boundary: it matches the resource isolation and closes cleanly on failure.

**This does not weaken NFR-SEC-02.** U2 opens no listener — it is a client. The
prohibition is on the toolchain accepting connections, not on it making them.

---

## OpenAPI Parsing

**Plain dict traversal**, not a spec library.

| Considered | Outcome |
|---|---|
| **Plain traversal** | **Chosen** — we need paths, methods, request and response shapes, status codes and security. Reading those from a parsed dict is a page of code |
| `openapi-spec-validator` | Rejected — validates conformance, which is not the question. An imperfect spec is still useful to us, and rejecting it would discard information |
| `prance` / `openapi-core` | Rejected — resolves `$ref` and builds a full object model. Substantially more dependency for a fraction more than we use |

**Rejecting the validator matters more than it looks.** A spec that fails validation
is still evidence of intended shapes, and BR-U2-5 already treats the spec as advisory
about shapes and never authoritative about existence. A validator would let us discard
a spec the code disagrees with — which is precisely the case where the discrepancy is
worth recording.

`$ref` resolution is handled by a small local resolver limited to same-document
references. Cross-document `$ref` is recorded as unresolved rather than fetched: a
spec that pulls in a remote document is a network fetch from an untrusted URL, and
that is not a capability worth having.

---

## YAML Safety

Both the Figma manifest and any OpenAPI spec are parsed with `yaml.safe_load`.

`safe_load` cannot instantiate arbitrary Python types. `yaml.load` with the default
loader can, which makes a YAML file from a shared folder or a repository a code
execution vector.

The manifest is an obvious untrusted input. **The spec is the easy one to miss** — it
arrives through a code path that feels internal, having come from "our own"
repository. It is a file that anyone with commit access can change.

---

## Rejected Alternatives

| Alternative | Why rejected |
|---|---|
| HTTP clients direct to Jira and Bitbucket | The MCP servers exist and are already the agent's path. A second integration would duplicate auth, paging and error handling, and the two would drift |
| Async MCP client | U1 declined async; U2-NFR-PRF-02 explains why sequential holds here |
| Caching responses on disk | The content hash already prevents refetching unchanged artefacts. A response cache would add invalidation for the same benefit |
| A Jira client library | The Atlassian MCP already normalises ADF to text and flattens tables. Bypassing it would mean reimplementing that |
