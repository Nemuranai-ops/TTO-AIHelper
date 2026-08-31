"""Mock Atlassian site: verifies the exact requests the server sends."""
import json, re, threading, base64
from http.server import BaseHTTPRequestHandler, HTTPServer

CALLS = []
STATE = {"page_version": 7, "throttle_left": 1, "v2_enabled": True}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _send(self, code, payload=None):
        data = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data: self.wfile.write(data)

    def handle_one_request(self):
        try: super().handle_one_request()
        except Exception: pass

    def _route(self, method):
        path, _, qs = self.path.partition("?")
        body = self._body() if method in ("POST","PUT") else {}
        CALLS.append({"method": method, "path": path, "qs": qs, "body": body,
                      "auth": self.headers.get("Authorization","")[:11]})

        # --- Jira ---
        if path == "/rest/api/3/myself":
            return self._send(200, {"displayName":"Supun S","emailAddress":"s@example.test"})
        if path == "/rest/api/3/search/approximate-count":
            if STATE.get("no_count_endpoint"):
                return self._send(404, {"errorMessages":["not found"]})
            return self._send(200, {"count": STATE.get("fake_total", 13412)})
        if path == "/rest/api/3/search/jql":
            jql = (body.get("jql") or "").strip()
            import re as _re
            if not _re.sub(r"(?i)order\s+by.*$", "", jql).strip():
                return self._send(400, {"errorMessages":[
                    "Unbounded JQL queries are not allowed here. Please add a search restriction to your query."]})
            # exercise 429 retry once
            if STATE["throttle_left"] > 0:
                STATE["throttle_left"] -= 1
                self.send_response(429); self.send_header("Retry-After","0")
                self.send_header("Content-Length","0"); self.end_headers(); return
            if (body.get("fields") or []) == ["id"]:
                page = int(body.get("nextPageToken") or 0)
                remaining = STATE.get("fake_total", 13412) - page
                take = min(100, max(0, remaining))
                return self._send(200, {
                    "issues": [{"id": str(page + i)} for i in range(take)],
                    "nextPageToken": str(page + take) if remaining > take else None,
                    "isLast": remaining <= take})
            return self._send(200, {"issues":[
                {"id":"1","key":"SMP-5537","fields":{"summary":"Send single message","labels":["MC"],
                 "status":{"name":"In Progress","statusCategory":{"name":"In Progress"}},
                 "issuetype":{"name":"Test"},"assignee":{"displayName":"Ben Jones"}}}],
                "nextPageToken":"TOK2","isLast":False})
        m = re.fullmatch(r"/rest/api/3/issue/([^/]+)/transitions", path)
        if m and method == "GET":
            return self._send(200, {"transitions":[
                {"id":"31","name":"Start Progress","to":{"name":"In Progress"},"fields":{}},
                {"id":"41","name":"Done","to":{"name":"Done"},"fields":{"resolution":{"required":True}}}]})
        if m and method == "POST":
            return self._send(204)
        if path == "/rest/api/3/issue/BAD-1":
            return self._send(404, {"errorMessages":["Issue does not exist"]})
        m = re.fullmatch(r"/rest/api/3/issue/([^/]+)", path)
        if m and method == "GET":
            return self._send(200, {"id":"1","key":m.group(1),"fields":{
                "summary":"Send single message","labels":["MC","regression"],
                "status":{"name":"In Progress","statusCategory":{"name":"In Progress"}},
                "issuetype":{"name":"Test"},
                "description":{"type":"doc","version":1,"content":[
                    {"type":"paragraph","content":[{"type":"text","text":"Verify the API returns 200."}]}]},
                "comment":{"total":1,"comments":[{"author":{"displayName":"QA"},"created":"2026-08-01T10:00:00+1000",
                    "body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"Passes."}]}]}}]}}})
        if m and method == "PUT":
            return self._send(204)
        if path == "/rest/api/3/issue" and method == "POST":
            return self._send(201, {"id":"99","key":"SMP-9999"})

        # --- Confluence ---
        if path.startswith("/wiki/api/v2/") and not STATE["v2_enabled"]:
            return self._send(404, {"message": "no v2 on this tenant"})

        # --- Confluence v1 (what pmo-inline uses) ---
        m = re.fullmatch(r"/wiki/rest/api/content/(\d+)/label", path)
        if m:
            return self._send(200, {"results":[{"name":"MC"},{"name":"forecast"}]})
        m = re.fullmatch(r"/wiki/rest/api/content/(\d+)", path)
        if m and method == "GET":
            return self._send(200, {"id":m.group(1),"type":"page","status":"current",
                "title":"Test Team Forecast","space":{"key":"SMP","id":555},
                "version":{"number":STATE["page_version"],"when":"2026-08-20T01:00:00Z"},
                "body":{"storage":{"value":"<h2>Forecast</h2><table><tbody><tr><th><p>Person</p></th><th><p>Alloc</p></th></tr><tr><td><p>Ben Jones</p></td><td><p>0.8</p></td></tr></tbody></table>","representation":"storage"}},
                "metadata":{"labels":{"results":[{"name":"MC"},{"name":"forecast"}]}},
                "_links":{"webui":"/spaces/SMP/pages/460947525/Forecast","base":"http://127.0.0.1:%d/wiki" % PORT}})
        if m and method == "PUT":
            STATE["page_version"] = body["version"]["number"]
            return self._send(200, {"id":m.group(1),"type":"page","status":"current",
                "title":body["title"],"space":{"key":"SMP"},
                "version":{"number":body["version"]["number"]},
                "_links":{"webui":"/spaces/SMP/pages/460947525/F","base":"http://127.0.0.1:%d/wiki" % PORT}})
        if path == "/wiki/rest/api/content" and method == "POST":
            return self._send(200, {"id":"777","type":"page","status":"current","title":body["title"],
                "space":{"key":body["space"]["key"]},"version":{"number":1},
                "_links":{"webui":"/spaces/SMP/pages/777/New","base":"http://127.0.0.1:%d/wiki" % PORT}})
        if path == "/wiki/rest/api/content" and method == "GET":
            return self._send(200, {"results":[{"id":"460947525","title":"Test Team Forecast"}]})

        if path == "/wiki/api/v2/spaces":
            return self._send(200, {"results":[{"id":"555","key":"SMP","name":"Messaging"}]})
        m = re.fullmatch(r"/wiki/api/v2/pages/(\d+)/labels", path)
        if m:
            return self._send(200, {"results":[{"name":"MC"},{"name":"forecast"}]})
        m = re.fullmatch(r"/wiki/api/v2/pages/(\d+)", path)
        if m and method == "GET":
            return self._send(200, {"id":m.group(1),"title":"Test Team Forecast","status":"current",
                "spaceId":"555","version":{"number":STATE["page_version"],"createdAt":"2026-08-20T01:00:00Z"},
                "body":{"storage":{"value":"<h2>Forecast</h2><table><tbody><tr><th><p>Person</p></th><th><p>Alloc</p></th></tr><tr><td><p>Ben Jones</p></td><td><p>0.8</p></td></tr></tbody></table>","representation":"storage"}},
                "_links":{"webui":"/spaces/SMP/pages/460947525/Forecast","base":"http://127.0.0.1:%d/wiki" % PORT}})
        if m and method == "PUT":
            STATE["page_version"] = body["version"]["number"]
            return self._send(200, {"id":m.group(1),"title":body["title"],"status":"current","spaceId":"555",
                "version":{"number":body["version"]["number"]},"_links":{"webui":"/spaces/SMP/pages/460947525/F","base":"http://127.0.0.1:%d/wiki" % PORT}})
        if path == "/wiki/api/v2/pages" and method == "POST":
            return self._send(200, {"id":"777","title":body["title"],"status":"current","spaceId":body["spaceId"],
                "version":{"number":1},"_links":{"webui":"/spaces/SMP/pages/777/New","base":"http://127.0.0.1:%d/wiki" % PORT}})
        if path == "/wiki/api/v2/pages" and method == "GET":
            return self._send(200, {"results":[{"id":"460947525","title":"Test Team Forecast"}]})
        if path == "/wiki/rest/api/search":
            return self._send(200, {"totalSize":2,"results":[
                {"content":{"id":"460947525","type":"page","title":"Test Team Forecast",
                            "space":{"key":"SMP"},"version":{"number":7},
                            "_links":{"webui":"/spaces/SMP/pages/460947525"}},
                 "excerpt":"Person <b>Alloc</b> Ben Jones","lastModified":"2026-08-20T01:00:00Z",
                 "url":"/spaces/SMP/pages/460947525"}]})

        # --- error-path fixture ---
        if path == "/rest/api/3/issue/BAD-1":
            return self._send(404, {"errorMessages":["Issue does not exist"]})
        return self._send(404, {"message":"no mock route for "+path})

    def do_GET(self): self._route("GET")
    def do_POST(self): self._route("POST")
    def do_PUT(self): self._route("PUT")

srv = HTTPServer(("127.0.0.1", 0), H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
