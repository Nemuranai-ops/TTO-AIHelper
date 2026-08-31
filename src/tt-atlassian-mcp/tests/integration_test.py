import os, json, importlib.util
import os as _os
# A corporate proxy will intercept 127.0.0.1 unless loopback is excluded.
_os.environ["NO_PROXY"] = _os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
import importlib.util as _ilu
if _ilu.find_spec("requests") is None:
    raise SystemExit("SKIP: requests is required for this test.  pip install requests")
import os as _os
_SERVER = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                        "atlassian_mcp_server.py")
import mock_atlassian as mock

os.environ.update({
    "ATLASSIAN_ENV_FILE": "/nonexistent/none.env",
    "ATLASSIAN_BASE_URL": f"http://127.0.0.1:{mock.PORT}",
    "ATLASSIAN_EMAIL": "supun@example.test",
    "ATLASSIAN_API_TOKEN": "fake-token-123",
    "ATLASSIAN_READ_ONLY": "false",  # exercise the write tools
    "ATLASSIAN_VERIFY_TLS": "true",
})
spec = importlib.util.spec_from_file_location("srv", _SERVER)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def run(name, args):
    r = m.call_tool(name, args)
    flag = "ERR " if r.get("isError") else "ok  "
    print(f"\n### {flag}{name}({json.dumps(args)[:70]})")
    print("    " + r["content"][0]["text"].replace("\n", "\n    ")[:620])
    return r

print("="*70); print("READ TOOLS"); print("="*70)
run("jira_search_issues", {"jql": 'project = SMP AND labels = "MC"', "max_results": 50})
run("jira_get_issue", {"issue_key": "SMP-5537"})
run("jira_get_transitions", {"issue_key": "SMP-5537"})
run("confluence_get_page", {"page_id": "460947525"})
run("confluence_search", {"label": "MC", "space_key": "SMP"})

print("\n" + "="*70); print("WRITE TOOLS"); print("="*70)
run("jira_create_issue", {"project_key":"SMP","summary":"New test","issue_type":"Test",
                          "description":"# Steps\n- do a thing","labels":["MC"]})
run("jira_update_issue", {"issue_key":"SMP-5537","labels_add":["regression"],"labels_remove":["old"]})
run("jira_transition_issue", {"issue_key":"SMP-5537","transition":"Done","resolution":"Done","comment":"Verified."})
run("confluence_create_page", {"space_key":"SMP","title":"New Page","body":"Hello","body_format":"text"})
run("confluence_update_page", {"page_id":"460947525","body":"<p>fresh</p>","mode":"append"})

print("\n" + "="*70); print("ERROR PATHS"); print("="*70)
run("jira_get_issue", {"issue_key": "BAD-1"})
run("jira_transition_issue", {"issue_key":"SMP-5537","transition":"Teleport"})

print("\n" + "="*70); print("REQUEST SHAPES SENT TO ATLASSIAN"); print("="*70)
for c in mock.CALLS:
    body = json.dumps(c["body"])[:150] if c["body"] else ""
    print(f"  {c['method']:5} {c['path']}{('?'+c['qs']) if c['qs'] else ''}")
    if body: print(f"        body: {body}")

print("\n" + "="*70); print("ASSERTIONS"); print("="*70)
paths = [(c["method"], c["path"]) for c in mock.CALLS]
search = [c for c in mock.CALLS if c["path"] == "/rest/api/3/search/jql"]
assert len(search) == 2, "429 should have been retried exactly once"
print("  429 retry with Retry-After honoured            : PASS")
assert "fields" in search[-1]["body"] and len(search[-1]["body"]["fields"]) > 5
print("  search sends explicit fields (else id+key only): PASS")
assert all(c["auth"].startswith("Basic ") for c in mock.CALLS), {c["auth"] for c in mock.CALLS}
print("  every request carries Basic auth header        : PASS")
put = [c for c in mock.CALLS if c["method"]=="PUT" and c["path"].startswith("/wiki/api/v2/pages/")][0]
assert put["body"]["version"]["number"] == 8, put["body"]["version"]
assert put["body"]["title"] == "Test Team Forecast", put["body"]["title"]
assert "<p>fresh</p>" in put["body"]["body"]["value"] and "<table>" in put["body"]["body"]["value"]
print("  page update: version 7->8, title preserved     : PASS")
print("  append mode kept existing table content        : PASS")
tr = [c for c in mock.CALLS if c["method"]=="POST" and c["path"].endswith("/transitions")][0]
assert tr["body"]["transition"]["id"] == "41", tr["body"]
assert tr["body"]["fields"]["resolution"]["name"] == "Done"
assert tr["body"]["update"]["comment"][0]["add"]["body"]["type"] == "doc"
print("  transition name 'Done' resolved to id 41       : PASS")
print("  transition comment sent as valid ADF           : PASS")
create = [c for c in mock.CALLS if c["method"]=="POST" and c["path"]=="/rest/api/3/issue"][0]
assert create["body"]["fields"]["description"]["type"] == "doc"
print("  create issue description converted to ADF      : PASS")
upd = [c for c in mock.CALLS if c["method"]=="PUT" and c["path"].startswith("/rest/api/3/issue/")][0]
assert upd["body"]["update"]["labels"] == [{"add":"regression"},{"remove":"old"}], upd["body"]
print("  labels_add/labels_remove use update ops        : PASS")
cp = [c for c in mock.CALLS if c["method"]=="POST" and c["path"]=="/wiki/api/v2/pages"][0]
assert cp["body"]["spaceId"] == "555", "space key must be resolved to numeric spaceId"
assert cp["body"]["body"]["value"] == "<p>Hello</p>"
print("  space key SMP resolved to spaceId 555          : PASS")
print("  body_format=text wrapped into storage XHTML    : PASS")
print("\nALL INTEGRATION ASSERTIONS PASSED")
