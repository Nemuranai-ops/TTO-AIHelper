import json, subprocess, sys, os
import os as _os
# A corporate proxy will intercept 127.0.0.1 unless loopback is excluded.
_os.environ["NO_PROXY"] = _os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
import os as _os
_SERVER = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                        "atlassian_mcp_server.py")
SERVER = _SERVER
msgs = [
 {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"vscode-copilot","version":"1.0"}}},
 {"jsonrpc":"2.0","method":"notifications/initialized"},
 {"jsonrpc":"2.0","id":2,"method":"ping"},
 {"jsonrpc":"2.0","id":3,"method":"tools/list"},
 {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"jira_search_issues","arguments":{}}},
 {"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"nope","arguments":{}}},
 {"jsonrpc":"2.0","id":6,"method":"resources/list"},
 {"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"jira_get_issue","arguments":{"issue_key":"SMP-1","bogus_arg":1}}},
 {"jsonrpc":"2.0","id":8,"method":"initialize","params":{"protocolVersion":"1999-01-01"}},
 {"jsonrpc":"2.0","id":9,"method":"unknown/method"},
]
env = dict(os.environ, ATLASSIAN_ENV_FILE="/nonexistent/none.env",
           ATLASSIAN_BASE_URL="", ATLASSIAN_EMAIL="", ATLASSIAN_API_TOKEN="")
stdin = "\n".join(json.dumps(m) for m in msgs) + "\nnot-json\n"
p = subprocess.run([sys.executable, SERVER], input=stdin, capture_output=True, text=True, env=env, timeout=60)
print("exit code:", p.returncode)
print("--- responses ---")
count = 0
for line in p.stdout.splitlines():
    m = json.loads(line); count += 1
    mid = m.get("id")
    if "error" in m:
        print(f"  id={mid}  ERROR {m['error']['code']}: {m['error']['message'][:75]}")
    else:
        r = m["result"]
        if "tools" in r: print(f"  id={mid}  tools/list -> {len(r['tools'])} tools")
        elif "protocolVersion" in r: print(f"  id={mid}  initialize -> protocol={r['protocolVersion']} server={r['serverInfo']['name']}")
        elif "content" in r: print(f"  id={mid}  tools/call isError={r.get('isError')} :: {r['content'][0]['text'][:95]}")
        else: print(f"  id={mid}  -> {json.dumps(r)[:70]}")
print(f"--- {count} responses for 10 requests + 1 notification + 1 garbage line ---")
print("--- stderr ---"); print(p.stderr.strip())
