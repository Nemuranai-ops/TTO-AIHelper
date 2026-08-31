#!/usr/bin/env python
"""Bitbucket MCP server  -  read-only access to cloned Bitbucket repositories.

Built for a TEST TEAM with READ-ONLY access to the application repositories.
Nothing in this server can write to a git repository or change a working tree:
every git call goes through an allowlist that permits only read subcommands,
mutating flags are rejected outright, and there is no write tool to grant.

This is the repository half of corpus-mcp, extracted and made standalone. There
is no SQLite store, no test-case corpus and no impact scoring here  -  every
tool answers from the clone itself and returns the answer inline.

Eight tools:

    bitbucket_repos      bitbucket_log        bitbucket_tags
    bitbucket_changes    bitbucket_diff       bitbucket_file
    bitbucket_grep       bitbucket_endpoints

Ranges can be given as refs (base..head) or as dates (since/until). A date is
resolved to a real commit and the resolution is always reported.

No third-party packages are required at all  -  stdlib only, so it runs on a
locked-down machine.

Run modes:
    python bitbucket_mcp_server.py                 # serve MCP over stdio
    python bitbucket_mcp_server.py --selftest      # check git + guard + clones
    python bitbucket_mcp_server.py --list-tools    # print tool schemas
    python bitbucket_mcp_server.py --call bitbucket_repos '{}'
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

SERVER_NAME = "bitbucket-mcp"
SERVER_VERSION = "1.0.0"
SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]


def log(message: str) -> None:
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


class ToolError(Exception):
    """Reported to the model as isError, not a crash."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_environment() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("BITBUCKET_ENV_FILE", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    here = Path(__file__).resolve().parent
    candidates += [here / ".env", Path.cwd() / ".env", here.parent / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if not os.environ.get(key, "").strip():
                os.environ[key] = value.strip().strip('"').strip("'")
        return path
    return None


class Config:
    def __init__(self) -> None:
        # BITBUCKET_REPO_ROOT is preferred; CORPUS_REPO_ROOT is accepted as a
        # fallback so this server can share one setting with corpus-mcp rather
        # than duplicating the path to the same clones.
        roots = (os.environ.get("BITBUCKET_REPO_ROOT", "").strip()
                 or os.environ.get("CORPUS_REPO_ROOT", "").strip())
        self.repo_roots = [Path(p.strip()) for p in roots.split(os.pathsep) if p.strip()]
        self.max_chars = int(os.environ.get("BITBUCKET_MAX_CHARS", "").strip() or 40000)
        self.git_timeout = int(os.environ.get("BITBUCKET_GIT_TIMEOUT", "").strip() or 120)


CONFIG = Config()


def truncate(text: str, limit: int | None = None) -> str:
    cap = limit or CONFIG.max_chars
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n\n... [truncated: {len(text):,} chars, showing first {cap:,}]"


# ---------------------------------------------------------------------------
# The read-only guarantee
# ---------------------------------------------------------------------------

# `grep` is here and is not in corpus-mcp's set: searching tracked content is a
# read, and bitbucket_grep needs it. Everything else matches corpus-mcp exactly.
GIT_READ_ONLY = {
    "log", "diff", "show", "ls-files", "ls-tree", "rev-parse", "rev-list",
    "cat-file", "describe", "shortlog", "blame", "for-each-ref", "merge-base",
    "name-rev", "status", "tag", "branch", "diff-tree", "grep",
}

# Rejected anywhere in the argument list, including after `--`.
GIT_FORBIDDEN_FLAGS = {
    "--output", "-o", "--git-dir", "--work-tree", "--exec-path", "-c",
    "--upload-pack", "--receive-pack", "--config-env", "--namespace",
}

# `git tag <name>` CREATES a tag and `git branch <name>` creates a branch, so
# these two are only allowed in explicit list mode.
GIT_LIST_ONLY = {"tag", "branch"}


def run_git(repo: Path, args: list[str], allow_status: tuple[int, ...] = (0,)) -> str:
    """Run one read-only git command. Raises ToolError on anything questionable.

    allow_status exists for `git grep`, which exits 1 to mean "no matches" -
    an answer, not a failure.
    """
    if not args:
        raise ToolError("No git arguments given.")
    subcommand = args[0]
    if subcommand not in GIT_READ_ONLY:
        raise ToolError(
            f"git '{subcommand}' is not permitted. This server only runs read-only git "
            f"commands ({', '.join(sorted(GIT_READ_ONLY))}) so it can never modify a "
            f"repository the test team has read access to."
        )
    for arg in args:
        base = arg.split("=", 1)[0]
        if base in GIT_FORBIDDEN_FLAGS:
            raise ToolError(f"git flag {base!r} is not permitted (it can write outside the query).")
    if subcommand in GIT_LIST_ONLY:
        positional = [a for a in args[1:] if not a.startswith("-")]
        listing = any(a in ("--list", "-l") or a.startswith("--list=") for a in args[1:])
        if positional and not listing:
            raise ToolError(
                f"git {subcommand} with a name would create a {subcommand}. "
                f"Use --list to enumerate instead."
            )

    repo = repo.expanduser().resolve()
    if not (repo / ".git").exists():
        raise ToolError(f"{repo} is not a git repository (no .git found).")

    env = dict(os.environ)
    env.update({
        "GIT_TERMINAL_PROMPT": "0",   # never block on credentials
        "GIT_OPTIONAL_LOCKS": "0",    # do not take locks or refresh the index
        "GIT_PAGER": "cat",
        "LC_ALL": "C",
    })
    try:
        result = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=str(repo), env=env, capture_output=True, text=True,
            timeout=CONFIG.git_timeout, shell=False,
        )
    except FileNotFoundError as error:
        raise ToolError("git is not on PATH.") from error
    except subprocess.TimeoutExpired as error:
        raise ToolError(f"git {subcommand} timed out after {CONFIG.git_timeout}s.") from error

    if result.returncode not in allow_status:
        raise ToolError(f"git {' '.join(args)} failed: {(result.stderr or '').strip()[:500]}")
    return result.stdout


# ---------------------------------------------------------------------------
# Repository helpers
# ---------------------------------------------------------------------------

def resolve_repo(repo: str) -> Path:
    """Accept an absolute path, or a repo name found under BITBUCKET_REPO_ROOT."""
    if not repo:
        raise ToolError(
            "repo is required  -  an absolute path, or a folder name under "
            "BITBUCKET_REPO_ROOT. Call bitbucket_repos to see what is available."
        )
    candidate = Path(repo).expanduser()
    if candidate.is_dir():
        return candidate.resolve()
    for root in CONFIG.repo_roots:
        option = (root / repo).expanduser()
        if option.is_dir():
            return option.resolve()
    searched = ", ".join(str(r) for r in CONFIG.repo_roots) or "(BITBUCKET_REPO_ROOT unset)"
    raise ToolError(f"Repository {repo!r} not found. Looked at that path and under: {searched}")


def ordered_tags(root: Path) -> list[str]:
    """Tags newest-first by commit topology, not by date.

    Tags created in the same second tie under --sort=creatordate and can come
    back reversed, which would silently invert every base..head range. Ordering
    by position in the commit history is unambiguous.
    """
    order = {sha: i for i, sha in enumerate(run_git(root, ["log", "--pretty=%H"]).split())}
    rows = run_git(root, ["for-each-ref", "--format=%(refname:short)%09%(objectname)%09%(*objectname)",
                          "refs/tags"]).splitlines()
    tags: list[tuple[int, str]] = []
    for row in rows:
        parts = row.split("\t")
        if not parts or not parts[0].strip():
            continue
        name = parts[0].strip()
        sha = (parts[2].strip() if len(parts) > 2 and parts[2].strip() else
               (parts[1].strip() if len(parts) > 1 else ""))
        if sha in order:
            tags.append((order[sha], name))
    tags.sort()
    return [name for _index, name in tags]


JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

REMOTE_URL_RE = re.compile(r"^\s*url\s*=\s*(\S+)\s*$", re.M)


def remote_url(root: Path) -> str:
    """Origin URL, read from .git/config as a file.

    `git config` is not on the allowlist  -  it can write  -  so the file is
    parsed directly. That is still a read and needs no git subprocess at all.
    """
    config = root / ".git" / "config"
    if not config.is_file():
        return ""
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    section = ""
    fallback = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            continue
        match = REMOTE_URL_RE.match(line)
        if not match:
            continue
        if section.replace('"', "") == "remote origin":
            return match.group(1)
        if section.startswith("remote") and not fallback:
            fallback = match.group(1)
    return fallback


def bitbucket_coordinates(url: str) -> dict:
    """Best-effort project/slug/browse URL from a Bitbucket remote.

    Handles Server/Data Center (/scm/PROJ/slug.git, ssh://host:7999/PROJ/slug.git)
    and Cloud (bitbucket.org/workspace/slug.git). Anything else returns blanks
    rather than a guess.
    """
    empty = {"host": "", "project": "", "slug": "", "web_url": ""}
    if not url:
        return empty
    cleaned = url.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    scp = re.match(r"^(?:ssh://)?(?:[^@/]+@)?([^:/]+)[:/](.+)$", cleaned)
    if cleaned.startswith(("http://", "https://")):
        without = re.sub(r"^https?://(?:[^@/]+@)?", "", cleaned)
        host, _, path = without.partition("/")
    elif scp:
        host, path = scp.group(1), scp.group(2)
        host = re.sub(r":\d+$", "", host)
    else:
        return empty

    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0].lower() == "scm":
        project, slug = parts[1], parts[2]
    elif len(parts) >= 2:
        project, slug = parts[-2], parts[-1]
    else:
        return {**empty, "host": host}

    if "bitbucket.org" in host.lower():
        web = f"https://{host}/{project}/{slug}"
    else:
        web = f"https://{host}/projects/{project.upper()}/repos/{slug}"
    return {"host": host, "project": project, "slug": slug, "web_url": web}


def commit_url(web: str, sha: str) -> str:
    return f"{web}/commits/{sha}" if web and sha else ""


def repo_summary(root: Path) -> dict:
    """One clone's identity. Every call here is read-only."""
    try:
        branch = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except ToolError:
        branch = ""
    try:
        head = run_git(root, ["log", "-1", "--pretty=%h%x1f%ad%x1f%an%x1f%s", "--date=short"]).strip()
        sha, date, author, subject = (head.split("\x1f") + ["", "", "", ""])[:4]
    except ToolError:
        sha = date = author = subject = ""
    try:
        tag_count = len([t for t in run_git(root, ["tag", "--list"]).splitlines() if t.strip()])
    except ToolError:
        tag_count = 0
    url = remote_url(root)
    coords = bitbucket_coordinates(url)
    return {
        "repo": root.name, "path": str(root), "branch": branch,
        "head_sha": sha, "head_date": date, "head_author": author, "head_subject": subject,
        "tags": tag_count, "remote": url, **coords,
        "head_url": commit_url(coords["web_url"], sha),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def bitbucket_repos(root: str = "", limit: int = 50) -> tuple[str, dict]:
    roots = [Path(root).expanduser()] if root else list(CONFIG.repo_roots)
    if not roots:
        raise ToolError(
            "No repository root configured. Set BITBUCKET_REPO_ROOT (or CORPUS_REPO_ROOT) "
            "to the folder holding your clones, or pass root explicitly."
        )

    found: list[dict] = []
    missing: list[str] = []
    for base in roots:
        base = base.expanduser()
        if not base.is_dir():
            missing.append(str(base))
            continue
        if (base / ".git").exists():
            found.append(repo_summary(base.resolve()))
            continue
        for child in sorted(base.iterdir()):
            if len(found) >= limit:
                break
            if child.is_dir() and (child / ".git").exists():
                found.append(repo_summary(child.resolve()))

    data = {"roots": [str(r) for r in roots], "missing_roots": missing,
            "count": len(found), "repos": found}
    lines = [f"Clones found: {len(found)}"]
    for item in found:
        lines.append("")
        lines.append(f"  {item['repo']}  ({item['branch'] or 'detached'})")
        lines.append(f"    path   : {item['path']}")
        if item["remote"]:
            lines.append(f"    remote : {item['remote']}")
        if item["project"]:
            lines.append(f"    bitbucket: project {item['project']} / repo {item['slug']}")
        if item["web_url"]:
            lines.append(f"    browse : {item['web_url']}")
        if item["head_sha"]:
            lines.append(f"    head   : {item['head_sha']} {item['head_date']} "
                         f"{item['head_author']}  {item['head_subject'][:70]}")
        lines.append(f"    tags   : {item['tags']}")
    for path in missing:
        lines.append(f"  WARN root does not exist: {path}")
    if not found:
        lines.append("  Nothing found. Check the root path, and that the clones have a .git folder.")
    return truncate("\n".join(lines)), data


def bitbucket_log(repo: str, base: str = "", head: str = "HEAD", since: str = "",
                  until: str = "", author: str = "", grep: str = "", path: str = "",
                  limit: int = 50) -> tuple[str, dict]:
    root = resolve_repo(repo)
    limit = max(1, min(int(limit or 50), 500))
    rng = f"{base}..{head}" if base else (head or "HEAD")

    args = ["log", "--pretty=%H%x1f%h%x1f%an%x1f%ad%x1f%s", "--date=short", f"-n{limit}"]
    if since:
        args += ["--since", since]
    if until:
        args += ["--until", until]
    if author:
        args += ["--author", author]
    if grep:
        args += ["--grep", grep, "-i"]
    args.append(rng)
    if path:
        args += ["--", path]

    commits: list[dict] = []
    keys: Counter = Counter()
    authors: Counter = Counter()
    web = bitbucket_coordinates(remote_url(root))["web_url"]
    for line in run_git(root, args).splitlines():
        bits = line.split("\x1f")
        if len(bits) < 5:
            continue
        found = JIRA_KEY_RE.findall(bits[4])
        keys.update(found)
        authors[bits[2]] += 1
        commits.append({"sha": bits[0], "short_sha": bits[1], "author": bits[2],
                        "date": bits[3], "subject": bits[4], "jira_keys": found,
                        "url": commit_url(web, bits[0])})

    tagged = sum(1 for c in commits if c["jira_keys"])
    coverage = (tagged * 100 // len(commits)) if commits else 0
    data = {"repo": root.name, "range": rng, "returned": len(commits), "limit": limit,
            "commits_with_jira_key": tagged, "jira_key_coverage_pct": coverage,
            "jira_keys": sorted(keys), "authors": authors.most_common(10),
            "commits": commits}

    lines = [f"{root.name}  {rng}" + (f"  -- {path}" if path else ""),
             f"  commits shown   : {len(commits)}" + (" (limit reached)" if len(commits) == limit else ""),
             f"  with a Jira key : {tagged} ({coverage}%)"]
    if keys:
        lines.append(f"  Jira keys       : {', '.join(sorted(keys)[:25])}")
    lines.append("")
    for item in commits:
        lines.append(f"  {item['short_sha']}  {item['date']}  {item['author'][:20]:<20}  {item['subject'][:80]}")
    if not commits:
        lines.append("  No commits matched. Widen the range or drop a filter.")
    return truncate("\n".join(lines)), data


def bitbucket_tags(repo: str, limit: int = 30, contains: str = "") -> tuple[str, dict]:
    root = resolve_repo(repo)
    limit = max(1, min(int(limit or 30), 500))
    detail: dict[str, dict] = {}
    rows = run_git(root, ["for-each-ref",
                          "--format=%(refname:short)%09%(objectname:short)%09%(creatordate:short)%09%(contents:subject)",
                          "refs/tags"]).splitlines()
    for row in rows:
        parts = (row.split("\t") + ["", "", "", ""])[:4]
        if parts[0].strip():
            detail[parts[0].strip()] = {"tag": parts[0].strip(), "sha": parts[1].strip(),
                                        "date": parts[2].strip(), "subject": parts[3].strip()}

    ordered = [t for t in ordered_tags(root) if not contains or contains.lower() in t.lower()]
    tags = [detail.get(name, {"tag": name, "sha": "", "date": "", "subject": ""}) for name in ordered[:limit]]

    data = {"repo": root.name, "total_tags": len(detail), "returned": len(tags),
            "order": "newest first by commit topology", "tags": tags}
    lines = [f"{root.name}: {len(detail)} tag(s), newest first by commit topology"]
    if contains:
        lines.append(f"  filtered by: {contains}")
    lines.append("")
    for item in tags:
        lines.append(f"  {item['tag']:<24} {item['sha']:<10} {item['date']}  {item['subject'][:60]}")
    if len(ordered) > limit:
        lines.append(f"  ... {len(ordered) - limit} more")
    if not tags:
        lines.append("  No tags. Release-to-release comparison needs an explicit base, e.g. base='HEAD~50'.")
    else:
        lines += ["", f"  Newest two: {tags[0]['tag']}"
                      + (f" and {tags[1]['tag']}  ->  bitbucket_changes base={tags[1]['tag']} head={tags[0]['tag']}"
                         if len(tags) > 1 else "")]
    return truncate("\n".join(lines)), data


# ---------------------------------------------------------------------------
# Date windows
# ---------------------------------------------------------------------------

def commit_before(root: Path, ref: str, date: str) -> str:
    """The newest commit on ref dated strictly before `date`."""
    return run_git(root, ["rev-list", "-n", "1", f"--before={date}", ref]).strip()


def commit_stamp(root: Path, sha: str) -> str:
    try:
        return run_git(root, ["log", "-1", "--pretty=%ad", "--date=short", sha]).strip()
    except ToolError:
        return ""


def resolve_window(root: Path, base: str, head: str, since: str, until: str) -> tuple[str, str, dict]:
    """Turn any mix of refs and dates into one base..head pair.

    A date is resolved to a real commit and reported, because "changes since
    1 August" is only ever an approximation of a commit range and the caller
    has to be able to see which commits it actually became.

    Both dates are exclusive at midnight, which is what git means by --before:
    since=2026-01-01 includes commits made on 1 January, and until=2026-06-30
    stops at the end of 29 June. Pass the following day to include a whole day.
    """
    if base and since:
        raise ToolError("Give either base or since, not both  -  they both decide where the range starts.")

    head_ref = head or "HEAD"
    meta: dict = {"resolved_from_dates": bool(since or until), "notes": []}

    if until:
        resolved = commit_before(root, head_ref, until)
        if not resolved:
            raise ToolError(
                f"No commit on {head_ref} before {until}. The history may start later than that date."
            )
        meta["notes"].append(f"head = last commit before {until} ({resolved[:10]}, {commit_stamp(root, resolved)})")
        head_ref = resolved

    base_ref = base
    if since:
        resolved = commit_before(root, head_ref, since)
        if resolved:
            base_ref = resolved
            meta["notes"].append(f"base = last commit before {since} ({resolved[:10]}, {commit_stamp(root, resolved)})")
        else:
            roots = run_git(root, ["rev-list", "--max-parents=0", head_ref]).split()
            if not roots:
                raise ToolError(f"Could not find any commit at or before {since} on {head_ref}.")
            base_ref = roots[-1]
            meta["notes"].append(
                f"nothing precedes {since} on this history, so the range starts at the root commit "
                f"({base_ref[:10]}) and that commit's own contents are NOT counted as changes"
            )

    meta["base_resolved"] = base_ref
    meta["head_resolved"] = head_ref
    meta["base_date"] = commit_stamp(root, base_ref) if base_ref else ""
    meta["head_date"] = commit_stamp(root, head_ref) if head_ref else ""
    return base_ref, head_ref, meta


def default_base(root: Path, head: str, meta: dict) -> str:
    """When no base and no since were given, start from the last release.

    The tag has to be one REACHABLE FROM HEAD, not simply the newest in the
    repository: with until= the head is an older commit, and a later tag would
    invert the range and report every change backwards.
    """
    tag = ""
    try:
        tag = run_git(root, ["describe", "--tags", "--abbrev=0", head]).strip()
    except ToolError:
        tag = ""
    if not tag:
        tags = ordered_tags(root)
        reachable = set(run_git(root, ["rev-list", head]).split())
        for name in tags:
            try:
                if run_git(root, ["rev-parse", f"{name}^{{commit}}"]).strip() in reachable:
                    tag = name
                    break
            except ToolError:
                continue
    if not tag:
        raise ToolError(
            "Nothing to start the range from: no base, no since, and no tag reachable from head. "
            "Pass base explicitly (e.g. base='HEAD~20') or a date (e.g. since='3 months ago')."
        )
    meta["notes"].append(f"base defaulted to {tag}, the most recent tag reachable from head")
    meta["base_resolved"] = tag
    meta["base_date"] = commit_stamp(root, tag)
    return tag


def bitbucket_changes(repo: str, base: str = "", head: str = "HEAD", since: str = "",
                      until: str = "", max_files: int = 400) -> tuple[str, dict]:
    root = resolve_repo(repo)
    base, head, window = resolve_window(root, base, head, since, until)
    if not base:
        base = default_base(root, head, window)
    rng = f"{base}..{head}"
    changed: list[dict] = []
    for line in run_git(root, ["diff", "--name-status", rng]).splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changed.append({"status": parts[0].strip(), "file": parts[-1].strip()})

    web = bitbucket_coordinates(remote_url(root))["web_url"]
    commits: list[dict] = []
    keys: Counter = Counter()
    for line in run_git(root, ["log", "--pretty=%H%x1f%an%x1f%s", rng]).splitlines():
        bits = line.split("\x1f")
        if len(bits) < 3:
            continue
        found = JIRA_KEY_RE.findall(bits[2])
        keys.update(found)
        commits.append({"sha": bits[0][:10], "author": bits[1], "subject": bits[2],
                        "jira_keys": found, "url": commit_url(web, bits[0])})

    tagged = sum(1 for c in commits if c["jira_keys"])
    coverage = (tagged * 100 // len(commits)) if commits else 0
    areas = Counter(str(Path(c["file"]).parent) for c in changed)
    data = {"repo": root.name, "range": rng, "base": base, "head": head,
            "since": since, "until": until, "window": window,
            "commits": len(commits), "commits_with_jira_key": tagged,
            "jira_key_coverage_pct": coverage, "jira_keys": sorted(keys),
            "files_changed": len(changed), "changes": changed[:max_files],
            "top_directories": areas.most_common(10), "commit_sample": commits[:20]}

    label = rng
    if since or until:
        label = f"{since or 'start'} .. {until or 'now'}   -> {base[:10]}..{head[:10]}"
    lines = [f"{root.name}  {label}",
             f"  commits          : {len(commits)}",
             f"  with a Jira key  : {tagged} ({coverage}%)",
             f"  files changed    : {len(changed)}"]
    if keys:
        lines.append(f"  Jira keys        : {', '.join(sorted(keys)[:20])}")
        lines.append("    -> commit -> Jira key -> test case is viable on this history.")
    else:
        lines.append("  Jira keys        : none found  -  selection has to lean on paths and endpoints.")
    for note in window["notes"]:
        lines.append(f"  window           : {note}")
    if keys and coverage <= 50:
        lines.append(f"    NOTE: only {coverage}% of commits carry a key  -  above 50% the key "
                     f"strategy carries the analysis, below it the evidence is weaker. Say which.")
    if areas:
        lines += ["", "Busiest directories:"]
        lines += [f"    {n:>4}  {d}" for d, n in areas.most_common(8)]
    lines += ["", "Changed files:"]
    lines += [f"    {c['status']:<3} {c['file']}" for c in changed[:40]]
    if len(changed) > 40:
        lines.append(f"    ... {len(changed) - 40} more")
    return truncate("\n".join(lines)), data


HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def bitbucket_diff(repo: str, base: str = "", head: str = "HEAD", since: str = "",
                   until: str = "", path: str = "", mode: str = "stat",
                   context: int = 3) -> tuple[str, dict]:
    root = resolve_repo(repo)
    mode = (mode or "stat").lower()
    if mode not in ("stat", "names", "patch"):
        raise ToolError("mode must be stat, names or patch.")
    base, head, window = resolve_window(root, base, head, since, until)
    if not base:
        base = default_base(root, head, window)
    rng = f"{base}..{head}"

    if mode == "stat":
        args = ["diff", "--stat", rng]
    elif mode == "names":
        args = ["diff", "--name-status", rng]
    else:
        args = ["diff", f"--unified={max(0, min(int(context or 3), 25))}", rng]
    if path:
        args += ["--", path]

    output = run_git(root, args)
    ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    if mode == "patch":
        current = ""
        for line in output.splitlines():
            if line.startswith("+++ b/"):
                current = line[6:].strip()
            elif line.startswith("@@") and current:
                match = HUNK_RE.match(line)
                if match:
                    start = int(match.group(1))
                    count = int(match.group(2) or 1)
                    ranges[current].append((start, start + max(count, 1) - 1))

    data = {"repo": root.name, "range": rng, "mode": mode, "path": path,
            "since": since, "until": until, "window": window,
            "changed_line_ranges": {k: v for k, v in ranges.items()},
            "bytes": len(output)}
    label = rng if not (since or until) else \
        f"{since or 'start'} .. {until or 'now'}   -> {base[:10]}..{head[:10]}"
    header = f"{root.name}  {label}  [{mode}]" + (f"  -- {path}" if path else "")
    for note in window["notes"]:
        header += f"\n  window: {note}"
    body = output.rstrip() or "(no differences in this range)"
    if mode == "patch" and ranges:
        header += f"\n  files with hunks: {len(ranges)}"
    return truncate(f"{header}\n\n{body}"), data


def bitbucket_file(repo: str, path: str, ref: str = "HEAD", start: int = 0,
                   end: int = 0) -> tuple[str, dict]:
    root = resolve_repo(repo)
    if not path:
        raise ToolError("path is required, relative to the repository root.")
    try:
        text = run_git(root, ["show", f"{ref or 'HEAD'}:{path}"])
    except ToolError as error:
        raise ToolError(
            f"{error}  Check the path is relative to the repo root; "
            f"bitbucket_grep or bitbucket_diff will show the exact spelling."
        ) from error

    lines = text.splitlines()
    first = max(1, int(start or 1))
    last = int(end) if end else len(lines)
    last = max(first, min(last, len(lines)))
    window = lines[first - 1: last]
    numbered = "\n".join(f"{first + i:>6}  {line}" for i, line in enumerate(window))

    data = {"repo": root.name, "path": path, "ref": ref or "HEAD",
            "total_lines": len(lines), "from_line": first, "to_line": last}
    header = f"{root.name}  {path}  @{ref or 'HEAD'}  (lines {first}-{last} of {len(lines)})"
    return truncate(f"{header}\n\n{numbered}"), data


def bitbucket_grep(repo: str, pattern: str, ref: str = "HEAD", path: str = "",
                   ignore_case: bool = True, limit: int = 100) -> tuple[str, dict]:
    root = resolve_repo(repo)
    if not pattern:
        raise ToolError("pattern is required.")
    limit = max(1, min(int(limit or 100), 500))

    args = ["grep", "-n", "-I"]
    if ignore_case:
        args.append("-i")
    args += ["-e", pattern, ref or "HEAD"]
    if path:
        args += ["--", path]

    # exit 1 from git grep means "no matches", which is an answer.
    output = run_git(root, args, allow_status=(0, 1))
    hits: list[dict] = []
    files: Counter = Counter()
    for line in output.splitlines():
        # <ref>:<file>:<line>:<text>
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        hits.append({"file": parts[1], "line": int(parts[2]) if parts[2].isdigit() else 0,
                     "text": parts[3].strip()[:300]})
        files[parts[1]] += 1

    shown = hits[:limit]
    data = {"repo": root.name, "ref": ref or "HEAD", "pattern": pattern,
            "matches": len(hits), "files": len(files), "returned": len(shown),
            "top_files": files.most_common(10), "hits": shown}
    lines = [f"{root.name}  @{ref or 'HEAD'}  /{pattern}/",
             f"  matches: {len(hits)} across {len(files)} file(s)"]
    if not hits:
        lines.append("  No matches. Try ignore_case, a shorter pattern, or a different ref.")
    else:
        lines.append("")
        for item in shown:
            lines.append(f"  {item['file']}:{item['line']}: {item['text'][:140]}")
        if len(hits) > limit:
            lines.append(f"  ... {len(hits) - limit} more")
    return truncate("\n".join(lines)), data


# ---------------------------------------------------------------------------
# Endpoint scan
# ---------------------------------------------------------------------------

ROUTE_PATTERNS: list[tuple[str, re.Pattern]] = [
    # C# / ASP.NET
    ("csharp", re.compile(r"""\[Http(Get|Post|Put|Delete|Patch)\s*\(\s*["']([^"']*)["']""", re.I)),
    ("csharp", re.compile(r"""\[Http(Get|Post|Put|Delete|Patch)\s*\]""", re.I)),
    ("csharp", re.compile(r"""\[Route\s*\(\s*["']([^"']+)["']""", re.I)),
    # Java / Spring
    ("java",   re.compile(r"""@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?["']([^"']*)["']""")),
    ("java",   re.compile(r"""@RequestMapping\s*\(\s*(?:value\s*=\s*)?["']([^"']+)["']""")),
    # Node / Express
    ("node",   re.compile(r"""\b(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["'`]([^"'`]+)["'`]""")),
    # Python / Flask / FastAPI
    ("python", re.compile(r"""@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["']([^"']+)["']""")),
    ("python", re.compile(r"""@(?:app|blueprint)\.route\s*\(\s*["']([^"']+)["']""")),
]

DECL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
NOT_A_SYMBOL = {
    "if", "for", "while", "switch", "catch", "return", "using", "lock", "foreach",
    "new", "await", "yield", "throw", "print", "assert", "with", "elif", "except",
}

INDEXABLE_SUFFIXES = {".cs", ".java", ".js", ".ts", ".py", ".go", ".rb", ".kt", ".php"}
SPEC_NAMES = ("swagger.json", "openapi.json", "swagger.yaml", "openapi.yaml", "openapi.yml")


def extract_symbol(lines: list[str], start: int) -> str:
    """Find the declaration a route attribute decorates.

    The attribute line itself parses as a call  -  `[HttpPut("/x")]` yields
    "HttpPut"  -  so annotation and comment lines are skipped and the first real
    declaration below them is taken instead.
    """
    for line in lines[start: start + 8]:
        stripped = line.strip()
        if not stripped or stripped[0] in "[@#" or stripped.startswith(("//", "*", "/*")):
            continue
        for match in DECL_RE.finditer(line):
            name = match.group(1)
            if name.lower() not in NOT_A_SYMBOL and not name.lower().startswith("http"):
                return name
        return ""
    return ""


def scan_endpoints(root: Path, max_files: int = 4000) -> tuple[list[dict], list[str], int, int]:
    listing = run_git(root, ["ls-files"]).splitlines()
    endpoints: list[dict] = []
    specs: list[str] = []
    scanned = 0
    for relative in listing[:max_files]:
        suffix = Path(relative).suffix.lower()
        if Path(relative).name.lower() in SPEC_NAMES:
            specs.append(relative)
        if suffix not in INDEXABLE_SUFFIXES:
            continue
        try:
            text = (root / relative).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        lines = text.splitlines()
        for language, pattern in ROUTE_PATTERNS:
            for match in pattern.finditer(text):
                groups = [g for g in match.groups() if g]
                if not groups:
                    continue
                if len(groups) >= 2:
                    method, route = groups[0].upper(), groups[1]
                elif re.fullmatch(r"(?i)get|post|put|delete|patch", groups[0]):
                    method, route = groups[0].upper(), ""
                else:
                    method, route = "", groups[0]
                line_no = text[:match.start()].count("\n") + 1
                endpoints.append({"method": method or "ANY", "route": route,
                                  "file": relative, "line": line_no,
                                  "symbol": extract_symbol(lines, line_no - 1),
                                  "language": language})
    return endpoints, specs, len(listing), scanned


def bitbucket_endpoints(repo: str, method: str = "", contains: str = "",
                        max_files: int = 4000, limit: int = 100) -> tuple[str, dict]:
    root = resolve_repo(repo)
    limit = max(1, min(int(limit or 100), 1000))
    endpoints, specs, tracked, scanned = scan_endpoints(root, max(1, int(max_files or 4000)))

    if method:
        wanted = method.strip().upper()
        endpoints = [e for e in endpoints if e["method"] == wanted]
    if contains:
        needle = contains.lower()
        endpoints = [e for e in endpoints
                     if needle in e["route"].lower() or needle in e["file"].lower()
                     or needle in (e["symbol"] or "").lower()]

    by_method = Counter(e["method"] for e in endpoints)
    routes = sorted({f"{e['method']:<6} {e['route']}" for e in endpoints})
    shown = endpoints[:limit]
    data = {"repo": root.name, "files_tracked": tracked, "files_scanned": scanned,
            "endpoints_found": len(endpoints), "distinct_routes": len(routes),
            "by_method": dict(by_method), "api_spec_files": specs,
            "returned": len(shown), "endpoints": shown}

    lines = [f"{root.name}  endpoints (read-only scan of the checked-out tree)",
             f"  tracked files : {tracked}",
             f"  scanned       : {scanned}",
             f"  endpoints     : {len(endpoints)} ({len(routes)} distinct routes)"]
    if by_method:
        lines.append("  by method     : " + ", ".join(f"{m} {n}" for m, n in by_method.most_common()))
    if specs:
        lines.append(f"  API specs     : {', '.join(specs[:5])}")
        lines.append("    -> the best source for expected results the test cases are missing.")
    lines.append("")
    for item in shown:
        symbol = f"  {item['symbol']}" if item["symbol"] else ""
        lines.append(f"  {item['method']:<6} {item['route'][:60]:<60} {item['file']}:{item['line']}{symbol}")
    if len(endpoints) > limit:
        lines.append(f"  ... {len(endpoints) - limit} more")
    if not endpoints:
        lines.append("  No routes matched. If this repo uses another framework, extend ROUTE_PATTERNS,"
                     " or drop the method/contains filter.")
    lines += ["", "NOTE: line numbers are from the CHECKED-OUT revision, not from any other ref."]
    return truncate("\n".join(lines)), data


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def _s(description: str, **extra: Any) -> dict:
    return {"type": "string", "description": description, **extra}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "bitbucket_repos",
        "title": "List cloned repositories",
        "description": (
            "List the Bitbucket clones this server can read, with the checked-out branch, the "
            "head commit, the tag count and  -  where the remote is recognisable  -  the "
            "Bitbucket project key, repository slug and browse URL. Start here: every other "
            "tool takes a repo name from this list."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "root": _s("Folder to look in. Defaults to BITBUCKET_REPO_ROOT (or CORPUS_REPO_ROOT)."),
                "limit": {"type": "integer", "description": "Max clones to report. Default 50.", "default": 50},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "bitbucket_log",
        "title": "Commit history",
        "description": (
            "Commit history for a ref or a base..head range, with Jira keys extracted from "
            "every subject and the percentage of commits that carry one  -  the number that "
            "decides whether commit-to-test-case linkage is viable on this history. Filter by "
            "date, author, message text or path. Read-only git."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": _s("Absolute path to the clone, or a folder name under BITBUCKET_REPO_ROOT."),
                "base": _s("Base ref. Supply it to read a range; omit for plain history of head."),
                "head": _s("Head ref. Default \"HEAD\".", default="HEAD"),
                "since": _s("Only commits after this date, e.g. \"2026-01-01\" or \"3 months ago\"."),
                "until": _s("Only commits before this date."),
                "author": _s("Restrict to an author (substring match)."),
                "grep": _s("Restrict to commits whose message matches this text (case-insensitive)."),
                "path": _s("Restrict to commits touching this path, e.g. \"src/SenderId\"."),
                "limit": {"type": "integer", "description": "Max commits, 1-500. Default 50.", "default": 50},
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "bitbucket_tags",
        "title": "Release tags",
        "description": (
            "List tags newest-first by COMMIT TOPOLOGY rather than by date, because tags "
            "created in the same second tie on date and can come back reversed, which would "
            "silently invert a base..head range. Use it to find the two refs to compare."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": _s("Absolute path to the clone, or a folder name under BITBUCKET_REPO_ROOT."),
                "limit": {"type": "integer", "description": "Max tags, 1-500. Default 30.", "default": 30},
                "contains": _s("Only tags containing this text, e.g. \"6.1\"."),
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "bitbucket_changes",
        "title": "What changed between two refs",
        "description": (
            "Files changed and commits made across a range, with Jira keys and the Jira-key "
            "coverage percentage, plus the busiest directories in the change. The range can be "
            "given as REFS (base/head) or as DATES (since/until)  -  since='2026-01-01', "
            "since='3 months ago', or since + until for a window such as one sprint. Dates are "
            "resolved to real commits and the resolution is reported, because a date range is "
            "only ever an approximation of a commit range. With neither, base defaults to the "
            "most recent tag. Read-only git."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": _s("Absolute path to the clone, or a folder name under BITBUCKET_REPO_ROOT."),
                "base": _s("Base ref  -  a tag, branch or SHA. Defaults to the most recent tag. Cannot be combined with since."),
                "head": _s("Head ref. Default \"HEAD\".", default="HEAD"),
                "since": _s("Start of a date range instead of base, e.g. \"2026-01-01\", \"3 months ago\", "
                            "\"last monday\". Commits made ON this date are included."),
                "until": _s("End of a date range, narrowing head to the last commit before it. Exclusive at "
                            "midnight, so pass the NEXT day to include a whole day."),
                "max_files": {"type": "integer", "description": "Cap on changed files returned. Default 400.", "default": 400},
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "bitbucket_diff",
        "title": "Diff between two refs",
        "description": (
            "The actual diff for a range, given as refs (base/head) or as dates (since/until). "
            "mode=stat (default) is the per-file summary, mode=names lists files with their "
            "change status, mode=patch returns the unified diff and also reports the changed "
            "line ranges per file. Narrow with path before asking for a patch  -  a whole-release "
            "patch is very large."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": _s("Absolute path to the clone, or a folder name under BITBUCKET_REPO_ROOT."),
                "base": _s("Base ref. Defaults to the most recent tag. Cannot be combined with since."),
                "head": _s("Head ref. Default \"HEAD\".", default="HEAD"),
                "since": _s("Start of a date range instead of base, e.g. \"2026-01-01\" or \"3 months ago\"."),
                "until": _s("End of a date range. Exclusive at midnight, so pass the NEXT day to include a whole day."),
                "path": _s("Restrict the diff to this path or pathspec."),
                "mode": _s("stat (default), names, or patch.", enum=["stat", "names", "patch"], default="stat"),
                "context": {"type": "integer", "description": "Context lines for mode=patch, 0-25. Default 3.", "default": 3},
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "bitbucket_file",
        "title": "Read a file at a ref",
        "description": (
            "Return a tracked file's contents as it stands at any ref  -  a tag, branch or "
            "SHA  -  with line numbers, optionally just a line window. Use it to read an "
            "OpenAPI spec, a controller or a config file without checking anything out."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": _s("Absolute path to the clone, or a folder name under BITBUCKET_REPO_ROOT."),
                "path": _s("File path relative to the repository root."),
                "ref": _s("Ref to read it at. Default \"HEAD\".", default="HEAD"),
                "start": {"type": "integer", "description": "First line to return. Default 1.", "default": 0},
                "end": {"type": "integer", "description": "Last line to return. Default end of file.", "default": 0},
            },
            "required": ["repo", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "bitbucket_grep",
        "title": "Search tracked content",
        "description": (
            "Search the tracked content of a repository at a ref and return file, line number "
            "and the matching text, plus which files match most. Binary files are skipped. "
            "This searches the repository, not the corpus  -  it is how you find where a "
            "feature actually lives before asking which tests cover it."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": _s("Absolute path to the clone, or a folder name under BITBUCKET_REPO_ROOT."),
                "pattern": _s("Text or basic regular expression to find."),
                "ref": _s("Ref to search. Default \"HEAD\".", default="HEAD"),
                "path": _s("Restrict to a path or pathspec, e.g. \"src/**/*.cs\"."),
                "ignore_case": {"type": "boolean", "description": "Case-insensitive. Default true.", "default": True},
                "limit": {"type": "integer", "description": "Max matches to show, 1-500. Default 100.", "default": 100},
            },
            "required": ["repo", "pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "bitbucket_endpoints",
        "title": "HTTP endpoints in the repository",
        "description": (
            "Scan the checked-out tree for HTTP endpoint definitions (C#, Java/Spring, "
            "Express, Flask/FastAPI) and report method, route, file, line and the symbol that "
            "defines each one, plus any OpenAPI/Swagger spec found  -  the best source for the "
            "expected results test cases are missing. Results are returned inline; nothing is "
            "stored."
        ),
        "annotations": {"readOnlyHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": _s("Absolute path to the clone, or a folder name under BITBUCKET_REPO_ROOT."),
                "method": _s("Restrict to one HTTP method, e.g. \"POST\"."),
                "contains": _s("Only endpoints whose route, file or symbol contains this text."),
                "max_files": {"type": "integer", "description": "Cap on files scanned. Default 4000.", "default": 4000},
                "limit": {"type": "integer", "description": "Max endpoints to list. Default 100.", "default": 100},
            },
            "required": ["repo"],
            "additionalProperties": False,
        },
    },
]

HANDLERS: dict[str, Callable[..., tuple[str, Any]]] = {
    "bitbucket_repos": bitbucket_repos,
    "bitbucket_log": bitbucket_log,
    "bitbucket_tags": bitbucket_tags,
    "bitbucket_changes": bitbucket_changes,
    "bitbucket_diff": bitbucket_diff,
    "bitbucket_file": bitbucket_file,
    "bitbucket_grep": bitbucket_grep,
    "bitbucket_endpoints": bitbucket_endpoints,
}


def call_tool(name: str, arguments: dict) -> dict:
    handler = HANDLERS.get(name)
    if handler is None:
        raise KeyError(name)
    schema = next(t for t in TOOLS if t["name"] == name)["inputSchema"]
    allowed = set(schema.get("properties") or {})
    unknown = set(arguments) - allowed
    clean = {k: v for k, v in arguments.items() if k in allowed}
    missing = [k for k in (schema.get("required") or []) if clean.get(k) in (None, "")]
    if missing:
        return {"content": [{"type": "text", "text":
                f"Error: {name} requires {', '.join(missing)}. "
                f"Accepted arguments: {', '.join(sorted(allowed))}."}], "isError": True}
    try:
        text, data = handler(**clean)
    except ToolError as error:
        return {"content": [{"type": "text", "text": f"Error: {error}"}], "isError": True}
    except TypeError as error:
        return {"content": [{"type": "text", "text": f"Error: bad arguments for {name}: {error}"}], "isError": True}
    except Exception as error:  # noqa: BLE001
        log(f"unhandled error in {name}: {traceback.format_exc()}")
        return {"content": [{"type": "text", "text": f"Error: {type(error).__name__}: {error}"}], "isError": True}
    if unknown:
        text = f"(ignored unrecognised argument(s): {', '.join(sorted(unknown))})\n\n{text}"
    return {"content": [{"type": "text", "text": text}], "structuredContent": data, "isError": False}


# ---------------------------------------------------------------------------
# MCP stdio server
# ---------------------------------------------------------------------------

def negotiate_protocol(requested: str) -> str:
    return requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]


def handle_message(message: dict) -> dict | None:
    method = message.get("method", "")
    message_id = message.get("id")
    params = message.get("params") or {}
    is_notification = message_id is None

    def ok(result: Any) -> dict | None:
        return None if is_notification else {"jsonrpc": "2.0", "id": message_id, "result": result}

    def fail(code: int, text: str) -> dict | None:
        return None if is_notification else {"jsonrpc": "2.0", "id": message_id,
                                             "error": {"code": code, "message": text}}

    if method == "initialize":
        return ok({
            "protocolVersion": negotiate_protocol(params.get("protocolVersion", "")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "Bitbucket (read-only clones)",
                           "version": SERVER_VERSION},
            "instructions": (
                "Read-only access to cloned Bitbucket repositories for a test team. Start with "
                "bitbucket_repos to see the clones, bitbucket_tags to find two refs, then "
                "bitbucket_changes for what a release contains. Every tool is read-only and no "
                "tool here can modify a repository. Quote the Jira-key coverage percentage "
                "whenever you use commit messages as evidence."
            ),
        })
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return fail(-32602, "arguments must be an object")
        try:
            return ok(call_tool(name, arguments))
        except KeyError:
            return fail(-32602, f"Unknown tool: {name}")
    if method == "resources/list":
        return ok({"resources": []})
    if method == "prompts/list":
        return ok({"prompts": []})
    return fail(-32601, f"Method not found: {method}")


def write_message(payload: dict) -> None:
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, ValueError):
        log("stdout closed by client  -  exiting")
        os._exit(0)


def serve_stdio() -> None:
    for stream, kwargs in (
        (sys.stdin, {"encoding": "utf-8", "errors": "replace"}),
        (sys.stdout, {"encoding": "utf-8", "newline": "\n"}),
        (sys.stderr, {"encoding": "utf-8", "errors": "replace"}),
    ):
        try:
            stream.reconfigure(**kwargs)  # type: ignore[attr-defined]
        except Exception:
            pass

    env_path = load_environment()
    CONFIG.__init__()
    log(f"{SERVER_NAME} {SERVER_VERSION} ready ({len(TOOLS)} tools)")
    log(f"env file: {env_path or 'none found'}")
    log(f"repo roots: {[str(r) for r in CONFIG.repo_roots] or '(BITBUCKET_REPO_ROOT unset)'}")
    log("git access: READ-ONLY (allowlisted subcommands only); no write tools exist")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            write_message({"jsonrpc": "2.0", "id": None,
                           "error": {"code": -32700, "message": f"Parse error: {error}"}})
            continue
        for item in (message if isinstance(message, list) else [message]):
            if not isinstance(item, dict):
                continue
            try:
                response = handle_message(item)
            except Exception:  # noqa: BLE001
                log(f"fatal handler error: {traceback.format_exc()}")
                response = {"jsonrpc": "2.0", "id": item.get("id"),
                            "error": {"code": -32603, "message": "Internal server error; see stderr."}}
            if response is not None:
                write_message(response)
    log("stdin closed  -  shutting down")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SHAPE_SAMPLE = '''
[HttpPost("/api/v1/senderids")]
public async Task<IActionResult> CreateSenderId(SenderIdRequest request) { }
'''


def selftest() -> int:
    env_path = load_environment()
    CONFIG.__init__()
    print(f"env file    : {env_path or '(none)'}")
    print(f"repo roots  : {[str(r) for r in CONFIG.repo_roots] or '(unset)'}")
    print("-" * 62)
    failures = 0

    # Offline shape check first, so a damaged file is reported as damaged
    # rather than as a repository problem.
    try:
        lines = SHAPE_SAMPLE.splitlines()
        hit = None
        for _language, pattern in ROUTE_PATTERNS:
            match = pattern.search(SHAPE_SAMPLE)
            if match:
                hit = match
                break
        symbol = extract_symbol(lines, 1)
        coords = bitbucket_coordinates("ssh://git@bitbucket.example.com:7999/smp/messaging-center.git")
        assert hit is not None, "no route pattern matched the canned sample"
        assert symbol == "CreateSenderId", f"symbol extraction returned {symbol!r}"
        assert coords["project"] == "smp" and coords["slug"] == "messaging-center", coords
        print("PASS  shape        : route patterns, symbol extraction and URL parsing intact")
    except Exception as error:  # noqa: BLE001
        print(f"FAIL  shape        : {error}  (this file may be damaged)"); failures += 1

    try:
        version = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=20)
        print(f"PASS  git          : {version.stdout.strip()}")
    except Exception as error:  # noqa: BLE001
        print(f"FAIL  git          : not available ({error})"); failures += 1

    for guard, args in (("write subcommand", ["checkout", "main"]),
                        ("tag creation", ["tag", "v9"]),
                        ("write flag", ["log", "--output=/tmp/x"])):
        try:
            run_git(Path.cwd(), args)
            print(f"FAIL  guard        : {guard} was NOT blocked"); failures += 1
        except ToolError:
            print(f"PASS  guard        : {guard} blocked")

    if not CONFIG.repo_roots:
        print("WARN  repo root    : BITBUCKET_REPO_ROOT unset  -  every tool will need an absolute path")
    for root in CONFIG.repo_roots:
        if not root.is_dir():
            print(f"WARN  repo root    : {root} does not exist"); continue
        repos = [p.name for p in root.iterdir() if (p / ".git").exists()]
        print(f"PASS  repo root    : {root} -> {len(repos)} clone(s) {repos[:6]}")

    print("-" * 62)
    print("Ready." if not failures else f"{failures} check(s) failed.")
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--call", nargs=2, metavar=("TOOL", "JSON_ARGS"))
    args = parser.parse_args()

    if args.selftest:
        return selftest()
    if args.list_tools:
        for tool in TOOLS:
            required = tool["inputSchema"].get("required") or []
            print(f"\n{tool['name']}  (read-only)")
            print(f"  {tool['description'][:200]}")
            for key, spec in (tool["inputSchema"].get("properties") or {}).items():
                mark = "*" if key in required else " "
                print(f"   {mark} {key} ({spec.get('type')}): {spec.get('description', '')[:110]}")
        return 0
    if args.call:
        load_environment(); CONFIG.__init__()
        name, raw = args.call
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError as error:
            print(f"Arguments must be valid JSON: {error}", file=sys.stderr); return 2
        try:
            result = call_tool(name, arguments)
        except KeyError:
            print(f"Unknown tool: {name}. Known: {', '.join(HANDLERS)}", file=sys.stderr); return 2
        print(result["content"][0]["text"])
        return 1 if result.get("isError") else 0

    serve_stdio()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
