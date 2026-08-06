#!/usr/bin/python
"""Routes answer rather than crash when the request is not what the UI would send.

Both cases here were 500s found while building the route/role test matrix: a URL
typed by hand, a link scanner, or a user list acted on after someone else changed
the data behind it. Neither needed a malicious caller.

Issues #94 and #95.
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


# --- #95: change_user_role -------------------------------------------------------

def test_changing_the_role_of_a_deleted_user_reports_it(client, as_role):
    """UserInfo.fromDb answers None for an unknown id, and the view assigned
    straight through it. Reachable by acting on a stale user list."""
    as_role("admin")
    response = client.post("/admin/change_user_role/9999/visitor/all")
    assert response.status_code == 302
    assert "/admin/users" in response.headers["Location"]


def test_an_unknown_role_is_refused(client, as_role, make_user):
    """Any string used to land in user.role. The account then failed every
    decorator, so it could reach nothing and no page said why."""
    as_role("admin")
    user_id = make_user(role="visitor", username="target")
    response = client.post(f"/admin/change_user_role/{user_id}/superuser/all")

    assert response.status_code == 302
    from mcritweb.db import UserInfo
    with client.application.app_context():
        assert UserInfo.fromDb(user_id=user_id).role == "visitor", "the role was written anyway"


@pytest.mark.parametrize("role", ["pending", "visitor", "contributor", "admin"])
def test_every_known_role_still_applies(client, as_role, make_user, role):
    as_role("admin")
    user_id = make_user(role="visitor", username="target")
    assert client.post(f"/admin/change_user_role/{user_id}/{role}/all").status_code == 302

    from mcritweb.db import UserInfo
    with client.application.app_context():
        assert UserInfo.fromDb(user_id=user_id).role == role


if __name__ == "__main__":
    unittest.main()
