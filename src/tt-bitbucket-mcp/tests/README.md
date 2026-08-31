# Offline tests

Self-contained. They build their own git repositories in a temp folder, touch no
real repository, and need no credentials or network.

```powershell
cd tests
python test_guards.py   # read-only git enforcement + MCP protocol
python test_tools.py    # all eight tools end-to-end against a built repo
```

Both should end with a `PASSED` line.

`test_guards.py` fires 37 mutating git commands at the allowlist, asserts every
one is refused, asserts the read-only ones still work, asserts no tool in the
server declares itself anything other than read-only, and asserts the working
tree is byte-identical afterwards. That last check is the guarantee that matters
most for a team with read-only repository access.

`test_tools.py` builds a two-release repository with a Bitbucket-style remote and
exercises every tool: clone discovery and URL parsing (Server, /scm and Cloud
remotes), tag ordering by topology, log filters, Jira-key coverage including the
sub-50% caveat, date-range windows (since, since+until, a since that predates
the history, until-only base defaulting, and the base+since conflict), all three
diff modes, reading a file at an older ref, grep with
and without matches, and the endpoint scan with its symbol extraction.
