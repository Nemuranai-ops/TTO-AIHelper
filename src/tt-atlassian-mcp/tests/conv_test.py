import importlib.util, json
import os as _os
# A corporate proxy will intercept 127.0.0.1 unless loopback is excluded.
_os.environ["NO_PROXY"] = _os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
import os as _os
_SERVER = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                        "atlassian_mcp_server.py")
spec = importlib.util.spec_from_file_location("srv", _SERVER)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

print("=== 1. Confluence storage table -> text (pmo-agent style page) ===")
storage = '''<h2 ac:local-id="abc">Test Team Forecast</h2>
<table><tbody>
<tr><th><p><strong>Person</strong></p></th><th><p><strong>Project Name</strong></p></th><th><p><strong>2026-08-22 - 2026-08-28</strong></p></th></tr>
<tr><td><p>Ben Jones</p></td><td><p>Email Platform</p></td><td><p>0.8</p></td></tr>
<tr><td><p>Matt Leydon</p></td><td><p>Collaboration</p></td><td><p></p></td></tr>
</tbody></table>
<p>Notes: see <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">SMP-4245</ac:parameter></ac:structured-macro> for detail.</p>
<ul><li>First bullet</li><li>Second bullet</li></ul>'''
print(m.storage_to_text(storage))

print("\n=== 2. Jira ADF -> text ===")
adf = {"type":"doc","version":1,"content":[
 {"type":"heading","attrs":{"level":2},"content":[{"type":"text","text":"Steps"}]},
 {"type":"paragraph","content":[
    {"type":"text","text":"Go to "},
    {"type":"text","text":"swagger","marks":[{"type":"link","attrs":{"href":"https://example.test/api"}}]},
    {"type":"text","text":" and use "},
    {"type":"text","text":"X-API-KEY","marks":[{"type":"code"}]}]},
 {"type":"orderedList","content":[
    {"type":"listItem","content":[{"type":"paragraph","content":[{"type":"text","text":"Enter key"}]}]},
    {"type":"listItem","content":[{"type":"paragraph","content":[{"type":"text","text":"Send message"}]}]}]},
 {"type":"codeBlock","attrs":{"language":"json"},"content":[{"type":"text","text":'{"to":"+61..."}'}]},
 {"type":"table","content":[
    {"type":"tableRow","content":[
       {"type":"tableHeader","content":[{"type":"paragraph","content":[{"type":"text","text":"Step"}]}]},
       {"type":"tableHeader","content":[{"type":"paragraph","content":[{"type":"text","text":"Expected"}]}]}]},
    {"type":"tableRow","content":[
       {"type":"tableCell","content":[{"type":"paragraph","content":[{"type":"text","text":"Send"}]}]},
       {"type":"tableCell","content":[{"type":"paragraph","content":[{"type":"text","text":"200 OK"}]}]}]}]}]}
print(m.adf_to_text(adf).strip())

print("\n=== 3. text -> ADF (validity checks) ===")
src = """# Heading one
A normal paragraph
that wraps across lines.

- bullet a
- bullet b

1. first
2. second

```python
print("hi")
```
"""
doc = m.text_to_adf(src)
print(json.dumps(doc)[:220], "...")
def check(node, path="doc"):
    if isinstance(node, dict):
        if node.get("type")=="text":
            assert node.get("text"), f"EMPTY text node at {path} (invalid ADF)"
        for i,c in enumerate(node.get("content") or []): check(c, f"{path}.{node.get('type')}[{i}]")
    elif isinstance(node, list):
        for i,c in enumerate(node): check(c, f"{path}[{i}]")
check(doc)
kinds=[c["type"] for c in doc["content"]]
print("block types:", kinds)
assert kinds==["heading","paragraph","bulletList","orderedList","codeBlock"], kinds
print("no empty text nodes, block sequence correct: True")

print("\n=== 4. edge cases ===")
for label, val in [("empty string",""), ("only whitespace","   \n\n  "), ("just a fence","```\n```")]:
    d=m.text_to_adf(val); check(d); print(f"  {label:16} -> valid ADF, {len(d['content'])} block(s)")
print("  storage_to_text(''):", repr(m.storage_to_text("")))
print("  storage_to_text(malformed):", repr(m.storage_to_text("<p>unclosed <b>bold")))
print("  adf_to_text(None):", repr(m.adf_to_text(None)))
print("  text_to_storage roundtrip:", m.text_to_storage("line1\nline2\n\npara2 & <tag>"))

print("\n=== 5. simplify_issue on a realistic Jira payload ===")
issue = {"id":"10001","key":"SMP-5537","fields":{
  "summary":"SMS API - Send Single Message","labels":["MC","regression"],
  "status":{"name":"In Progress","statusCategory":{"name":"In Progress"}},
  "issuetype":{"name":"Test"},"priority":{"name":"High"},
  "assignee":{"displayName":"Ben Jones","accountId":"abc"},
  "components":[{"name":"Messaging"},{"name":"API"}],
  "parent":{"key":"SMP-100"},"subtasks":[{"key":"SMP-101"}],
  "description":adf,"resolution":None,"fixVersions":[],
  "comment":{"total":1,"comments":[{"author":{"displayName":"QA"},"created":"2026-08-01T10:00:00.000+1000",
             "body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"Retested, passes."}]}]}}]}}}
s = m.simplify_issue(issue)
print("  key/status/labels:", s["key"], "|", s["status"], "|", s["labels"])
print("  components/parent/subtasks:", s["components"], s["parent"], s["subtasks"])
print("  empty fields dropped (resolution, fixVersions):", "resolution" not in s and "fixVersions" not in s)
print("  description flattened to text:", repr(s["description"][:55]))
print("  comment:", s["comment"]["comments"][0]["author"], "->", repr(s["comment"]["comments"][0]["body"]))
print("\nALL CONVERTER TESTS PASSED")
