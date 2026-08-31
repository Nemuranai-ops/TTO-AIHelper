"""L13 SecretScanner - what may not be rendered into TypeScript as a literal.

The generated project is pushed to a Bitbucket repository and read by Jenkins. That
is where a literal credential stops being a code-quality problem and becomes a
disclosure (NFR-SEC-10, U5-NFR-SEC-01).

Distinct from L9 `PersonalDataDetector`, deliberately. L9 asks *is this a real
person's data*; this asks *is this a secret or an environment-specific value*. A
password field holding `Passw0rd!` passes L9 correctly - it is nobody's real data -
and must still never be committed. Neither check subsumes the other, and merging them
would produce one pattern set too broad for one purpose and too narrow for the other.

Pure, like L9. The finding names where and what shape, **never what**: a refusal that
quoted the secret would copy it into the log, and the log may be shipped with the
handover.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

#: Field names that carry a secret regardless of the value's shape. `password:
#: "hunter2"` is the single most likely literal to appear, and no value-shape rule
#: would catch it.
CREDENTIAL_FIELDS = frozenset({
    "password", "passwd", "pwd", "token", "secret", "apikey", "api_key", "api-key",
    "authorization", "auth", "credential", "credentials", "private_key", "privatekey",
    "client_secret", "access_token", "refresh_token", "session_token", "passphrase",
})

_BEARER = re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._\-]{16,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_CONNECTION = re.compile(
    r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s:/@]+@[^\s/]+", re.IGNORECASE
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")
_URL = re.compile(r"\bhttps?://([^\s/:?#]+)", re.IGNORECASE)

#: Hosts that are safe to appear as literals. Anything else is environment-specific:
#: baking it in means the suite runs against one environment and silently fails
#: everywhere else.
_SAFE_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "[::1]"})
_SAFE_HOST_SUFFIXES = (".example.com", ".example.org", ".example.net", ".test",
                       ".example", ".invalid", ".localhost")
_SAFE_HOST_EXACT = frozenset({"example.com", "example.org", "example.net"})

KINDS = ("credential-field", "private-key", "connection-string", "token-shape",
         "environment-url")

_REMEDY = {
    "credential-field": "read it from process.env and document it in .env.example",
    "private-key": "never commit a key; read it from process.env at run time",
    "connection-string": "read the connection string from process.env",
    "token-shape": "read the token from process.env and document it in .env.example",
    "environment-url": "use the configured baseURL from playwright.config.ts",
}


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """Where a secret was found and what to use instead. Never the value itself."""

    field: str
    kind: str
    remedy: str

    def message(self) -> str:
        return f"{self.field} carries a {self.kind} literal. Instead, {self.remedy}."


def _host_is_safe(host: str) -> bool:
    lowered = host.lower().split(":")[0]
    if lowered in _SAFE_HOSTS or lowered in _SAFE_HOST_EXACT:
        return True
    return any(lowered.endswith(suffix) for suffix in _SAFE_HOST_SUFFIXES)


def scan_value(
    field: str,
    value: str,
    *,
    extra_credential_fields: Iterable[str] = (),
) -> SecretFinding | None:
    """Return a finding when `value` must not be rendered as a literal, else None.

    Checked in a fixed order so a value matching two rules reports the same one every
    time. An unstable verdict would make the same emission fail differently on two
    runs, which is indistinguishable from a flaky check.
    """
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    names = CREDENTIAL_FIELDS | {f.lower() for f in extra_credential_fields}

    normalised_field = field.lower().strip()
    leaf = normalised_field.split()[-1].strip("'\"") if normalised_field else ""
    if leaf in names or any(n in normalised_field for n in names):
        return SecretFinding(field, "credential-field", _REMEDY["credential-field"])

    if _PRIVATE_KEY.search(text):
        return SecretFinding(field, "private-key", _REMEDY["private-key"])
    if _CONNECTION.search(text):
        return SecretFinding(field, "connection-string", _REMEDY["connection-string"])
    if _BEARER.search(text) or _JWT.search(text):
        return SecretFinding(field, "token-shape", _REMEDY["token-shape"])

    match = _URL.search(text)
    if match and not _host_is_safe(match.group(1)):
        return SecretFinding(field, "environment-url", _REMEDY["environment-url"])

    return None


def scan_case(
    case: Any, *, extra_credential_fields: Iterable[str] = ()
) -> list[SecretFinding]:
    """Every finding in a case, not the first.

    The same reasoning as the batch validator and L9: an agent that fixes one value
    and resubmits, four times over, has spent four model round-trips on one
    correction pass.
    """
    findings: list[SecretFinding] = []
    for datum in getattr(case, "test_data", []) or []:
        finding = scan_value(
            f"step {datum.step_ordinal} data '{datum.field_name}'",
            datum.value,
            extra_credential_fields=extra_credential_fields,
        )
        if finding is not None:
            findings.append(finding)

    for label, text in (
        ("preconditions", getattr(case, "preconditions", "")),
        *[(f"step {s.ordinal} action", s.action) for s in getattr(case, "steps", [])],
        *[(f"step {s.ordinal} expected", s.expected) for s in getattr(case, "steps", [])],
    ):
        # Field-name signals do not apply to prose, so only the value shapes run
        # here. A step reading "enter the password" is a description, not a secret.
        finding = scan_value(label, text)
        if finding is not None and finding.kind != "credential-field":
            findings.append(finding)
    return findings
