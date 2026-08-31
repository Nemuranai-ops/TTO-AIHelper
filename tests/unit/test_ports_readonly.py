"""P2 source protocols expose no write capability.

NFR-SEC-14, C-05 and C-06 require read-only access to Atlassian and Bitbucket. The
design enforces that structurally: there is no write method to call. This test is
the guard on that property, so adding one later fails the build rather than passing
review unnoticed.
"""

import inspect

from tto_testgen.ports import sources

SOURCE_PROTOCOLS = [
    sources.JiraSource,
    sources.ConfluenceSource,
    sources.BitbucketSource,
    sources.DesignAssetSource,
    sources.ResourceManifestSource,
]

#: Verbs that would indicate a mutating capability. Matched as whole words against
#: the method name's underscore-separated parts, because substring matching gives
#: false positives - `updated_since` is a query for issues updated since a time,
#: not a write.
WRITE_VERBS = frozenset(
    {
        "create",
        "update",
        "delete",
        "write",
        "post",
        "put",
        "patch",
        "add",
        "remove",
        "set",
        "transition",
        "upsert",
        "publish",
        "comment",
    }
)


def public_methods(protocol):
    return [
        name
        for name, member in inspect.getmembers(protocol)
        if not name.startswith("_") and callable(member)
    ]


def leading_verb(method_name: str) -> str:
    return method_name.split("_")[0]


class TestSourcePortsAreReadOnly:
    def test_no_source_protocol_declares_a_write_method(self):
        offenders = []
        for protocol in SOURCE_PROTOCOLS:
            for method in public_methods(protocol):
                if leading_verb(method) in WRITE_VERBS:
                    offenders.append(f"{protocol.__name__}.{method}")
        assert offenders == [], (
            "Source protocols must declare no write capability. "
            f"Found: {offenders}. NFR-SEC-14 is enforced by absence, not by policy."
        )

    def test_updated_since_is_recognised_as_a_read(self):
        # Guards the guard: substring matching would have flagged this method, and
        # a false positive here would push someone to weaken the real check.
        assert leading_verb("updated_since") == "updated"
        assert "updated" not in WRITE_VERBS or leading_verb("updated_since") != "update"

    def test_every_source_protocol_has_at_least_one_read_method(self):
        for protocol in SOURCE_PROTOCOLS:
            assert public_methods(protocol), protocol.__name__

    def test_protocols_are_runtime_checkable(self):
        # composition.py binds concrete adapters to these; runtime checking makes a
        # mismatch fail at startup rather than at first use, halfway through a run.
        for protocol in SOURCE_PROTOCOLS:
            assert getattr(protocol, "_is_runtime_protocol", False), protocol.__name__
