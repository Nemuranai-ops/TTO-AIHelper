"""X4 ResilienceGateway - bounded retry and per-item failure isolation.

No circuit breaker, deliberately. A breaker guards a shared downstream against a
stampede of concurrent callers; there is one operator, one process and sequential
requests, so that failure mode cannot occur. Retry plus isolation covers the ones
that can. Recorded in nfr-design-patterns.md section 7.

Requirements: NFR-REL-02, NFR-REL-03, NFR-REL-04. Patterns: P-RES-02, P-RES-03.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Generic, Iterable, TypeVar

from tto_testgen.platform.logging import Logger
from tto_testgen.platform.result import Err, ErrorCode, Ok, Result

T = TypeVar("T")
I = TypeVar("I")

#: Failures worth a second attempt. Everything else fails immediately: a 401 will
#: not become a 200 on retry, and retrying it wastes the operator's time and can
#: trip an account lockout.
RETRYABLE = frozenset(
    {
        ErrorCode.FAILED_MCP_UNREACHABLE,
        ErrorCode.FAILED_TIMEOUT,
        ErrorCode.FAILED_LOCKED,
    }
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_ms: int = 1000
    retryable: frozenset[ErrorCode] = RETRYABLE

    def backoff_ms(self, attempt: int, rng: random.Random) -> int:
        """Full jitter: uniform in [0, base * 2**attempt].

        Ingestion issues many requests in a burst. Fixed backoff would synchronise
        the retries and hit a rate-limited server harder on the second wave than
        the first; jitter spreads them.
        """
        ceiling = self.base_ms * (2**attempt)
        return rng.randint(0, ceiling)


def with_retry(
    operation: Callable[[], Result[T]],
    policy: RetryPolicy,
    logger: Logger,
    *,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> Result[T]:
    """Run `operation`, retrying only transient failures, at most `policy.attempts` times."""
    generator = rng or random.Random()
    last: Result[T] | None = None

    for attempt in range(policy.attempts):
        result = operation()
        if isinstance(result, Ok):
            if attempt:
                logger.info("operation succeeded after retry", attempt=attempt + 1)
            return result

        last = result
        if result.code not in policy.retryable:
            logger.warning(
                "operation failed, not retryable", code=result.code.value, attempt=attempt + 1
            )
            return result

        if attempt == policy.attempts - 1:
            break

        delay_ms = policy.backoff_ms(attempt, generator)
        logger.warning(
            "operation failed, retrying",
            code=result.code.value,
            attempt=attempt + 1,
            backoff_ms=delay_ms,
        )
        sleep(delay_ms / 1000.0)

    logger.error(
        "retries exhausted",
        code=last.code.value if isinstance(last, Err) else "unknown",
        attempts=policy.attempts,
    )
    return last  # type: ignore[return-value]


@dataclass(slots=True)
class IsolatedResults(Generic[I, T]):
    """Outcome of an isolated batch: successes and failures, both preserved."""

    succeeded: list[tuple[I, T]] = field(default_factory=list)
    failed: list[tuple[I, Err]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.succeeded) + len(self.failed)

    @property
    def any_failed(self) -> bool:
        return bool(self.failed)


def isolate(
    items: Iterable[I],
    operation: Callable[[I], Result[T]],
    logger: Logger,
) -> IsolatedResults[I, T]:
    """Run `operation` per item so one failure does not stop the batch.

    This is the one place the all-or-nothing rule is relaxed, and only for
    ingestion: at 3-10 repositories and hundreds of Jira issues, one unreachable
    source must not discard an hour of successful retrieval (NFR-REL-04).
    """
    results: IsolatedResults[I, T] = IsolatedResults()
    for item in items:
        try:
            outcome = operation(item)
        except Exception as exc:  # noqa: BLE001 - isolation boundary, by design
            logger.error("isolated operation raised", item=str(item), error=str(exc))
            from tto_testgen.platform.result import err

            results.failed.append(
                (item, err(ErrorCode.FAILED_INTERNAL, f"Unhandled error: {exc}"))
            )
            continue

        if isinstance(outcome, Ok):
            results.succeeded.append((item, outcome.value))
        else:
            logger.warning("isolated operation failed", item=str(item), code=outcome.code.value)
            results.failed.append((item, outcome))
    return results
