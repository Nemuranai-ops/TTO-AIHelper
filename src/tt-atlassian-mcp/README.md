# Atlassian MCP server — Confluence + Jira

A single-file MCP server exposing 10 Confluence and Jira tools to GitHub Copilot
in VS Code (or any other MCP client). Auth reuses the pmo-inline agent's scheme:
HTTP Basic with `ATLASSIAN_EMAIL` + `ATLASSIAN_API_TOKEN` from `.env`.

**Only `requests` is required.** The MCP protocol is implemented directly rather
than via the MCP SDK, so there is no heavy dependency tree to install on a
locked-down corporate machine.

## Install (office PC)

```powershell
# 1. Copy this folder somewhere stable, e.g. C:\tools\tt-atlassian-mcp
pip install requests

# 2. Create your .env
copy .env.example .env
notepad .env          # fill in base URL, email, API token

# 3. Verify credentials and connectivity BEFORE wiring into VS Code
python atlassian_mcp_server.py --selftest
```

`--selftest` runs an offline **shape check** first — it pushes a canned payload
through the simplifiers every tool answer passes through, so a damaged file is
reported as damaged rather than as a network problem, with no credentials
needed. Then it checks Jira auth, Jira search, Confluence v2 and Confluence CQL
independently, and tells you which one failed. Get this passing first — almost
every problem shows up here rather than inside VS Code.

## Wire into VS Code Copilot

Copy `mcp.json.example` to `.vscode/mcp.json` in your workspace (or use
**MCP: Open User Configuration** for a global one), and fix the path in `args`.
Prefer `mcp.json.prompt-for-token.example` if you would rather VS Code prompt
for the token than keep it in a file.

Then: **MCP: List Servers** → `atlassian` → Start. The 10 tools appear in the
Copilot Chat tool picker (agent mode).

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `confluence_get_page` | read | Page by id, or title + space key. Returns readable text (tables become pipe rows), metadata and labels. |
| `confluence_search` | read | CQL, or convenience `text` / `space_key` / `label` / `title`. |
| `confluence_create_page` | write | New page in a space, optionally under a parent. |
| `confluence_update_page` | write | `replace` / `append` / `prepend`. Reads current version first. |
| `jira_search_issues` | read | JQL → simplified issue records. Cursor pagination. |
| `jira_get_issue` | read | One issue with description + comments, ADF flattened to text. |
| `jira_create_issue` | write | Plain text description auto-converted to ADF. |
| `jira_update_issue` | write | Fields, plus `labels_set` / `labels_add` / `labels_remove`. |
| `jira_get_transitions` | read | Available transitions with ids, target status, required fields. |
| `jira_transition_issue` | write | Accepts transition id, transition name, or target status name. |

`python atlassian_mcp_server.py --list-tools` prints every argument.

### Jira queries must be bounded

This Jira rejects unbounded JQL: every search needs at least one restricting
clause, and `ORDER BY` alone is not one.

```
project = SMP AND labels = "MC" ORDER BY updated DESC    works
created >= -30d ORDER BY created DESC                    works
ORDER BY created DESC                                    400 Unbounded
```

When it happens, the error names two valid rewrites of your own query.

### Getting values by tag

Tags are **Jira labels** and **Confluence labels**:

```
jira_search_issues   jql = project = SMP AND labels = "MC" ORDER BY updated DESC
confluence_search    label = "MC", space_key = "SMP"
```

For custom fields, pass `fields: ["*all"]` to `jira_get_issue` once to discover
the `customfield_xxxxx` id, then request it by name from then on.

## Defaults match pmo-inline

Two defaults are set for this corporate network specifically:

| Setting | Default | Why |
|---|---|---|
| `ATLASSIAN_VERIFY_TLS` | **false** | The proxy re-signs certificates with a CA that is not in the system trust store. Verification fails with *self-signed certificate in certificate chain*. pmo-inline passes `verify=False` on every call for the same reason. |
| `ATLASSIAN_READ_ONLY` | **true** | The five create/update/transition tools refuse; the five read tools work. |

To turn verification back on you need the proxy CA:

```
REQUESTS_CA_BUNDLE=C:\path\to\mbkproxy-ca.pem
ATLASSIAN_VERIFY_TLS=true
```

To allow writes: `ATLASSIAN_READ_ONLY=false`.

## APIs used

| Area | API | Endpoint |
|---|---|---|
| Confluence pages | REST **v2**, falling back to **v1** | `/wiki/api/v2/pages`, else `/wiki/rest/api/content` |
| Confluence search | REST **v1** | `/wiki/rest/api/search` — CQL has no v2 equivalent |
| Jira issues | REST **v3** | `/rest/api/3/issue` |
| Jira search | REST **v3** | `/rest/api/3/search/jql` — the old `/rest/api/3/search` was removed |

Jira v3 returns rich text as Atlassian Document Format. The server flattens ADF
to readable text on read, and converts plain text / light markdown (`#`, `-`,
`1.`, ``` fences) to ADF on write.

## Confluence v1 fallback

Some tenants and corporate gateways do not expose `/wiki/api/v2`. The pmo-inline
agent has been running against `/wiki/rest/api/content` for a long time, so v1 is
the known-good path here.

Default is `auto`: try v2, and on 401/403/404/405/410/501 fall back to v1 and
remember that for the rest of the session. Pin it if you already know:

```
ATLASSIAN_CONFLUENCE_API=v1     # skip the probe, go straight to v1
```

`--selftest` reports both versions separately, so you can see which one your
account can actually reach. Only a failure of *both* is fatal.

## Corporate proxy

A gateway such as McAfee Web Gateway will intercept **even 127.0.0.1** if
`HTTP_PROXY` is set and `NO_PROXY` does not exclude loopback - it answers with
its own HTML page and the client sees a 502. This server therefore always adds
`127.0.0.1,localhost,::1` to `NO_PROXY` before creating its session.

If a gateway answers instead of Atlassian, the error says so by name rather than
dumping HTML at you. Set `ATLASSIAN_PROXY` if the system proxy is not picked up
automatically.

## Behaviour worth knowing

- **Confluence updates are version-safe.** The current version is read, then
  written back as `version + 1`. A concurrent edit returns HTTP 409, which the
  server retries once against the fresh version rather than clobbering it. The
  fetched title is always reused — sending a different one trips Confluence's
  "page with this title already exists" error.
- **`mode=append` preserves existing content.** Only `mode=replace` overwrites.
- **429 and 5xx are retried** with backoff, honouring `Retry-After`.
- **Large results are truncated** at `ATLASSIAN_MAX_CHARS` (default 40 000) with
  a visible marker, so one huge page cannot swamp the model's context.
- **Jira search always sends an explicit field list** — `/search/jql` returns
  only `id` and `key` otherwise.
- **Secrets never reach stdout.** All logging goes to stderr; stdout carries
  JSON-RPC only.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `401` | `ATLASSIAN_EMAIL` must be the account email and the token an API token from id.atlassian.com — not your password. |
| `403` | Authenticated but no rights on that project/space. |
| `404` on a page id | The id is the number in the URL after `/pages/`. |
| TLS handshake failed | Corporate proxy re-signing certs. Point `REQUESTS_CA_BUNDLE` at the proxy CA; `ATLASSIAN_VERIFY_TLS=false` is the last resort. |
| Server won't start in VS Code | Run `--selftest` first. Then check `python` is on PATH — use a full interpreter path in `args` if not. |
| `AttributeError: 'dict' object has no attribute 'Get'` (or any capitalised method) on **every** call | The copy VS Code runs is damaged — an editor capitalised `.get(` to `.Get(`. The file still imports, so the server starts and only fails at the first tool call. `--selftest` names it as a shape failure. Fix or re-paste, then **restart the server** — VS Code keeps the old process, so the error looks identical until it reloads. |
| Confluence CQL warning in selftest | Only `confluence_search` is affected; everything else still works. |

## Testing status

Verified locally against a mock Atlassian API: the MCP handshake and all
protocol paths, every tool's request shape, 429 retry, version-safe page
updates, ADF conversion both directions, Confluence table rendering, error
mapping and read-only enforcement.

Not yet run against the real site — `--selftest` is the first thing to run on
the office PC.
