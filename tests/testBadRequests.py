#!/usr/bin/python
"""Routes answer rather than crash when the request is not what the UI would send.

A 500 found while building the route/role test matrix: no malicious caller needed,
just a URL typed by hand or followed by a link scanner.

Issue #94.
"""

import logging
import unittest

import pytest

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


# --- #94: start_cross_compare ----------------------------------------------------

@pytest.mark.parametrize("query", ["", "?samples=", "?samples=abc", "?samples=1,,2", "?samples=-1"])
def test_cross_compare_without_usable_samples_redirects(client, as_role, query):
    """job_id was only bound inside `if selected != ''`, so a bare request fell
    through to a redirect naming an unbound local. `?samples=abc` raised from
    int() on the same line."""
    as_role("visitor")
    response = client.get(f"/analyze/start_cross_compare{query}")
    assert response.status_code == 302
    assert "/analyze/cross_compare" in response.headers["Location"]


class TestCrossCompareStillWorks:
    """The strict fake raises on requestMatchesCross and the permissive one answers
    None, which is not a job id the redirect can be built from. Teach it one."""

    @pytest.fixture
    def fake_mcrit(self, recording_mcrit):
        def _request_matches_cross(*args, **kwargs):
            recording_mcrit._record("requestMatchesCross", *args, **kwargs)
            return "0123456789abcdef01234567"
        recording_mcrit.requestMatchesCross = _request_matches_cross
        return recording_mcrit

    def test_cross_compare_with_samples_still_queues_a_job(self, client, as_role, fake_mcrit):
        """The guard must not swallow the working case."""
        as_role("visitor")
        response = client.get("/analyze/start_cross_compare?samples=1,2")

        assert response.status_code == 302
        assert "/data/jobs/" in response.headers["Location"]
        queued = [args for name, args, _ in fake_mcrit.calls if name == "requestMatchesCross"]
        assert queued, "no job was queued"
        assert queued[0][0] == [1, 2], "the selected samples did not reach the backend"


if __name__ == "__main__":
    unittest.main()
