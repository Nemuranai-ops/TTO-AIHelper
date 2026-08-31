"""Every tool against a purpose-built repository. No network, no credentials."""
import importlib.util, os, pathlib, subprocess, tempfile

SERVER = pathlib.Path(__file__).resolve().parent.parent / "bitbucket_mcp_server.py"
spec = importlib.util.spec_from_file_location("srv", SERVER)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

CONTROLLER = '''[Route("api/v1")]
public class SenderIdController {
    [HttpGet("/api/v1/senderids")]
    public IActionResult ListSenderIds() { }

    [HttpPost("/api/v1/senderids")]
    public IActionResult CreateSenderId(SenderIdRequest r) { }
}
'''
UPDATE = '''
[HttpPut("/api/v1/senderids/{id}")]
public IActionResult UpdateSenderId(int id) { }
'''

def git(repo, *args):
    subprocess.run(["git","-C",str(repo),*args],capture_output=True,check=False)

def build(root):
    repo = root / "messaging-center"
    repo.mkdir(parents=True)
    git(repo, "init","-q",".")
    git(repo, "config","user.email","t@t"); git(repo, "config","user.name","tester")
    git(repo, "remote","add","origin","ssh://git@bitbucket.example.com:7999/SMP/messaging-center.git")
    (repo/"src").mkdir()
    (repo/"src"/"SenderIdController.cs").write_text(CONTROLLER)
    (repo/"swagger.json").write_text('{"openapi":"3.0.0"}')
    git(repo,"add","-A"); git(repo,"commit","-qm","SMP-1001 add sender id endpoints")
    git(repo,"tag","v6.0")
    with (repo/"src"/"SenderIdController.cs").open("a") as fh:
        fh.write(UPDATE)
    git(repo,"add","-A"); git(repo,"commit","-qm","SMP-1002 update sender id")
    with (repo/"src"/"SenderIdController.cs").open("a") as fh:
        fh.write("// no ticket\n")
    git(repo,"add","-A"); git(repo,"commit","-qm","tidy up")
    git(repo,"tag","v6.1")
    return repo

def build_dated(root):
    """A repo whose four commits sit on known, widely separated dates."""
    repo = root / "dated-repo"
    repo.mkdir(parents=True)
    git(repo, "init","-q",".")
    git(repo, "config","user.email","t@t"); git(repo, "config","user.name","tester")
    for n, (subject, date) in enumerate([
        ("SMP-100 january work", "2026-01-15"),
        ("SMP-200 march work",   "2026-03-10"),
        ("SMP-300 june work",    "2026-06-20"),
        ("SMP-400 august work",  "2026-08-05"),
    ], start=1):
        (repo/f"f{n}.txt").write_text(subject)
        stamp = f"{date}T10:00:00"
        subprocess.run(["git","-C",str(repo),"add","-A"],capture_output=True)
        subprocess.run(["git","-C",str(repo),"commit","-qm",subject],capture_output=True,
                       env={**os.environ,"GIT_AUTHOR_DATE":stamp,"GIT_COMMITTER_DATE":stamp})
    git(repo,"tag","v1.0","HEAD~2")
    return repo


def date_windows(root):
    m.CONFIG.repo_roots = [root]

    text, data = m.bitbucket_changes("dated-repo", since="2026-03-01")
    assert data["commits"] == 3 and data["files_changed"] == 3, data
    assert data["jira_keys"] == ["SMP-200","SMP-300","SMP-400"], data
    assert data["window"]["base_date"] == "2026-01-15", data["window"]
    assert "base = last commit before 2026-03-01" in text
    print("  since      : 3 commits after 1 March, base resolved to the 15 Jan commit")

    text, data = m.bitbucket_changes("dated-repo", since="2026-03-01", until="2026-07-01")
    assert data["commits"] == 2, data
    assert data["jira_keys"] == ["SMP-200","SMP-300"], data
    assert data["window"]["head_date"] == "2026-06-20", data["window"]
    print("  since+until: a two-commit window, head resolved to the 20 June commit")

    # a since that predates the whole history falls back to the root commit,
    # and must say that the root commit's own contents are not counted
    text, data = m.bitbucket_changes("dated-repo", since="2020-01-01")
    assert data["commits"] == 3, data
    assert "NOT counted as changes" in text, text
    print("  since<start: falls back to the root commit and says what that excludes")

    # until alone must not default the base to a tag AHEAD of the resolved head
    text, data = m.bitbucket_changes("dated-repo", until="2026-07-01")
    assert data["base"] == "v1.0" and data["commits"] == 1, data
    assert "reachable from head" in text
    print("  until only : base defaults to the newest tag reachable from head")

    try:
        m.bitbucket_changes("dated-repo", base="HEAD~2", since="2026-03-01")
        raise AssertionError("base + since should be refused")
    except m.ToolError as error:
        assert "not both" in str(error), error
    print("  conflict   : base and since together are refused")

    text, data = m.bitbucket_diff("dated-repo", since="2026-04-01", mode="names")
    assert "f3.txt" in text and "f4.txt" in text and "f2.txt" not in text, text
    assert data["window"]["resolved_from_dates"] is True, data["window"]
    print("  diff dates : the same window works on the diff")

    status = subprocess.run(["git","-C",str(root/"dated-repo"),"status","--porcelain"],
                            capture_output=True,text=True).stdout.strip()
    assert status == "", f"working tree was modified: {status}"


def main():
    root = pathlib.Path(tempfile.mkdtemp())
    repo = build(root)
    m.CONFIG.repo_roots = [root]

    text, data = m.bitbucket_repos()
    assert data["count"] == 1, data
    only = data["repos"][0]
    assert only["project"] == "SMP" and only["slug"] == "messaging-center", only
    assert only["web_url"].endswith("/projects/SMP/repos/messaging-center"), only
    assert only["tags"] == 2, only
    print(f"  repos      : {only['repo']} {only['branch']} -> {only['web_url']}")

    text, data = m.bitbucket_tags("messaging-center")
    assert [t["tag"] for t in data["tags"]] == ["v6.1","v6.0"], data["tags"]
    print("  tags       : newest first by topology, v6.1 then v6.0")

    text, data = m.bitbucket_log("messaging-center", limit=10)
    assert data["returned"] == 3 and data["commits_with_jira_key"] == 2, data
    assert data["jira_key_coverage_pct"] == 66, data
    assert data["commits"][0]["url"].endswith(data["commits"][0]["sha"]), data["commits"][0]
    print(f"  log        : 3 commits, key coverage {data['jira_key_coverage_pct']}%")

    text, data = m.bitbucket_log("messaging-center", grep="update", limit=10)
    assert data["returned"] == 1, data
    text, data = m.bitbucket_log("messaging-center", path="src", limit=10)
    assert data["returned"] == 3, data
    print("  log filters: grep and path both narrow the history")

    text, data = m.bitbucket_changes("messaging-center", base="v6.0", head="v6.1")
    assert data["commits"] == 2 and data["files_changed"] == 1, data
    assert data["jira_keys"] == ["SMP-1002"], data
    assert data["jira_key_coverage_pct"] == 50, data
    assert "only 50%" in text, "the sub-50% caveat was not stated"
    print("  changes    : 2 commits, 1 file, coverage caveat stated")

    # base defaults to the most recent tag
    text, data = m.bitbucket_changes("messaging-center")
    assert data["base"] == "v6.1", data
    print("  changes    : base defaults to the newest tag")

    text, data = m.bitbucket_diff("messaging-center", base="v6.0", head="v6.1", mode="patch")
    assert data["changed_line_ranges"], data
    assert "+public IActionResult UpdateSenderId" in text
    text, data = m.bitbucket_diff("messaging-center", base="v6.0", head="v6.1", mode="names")
    assert "src/SenderIdController.cs" in text
    print("  diff       : patch reports hunk ranges, names lists status")

    text, data = m.bitbucket_file("messaging-center", "src/SenderIdController.cs", ref="v6.0")
    assert data["total_lines"] == 8, data
    assert "UpdateSenderId" not in text, "v6.0 should predate the update endpoint"
    text, data = m.bitbucket_file("messaging-center", "src/SenderIdController.cs", start=3, end=4)
    assert data["from_line"] == 3 and data["to_line"] == 4, data
    print("  file       : reads at a ref, and a line window")

    text, data = m.bitbucket_grep("messaging-center", "senderid")
    assert data["matches"] >= 6, data
    text, data = m.bitbucket_grep("messaging-center", "nothinghere")
    assert data["matches"] == 0 and "No matches" in text, "no-match must be an answer"
    print("  grep       : matches found, and an empty result is not an error")

    text, data = m.bitbucket_endpoints("messaging-center")
    routes = {(e["method"], e["route"]) for e in data["endpoints"]}
    assert ("POST","/api/v1/senderids") in routes, routes
    assert ("PUT","/api/v1/senderids/{id}") in routes, routes
    assert data["api_spec_files"] == ["swagger.json"], data
    symbols = {e["symbol"] for e in data["endpoints"]}
    assert "CreateSenderId" in symbols and "UpdateSenderId" in symbols, symbols
    print(f"  endpoints  : {data['endpoints_found']} found, spec {data['api_spec_files']}")

    text, data = m.bitbucket_endpoints("messaging-center", method="POST")
    assert data["endpoints_found"] == 1, data
    print("  endpoints  : method filter narrows to one")

    for url, project, slug in [
        ("ssh://git@bb.example.com:7999/SMP/messaging-center.git","SMP","messaging-center"),
        ("https://bb.example.com/scm/smp/messaging-center.git","smp","messaging-center"),
        ("git@bitbucket.org:acme/messaging-center.git","acme","messaging-center"),
    ]:
        coords = m.bitbucket_coordinates(url)
        assert coords["project"] == project and coords["slug"] == slug, (url, coords)
    assert m.bitbucket_coordinates("")["web_url"] == ""
    print("  urls       : server, scm and cloud remotes all parsed; unknown stays blank")

    dated_root = pathlib.Path(tempfile.mkdtemp())
    build_dated(dated_root)
    date_windows(dated_root)
    m.CONFIG.repo_roots = [root]

    status = subprocess.run(["git","-C",str(repo),"status","--porcelain"],
                            capture_output=True,text=True).stdout.strip()
    assert status == "", f"working tree was modified: {status}"
    print("  working tree unchanged after every tool")

    print("PASSED")

if __name__ == "__main__":
    main()
