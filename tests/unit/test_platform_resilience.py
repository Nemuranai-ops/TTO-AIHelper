"""X4 ResilienceGateway. Requirements: NFR-REL-02, NFR-REL-03, NFR-REL-04."""

import random

import pytest

from tto_testgen.platform.logging import configure
from tto_testgen.platform.resilience import (
    RETRYABLE,
    RetryPolicy,
    isolate,
    with_retry,
)
from tto_testgen.platform.result import ErrorCode, err, ok


@pytest.fixture
def log():
    return configure("CRITICAL")


@pytest.fixture
def no_sleep():
    return lambda _: None


class TestRetryPolicy:
    def test_backoff_is_bounded_by_exponential_ceiling(self):
        policy = RetryPolicy(base_ms=1000)
        rng = random.Random(7)
        for attempt in range(3):
            ceiling = 1000 * (2**attempt)
            assert 0 <= policy.backoff_ms(attempt, rng) <= ceiling

    def test_full_jitter_produces_spread(self):
        # Fixed backoff would synchronise retries and hit a rate-limited server
        # harder on the second wave than the first.
        policy = RetryPolicy(base_ms=1000)
        rng = random.Random(1)
        samples = {policy.backoff_ms(2, rng) for _ in range(30)}
        assert len(samples) > 1

    def test_only_transient_codes_are_retryable(self):
        assert ErrorCode.FAILED_MCP_UNREACHABLE in RETRYABLE
        assert ErrorCode.FAILED_TIMEOUT in RETRYABLE
        assert ErrorCode.FAILED_LOCKED in RETRYABLE
        for code in ErrorCode:
            if code.is_rejection:
                assert code not in RETRYABLE, code


class TestWithRetry:
    def test_returns_immediately_on_success(self, log, no_sleep):
        calls = []
        result = with_retry(
            lambda: (calls.append(1), ok("done"))[1], RetryPolicy(), log, sleep=no_sleep
        )
        assert result.ok
        assert len(calls) == 1

    def test_retries_transient_failure_until_success(self, log, no_sleep):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            return ok("done") if calls["n"] == 3 else err(ErrorCode.FAILED_TIMEOUT, "timeout")

        result = with_retry(flaky, RetryPolicy(attempts=3), log, sleep=no_sleep)
        assert result.ok
        assert calls["n"] == 3

    def test_never_retries_a_rejection(self, log, no_sleep):
        # A 401 does not become a 200 on retry; retrying wastes the operator's
        # time and can trip an account lockout.
        calls = {"n": 0}

        def unauthorised():
            calls["n"] += 1
            return err(ErrorCode.REJECTED_ROLE_NOT_PERMITTED, "401")

        result = with_retry(unauthorised, RetryPolicy(attempts=3), log, sleep=no_sleep)
        assert not result.ok
        assert calls["n"] == 1

    def test_stops_at_attempt_limit(self, log, no_sleep):
        calls = {"n": 0}

        def always_down():
            calls["n"] += 1
            return err(ErrorCode.FAILED_MCP_UNREACHABLE, "down")

        result = with_retry(always_down, RetryPolicy(attempts=3), log, sleep=no_sleep)
        assert not result.ok
        assert calls["n"] == 3
        assert result.code is ErrorCode.FAILED_MCP_UNREACHABLE

    def test_sleeps_between_attempts_but_not_after_the_last(self, log):
        slept = []
        calls = {"n": 0}

        def always_down():
            calls["n"] += 1
            return err(ErrorCode.FAILED_TIMEOUT, "t")

        with_retry(
            always_down,
            RetryPolicy(attempts=3),
            log,
            sleep=slept.append,
            rng=random.Random(3),
        )
        assert len(slept) == 2  # 3 attempts, 2 gaps


class TestIsolate:
    def test_one_failure_does_not_stop_the_batch(self, log):
        results = isolate(
            ["a", "b", "c"],
            lambda i: err(ErrorCode.FAILED_MCP_UNREACHABLE, "down") if i == "b" else ok(i.upper()),
            log,
        )
        assert [v for _, v in results.succeeded] == ["A", "C"]
        assert [i for i, _ in results.failed] == ["b"]
        assert results.total == 3
        assert results.any_failed

    def test_raised_exception_is_contained_as_a_failure(self, log):
        def explode(item):
            raise RuntimeError("kaboom")

        results = isolate(["only"], explode, log)
        assert not results.succeeded
        assert results.failed[0][1].code is ErrorCode.FAILED_INTERNAL

    def test_all_success_reports_no_failures(self, log):
        results = isolate([1, 2, 3], lambda i: ok(i * 2), log)
        assert not results.any_failed
        assert [v for _, v in results.succeeded] == [2, 4, 6]

    def test_empty_input_is_not_a_failure(self, log):
        results = isolate([], lambda i: ok(i), log)
        assert results.total == 0
        assert not results.any_failed
