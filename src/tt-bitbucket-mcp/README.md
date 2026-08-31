# Bitbucket MCP - read-only access to cloned repositories

Eight tools that answer questions about Bitbucket repositories from the clones
on disk: what changed in a release, which commits carry Jira keys, where a
feature lives in the code, what the endpoints are, and what a file said at any
ref.

This is the repository half of `corpus-mcp`, extracted and made standalone.
**There is no SQLite store here** - no test-case corpus, no dedupe, no impact
scoring. Every tool answers from the clone and returns the answer inline.

**No dependencies at all** - stdlib Python. Nothing to install on a locked-down
corporate machine.

## The read-only guarantee

Every git call goes through an allowlist. Only these subcommands can run:

```
log  diff  show  ls-files  ls-tree  rev-parse  rev-list  cat-file  describe
shortlog  blame  for-each-ref  merge-base  name-rev  status  tag  branch
diff-tree  grep
```

`checkout`, `reset`, `clean`, `commit`, `push`, `pull`, `fetch`, `merge`,
`rebase`, `stash`, `remote`, `worktree`, `update-ref`, `config` and everything
else are absent from the set and refused. `tag` and `branch` are further
restricted to list mode, because `git tag <name>` would *create* a tag. Flags
that write outside the query (`--output`, `--git-dir`, `-c`, ...) are rejected
anywhere in the argument list. Commands run with `GIT_OPTIONAL_LOCKS=0`, so the
index is never even refreshed.

Two things make this stronger than a convention:

- **There is no write tool to grant.** All eight tools declare `readOnlyHint`,
  and the test suite asserts that none of them ever stops doing so.
- **`--selftest` actively verifies the guard** rather than trusting it, and the
  test suite fires 37 mutating commands at it and asserts the working tree is
  byte-identical afterwards.

`grep` is the one addition to corpus-mcp's allowlist: searching tracked content
is a read, and `bitbucket_grep` needs it.

## Install

```powershell
copy .env.example .env      # set BITBUCKET_REPO_ROOT to where your clones live
python bitbucket_mcp_server.py --selftest
```

Then copy `mcp.json.example` to `.vscode/mcp.json`, fix the paths, and start it
from **MCP: List Servers**.

## Tools

| Tool | What it does |
|---|---|
| `bitbucket_repos` | The clones this server can read: branch, head commit, tag count, and the Bitbucket project key, repo slug and browse URL where the remote is recognisable. **Start here.** |
| `bitbucket_log` | Commit history for a ref or range, with Jira keys and the key-coverage percentage. Filters: `since`, `until`, `author`, `grep`, `path`. |
| `bitbucket_tags` | Tags newest-first by commit topology. Use it to pick the two refs to compare. |
| `bitbucket_changes` | Files and commits across a range, Jira keys, coverage percentage, busiest directories. Range by **refs** (`base`/`head`) or by **dates** (`since`/`until`). |
| `bitbucket_diff` | The diff itself, over the same ref-or-date range: `mode=stat` (default), `names`, or `patch` - and `patch` also reports the changed line ranges per file. |
| `bitbucket_file` | A tracked file's contents at any ref, with line numbers, optionally a line window. |
| `bitbucket_grep` | Search tracked content at a ref: file, line, matching text, and which files match most. |
| `bitbucket_endpoints` | HTTP endpoints (C#, Java/Spring, Express, Flask/FastAPI) with method, route, file, line and defining symbol, plus any OpenAPI spec found. |

`python bitbucket_mcp_server.py --list-tools` prints every argument.

## The workflow

```
1. bitbucket_repos                          which clones are readable
2. bitbucket_tags     repo=messaging-center the two refs to compare
3. bitbucket_changes  v6.0..v6.1            what the release contains
   bitbucket_changes  since=2026-03-01      ... or the same by date range
4. bitbucket_diff     mode=patch path=...   what actually changed in it
5. bitbucket_grep / bitbucket_file          where the behaviour lives
6. bitbucket_endpoints                      the API surface, and the spec
```

## Date ranges

`bitbucket_changes` and `bitbucket_diff` take a range as refs **or** as dates.
Anything git understands as a date works:

```
bitbucket_changes repo=messaging-center since="2026-01-01"
bitbucket_changes repo=messaging-center since="3 months ago"
bitbucket_changes repo=messaging-center since="2026-03-01" until="2026-07-01"
bitbucket_diff    repo=messaging-center since="last monday" mode=names
```

Four things are worth knowing before you quote a date-ranged answer.

**A date is resolved to a real commit, and the resolution is reported.** A date
range is only ever an approximation of a commit range, so every answer shows
which commits it actually became:

```
  window : base = last commit before 2026-03-01 (484e74ac69, 2026-01-15)
```

**Both dates are exclusive at midnight**, which is what `--before` means to git.
`since=2026-01-01` includes commits made on 1 January, because the base becomes
the last commit *before* that date. `until=2026-06-30` stops at the end of 29
June - pass the following day to include a whole day.

**`base` and `since` cannot be combined.** They both decide where the range
starts, so passing both is refused rather than silently preferring one. `head`
and `until` do combine: `until` narrows whichever head you named to the last
commit before that date.

**A `since` that predates the whole history** falls back to the root commit and
says so - and says that the root commit's own contents are not counted as
changes, because a commit with no parent has nothing to be diffed against.

With neither a base nor a since, base defaults to the most recent tag
**reachable from head**, not simply the newest tag in the repository. That
distinction matters with `until`: the newest tag may sit after the resolved
head, which would invert the range and report every change backwards.

## Jira-key coverage decides how much the history is worth

`bitbucket_log` and `bitbucket_changes` both report what percentage of commits
carry a Jira key, because that number decides whether commit messages can link
code to test cases at all:

- **above 50%** - the key strategy carries the analysis; selections are strong.
- **50% or below** - the tools say so explicitly in their output, and any answer
  built on those commits should repeat the caveat rather than presenting the
  ranking as solid.

## Bitbucket coordinates are best-effort

The origin URL is read from `.git/config` **as a file**, because `git config`
can write and is therefore not on the allowlist. Parsing it gives the project
key, repo slug and a browse URL:

| Remote | Browse URL |
|---|---|
| `ssh://git@host:7999/SMP/repo.git` | `https://host/projects/SMP/repos/repo` |
| `https://host/scm/smp/repo.git` | `https://host/projects/SMP/repos/repo` |
| `git@bitbucket.org:acme/repo.git` | `https://bitbucket.org/acme/repo` |

Anything else returns blanks rather than a guess. Commit URLs are built as
`<browse>/commits/<sha>`, which is the same suffix on Server and Cloud. Treat
these as convenience links, not verified endpoints - the server never contacts
Bitbucket to check them.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `BITBUCKET_REPO_ROOT` | - | Where the clones live; `repo` may then be a bare folder name. Several paths may be joined with the OS path separator. |
| `CORPUS_REPO_ROOT` | - | Accepted as a fallback when `BITBUCKET_REPO_ROOT` is unset, so this server and corpus-mcp can share one setting rather than duplicating the path to the same clones. |
| `BITBUCKET_MAX_CHARS` | 40000 | Response size cap, applied with a visible truncation marker. |
| `BITBUCKET_GIT_TIMEOUT` | 120 | Seconds before a git command is abandoned. |
| `BITBUCKET_ENV_FILE` | - | Explicit path to the `.env` file. |

No credentials are needed or read. This server never contacts Bitbucket over
the network - it only reads clones that are already on disk, so it works
offline and behind any proxy.

## Running it beside corpus-mcp

The tools are named `bitbucket_*` precisely so both servers can run at once
without a collision: corpus-mcp keeps `repo_index`, `repo_changes`,
`impact_analyze` and `impact_backtest`, and those still do the things this
server deliberately does not.

| Question | Server |
|---|---|
| What changed in this release? | either - `bitbucket_changes` is the lighter answer |
| Which test cases does that change affect? | corpus-mcp (`impact_analyze`) |
| Where does this feature live in the code? | this one (`bitbucket_grep`) |
| What are the endpoints, and is there a spec? | either - this one returns them inline, corpus-mcp stores them for impact analysis |
| How healthy is the test suite? | corpus-mcp |

If you only need to read repositories, run this one alone and skip the
database entirely.

## Limits worth knowing

- **Endpoint line numbers come from the checked-out revision.** The scan reads
  files from the working tree, not from a ref, so results describe whatever is
  currently checked out.
- **Only HTTP endpoints are recognised.** Message handlers, scheduled jobs and
  UI components are not, and a repository using another framework needs
  `ROUTE_PATTERNS` extended.
- **`bitbucket_grep` uses basic git regular expressions**, not PCRE. Prefer a
  plain substring unless you know the syntax.
- **`bitbucket_diff mode=patch` can be enormous.** Narrow with `path` first; the
  response is truncated at `BITBUCKET_MAX_CHARS` with a visible marker, and the
  marker is the only signal that you did not see everything.
- **Nothing is cached.** Every call re-runs git, so a large repository costs the
  same on the tenth call as on the first. corpus-mcp's `repo_index` exists
  precisely because storing that scan is sometimes worth it.
- **Coordinates come from a local file.** If the clone's origin is a mirror or a
  local path, the project and slug will reflect that, not the real Bitbucket
  location.

## Testing status

Verified locally against purpose-built repositories:

```powershell
cd tests
python test_guards.py   # 37 mutating git commands refused, MCP protocol, no tool writes
python test_tools.py    # all eight tools end-to-end against a built repo
```

Both end with a `PASSED` line, and both assert the working tree is unchanged
afterwards - the guarantee that matters most for a team with read-only access.

Not yet run against the real Bitbucket clones. `--selftest` is the first thing
to run on the office PC.
