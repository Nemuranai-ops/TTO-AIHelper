#!/usr/bin/env python
"""Atlassian MCP server  -  Confluence + Jira tools over stdio JSON-RPC.

Exposes 10 tools to any MCP client (GitHub Copilot in VS Code, Claude Code, etc.):

    confluence_create_page   confluence_update_page   confluence_get_page
    confluence_search        jira_create_issue        jira_update_issue
    jira_search_issues       jira_get_issue           jira_get_transitions
    jira_transition_issue

Auth reuses the pmo-inline agent's scheme: HTTP Basic with
ATLASSIAN_EMAIL + ATLASSIAN_API_TOKEN, read from .env. One API token covers
both Jira and Confluence.

APIs used:
    Confluence pages   REST v2  /wiki/api/v2/pages
    Confluence search  REST v1  /wiki/rest/api/search   (CQL has no v2 equivalent)
    Jira               REST v3  /rest/api/3/...         (search via /search/jql)

Dependencies: requests. python-dotenv is optional (a built-in .env loader is
used when it is absent). No MCP SDK required  -  the stdio protocol is
implemented directly, so nothing heavy needs installing on a locked-down box.

Run modes:
    python atlassian_mcp_server.py              # serve MCP over stdio (normal)
    python atlassian_mcp_server.py --selftest   # verify credentials + connectivity
    python atlassian_mcp_server.py --list-tools # print the tool schemas
    python atlassian_mcp_server.py --call jira_get_issue '{"issue_key":"SMP-4245"}'
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import traceback
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

try:
    import requests
except ImportError:  # keep --list-tools usable on a bare machine
    requests = None  # type: ignore[assignment]

SERVER_NAME = "atlassian-mcp"
SERVER_VERSION = "1.0.0"

# Protocol versions this server understands, newest first.
SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

DEFAULT_TIMEOUT = 60
MAX_RETRIES = 4


# ---------------------------------------------------------------------------
# Logging  -  MUST go to stderr. stdout carries JSON-RPC only.
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_environment() -> Path | None:
    """Load .env without requiring python-dotenv.

    Real environment variables win over .env values, so anything set in
    mcp.json "env" overrides the file. Search order:
      ATLASSIAN_ENV_FILE -> ./ .env next to this script -> cwd -> parent dir
    """
    candidates: list[Path] = []
    explicit = os.environ.get("ATLASSIAN_ENV_FILE", "").strip()
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
            # setdefault would treat an empty env var as "already set", so an
            # blank entry in mcp.json would silently mask the .env value.
            if not os.environ.get(key, "").strip():
                os.environ[key] = value.strip().strip('"').strip("'")
        return path
    return None


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


class Config:
    def __init__(self) -> None:
        self.base_url = os.environ.get("ATLASSIAN_BASE_URL", "").strip().rstrip("/")
        self.email = os.environ.get("ATLASSIAN_EMAIL", "").strip()
        self.token = os.environ.get("ATLASSIAN_API_TOKEN", "").strip()
        # Default OFF, matching pmo-inline. The corporate proxy re-signs every
        # certificate with a CA that is not in the system trust store, so
        # verification cannot succeed here without REQUESTS_CA_BUNDLE. Set
        # ATLASSIAN_VERIFY_TLS=true once you have that CA file.
        self.verify_tls = env_flag("ATLASSIAN_VERIFY_TLS", False)
        # Default ON: this server is used for reading. Set false to allow the
        # five create/update/transition tools.
        self.read_only = env_flag("ATLASSIAN_READ_ONLY", True)
        self.timeout = env_int("ATLASSIAN_TIMEOUT", DEFAULT_TIMEOUT)
        self.max_chars = env_int("ATLASSIAN_MAX_CHARS", 40000)
        self.proxy = os.environ.get("ATLASSIAN_PROXY", "").strip()
        # auto = try v2 and fall back to v1; v1/v2 pin to one.
        self.confluence_api = (os.environ.get("ATLASSIAN_CONFLUENCE_API", "").strip().lower()
                               or "auto")

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("ATLASSIAN_BASE_URL", self.base_url),
                ("ATLASSIAN_EMAIL", self.email),
                ("ATLASSIAN_API_TOKEN", self.token),
            )
            if not value
        ]
        if missing:
            raise ToolError(
                "Missing required settings: "
                + ", ".join(missing)
                + ". Set them in .env next to atlassian_mcp_server.py, or in the "
                  "\"env\" block of mcp.json."
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ToolError(
                f"ATLASSIAN_BASE_URL must include the scheme, e.g. "
                f"https://your-site.atlassian.net (got {self.base_url!r})"
            )


CONFIG = Config()


class ToolError(Exception):
    """An error that should be reported to the model as isError, not a crash."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class AtlassianClient:
    """Shared session for Jira and Confluence with retry + error mapping."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._session: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            if requests is None:
                raise ToolError(
                    "The 'requests' package is not installed. Run: pip install requests"
                )
            self.config.validate()
            encoded = base64.b64encode(
                f"{self.config.email}:{self.config.token}".encode()
            ).decode()
            # A corporate proxy (McAfee Web Gateway and friends) will happily
            # intercept 127.0.0.1 too, returning its own HTML error page, unless
            # loopback is excluded. This is what breaks the offline mock tests.
            no_proxy = os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "")
            wanted = ["127.0.0.1", "localhost", "::1"]
            merged = [h for h in no_proxy.split(",") if h.strip()]
            merged += [h for h in wanted if h not in no_proxy]
            os.environ["NO_PROXY"] = os.environ["no_proxy"] = ",".join(merged)

            session = requests.Session()
            if self.config.proxy:
                session.proxies = {"http": self.config.proxy, "https": self.config.proxy}
                log(f"using explicit proxy from ATLASSIAN_PROXY")
            session.headers.update({
                "Authorization": f"Basic {encoded}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": f"{SERVER_NAME}/{SERVER_VERSION}",
                # Confluence rejects some POSTs from non-browser clients without this.
                "X-Atlassian-Token": "no-check",
            })
            session.verify = self.config.verify_tls
            if not self.config.verify_tls:
                try:
                    import urllib3

                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                except Exception:  # pragma: no cover - urllib3 always ships with requests
                    pass
                log("TLS verification is OFF (matches pmo-inline; the corporate proxy "
                    "re-signs certificates). Set ATLASSIAN_VERIFY_TLS=true with "
                    "REQUESTS_CA_BUNDLE pointed at the proxy CA to turn it on.")
            self._session = session
        return self._session

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        url = f"{self.config.base_url}{path}"
        clean_params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        last_error: str = ""

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=clean_params or None,
                    json=json_body,
                    timeout=self.config.timeout,
                )
            except requests.exceptions.SSLError as error:
                hint = ("Verification is currently ON. This server defaults it OFF for "
                        "this network - remove ATLASSIAN_VERIFY_TLS=true from .env."
                        if self.config.verify_tls else
                        "Verification is already off, so this is a deeper TLS problem "
                        "than the usual re-signing proxy.")
                raise ToolError(f"TLS handshake failed for {url}. {hint} Detail: {error}") from error
            except requests.exceptions.ProxyError as error:
                raise ToolError(
                    f"A proxy rejected the request to {url}. If this is a corporate "
                    f"gateway, set ATLASSIAN_PROXY to it, or clear HTTP_PROXY/HTTPS_PROXY "
                    f"for this process. Detail: {error}"
                ) from error
            except requests.exceptions.RequestException as error:
                last_error = str(error)
                if attempt == MAX_RETRIES - 1:
                    raise ToolError(f"Network error calling {url}: {error}") from error
                time.sleep(2 ** attempt)
                continue

            # Throttled or transiently unavailable  -  back off and retry.
            if response.status_code in (429, 502, 503, 504):
                if attempt == MAX_RETRIES - 1:
                    raise ToolError(self._describe_error(response, method, url))
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = float(retry_after) if retry_after else 2 ** attempt
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(min(delay, 30))
                continue

            if response.status_code >= 400:
                raise ToolError(self._describe_error(response, method, url),
                                status=response.status_code)

            if response.status_code == 204 or not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                return response.text

        raise ToolError(f"Request to {url} failed after {MAX_RETRIES} attempts. {last_error}")

    @staticmethod
    def _describe_error(response: requests.Response, method: str, url: str) -> str:
        detail = ""
        try:
            payload = response.json()
            parts: list[str] = []
            for key in ("errorMessages", "errors", "message", "title", "detail"):
                value = payload.get(key) if isinstance(payload, dict) else None
                if not value:
                    continue
                if isinstance(value, list):
                    parts.extend(str(v) for v in value)
                elif isinstance(value, dict):
                    parts.extend(f"{k}: {v}" for k, v in value.items())
                else:
                    parts.append(str(value))
            detail = "; ".join(parts) or json.dumps(payload)[:600]
        except ValueError:
            body = (response.text or "")
            if "<html" in body[:400].lower():
                title = re.search(r"<title>(.*?)</title>", body[:2000], re.I | re.S)
                named = title.group(1).strip() if title else "an HTML error page"
                detail = (f"the response was {named!r}, not JSON - a proxy or gateway "
                          f"answered instead of Atlassian")
            else:
                detail = body[:600]

        hints = {
            400: "Bad request  -  check field names, JQL/CQL syntax, or required fields for this issue type.",
            401: "Authentication failed  -  ATLASSIAN_EMAIL must be the account email and "
                 "ATLASSIAN_API_TOKEN a token from id.atlassian.com/manage-profile/security/api-tokens.",
            403: "Permission denied  -  the account is authenticated but lacks rights on this "
                 "project/space, or the token scope is too narrow.",
            404: "Not found  -  check the id/key, and that the account can see it.",
            409: "Version conflict  -  the page changed since it was read. Re-read it and retry.",
            410: "Endpoint gone  -  this API version was removed on this site.",
        }
        hint = hints.get(response.status_code, "")
        return (
            f"{method} {url} failed with HTTP {response.status_code}. "
            f"{detail}{(' ' + hint) if hint else ''}"
        )

    def paginate_v2(self, path: str, params: dict[str, Any], limit: int) -> list[dict]:
        """Follow Confluence v2 cursor pagination up to `limit` results."""
        results: list[dict] = []
        query = dict(params)
        query["limit"] = min(limit, 250)
        while True:
            payload = self.request("GET", path, params=query)
            if not isinstance(payload, dict):
                break
            batch = payload.get("results") or []
            results.extend(batch)
            if len(results) >= limit:
                return results[:limit]
            next_link = ((payload.get("_links") or {}).get("next")) or ""
            if not next_link or not batch:
                return results
            cursor = re.search(r"[?&]cursor=([^&]+)", next_link)
            if not cursor:
                return results
            query["cursor"] = requests.utils.unquote(cursor.group(1))
        return results

    def require_write(self, tool: str) -> None:
        if self.config.read_only:
            raise ToolError(
                f"{tool} is blocked: the server is running with ATLASSIAN_READ_ONLY=true. "
                f"Remove that setting from .env or mcp.json to allow writes."
            )


CLIENT = AtlassianClient(CONFIG)


def web_url(links: dict | None) -> str:
    """Turn Atlassian's relative _links.webui into a clickable absolute URL."""
    if not isinstance(links, dict):
        return ""
    webui = links.get("webui") or links.get("self") or ""
    if not webui:
        return ""
    if webui.startswith("http"):
        return webui
    base = links.get("base") or f"{CONFIG.base_url}/wiki"
    return f"{base.rstrip('/')}{webui}"


def truncate(text: str, limit: int | None = None) -> str:
    cap = limit or CONFIG.max_chars
    if len(text) <= cap:
        return text
    return (
        text[:cap]
        + f"\n\n... [truncated: {len(text):,} chars total, showing first {cap:,}. "
          f"Narrow the query or raise ATLASSIAN_MAX_CHARS to see more.]"
    )


# ---------------------------------------------------------------------------
# Content conversion: ADF <-> text, Confluence storage XHTML -> text
# ---------------------------------------------------------------------------

def adf_to_text(node: Any, depth: int = 0) -> str:
    """Flatten Jira's Atlassian Document Format into readable plain text.

    Jira REST v3 returns description/comment bodies as ADF JSON, which is
    unreadable to a model as raw JSON. This keeps structure (headings, lists,
    tables, code) without the noise.
    """
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(child, depth) for child in node)
    if not isinstance(node, dict):
        return str(node)

    kind = node.get("type", "")
    content = node.get("content")

    if kind == "text":
        text = node.get("text", "")
        for mark in node.get("marks") or []:
            mark_type = mark.get("type")
            if mark_type == "code":
                text = f"`{text}`"
            elif mark_type == "strong":
                text = f"**{text}**"
            elif mark_type == "em":
                text = f"*{text}*"
            elif mark_type == "strike":
                text = f"~~{text}~~"
            elif mark_type == "link":
                href = (mark.get("attrs") or {}).get("href", "")
                if href:
                    text = f"[{text}]({href})"
        return text

    if kind == "hardBreak":
        return "\n"
    if kind == "rule":
        return "\n---\n"
    if kind == "emoji":
        attrs = node.get("attrs") or {}
        return attrs.get("text") or attrs.get("shortName") or ""
    if kind == "mention":
        return "@" + ((node.get("attrs") or {}).get("text", "").lstrip("@"))
    if kind == "date":
        return (node.get("attrs") or {}).get("timestamp", "")
    if kind in ("inlineCard", "blockCard", "embedCard"):
        return (node.get("attrs") or {}).get("url", "")
    if kind == "status":
        return f"[{(node.get('attrs') or {}).get('text', '')}]"

    if kind == "paragraph":
        return adf_to_text(content, depth) + "\n"
    if kind == "heading":
        level = (node.get("attrs") or {}).get("level", 1)
        return "\n" + "#" * int(level) + " " + adf_to_text(content, depth).strip() + "\n"
    if kind == "codeBlock":
        language = (node.get("attrs") or {}).get("language", "")
        return f"\n```{language}\n" + adf_to_text(content, depth).rstrip() + "\n```\n"
    if kind == "blockquote":
        inner = adf_to_text(content, depth).strip().splitlines()
        return "\n".join(f"> {line}" for line in inner) + "\n"

    if kind in ("bulletList", "orderedList"):
        lines = []
        for index, item in enumerate(content or [], start=1):
            bullet = f"{index}." if kind == "orderedList" else "-"
            body = adf_to_text(item, depth + 1).strip()
            if not body:
                continue
            pad = "  " * depth
            first, *rest = body.splitlines()
            lines.append(f"{pad}{bullet} {first}")
            lines.extend(f"{pad}   {line}" for line in rest)
        return "\n".join(lines) + "\n"
    if kind == "listItem":
        return adf_to_text(content, depth)

    if kind == "table":
        rows = []
        for row in content or []:
            cells = [
                adf_to_text(cell.get("content"), depth).strip().replace("\n", " ")
                for cell in row.get("content") or []
            ]
            rows.append("| " + " | ".join(cells) + " |")
        return "\n" + "\n".join(rows) + "\n"
    if kind in ("tableRow", "tableCell", "tableHeader"):
        return adf_to_text(content, depth)

    if kind in ("mediaSingle", "mediaGroup", "media"):
        attrs = node.get("attrs") or {}
        return f"[attachment: {attrs.get('id') or attrs.get('url') or 'media'}]"
    if kind == "panel":
        return "\n" + adf_to_text(content, depth).strip() + "\n"

    return adf_to_text(content, depth)


_FENCE_RE = re.compile(r"^```(\w*)\s*$")


def text_to_adf(text: str) -> dict:
    """Convert plain text / light markdown into a valid ADF document.

    Jira REST v3 accepts ADF only for rich-text fields. Supports paragraphs,
    '#' headings, '-'/'*' bullets, '1.' numbered lists and ``` code fences  -
    enough for anything an agent will realistically write.
    """
    doc: dict[str, Any] = {"type": "doc", "version": 1, "content": []}
    if not text or not text.strip():
        doc["content"] = [{"type": "paragraph", "content": []}]
        return doc

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = _FENCE_RE.match(line.strip())

        if fence:
            language = fence.group(1)
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not _FENCE_RE.match(lines[index].strip()):
                code_lines.append(lines[index])
                index += 1
            index += 1  # consume closing fence
            block: dict[str, Any] = {"type": "codeBlock", "content": []}
            if language:
                block["attrs"] = {"language": language}
            body = "\n".join(code_lines)
            if body:
                block["content"] = [{"type": "text", "text": body}]
            doc["content"].append(block)
            continue

        if not line.strip():
            index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            doc["content"].append({
                "type": "heading",
                "attrs": {"level": len(heading.group(1))},
                "content": _inline_adf(heading.group(2)),
            })
            index += 1
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.*)$", line)
        number = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if bullet or number:
            ordered = number is not None
            pattern = r"^\s*\d+[.)]\s+(.*)$" if ordered else r"^\s*[-*+]\s+(.*)$"
            items: list[dict] = []
            while index < len(lines):
                match = re.match(pattern, lines[index])
                if not match:
                    break
                items.append({
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": _inline_adf(match.group(1))}],
                })
                index += 1
            doc["content"].append({
                "type": "orderedList" if ordered else "bulletList",
                "content": items,
            })
            continue

        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not _FENCE_RE.match(lines[index].strip()):
            if re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[index]) or re.match(r"^#{1,6}\s+", lines[index]):
                break
            paragraph.append(lines[index])
            index += 1
        if paragraph:
            doc["content"].append({"type": "paragraph", "content": _inline_adf(" ".join(paragraph))})

    if not doc["content"]:
        doc["content"] = [{"type": "paragraph", "content": []}]
    return doc


def _inline_adf(text: str) -> list[dict]:
    """ADF forbids empty text nodes, so drop them rather than emit invalid JSON."""
    return [{"type": "text", "text": text}] if text else []


class _StorageTextExtractor(HTMLParser):
    """Render Confluence storage-format XHTML as readable text.

    Tables become pipe rows so a model can actually read a Confluence table,
    which is the common case for these pages.
    """

    SKIP = {"ac:parameter", "ri:user", "ac:plain-text-body", "style", "script"}
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._cell = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if self._cell and tag in ("p", "div", "br", "table", "blockquote", "li"):
            return  # stay on the current row
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "tr":
            self.parts.append("\n|")
        elif tag in ("td", "th"):
            self._cell = True
        elif tag == "br":
            self.parts.append("\n")
        elif tag in ("p", "div", "table", "blockquote"):
            self.parts.append("\n")
        elif tag == "ac:structured-macro":
            name = dict(attrs).get("ac:name", "")
            if name:
                self.parts.append(f"\n[macro: {name}]")
        elif tag == "ri:page":
            title = dict(attrs).get("ri:content-title", "")
            if title:
                self.parts.append(f"[link: {title}]")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in ("td", "th"):
            self.parts.append(" |")
            self._cell = False
        elif self._cell:
            return  # stay on the current row
        elif tag in ("li", "tr"):
            pass  # the next <li>/<tr> supplies its own newline
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"[ \t]+", " ", data)
        if self._cell:
            text = text.strip()
            if text:
                self.parts.append(" " + text)
        elif text.strip():
            self.parts.append(text)

    def result(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def storage_to_text(storage_xhtml: str) -> str:
    if not storage_xhtml:
        return ""
    parser = _StorageTextExtractor()
    try:
        parser.feed(storage_xhtml)
        parser.close()
    except Exception:
        # Malformed storage should degrade to a crude strip, never crash a read.
        return re.sub(r"<[^>]+>", " ", storage_xhtml)
    return parser.result()


def text_to_storage(text: str) -> str:
    """Wrap plain text as Confluence storage XHTML paragraphs."""
    import html as html_module

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if b.strip()]
    if not blocks:
        return "<p></p>"
    return "\n".join(
        "<p>" + html_module.escape(b).replace("\n", "<br/>") + "</p>" for b in blocks
    )


# ---------------------------------------------------------------------------
# Confluence - v2 with a v1 fallback
#
# Some tenants and corporate gateways do not expose /wiki/api/v2. The
# pmo-inline agent has been running against /wiki/rest/api/content for a long
# time, so v1 is the known-good path here. Default behaviour is to try v2 and
# fall back to v1 automatically, remembering the answer for the session.
# Pin with ATLASSIAN_CONFLUENCE_API=v1 (or v2) to skip the probe entirely.
# ---------------------------------------------------------------------------

FALLBACK_STATUSES = {401, 403, 404, 405, 410, 501}
_CONFLUENCE_MODE: dict[str, str | None] = {"resolved": None}


def confluence_call(v2_fn: Callable[[], Any], v1_fn: Callable[[], Any], what: str) -> Any:
    mode = CONFIG.confluence_api
    if mode == "v1":
        return v1_fn()
    if mode == "v2":
        return v2_fn()
    if _CONFLUENCE_MODE["resolved"] == "v1":
        return v1_fn()
    try:
        result = v2_fn()
        _CONFLUENCE_MODE["resolved"] = "v2"
        return result
    except ToolError as error:
        if error.status in FALLBACK_STATUSES:
            log(f"Confluence v2 {what} returned {error.status}; falling back to v1")
            result = v1_fn()
            _CONFLUENCE_MODE["resolved"] = "v1"
            return result
        raise


def confluence_api_in_use() -> str:
    if CONFIG.confluence_api in ("v1", "v2"):
        return CONFIG.confluence_api + " (pinned)"
    return _CONFLUENCE_MODE["resolved"] or "auto (not yet probed)"


def resolve_space_id(space_key: str) -> str:
    """Numeric space id - only v2 needs this; v1 takes the space key directly."""
    payload = CLIENT.request("GET", "/wiki/api/v2/spaces", params={"keys": space_key, "limit": 1})
    results = (payload or {}).get("results") or []
    if not results:
        raise ToolError(
            f"No Confluence space with key {space_key!r} is visible to this account. "
            f"The key is the short code in the page URL (.../wiki/spaces/<KEY>/...)."
        )
    return str(results[0].get("id"))


def summarize_page(page: dict, labels: list[str] | None = None) -> dict:
    """Normalise a page object from either API version into one shape."""
    version = page.get("version") or {}
    space = page.get("space") or {}
    if labels is None:
        meta_labels = ((page.get("metadata") or {}).get("labels") or {}).get("results") or []
        labels = [l.get("name", "") for l in meta_labels] if meta_labels else []
    return {
        "id": str(page.get("id", "")),
        "title": page.get("title", ""),
        "status": page.get("status", ""),
        "space_id": str(page.get("spaceId", "") or space.get("id", "")),
        "space_key": space.get("key", ""),
        "parent_id": str(page.get("parentId") or ""),
        "version": version.get("number"),
        "version_message": version.get("message", ""),
        "last_modified": version.get("createdAt") or version.get("when", ""),
        "labels": labels,
        "url": web_url(page.get("_links")),
    }


def fetch_page_labels(page_id: str) -> list[str]:
    def v2() -> list[str]:
        payload = CLIENT.request("GET", f"/wiki/api/v2/pages/{page_id}/labels", params={"limit": 100})
        return [l.get("name", "") for l in (payload or {}).get("results") or []]

    def v1() -> list[str]:
        payload = CLIENT.request("GET", f"/wiki/rest/api/content/{page_id}/label", params={"limit": 100})
        return [l.get("name", "") for l in (payload or {}).get("results") or []]

    try:
        return confluence_call(v2, v1, "labels")
    except ToolError:
        return []


def _read_page(page_id: str, want_body: bool) -> dict:
    def v2() -> dict:
        return CLIENT.request("GET", f"/wiki/api/v2/pages/{page_id}",
                              params={"body-format": "storage"} if want_body else None)

    def v1() -> dict:
        expand = "version,space" + (",body.storage" if want_body else "") + ",metadata.labels"
        return CLIENT.request("GET", f"/wiki/rest/api/content/{page_id}", params={"expand": expand})

    page = confluence_call(v2, v1, f"get page {page_id}")
    if not isinstance(page, dict):
        raise ToolError(f"Unexpected response reading page {page_id}.")
    return page


def _page_storage(page: dict) -> str:
    return ((page.get("body") or {}).get("storage") or {}).get("value", "")


def _find_page_by_title(title: str, space_key: str) -> str:
    def v2() -> list[dict]:
        params: dict[str, Any] = {"title": title, "limit": 2}
        if space_key:
            params["space-id"] = resolve_space_id(space_key)
        return (CLIENT.request("GET", "/wiki/api/v2/pages", params=params) or {}).get("results") or []

    def v1() -> list[dict]:
        params: dict[str, Any] = {"title": title, "limit": 2, "type": "page"}
        if space_key:
            params["spaceKey"] = space_key
        return (CLIENT.request("GET", "/wiki/rest/api/content", params=params) or {}).get("results") or []

    found = confluence_call(v2, v1, "find page by title")
    if not found:
        where = f" in space {space_key}" if space_key else ""
        raise ToolError(f"No page titled {title!r}{where}. Titles must match exactly; try confluence_search.")
    if len(found) > 1:
        listed = ", ".join(f"{p.get('title')} (id {p.get('id')})" for p in found)
        raise ToolError(f"Title {title!r} is ambiguous: {listed}. Call again with page_id.")
    return str(found[0].get("id"))


def confluence_get_page(
    page_id: str = "",
    title: str = "",
    space_key: str = "",
    body_format: str = "text",
    include_labels: bool = True,
) -> tuple[str, dict]:
    if not page_id and not title:
        raise ToolError("Provide either page_id, or title together with space_key.")
    if not page_id:
        page_id = _find_page_by_title(title, space_key)

    want_body = body_format in ("text", "storage", "both")
    page = _read_page(page_id, want_body)

    data = summarize_page(page)
    if include_labels and not data["labels"]:
        data["labels"] = fetch_page_labels(page_id)
    labels = data["labels"]
    storage = _page_storage(page)

    if body_format in ("text", "both"):
        data["body_text"] = storage_to_text(storage)
    if body_format in ("storage", "both"):
        data["body_storage"] = storage
    data["api"] = confluence_api_in_use()

    lines = [
        f"# {data['title']}",
        f"page_id: {data['id']}  |  version: {data['version']}  |  status: {data['status']}",
        f"url: {data['url']}",
    ]
    if labels:
        lines.append(f"labels: {', '.join(labels)}")
    if data.get("body_text"):
        lines += ["", "--- content ---", data["body_text"]]
    elif data.get("body_storage"):
        lines += ["", "--- storage XHTML ---", data["body_storage"]]
    return truncate("\n".join(lines)), data


def confluence_search(
    cql: str = "",
    text: str = "",
    space_key: str = "",
    label: str = "",
    title: str = "",
    limit: int = 25,
) -> tuple[str, dict]:
    if not cql:
        clauses: list[str] = []
        if space_key:
            clauses.append(f'space = "{space_key}"')
        if label:
            for one in [l.strip() for l in label.split(",") if l.strip()]:
                clauses.append(f'label = "{one}"')
        if title:
            clauses.append(f'title ~ "{title}"')
        if text:
            clauses.append(f'text ~ "{text}"')
        if not clauses:
            raise ToolError(
                "Give a cql string, or at least one of text / space_key / label / title. "
                'Example cql: type = page AND label = "MC" ORDER BY lastmodified DESC'
            )
        clauses.append("type = page")
        cql = " AND ".join(clauses) + " ORDER BY lastmodified DESC"

    limit = max(1, min(int(limit or 25), 100))
    payload = CLIENT.request(
        "GET", "/wiki/rest/api/search",
        params={"cql": cql, "limit": limit, "expand": "content.version,content.space"},
    )

    results = []
    for hit in (payload or {}).get("results") or []:
        content = hit.get("content") or {}
        excerpt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", hit.get("excerpt") or "")).strip()
        results.append({
            "id": str(content.get("id") or ""),
            "title": content.get("title") or hit.get("title") or "",
            "type": content.get("type") or "",
            "space": ((content.get("space") or {}).get("key")) or "",
            "version": ((content.get("version") or {}).get("number")),
            "last_modified": hit.get("lastModified") or "",
            "excerpt": excerpt,
            "url": web_url(content.get("_links")) or (CONFIG.base_url + (hit.get("url") or "")),
        })

    total = (payload or {}).get("totalSize", len(results))
    data = {"cql": cql, "total": total, "returned": len(results), "results": results}

    lines = [f"CQL: {cql}", f"{len(results)} of ~{total} result(s)", ""]
    for item in results:
        lines.append(f"- [{item['id']}] {item['title']}  (space {item['space']}, v{item['version']})")
        if item["excerpt"]:
            lines.append(f"    {item['excerpt'][:220]}")
        lines.append(f"    {item['url']}")
    if not results:
        lines.append("(no matches - check the space key, label spelling, or widen the query)")
    return truncate("\n".join(lines)), data


def confluence_create_page(
    space_key: str,
    title: str,
    body: str = "",
    parent_id: str = "",
    body_format: str = "storage",
) -> tuple[str, dict]:
    CLIENT.require_write("confluence_create_page")
    if not space_key or not title:
        raise ToolError("space_key and title are both required.")
    value = (text_to_storage(body) if body_format == "text" else body) or "<p></p>"

    def v2() -> dict:
        payload: dict[str, Any] = {
            "spaceId": resolve_space_id(space_key),
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": value},
        }
        if parent_id:
            payload["parentId"] = str(parent_id)
        return CLIENT.request("POST", "/wiki/api/v2/pages", json_body=payload)

    def v1() -> dict:
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {"storage": {"value": value, "representation": "storage"}},
        }
        if parent_id:
            payload["ancestors"] = [{"id": str(parent_id)}]
        return CLIENT.request("POST", "/wiki/rest/api/content", json_body=payload)

    page = confluence_call(v2, v1, "create page")
    data = summarize_page(page or {})
    data["api"] = confluence_api_in_use()
    return (
        f"Created page {data['id']} \"{data['title']}\" (v{data['version']}) in {space_key}.\n{data['url']}",
        data,
    )


def confluence_update_page(
    page_id: str,
    body: str = "",
    title: str = "",
    body_format: str = "storage",
    mode: str = "replace",
    version_message: str = "",
) -> tuple[str, dict]:
    CLIENT.require_write("confluence_update_page")
    if not page_id:
        raise ToolError("page_id is required.")
    if mode not in ("replace", "append", "prepend"):
        raise ToolError("mode must be one of: replace, append, prepend.")

    new_fragment = text_to_storage(body) if body_format == "text" else body

    # Optimistic locking: read the current version, then PUT version+1. A
    # concurrent save returns 409, so re-read once and retry rather than clobber.
    for attempt in range(2):
        current = _read_page(page_id, want_body=True)
        current_version = int((current.get("version") or {}).get("number") or 0)
        current_body = _page_storage(current)
        current_title = current.get("title", "")

        if mode == "append":
            value = current_body + "\n" + new_fragment
        elif mode == "prepend":
            value = new_fragment + "\n" + current_body
        else:
            value = new_fragment

        # Reusing the fetched title is required - sending a different one trips
        # "a page with this title already exists".
        final_title = title or current_title
        message = version_message or f"Updated via {SERVER_NAME}"

        def v2() -> dict:
            return CLIENT.request("PUT", f"/wiki/api/v2/pages/{page_id}", json_body={
                "id": str(page_id),
                "status": "current",
                "title": final_title,
                "body": {"representation": "storage", "value": value},
                "version": {"number": current_version + 1, "message": message},
            })

        def v1() -> dict:
            return CLIENT.request("PUT", f"/wiki/rest/api/content/{page_id}", json_body={
                "version": {"number": current_version + 1, "message": message},
                "title": final_title,
                "type": "page",
                "body": {"storage": {"value": value, "representation": "storage"}},
            })

        try:
            page = confluence_call(v2, v1, "update page")
        except ToolError as error:
            if error.status == 409 and attempt == 0:
                log("409 conflict on update; re-reading page and retrying once")
                continue
            raise
        data = summarize_page(page or {})
        data["mode"] = mode
        data["api"] = confluence_api_in_use()
        return (
            f"Updated page {data['id']} \"{data['title']}\" to v{data['version']} (mode: {mode}).\n{data['url']}",
            data,
        )
    raise ToolError(f"Page {page_id} kept changing under us; update abandoned after 2 attempts.")


# ---------------------------------------------------------------------------
# Jira helpers
# ---------------------------------------------------------------------------

# /rest/api/3/search/jql returns ONLY id and key unless fields are named
# explicitly, so every search sends this set by default.
DEFAULT_SEARCH_FIELDS = [
    "summary", "status", "issuetype", "labels", "components", "priority",
    "assignee", "reporter", "parent", "created", "updated", "resolution",
    "fixVersions", "duedate",
]

DEFAULT_ISSUE_FIELDS = DEFAULT_SEARCH_FIELDS + ["description", "issuelinks", "subtasks"]


def simplify_field(name: str, value: Any) -> Any:
    """Collapse Jira's deeply nested field objects into plain values."""
    if value is None:
        return None
    if isinstance(value, dict):
        if value.get("type") == "doc":  # ADF rich text
            return adf_to_text(value).strip()
        if name == "status":
            category = (value.get("statusCategory") or {}).get("name", "")
            return {"name": value.get("name", ""), "category": category}
        if name == "comment":
            comments = [
                {
                    "author": ((c.get("author") or {}).get("displayName", "")),
                    "created": c.get("created", ""),
                    "body": adf_to_text(c.get("body")).strip(),
                }
                for c in value.get("comments") or []
            ]
            return {"total": value.get("total", len(comments)), "comments": comments}
        for key in ("displayName", "name", "value"):
            if key in value:
                return value[key]
        if "key" in value:
            return value["key"]
        return value
    if isinstance(value, list):
        return [simplify_field(name, item) for item in value]
    return value


def simplify_issue(issue: dict) -> dict:
    fields = issue.get("fields") or {}
    simple: dict[str, Any] = {
        "key": issue.get("key", ""),
        "id": str(issue.get("id", "")),
        "url": f"{CONFIG.base_url}/browse/{issue.get('key', '')}",
    }
    for name, value in fields.items():
        if value in (None, [], ""):
            continue
        if name == "parent" and isinstance(value, dict):
            simple["parent"] = value.get("key", "")
            continue
        if name == "subtasks" and isinstance(value, list):
            simple["subtasks"] = [s.get("key", "") for s in value]
            continue
        if name == "issuelinks" and isinstance(value, list):
            links = []
            for link in value:
                other = link.get("outwardIssue") or link.get("inwardIssue") or {}
                if other.get("key"):
                    links.append(f"{(link.get('type') or {}).get('name', 'relates')}: {other['key']}")
            if links:
                simple["issuelinks"] = links
            continue
        simple[name] = simplify_field(name, value)
    return simple


def format_issue_rows(issues: list[dict]) -> list[str]:
    lines = []
    for issue in issues:
        status = issue.get("status")
        status_text = status.get("name") if isinstance(status, dict) else (status or "")
        bits = [f"{issue.get('key', ''):<12}", f"{str(status_text):<14}", str(issue.get("summary", ""))[:90]]
        line = "  ".join(bits)
        extras = []
        if issue.get("labels"):
            extras.append("labels=" + ",".join(issue["labels"]))
        if issue.get("components"):
            extras.append("components=" + ",".join(str(c) for c in issue["components"]))
        if issue.get("assignee"):
            extras.append(f"assignee={issue['assignee']}")
        if extras:
            line += "\n              " + "  ".join(extras)
        lines.append(line)
    return lines


def normalize_fields_arg(fields: Any, default: list[str]) -> list[str]:
    if not fields:
        return list(default)
    if isinstance(fields, str):
        return [f.strip() for f in fields.split(",") if f.strip()]
    return [str(f) for f in fields]


# ---------------------------------------------------------------------------
# Jira tools
# ---------------------------------------------------------------------------

COUNT_PAGE_SIZE = 100
COUNT_HARD_CAP = 100000


def jira_count(jql: str) -> tuple[int | None, str]:
    """Total matches for a JQL query.

    /rest/api/3/search/jql deliberately stopped returning `total`, so the count
    comes from the dedicated endpoint. That endpoint is itself flagged for
    change, so if it is unavailable we page through ids only - cheap, because no
    fields come back - and return an exact count instead.

    Returns (count, method) where method is approximate | exact | unavailable.
    """
    try:
        payload = CLIENT.request("POST", "/rest/api/3/search/approximate-count",
                                 json_body={"jql": jql})
        if isinstance(payload, dict):
            for key in ("count", "approximateCount", "total", "issueCount"):
                value = payload.get(key)
                if isinstance(value, int):
                    return value, "approximate"
    except ToolError as error:
        if error.status not in (400, 404, 405, 410, 501):
            log(f"approximate-count failed ({error.status}); falling back to paged count")

    total = 0
    token = ""
    for _page in range(COUNT_HARD_CAP // COUNT_PAGE_SIZE):
        body: dict[str, Any] = {"jql": jql, "maxResults": COUNT_PAGE_SIZE, "fields": ["id"]}
        if token:
            body["nextPageToken"] = token
        try:
            payload = CLIENT.request("POST", "/rest/api/3/search/jql", json_body=body)
        except ToolError:
            return (total or None), ("exact" if total else "unavailable")
        if not isinstance(payload, dict):
            break
        total += len(payload.get("issues") or [])
        token = payload.get("nextPageToken") or ""
        if not token or payload.get("isLast") is True:
            return total, "exact"
    return total, "exact (capped)"


def jira_search_issues(
    jql: str,
    fields: Any = None,
    max_results: int = 50,
    next_page_token: str = "",
    fetch_all: bool = False,
    count_only: bool = False,
    max_total: int = 1000,
) -> tuple[str, dict]:
    if not jql or not jql.strip():
        raise ToolError(
            'jql is required. Examples: project = SMP AND labels = "MC" ORDER BY created DESC  |  '
            'project = SMP AND issuetype = Test AND status != Done'
        )

    if count_only:
        total, method = jira_count(jql)
        if total is None:
            raise ToolError(f"Could not count matches for this JQL. Check the syntax: {jql}")
        data = {"jql": jql, "total": total, "count_method": method, "issues": []}
        return (f"JQL: {jql}\n{total:,} issue(s) match ({method} count).\n"
                f"No issues fetched - count_only was set."), data

    field_list = normalize_fields_arg(fields, DEFAULT_SEARCH_FIELDS)
    page_size = max(1, min(int(max_results or 50), 100))
    collected: list[dict] = []
    token = next_page_token or ""
    pages = 0
    hard_cap = max(1, min(int(max_total or 1000), COUNT_HARD_CAP)) if fetch_all else page_size

    while True:
        body: dict[str, Any] = {"jql": jql, "maxResults": page_size, "fields": field_list}
        if token:
            body["nextPageToken"] = token
        try:
            payload = CLIENT.request("POST", "/rest/api/3/search/jql", json_body=body)
        except ToolError as error:
            if "unbounded" in str(error).lower():
                # Splice the restriction before ORDER BY so the suggestion is
                # valid JQL the model can use verbatim.
                order = re.search(r"(?i)\border\s+by\b.*$", jql.strip())
                where = jql.strip()[:order.start()].strip() if order else jql.strip()
                tail = (" " + order.group(0).strip()) if order else ""
                joiner = " AND " if where else ""
                raise ToolError(
                    f"Jira rejected this as an unbounded query: every search needs at least "
                    f"one restricting clause, and sorting alone is not one. Add a project, "
                    f"key, date or field filter, e.g.\n"
                    f"  project = SMP{joiner}{where}{tail}\n"
                    f"  created >= -30d{joiner}{where}{tail}"
                ) from error
            raise
        if not isinstance(payload, dict):
            raise ToolError("Unexpected response from Jira search.")

        collected.extend(simplify_issue(i) for i in payload.get("issues") or [])
        token = payload.get("nextPageToken") or ""
        pages += 1
        is_last = payload.get("isLast")
        if not fetch_all or not token or is_last is True or len(collected) >= hard_cap:
            break

    total, method = jira_count(jql)
    data = {
        "jql": jql,
        "total": total,
        "count_method": method,
        "returned": len(collected),
        "next_page_token": token,
        "issues": collected[:hard_cap],
    }

    if total is None:
        headline = f"{len(collected)} issue(s) returned (total unavailable)"
    elif total > len(collected):
        headline = (f"{total:,} issue(s) match ({method} count). "
                    f"Showing {len(collected)}.")
    else:
        headline = f"{total:,} issue(s) match ({method} count). All shown."

    lines = [f"JQL: {jql}", headline, ""]
    lines.extend(format_issue_rows(data["issues"]))
    if not collected:
        lines.append("(no matches  -  verify the project key, label spelling and field names)")
    if token:
        lines.append(f"\nMore results available. Pass next_page_token=\"{token}\" to continue, "
                     f"or fetch_all=true with max_total to pull more in one call.")
    if total and total > 2000 and not count_only:
        lines.append(f"\nThat is a large result set. For an inventory figure use count_only=true, "
                     f"which returns the number without pulling {total:,} records into context.")
    return truncate("\n".join(lines)), data


def jira_get_issue(
    issue_key: str,
    fields: Any = None,
    include_comments: bool = True,
) -> tuple[str, dict]:
    if not issue_key:
        raise ToolError("issue_key is required, e.g. SMP-4245.")

    field_list = normalize_fields_arg(fields, DEFAULT_ISSUE_FIELDS)
    if include_comments and "comment" not in field_list and "*all" not in field_list:
        field_list = field_list + ["comment"]

    issue = CLIENT.request(
        "GET", f"/rest/api/3/issue/{quote(issue_key)}",
        params={"fields": ",".join(field_list)},
    )
    if not isinstance(issue, dict):
        raise ToolError(f"Unexpected response reading issue {issue_key}.")

    data = simplify_issue(issue)
    status = data.get("status")
    status_text = status.get("name") if isinstance(status, dict) else (status or "")

    lines = [
        f"# {data.get('key')}  -  {data.get('summary', '')}",
        f"status: {status_text}   type: {data.get('issuetype', '')}   priority: {data.get('priority', '')}",
        f"assignee: {data.get('assignee', 'Unassigned')}   reporter: {data.get('reporter', '')}",
        f"url: {data.get('url')}",
    ]
    if data.get("labels"):
        lines.append(f"labels: {', '.join(data['labels'])}")
    if data.get("components"):
        lines.append(f"components: {', '.join(str(c) for c in data['components'])}")
    if data.get("parent"):
        lines.append(f"parent: {data['parent']}")
    if data.get("subtasks"):
        lines.append(f"subtasks: {', '.join(data['subtasks'])}")
    if data.get("issuelinks"):
        lines.append(f"links: {'; '.join(data['issuelinks'])}")
    if data.get("description"):
        lines += ["", "--- description ---", str(data["description"])]

    comment_block = data.get("comment") or {}
    if include_comments and isinstance(comment_block, dict) and comment_block.get("comments"):
        lines += ["", f"--- comments ({comment_block.get('total', 0)}) ---"]
        for comment in comment_block["comments"][-10:]:
            lines.append(f"[{comment['created'][:10]}] {comment['author']}: {comment['body']}")
    return truncate("\n".join(lines)), data


def jira_create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str = "",
    labels: Any = None,
    components: Any = None,
    priority: str = "",
    assignee_account_id: str = "",
    parent_key: str = "",
    extra_fields: dict | None = None,
) -> tuple[str, dict]:
    CLIENT.require_write("jira_create_issue")
    if not project_key or not summary:
        raise ToolError("project_key and summary are both required.")

    fields: dict[str, Any] = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = text_to_adf(description)
    if labels:
        fields["labels"] = labels if isinstance(labels, list) else [
            l.strip() for l in str(labels).split(",") if l.strip()
        ]
    if components:
        names = components if isinstance(components, list) else [
            c.strip() for c in str(components).split(",") if c.strip()
        ]
        fields["components"] = [{"name": n} for n in names]
    if priority:
        fields["priority"] = {"name": priority}
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}
    if parent_key:
        fields["parent"] = {"key": parent_key}
    if extra_fields:
        fields.update(extra_fields)

    created = CLIENT.request("POST", "/rest/api/3/issue", json_body={"fields": fields})
    key = (created or {}).get("key", "")
    data = {"key": key, "id": str((created or {}).get("id", "")), "url": f"{CONFIG.base_url}/browse/{key}"}
    return f"Created {key} in {project_key}.\n{data['url']}", data


def jira_update_issue(
    issue_key: str,
    summary: str = "",
    description: str = "",
    labels_set: Any = None,
    labels_add: Any = None,
    labels_remove: Any = None,
    priority: str = "",
    assignee_account_id: str = "",
    extra_fields: dict | None = None,
    notify_users: bool = True,
) -> tuple[str, dict]:
    CLIENT.require_write("jira_update_issue")
    if not issue_key:
        raise ToolError("issue_key is required, e.g. SMP-4245.")

    def as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v) for v in value]
        return [v.strip() for v in str(value).split(",") if v.strip()]

    fields: dict[str, Any] = {}
    update: dict[str, Any] = {}

    if summary:
        fields["summary"] = summary
    if description:
        fields["description"] = text_to_adf(description)
    if labels_set is not None:
        fields["labels"] = as_list(labels_set)
    if priority:
        fields["priority"] = {"name": priority}
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}
    if extra_fields:
        fields.update(extra_fields)
    if labels_add:
        update.setdefault("labels", []).extend({"add": l} for l in as_list(labels_add))
    if labels_remove:
        update.setdefault("labels", []).extend({"remove": l} for l in as_list(labels_remove))

    if not fields and not update:
        raise ToolError("Nothing to update  -  supply at least one field to change.")
    if "labels" in fields and "labels" in update:
        raise ToolError("Use either labels_set or labels_add/labels_remove, not both.")

    payload: dict[str, Any] = {}
    if fields:
        payload["fields"] = fields
    if update:
        payload["update"] = update

    CLIENT.request(
        "PUT", f"/rest/api/3/issue/{quote(issue_key)}",
        params={"notifyUsers": "true" if notify_users else "false"},
        json_body=payload,
    )
    changed = sorted(set(fields) | set(update))
    data = {
        "key": issue_key,
        "updated_fields": changed,
        "url": f"{CONFIG.base_url}/browse/{issue_key}",
    }
    return f"Updated {issue_key}: {', '.join(changed)}.\n{data['url']}", data


def jira_get_transitions(issue_key: str) -> tuple[str, dict]:
    if not issue_key:
        raise ToolError("issue_key is required, e.g. SMP-4245.")

    payload = CLIENT.request(
        "GET", f"/rest/api/3/issue/{quote(issue_key)}/transitions",
        params={"expand": "transitions.fields"},
    )
    transitions = []
    for transition in (payload or {}).get("transitions") or []:
        required = [
            name
            for name, spec in (transition.get("fields") or {}).items()
            if spec.get("required")
        ]
        transitions.append({
            "id": str(transition.get("id", "")),
            "name": transition.get("name", ""),
            "to_status": ((transition.get("to") or {}).get("name", "")),
            "required_fields": required,
        })

    data = {"key": issue_key, "transitions": transitions}
    lines = [f"Transitions available on {issue_key} for this account:", ""]
    for transition in transitions:
        line = f"  id={transition['id']:<5} {transition['name']}  ->  {transition['to_status']}"
        if transition["required_fields"]:
            line += f"   (requires: {', '.join(transition['required_fields'])})"
        lines.append(line)
    if not transitions:
        lines.append("  (none  -  the issue may be closed, or the workflow allows no moves for this user)")
    return "\n".join(lines), data


def jira_transition_issue(
    issue_key: str,
    transition: str,
    comment: str = "",
    resolution: str = "",
    fields: dict | None = None,
) -> tuple[str, dict]:
    CLIENT.require_write("jira_transition_issue")
    if not issue_key or not transition:
        raise ToolError("issue_key and transition are both required.")

    _, available = jira_get_transitions(issue_key)
    options = available["transitions"]
    if not options:
        raise ToolError(f"{issue_key} has no transitions available to this account.")

    wanted = str(transition).strip()
    match = next((t for t in options if t["id"] == wanted), None)
    if match is None:
        match = next((t for t in options if t["name"].lower() == wanted.lower()), None)
    if match is None:
        match = next((t for t in options if t["to_status"].lower() == wanted.lower()), None)
    if match is None:
        listed = ", ".join(f"{t['name']} (id {t['id']} -> {t['to_status']})" for t in options)
        raise ToolError(f"No transition matching {transition!r} on {issue_key}. Available: {listed}")

    payload: dict[str, Any] = {"transition": {"id": match["id"]}}
    if fields:
        payload["fields"] = dict(fields)
    if resolution:
        payload.setdefault("fields", {})["resolution"] = {"name": resolution}
    if comment:
        payload["update"] = {"comment": [{"add": {"body": text_to_adf(comment)}}]}

    CLIENT.request("POST", f"/rest/api/3/issue/{quote(issue_key)}/transitions", json_body=payload)
    data = {
        "key": issue_key,
        "transition": match["name"],
        "new_status": match["to_status"],
        "url": f"{CONFIG.base_url}/browse/{issue_key}",
    }
    return (
        f"Transitioned {issue_key} via \"{match['name']}\" -> {match['to_status']}.\n{data['url']}",
        data,
    )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def _string(description: str, **extra: Any) -> dict:
    return {"type": "string", "description": description, **extra}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "confluence_get_page",
        "title": "Get Confluence page",
        "description": (
            "Read a Confluence page by id (or by exact title + space key) and return its "
            "content as readable text, plus metadata and labels/tags. Use this to pull "
            "values out of a page, including tables, which are rendered as pipe-separated rows."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_id": _string("Numeric page id, e.g. \"460947525\". Found in the page URL after /pages/."),
                "title": _string("Exact page title. Only used when page_id is omitted; needs space_key to disambiguate."),
                "space_key": _string("Space key, e.g. \"SMP\"  -  the short code in /wiki/spaces/<KEY>/."),
                "body_format": _string(
                    "How to return the body: \"text\" (readable, default), \"storage\" (raw XHTML, "
                    "needed if you intend to edit and write it back), \"both\", or \"none\" for metadata only.",
                    enum=["text", "storage", "both", "none"], default="text",
                ),
                "include_labels": {"type": "boolean", "description": "Also fetch the page's labels (tags). Default true.", "default": True},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "confluence_search",
        "title": "Search Confluence",
        "description": (
            "Find Confluence pages by CQL, or by any combination of free text, space key, "
            "label (tag) and title. Returns id, title, space, excerpt and URL for each hit. "
            "Best way to locate pages by tag: label=\"MC\". Raw CQL example: "
            "type = page AND space = \"SMP\" AND label = \"MC\" ORDER BY lastmodified DESC"
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "cql": _string("Raw CQL query. Overrides the convenience fields below when supplied."),
                "text": _string("Free-text search across page content and titles."),
                "space_key": _string("Restrict to one space, e.g. \"SMP\"."),
                "label": _string("Label/tag to match. Comma-separate to require several, e.g. \"MC,regression\"."),
                "title": _string("Partial title match."),
                "limit": {"type": "integer", "description": "Max results, 1-100. Default 25.", "default": 25, "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "confluence_create_page",
        "title": "Create Confluence page",
        "description": "Create a new Confluence page in a space, optionally under a parent page.",
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "space_key": _string("Space key to create the page in, e.g. \"SMP\"."),
                "title": _string("Page title. Must be unique within the space."),
                "body": _string("Page content."),
                "parent_id": _string("Optional parent page id, to nest this page beneath it."),
                "body_format": _string(
                    "\"storage\" (default) treats body as Confluence storage XHTML. "
                    "\"text\" wraps plain text into paragraphs for you.",
                    enum=["storage", "text"], default="storage",
                ),
            },
            "required": ["space_key", "title"],
            "additionalProperties": False,
        },
    },
    {
        "name": "confluence_update_page",
        "title": "Update Confluence page",
        "description": (
            "Update an existing Confluence page. Reads the current version first and "
            "increments it, so concurrent edits surface as a conflict rather than being "
            "silently overwritten. mode=append adds to the end instead of replacing."
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_id": _string("Numeric page id to update."),
                "body": _string("New content, or the fragment to append/prepend."),
                "title": _string("New title. Omit to keep the existing title (recommended)."),
                "body_format": _string("\"storage\" (default) or \"text\".", enum=["storage", "text"], default="storage"),
                "mode": _string(
                    "\"replace\" overwrites the whole body (default). \"append\" adds to the end, "
                    "\"prepend\" to the start  -  both preserve existing content.",
                    enum=["replace", "append", "prepend"], default="replace",
                ),
                "version_message": _string("Optional note shown in the page's version history."),
            },
            "required": ["page_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jira_search_issues",
        "title": "Search Jira issues",
        "description": (
            "Search Jira with JQL and return simplified issue records (key, summary, status, "
            "type, labels, components, assignee, dates). This is the main way to pull values "
            "in bulk. Every result reports the TOTAL number of matches, not just the page "
            "size, so a 13,000-issue query reports 13,000. Set count_only=true to get that "
            "number without fetching any issues. The query MUST be bounded - include at least one restricting clause "
            "such as a project, key, date or field filter; a bare ORDER BY is rejected. "
            "Examples: project = SMP AND labels = \"MC\"  |  "
            "project = SMP AND issuetype = Test AND status != Done ORDER BY updated DESC  |  "
            "key in (SMP-4245, SMP-4246)  |  created >= -30d ORDER BY created DESC"
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "jql": _string("JQL query. Required, and must be bounded - at least one "
                               "restricting clause, not just ORDER BY."),
                "fields": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Field names to return. Defaults to a useful set. Use [\"*all\"] for everything, or name custom fields like \"customfield_10014\".",
                },
                "max_results": {"type": "integer", "description": "Page size, 1-100. Default 50.", "default": 50, "minimum": 1, "maximum": 100},
                "next_page_token": _string("Token from a previous call's next_page_token, to fetch the following page."),
                "fetch_all": {"type": "boolean", "description": "Follow pagination automatically up to max_total. Default false.", "default": False},
                "max_total": {"type": "integer", "description": "Ceiling when fetch_all is set. Default 1000, max 100000. Large values pull a lot into context - prefer count_only for inventory figures.", "default": 1000},
                "count_only": {"type": "boolean", "description": "Return ONLY the number of matching issues, fetching none of them. Use this for inventory questions like 'how many test cases are there' - it works for result sets of any size.", "default": False},
            },
            "required": ["jql"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jira_get_issue",
        "title": "Get Jira issue",
        "description": (
            "Read one Jira issue in full by key, including description and comments, with "
            "rich-text (ADF) content flattened to readable text."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_key": _string("Issue key, e.g. \"SMP-4245\"."),
                "fields": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Field names to return. Defaults to a useful set. Use [\"*all\"] for every field including custom ones.",
                },
                "include_comments": {"type": "boolean", "description": "Include the comment thread. Default true.", "default": True},
            },
            "required": ["issue_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jira_create_issue",
        "title": "Create Jira issue",
        "description": "Create a Jira issue. Plain-text description is converted to Atlassian Document Format automatically.",
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_key": _string("Project key, e.g. \"SMP\"."),
                "summary": _string("Issue summary / title."),
                "issue_type": _string("Issue type name as configured in the project, e.g. \"Task\", \"Bug\", \"Test\". Default \"Task\".", default="Task"),
                "description": _string("Description. Plain text or light markdown (#, -, 1., ``` fences)."),
                "labels": {"type": "array", "items": {"type": "string"}, "description": "Labels (tags) to set."},
                "components": {"type": "array", "items": {"type": "string"}, "description": "Component names, which must already exist in the project."},
                "priority": _string("Priority name, e.g. \"High\"."),
                "assignee_account_id": _string("Atlassian accountId of the assignee (not a username or email)."),
                "parent_key": _string("Parent issue key, for subtasks or issues under an epic."),
                "extra_fields": {"type": "object", "description": "Raw Jira field map merged in last, for custom fields e.g. {\"customfield_10014\": \"SMP-1\"}.", "additionalProperties": True},
            },
            "required": ["project_key", "summary"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jira_update_issue",
        "title": "Update Jira issue",
        "description": (
            "Update fields on an existing Jira issue. Labels can be replaced wholesale "
            "(labels_set) or adjusted incrementally (labels_add / labels_remove)."
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_key": _string("Issue key, e.g. \"SMP-4245\"."),
                "summary": _string("New summary."),
                "description": _string("New description. Plain text or light markdown."),
                "labels_set": {"type": "array", "items": {"type": "string"}, "description": "Replace all labels with this list."},
                "labels_add": {"type": "array", "items": {"type": "string"}, "description": "Labels to add, leaving existing ones intact."},
                "labels_remove": {"type": "array", "items": {"type": "string"}, "description": "Labels to remove."},
                "priority": _string("Priority name."),
                "assignee_account_id": _string("Atlassian accountId of the new assignee."),
                "extra_fields": {"type": "object", "description": "Raw Jira field map merged in last, for custom fields.", "additionalProperties": True},
                "notify_users": {"type": "boolean", "description": "Send Jira notification emails for this change. Default true.", "default": True},
            },
            "required": ["issue_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jira_get_transitions",
        "title": "Get available transitions",
        "description": (
            "List the workflow transitions currently available on an issue for the "
            "authenticated account, with each transition's id, name, target status and any "
            "required fields. Call this before jira_transition_issue."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {"issue_key": _string("Issue key, e.g. \"SMP-4245\".")},
            "required": ["issue_key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "jira_transition_issue",
        "title": "Transition Jira issue status",
        "description": (
            "Move an issue through its workflow. The transition may be given as a transition "
            "id, a transition name (\"Start Progress\"), or the target status name (\"Done\")  -  "
            "it is resolved against what is actually available on the issue."
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True},
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_key": _string("Issue key, e.g. \"SMP-4245\"."),
                "transition": _string("Transition id, transition name, or target status name."),
                "comment": _string("Optional comment to add as part of the transition."),
                "resolution": _string("Resolution name to set, e.g. \"Done\". Required by some workflows when closing."),
                "fields": {"type": "object", "description": "Extra fields required by the transition screen.", "additionalProperties": True},
            },
            "required": ["issue_key", "transition"],
            "additionalProperties": False,
        },
    },
]

HANDLERS: dict[str, Callable[..., tuple[str, Any]]] = {
    "confluence_get_page": confluence_get_page,
    "confluence_search": confluence_search,
    "confluence_create_page": confluence_create_page,
    "confluence_update_page": confluence_update_page,
    "jira_search_issues": jira_search_issues,
    "jira_get_issue": jira_get_issue,
    "jira_create_issue": jira_create_issue,
    "jira_update_issue": jira_update_issue,
    "jira_get_transitions": jira_get_transitions,
    "jira_transition_issue": jira_transition_issue,
}


def call_tool(name: str, arguments: dict) -> dict:
    """Run a tool and shape the MCP tools/call result."""
    handler = HANDLERS.get(name)
    if handler is None:
        raise KeyError(name)

    # Drop unknown keys so a hallucinated argument produces a clear message
    # instead of a TypeError traceback.
    schema = next(t for t in TOOLS if t["name"] == name)["inputSchema"]
    allowed = set(schema.get("properties") or {})
    unknown = set(arguments) - allowed
    clean = {k: v for k, v in arguments.items() if k in allowed}

    missing = [
        key for key in (schema.get("required") or [])
        if clean.get(key) in (None, "")
    ]
    if missing:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: {name} requires {', '.join(missing)}. "
                        f"Accepted arguments: {', '.join(sorted(allowed))}.",
            }],
            "isError": True,
        }

    try:
        text, data = handler(**clean)
    except ToolError as error:
        return {"content": [{"type": "text", "text": f"Error: {error}"}], "isError": True}
    except TypeError as error:
        return {
            "content": [{"type": "text", "text": f"Error: bad arguments for {name}: {error}"}],
            "isError": True,
        }
    except Exception as error:  # noqa: BLE001 - never let a bug kill the server
        log(f"unhandled error in {name}: {traceback.format_exc()}")
        return {
            "content": [{"type": "text", "text": f"Error: {type(error).__name__}: {error}"}],
            "isError": True,
        }

    if unknown:
        text = f"(ignored unrecognised argument(s): {', '.join(sorted(unknown))})\n\n{text}"
    return {"content": [{"type": "text", "text": text}], "structuredContent": data, "isError": False}


# ---------------------------------------------------------------------------
# MCP stdio server (JSON-RPC 2.0, newline-delimited)
# ---------------------------------------------------------------------------

def negotiate_protocol(requested: str) -> str:
    """Echo the client's version when we speak it, else offer our newest."""
    return requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]


def handle_message(message: dict) -> dict | None:
    """Return a JSON-RPC response, or None for notifications."""
    method = message.get("method", "")
    message_id = message.get("id")
    params = message.get("params") or {}
    is_notification = message_id is None

    def ok(result: Any) -> dict | None:
        return None if is_notification else {"jsonrpc": "2.0", "id": message_id, "result": result}

    def fail(code: int, text: str) -> dict | None:
        return None if is_notification else {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": text}}

    if method == "initialize":
        return ok({
            "protocolVersion": negotiate_protocol(params.get("protocolVersion", "")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "title": "Atlassian (Confluence + Jira)", "version": SERVER_VERSION},
            "instructions": (
                "Confluence and Jira access for this Atlassian site. Search first "
                "(jira_search_issues with JQL, confluence_search with CQL or a label), then "
                "read specific items. Tags are Jira 'labels' and Confluence 'label'. "
                "Call jira_get_transitions before jira_transition_issue."
            ),
        })

    if method in ("notifications/initialized", "notifications/cancelled", "notifications/progress"):
        return None
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

    # Declared capabilities do not include these, but some clients probe anyway.
    if method == "resources/list":
        return ok({"resources": []})
    if method == "prompts/list":
        return ok({"prompts": []})

    return fail(-32601, f"Method not found: {method}")


def serve_stdio() -> None:
    # stdout must carry framed JSON only, and Windows must not rewrite \n as \r\n.
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
    CONFIG.__init__()  # re-read now that .env is loaded
    log(f"{SERVER_NAME} {SERVER_VERSION} ready ({len(TOOLS)} tools)")
    log(f"env file: {env_path or 'none found  -  relying on process environment'}")
    log(f"site: {CONFIG.base_url or '(ATLASSIAN_BASE_URL not set)'}  read_only={CONFIG.read_only}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            write_message({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {error}"}})
            continue

        # Pre-2025-06-18 clients may still send JSON-RPC batches.
        batch = message if isinstance(message, list) else [message]
        for item in batch:
            if not isinstance(item, dict):
                continue
            try:
                response = handle_message(item)
            except Exception:  # noqa: BLE001 - a bug must not take the server down
                log(f"fatal handler error: {traceback.format_exc()}")
                response = {
                    "jsonrpc": "2.0", "id": item.get("id"),
                    "error": {"code": -32603, "message": "Internal server error; see stderr log."},
                }
            if response is not None:
                write_message(response)

    log("stdin closed  -  shutting down")


def write_message(payload: dict) -> None:
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, ValueError):
        # The client closed the pipe (normal shutdown, or VS Code restarting the
        # server). Exit quietly rather than dumping a traceback into its log.
        log("stdout closed by client  -  exiting")
        os._exit(0)


# ---------------------------------------------------------------------------
# CLI helpers for verifying the install without an MCP client
# ---------------------------------------------------------------------------

# One issue carrying every shape the simplifiers have to handle: ADF rich text,
# a status object, a comment thread, a parent, subtasks and a link.
SHAPE_FIXTURE_ISSUE = {
    "key": "SMP-16660",
    "id": 123456,
    "fields": {
        "summary": "Sender ID update returns 500",
        "status": {"name": "In Progress", "statusCategory": {"name": "In Progress"}},
        "assignee": {"displayName": "A Perera"},
        "labels": ["regression", "smoke"],
        "parent": {"key": "SMP-16000"},
        "subtasks": [{"key": "SMP-16661"}],
        "issuelinks": [{"type": {"name": "blocks"}, "outwardIssue": {"key": "SMP-16999"}}],
        "description": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Steps to reproduce"}]}]},
        "comment": {"total": 1, "comments": [{
            "author": {"displayName": "B Silva"},
            "created": "2026-08-20T10:00:00.000+0000",
            "body": {"type": "doc", "version": 1, "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Reproduced on 7.0"}]}]},
        }]},
        "nothing_here": None,
    },
}


def shape_check() -> list[str]:
    """Run the payload shapers over canned data. No credentials, no network.

    Every tool answer passes through these functions, so one mistyped attribute
    in them breaks every call while the file still imports and the server still
    starts happily. That failure mode is otherwise only visible as a traceback
    on the first tool call, from inside a client. Checking here turns it into
    one named line before any network work is attempted.
    """
    problems: list[str] = []

    def check(label: str, function: Callable[..., Any], *args: Any) -> Any:
        try:
            return function(*args)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{label} raised {type(error).__name__}: {error}")
            return None

    simple = check("simplify_issue", simplify_issue, SHAPE_FIXTURE_ISSUE)
    if isinstance(simple, dict):
        for field, want in (("key", "SMP-16660"), ("id", "123456"), ("parent", "SMP-16000"),
                            ("assignee", "A Perera"), ("subtasks", ["SMP-16661"]),
                            ("issuelinks", ["blocks: SMP-16999"]),
                            ("labels", ["regression", "smoke"])):
            if simple.get(field) != want:
                problems.append(f"simplify_issue[{field}] gave {simple.get(field)!r}, "
                                f"expected {want!r}")
        if (simple.get("status") or {}).get("name") != "In Progress":
            problems.append(f"simplify_issue[status] gave {simple.get('status')!r}")
        if "Steps to reproduce" not in str(simple.get("description", "")):
            problems.append("simplify_issue[description] lost the ADF text")
        if "nothing_here" in simple:
            problems.append("simplify_issue kept an empty field it should have dropped")
        comments = (simple.get("comment") or {}).get("comments") or []
        if not comments or "Reproduced on" not in str(comments[0].get("body", "")):
            problems.append("simplify_issue[comment] lost the comment body")

    rows = check("format_issue_rows", format_issue_rows,
                 [simple] if isinstance(simple, dict) else [])
    if rows is not None and (not rows or "SMP-16660" not in rows[0]):
        problems.append("format_issue_rows dropped the issue key")

    text = check("storage_to_text", storage_to_text,
                 "<h2>Forecast</h2><table><tbody>"
                 "<tr><th><p>Person</p></th><th><p>Load</p></th></tr>"
                 "<tr><td><p>Ben Jones</p></td><td><p>0.8</p></td></tr>"
                 "</tbody></table><ul><li>First bullet</li></ul>")
    if text is not None and ("Ben Jones" not in text or "Person" not in text):
        problems.append("storage_to_text lost the table cells")

    if check("simplify_field", simplify_field, "components", [{"name": "SMS"}]) not in (None, ["SMS"]):
        problems.append("simplify_field did not flatten a component list to names")

    # The degenerate inputs a real tenant will eventually send.
    check("adf_to_text(None)", adf_to_text, None)
    check("storage_to_text('')", storage_to_text, "")
    check("simplify_issue({})", simplify_issue, {})
    return problems


def selftest() -> int:
    env_path = load_environment()
    CONFIG.__init__()
    print(f"env file        : {env_path or '(none found)'}")
    print(f"base url        : {CONFIG.base_url or '(unset)'}")
    print(f"email           : {CONFIG.email or '(unset)'}")
    print(f"api token       : {'set (' + str(len(CONFIG.token)) + ' chars)' if CONFIG.token else '(unset)'}")
    print(f"verify tls      : {CONFIG.verify_tls}")
    print(f"read only       : {CONFIG.read_only}")
    print(f"confluence api  : {CONFIG.confluence_api}")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "REQUESTS_CA_BUNDLE"):
        value = os.environ.get(name) or os.environ.get(name.lower()) or ""
        if value:
            print(f"{name:<16}: {value}")
    print(f"explicit proxy  : {CONFIG.proxy or '(none)'}")
    print("-" * 60)

    # Offline first: this needs no credentials, so it still answers on a bare
    # machine, and it tells a damaged file apart from a network problem.
    shape_problems = shape_check()
    if shape_problems:
        print(f"FAIL  shape        : {len(shape_problems)} payload check(s) failed  -  this file "
              f"is damaged, not misconfigured")
        for line in shape_problems[:6]:
            print(f"      {line}")
        if len(shape_problems) > 6:
            print(f"      ... {len(shape_problems) - 6} more")
        print("      Every tool answer passes through these, so every call would fail.")
        print("      Re-paste the file, then restart the MCP server so the fix is loaded.")
    else:
        print("PASS  shape        : payload shaping intact (offline, no credentials needed)")

    try:
        CONFIG.validate()
    except ToolError as error:
        print(f"FAIL  config: {error}")
        return 1

    failures = 1 if shape_problems else 0

    try:
        me = CLIENT.request("GET", "/rest/api/3/myself")
        print(f"PASS  Jira auth      : {me.get('displayName')} <{me.get('emailAddress', 'hidden')}>")
    except ToolError as error:
        print(f"FAIL  Jira auth      : {error}")
        failures += 1

    try:
        # Must be BOUNDED - this Jira rejects "unbounded" JQL that has no
        # restricting clause, so a bare ORDER BY is a 400.
        payload = CLIENT.request("POST", "/rest/api/3/search/jql",
                                 json_body={"jql": "created >= -30d ORDER BY created DESC",
                                            "maxResults": 1, "fields": ["summary"]})
        issues = payload.get("issues") or []
        sample = issues[0].get("key") if issues else "(none created in the last 30 days)"
        print(f"PASS  Jira search    : /search/jql reachable, sample {sample}")
    except ToolError as error:
        print(f"FAIL  Jira search    : {error}")
        failures += 1

    v2_ok = False
    try:
        spaces = CLIENT.request("GET", "/wiki/api/v2/spaces", params={"limit": 3})
        keys = [s.get("key") for s in (spaces.get("results") or [])]
        print(f"PASS  Confluence v2  : spaces visible {keys}")
        v2_ok = True
    except ToolError as error:
        print(f"WARN  Confluence v2  : {error}")
        print("      Not fatal - the server falls back to v1 automatically.")

    try:
        probe = CLIENT.request("GET", "/wiki/rest/api/content", params={"limit": 1, "type": "page"})
        n = len((probe or {}).get("results") or [])
        print(f"PASS  Confluence v1  : /wiki/rest/api/content reachable ({n} page visible)")
        print(f"      -> the endpoints pmo-inline already uses work from here.")
    except ToolError as error:
        print(f"FAIL  Confluence v1  : {error}")
        if not v2_ok:
            print("      Neither API version answered - Confluence tools will not work.")
            failures += 1

    try:
        CLIENT.request("GET", "/wiki/rest/api/search", params={"cql": "type = page", "limit": 1})
        print("PASS  Confluence CQL : /wiki/rest/api/search reachable")
    except ToolError as error:
        print(f"WARN  Confluence CQL : {error}")
        print("      confluence_search will not work; everything else is unaffected.")

    print("-" * 60)
    print("All good  -  add the server to mcp.json." if failures == 0 else f"{failures} check(s) failed.")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--selftest", action="store_true", help="Verify credentials and endpoint connectivity, then exit.")
    parser.add_argument("--list-tools", action="store_true", help="Print the tool names and schemas, then exit.")
    parser.add_argument("--call", nargs=2, metavar=("TOOL", "JSON_ARGS"), help="Invoke one tool directly for debugging.")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if args.list_tools:
        for tool in TOOLS:
            required = tool["inputSchema"].get("required") or []
            print(f"\n{tool['name']}  ({'read-only' if tool['annotations'].get('readOnlyHint') else 'write'})")
            print(f"  {tool['description']}")
            for key, spec in (tool["inputSchema"].get("properties") or {}).items():
                mark = "*" if key in required else " "
                print(f"   {mark} {key} ({spec.get('type')}): {spec.get('description', '')}")
        return 0

    if args.call:
        load_environment()
        CONFIG.__init__()
        name, raw = args.call
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError as error:
            print(f"Arguments must be valid JSON: {error}", file=sys.stderr)
            return 2
        try:
            result = call_tool(name, arguments)
        except KeyError:
            print(f"Unknown tool: {name}. Known: {', '.join(HANDLERS)}", file=sys.stderr)
            return 2
        print(result["content"][0]["text"])
        return 1 if result.get("isError") else 0

    serve_stdio()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
