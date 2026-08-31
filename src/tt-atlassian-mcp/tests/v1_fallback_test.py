"""Prove the Confluence v1 fallback works when a tenant has no v2."""
import os
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
import importlib.util, sys
sys.path.insert(0, ".")
import mock_atlassian as mock

os.environ.update({"ATLASSIAN_ENV_FILE": "/nonexistent",
                   "ATLASSIAN_BASE_URL": f"http://127.0.0.1:{mock.PORT}",
                   "ATLASSIAN_EMAIL": "a@b.c", "ATLASSIAN_API_TOKEN": "t",
                   "ATLASSIAN_READ_ONLY": "false",
                   "ATLASSIAN_CONFLUENCE_API": "auto"})
spec = importlib.util.spec_from_file_location("srv", "../atlassian_mcp_server.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def paths():
    return [c["path"] for c in mock.CALLS]

print("=== 1. v2 available: should use v2 and never touch v1 ===")
mock.STATE["v2_enabled"] = True; mock.CALLS.clear()
text, data = m.confluence_get_page(page_id="460947525")
assert any("/wiki/api/v2/pages/460947525" in p for p in paths()), paths()
assert not any("/wiki/rest/api/content" in p for p in paths()), paths()
print(f"    api used: {data['api']}   title: {data['title']}")
print(f"    labels: {data['labels']}   version: {data['version']}")

print("\n=== 2. tenant has NO v2: must fall back to v1 automatically ===")
m._CONFLUENCE_MODE["resolved"] = None
mock.STATE["v2_enabled"] = False; mock.CALLS.clear()
text, data = m.confluence_get_page(page_id="460947525")
assert any("/wiki/rest/api/content/460947525" in p for p in paths()), paths()
print(f"    api used: {data['api']}")
print(f"    tried v2 first: {any('/wiki/api/v2' in p for p in paths())}")
print(f"    title/version/labels still correct: {data['title']!r} v{data['version']} {data['labels']}")
assert data["title"] == "Test Team Forecast" and data["labels"] == ["MC", "forecast"]
assert "| Ben Jones | 0.8 |" in data["body_text"], "table must still render"

print("\n=== 3. session remembers v1 - no repeated v2 probing ===")
mock.CALLS.clear()
m.confluence_get_page(page_id="460947525")
assert not any("/wiki/api/v2" in p for p in paths()), paths()
print(f"    second call went straight to v1: {[p for p in paths() if 'content' in p][:2]}")

print("\n=== 4. update + create over v1 (pmo-inline's exact payload shape) ===")
mock.CALLS.clear()
text, data = m.confluence_update_page(page_id="460947525", body="<p>fresh</p>", mode="append")
put = [c for c in mock.CALLS if c["method"] == "PUT"][0]
assert put["path"] == "/wiki/rest/api/content/460947525", put["path"]
assert put["body"]["version"]["number"] == 8 and put["body"]["type"] == "page"
assert put["body"]["title"] == "Test Team Forecast"
assert "<table>" in put["body"]["body"]["storage"]["value"], "append must keep existing content"
print(f"    PUT {put['path']}  version->{put['body']['version']['number']}  title preserved")
print(f"    payload keys: {sorted(put['body'])}  (matches pmo-inline)")

mock.CALLS.clear()
text, data = m.confluence_create_page(space_key="SMP", title="New Page", body="Hello", body_format="text")
post = [c for c in mock.CALLS if c["method"] == "POST"][0]
assert post["path"] == "/wiki/rest/api/content", post["path"]
assert post["body"]["space"]["key"] == "SMP" and post["body"]["type"] == "page"
print(f"    POST {post['path']}  space.key={post['body']['space']['key']}  (no numeric spaceId needed)")

print("\n=== 5. pinning ATLASSIAN_CONFLUENCE_API=v1 skips the probe entirely ===")
m.CONFIG.confluence_api = "v1"; m._CONFLUENCE_MODE["resolved"] = None
mock.STATE["v2_enabled"] = True; mock.CALLS.clear()
data = m.confluence_get_page(page_id="460947525")[1]
assert not any("/wiki/api/v2" in p for p in paths()), paths()
print(f"    api used: {data['api']} - v2 never contacted even though it works")

m.CONFIG.confluence_api = "auto"; mock.STATE["v2_enabled"] = True
print("\nV1 FALLBACK TESTS PASSED")
