"""X5 HealthCheck. Requirements: NFR-OBS-02, RESILIENCY-06. Pattern: P-OBS-02."""

from tto_testgen.platform.health import ComponentHealth, Status, check


def probe(name, status, detail=""):
    return lambda: ComponentHealth(name, status, detail)


class TestHealthReport:
    def test_all_ok_reports_ok(self):
        report = check({"db": probe("db", Status.OK), "jira": probe("jira", Status.OK)})
        assert report.overall is Status.OK

    def test_partial_failure_is_degraded_not_unavailable(self):
        # The operator can proceed with what works. Collapsing degraded into
        # unavailable would tell them to stop when they could continue.
        report = check(
            {"db": probe("db", Status.OK), "jira": probe("jira", Status.UNAVAILABLE, "timeout")}
        )
        assert report.overall is Status.DEGRADED

    def test_everything_down_is_unavailable(self):
        report = check(
            {
                "db": probe("db", Status.UNAVAILABLE),
                "jira": probe("jira", Status.UNAVAILABLE),
            }
        )
        assert report.overall is Status.UNAVAILABLE

    def test_no_probes_is_unavailable(self):
        assert check({}).overall is Status.UNAVAILABLE

    def test_components_are_reported_independently(self):
        report = check(
            {"db": probe("db", Status.OK), "bitbucket": probe("bitbucket", Status.UNAVAILABLE)}
        )
        by_name = {c.name: c.status for c in report.components}
        assert by_name == {"db": Status.OK, "bitbucket": Status.UNAVAILABLE}

    def test_raising_probe_does_not_break_the_check(self):
        def boom():
            raise RuntimeError("probe exploded")

        report = check({"db": probe("db", Status.OK), "boom": boom})
        assert len(report.components) == 2
        assert report.overall is Status.DEGRADED
        broken = next(c for c in report.components if c.name == "boom")
        assert broken.status is Status.UNAVAILABLE
        assert "exploded" in broken.detail

    def test_to_dict_is_serialisable(self):
        payload = check({"db": probe("db", Status.OK, "schema v3")}).to_dict()
        assert payload["overall"] == "ok"
        assert payload["components"] == [
            {"name": "db", "status": "ok", "detail": "schema v3"}
        ]
