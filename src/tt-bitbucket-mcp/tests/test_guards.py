"""Read-only guarantee + MCP protocol. No credentials, no network, no repo writes."""
import importlib.util, json, os, subprocess, sys, tempfile, pathlib

SERVER = pathlib.Path(__file__).resolve().parent.parent / "bitbucket_mcp_server.py"
spec = importlib.util.spec_from_file_location("srv", SERVER)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

MUTATING = [
    ["checkout","main"],["switch","-c","x"],["reset","--hard"],["clean","-fd"],
    ["commit","-m","x"],["add","."],["push"],["pull"],["fetch"],["merge","x"],
    ["rebase","main"],["stash"],["restore","."],["rm","-r","."],["init"],
    ["remote","add","o","u"],["gc","--prune=now"],["worktree","add","/tmp/x"],
    ["update-ref","refs/heads/main","HEAD"],["filter-branch"],["cherry-pick","abc"],
    ["revert","HEAD"],["apply","p.patch"],["submodule","update"],["bisect","start"],
    ["config","user.email","x@y"],["credential","fill"],["daemon"],["send-email"],
    ["tag","v9.9.9"],["branch","newbranch"],["symbolic-ref","HEAD","refs/heads/x"],
    ["log","--output=/tmp/pwned"],["diff","-o","/tmp/pwned"],
    ["show","--git-dir=/other/.git"],["log","-c","core.editor=evil"],
    ["grep","--output=/tmp/pwned","-e","x"],
]
READ_ONLY = [["log","--oneline"],["ls-files"],["tag","--list"],["rev-parse","HEAD"],
             ["status","--porcelain"],["for-each-ref","refs/tags"],["grep","-n","-e","hello","HEAD"]]

def main():
    tmp = pathlib.Path(tempfile.mkdtemp())
    subprocess.run(["git","init","-q",str(tmp)],capture_output=True)
    (tmp/"a.txt").write_text("hello\n")
    for c in [["add","."],["-c","user.email=t@t","-c","user.name=t","commit","-qm","SMP-1 x"]]:
        subprocess.run(["git","-C",str(tmp)]+c,capture_output=True)

    blocked = 0
    for args in MUTATING:
        try:
            m.run_git(tmp, args); print(f"  FAIL not blocked: git {' '.join(args)}")
        except m.ToolError:
            blocked += 1
    print(f"  {blocked}/{len(MUTATING)} mutating git commands refused")
    assert blocked == len(MUTATING), "a mutating git command got through"

    for args in READ_ONLY:
        m.run_git(tmp, args, allow_status=(0,1))
    print(f"  {len(READ_ONLY)}/{len(READ_ONLY)} read-only git commands still work")

    # git grep exits 1 for "no matches" - an answer, not a failure
    assert m.run_git(tmp, ["grep","-n","-e","nothinghere","HEAD"], allow_status=(0,1)) == ""
    try:
        m.run_git(tmp, ["grep","-n","-e","nothinghere","HEAD"])
        print("  FAIL: exit 1 was not surfaced when allow_status excluded it")
    except m.ToolError:
        print("  git grep: exit 1 is an answer with allow_status, an error without it")

    # no tool in the server may be anything other than read-only
    writers = [t["name"] for t in m.TOOLS if not t["annotations"].get("readOnlyHint")]
    assert not writers, f"non-read-only tool declared: {writers}"
    assert set(m.HANDLERS) == {t["name"] for t in m.TOOLS}, "TOOLS and HANDLERS disagree"
    print(f"  all {len(m.TOOLS)} tools declare readOnlyHint, handlers match")

    # the working tree must be untouched
    status = subprocess.run(["git","-C",str(tmp),"status","--porcelain"],
                            capture_output=True,text=True).stdout.strip()
    assert status == "", f"working tree was modified: {status}"
    print("  working tree unchanged after all calls")

    msgs = [
        {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{}}},
        {"jsonrpc":"2.0","method":"notifications/initialized"},
        {"jsonrpc":"2.0","id":2,"method":"tools/list"},
        {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"bitbucket_changes","arguments":{}}},
        {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"ghost","arguments":{}}},
        {"jsonrpc":"2.0","id":5,"method":"ping"},
    ]
    env = dict(os.environ, BITBUCKET_ENV_FILE="/nonexistent", BITBUCKET_REPO_ROOT="")
    p = subprocess.run([sys.executable,str(SERVER)],
                       input="\n".join(json.dumps(x) for x in msgs)+"\nbad\n",
                       capture_output=True,text=True,env=env,timeout=120)
    responses = [json.loads(l) for l in p.stdout.splitlines()]
    assert len(responses) == 6, f"expected 6 responses (notification silent), got {len(responses)}"
    assert responses[0]["result"]["serverInfo"]["name"] == "bitbucket-mcp"
    tools = responses[1]["result"]["tools"]
    assert tools, "no tools listed"
    assert responses[2]["result"]["isError"], "missing required arg was not an error"
    assert "error" in responses[3], "unknown tool was not rejected"
    print(f"  MCP: {len(responses)} responses, {len(tools)} tools, exit {p.returncode}")

    print("PASSED")

if __name__ == "__main__":
    main()
