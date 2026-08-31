# Offline tests

These run entirely against a mock Atlassian API on localhost. No credentials,
no network, no changes to any real Jira or Confluence site. Use them to confirm
the server is healthy on a new machine before pointing it at the live site.

```powershell
cd tests
python conv_test.py          # ADF and Confluence storage-format conversion
python mcp_test.py           # MCP protocol handshake and error paths
python integration_test.py   # all 10 tools + request shapes against the mock
```

All three should end with a "PASSED" line. Then run
`python ..\atlassian_mcp_server.py --selftest` to check the real credentials.
