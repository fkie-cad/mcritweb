#!/usr/bin/python
"""Routes answer rather than crash when the request is not what the UI would send.

All three cases here were 500s found while building the route/role test matrix and
the result-page fixtures: a URL typed by hand, a link scanner, or a page acted on
after someone else changed the data behind it. None needed a malicious caller - the
last one just needs two admins with the user list open at the same time.

Issues #94, #95, #96.
"""

import logging
import unittest

import pytest
from fixtureData import job_id_of

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

#: The h1 of result_corrupted.html. Asserting on the template name would pass
#: whatever the page said, since the name appears nowhere in the rendered output.
CORRUPTED_MARKER = b"are corrupted"


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


# --- #96: a function deleted since the job ran -----------------------------------

class TestMissingFunctions:
    """These need the captured corpus, so the fake backend is overridden for them."""

    @pytest.fixture
    def fake_mcrit(self, corpus_mcrit):
        return corpus_mcrit

    def test_a_missing_function_renders_the_corrupted_page(self, client, as_role, fake_mcrit):
        """getFunctionsByIds returns only what the backend still has, and the view
        indexed the result directly. A sample deleted after the job finished left
        ids behind that resolve to nothing, and the report 500'd instead of saying
        so - while the cross-compare path had handled the same case for years.

        This drives the 1-vs-1 report, which is the path issue #96 was reported
        against. The other two call sites share `assign_matched_offsets`, whose
        contract is covered directly below."""
        as_role("visitor")
        job_id = job_id_of("matches_for_sample_vs")
        assert client.get(f"/data/result/{job_id}").status_code == 200, "the report does not render even intact"

        requested = [
            function_id
            for name, args, _ in fake_mcrit.calls
            if name == "getFunctionsByIds"
            for function_id in args[0]
        ]
        assert requested, "this path no longer looks up matched functions - the test is watching nothing"
        fake_mcrit._functions.pop(int(requested[0]))

        response = client.get(f"/data/result/{job_id}")
        assert response.status_code == 200
        assert CORRUPTED_MARKER in response.data


class FunctionEntry:
    def __init__(self, offset):
        self.offset = offset


class FunctionMatch:
    def __init__(self, matched_function_id):
        self.matched_function_id = matched_function_id
        self.matched_offset = None


class LookupClient:
    """Answers only for the ids it was given, as getFunctionsByIds does."""

    def __init__(self, offsets_by_id):
        self._offsets_by_id = offsets_by_id

    def getFunctionsByIds(self, function_ids, *args, **kwargs):
        return {fid: FunctionEntry(self._offsets_by_id[fid]) for fid in function_ids if fid in self._offsets_by_id}


def test_offsets_are_assigned_when_every_function_is_present():
    from mcritweb.views.data import assign_matched_offsets

    matches = [FunctionMatch(1), FunctionMatch(2)]
    assert assign_matched_offsets(LookupClient({1: 0x1000, 2: 0x2000}), matches) is True
    assert [match.matched_offset for match in matches] == [0x1000, 0x2000]


def test_a_missing_function_is_reported_rather_than_raising():
    from mcritweb.views.data import assign_matched_offsets

    matches = [FunctionMatch(1), FunctionMatch(2)]
    assert assign_matched_offsets(LookupClient({1: 0x1000}), matches) is False
    assert matches[0].matched_offset == 0x1000, "the entries that survive are still assigned"


def test_a_backend_answering_nothing_is_reported_rather_than_raising():
    """`or {}` in the helper - a None answer used to be an AttributeError one line on."""
    from mcritweb.views.data import assign_matched_offsets

    class SilentClient:
        def getFunctionsByIds(self, function_ids, *args, **kwargs):
            return None

    assert assign_matched_offsets(SilentClient(), [FunctionMatch(1)]) is False


if __name__ == "__main__":
    unittest.main()
