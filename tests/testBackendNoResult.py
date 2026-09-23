#!/usr/bin/python
"""What a page does when the backend answers a call with nothing.

This is the second half of issue #43. `handle_response` in mcrit returns `None` for
400, 404, 410, 500, 501 *and* for every status it does not enumerate, so any view
that uses a client result without checking it breaks on a backend hiccup - and
breaks as a stack trace, because `None` is the wrong shape for whatever the view
does next.

Every route below was audited by walking the AST of `mcritweb/views/` for calls on a
`get_client()` result and asking whether the value is ever tested. The ones here are
the sites where it was not and where `None` actually damages the page; the audit's
other outcomes are pinned further down, because "we deliberately left this one
alone" is as much a decision as a fix and regresses just as quietly.
"""

import logging
import unittest

import pytest
import requests
from fixtureData import job_id_of

from mcritweb.backend_errors import NoResultFromBackend, require_result
from mcritweb.views.client import CLIENT_RAISES_SERVER_ERRORS

#: With a client that raises server failures (mcrit's half of #43) a None can only mean
#: "not there, gone or refused", and the page says so with a 404; against an older
#: mcrit it still has to cover a crashed backend and answers 502.
NO_RESULT_STATUS = 404 if CLIENT_RAISES_SERVER_ERRORS else 502

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


class NullingBackend:
    """The corpus, with one named method answering None the way a real one can.

    `_extra` fills in methods the captured corpus has no fixture for but the route
    under test calls anyway. Those are stubs for calls the test is not about; the one
    the test *is* about is always the forced None.
    """

    def __init__(self, inner, method, extra=None):
        self._inner = inner
        self._method = method
        self._extra = extra or {}

    def __getattr__(self, name):
        if name == self._method:
            return lambda *args, **kwargs: None
        if name in self._extra:
            value = self._extra[name]
            return lambda *args, **kwargs: value
        return getattr(self._inner, name)

    def raw_variant(self):
        """The raw-response client, still nulling the same method.

        Same reasoning as the transport tests: a conftest that hands out
        `fake_mcrit.raw_variant()` when a view asks for raw responses must not fall
        through to a healthy inner client, or the /api/ assertion below would stop
        exercising anything while still passing.
        """
        inner = self._inner.raw_variant() if hasattr(type(self._inner), "raw_variant") else self._inner
        return NullingBackend(inner, self._method, self._extra)


@pytest.fixture
def fake_mcrit(corpus_mcrit, request):
    method, extra = request.param
    return NullingBackend(corpus_mcrit, method, extra)


# --- the helper itself -----------------------------------------------------------

def test_require_result_hands_back_what_the_backend_gave():
    assert require_result({"job_id": "7"}, "a job") == {"job_id": "7"}


@pytest.mark.parametrize("empty", [{}, [], 0, "", False], ids=["dict", "list", "int", "str", "bool"])
def test_an_empty_answer_is_still_an_answer(empty):
    """`if not result` would be the shorter check and the wrong one. An empty family
    list, a queue with no jobs and a sample id of 0 are all real answers, and mcrit
    distinguishes them from a failed call by returning None only for the failure."""
    assert require_result(empty, "a collection") is empty


def test_a_missing_result_names_what_was_missing():
    with pytest.raises(NoResultFromBackend) as raised:
        require_result(None, "a job for this comparison")

    assert raised.value.what == "a job for this comparison"
    assert "a job for this comparison" in str(raised.value)


# --- the pages ------------------------------------------------------------------

DELETE_FAMILY = {"family_id": "1", "family_delete": "1"}
RENAME_FAMILY = {"family_id": "1", "family_new_name": "renamed"}
DELETE_SAMPLE = {"sample_id": "1", "sample_delete": "1"}

#: role, HTTP verb, url, the method to null, form data, extra stubs.
#: Every one of these raised an unhandled exception before this change - the kind is
#: named beside it, because that is what the test is here to keep from coming back.
UNGUARDED_ROUTES = [
    # url_for(job_id=None) is a BuildError: werkzeug drops the None and then cannot
    # build a rule that requires it. Twelve sites scheduled a job and redirected to
    # it without ever looking at what came back.
    ("admin", "post", "/admin/schedule_rebuild_index", "rebuildIndex", None, None),
    ("admin", "post", "/admin/schedule_recalc_pichashes", "recalculatePicHashes", None, None),
    ("admin", "post", "/admin/schedule_recalc_minhashes", "recalculateMinHashes", None, None),
    ("visitor", "get", "/analyze/blocks/sample/1", "requestUniqueBlocksForSamples", None, None),
    ("visitor", "get", "/analyze/compare/1", "requestMatchesForSample", None, None),
    ("visitor", "get", "/analyze/compare/1/2", "requestMatchesForSampleVs", None, None),
    ("visitor", "get", "/analyze/start_cross_compare?samples=1,2", "requestMatchesCross", None, None),
    ("contributor", "post", "/explore/modifyFamily", "deleteFamily", DELETE_FAMILY, None),
    ("contributor", "post", "/explore/modifySample", "deleteSample", DELETE_SAMPLE, None),
    # AttributeError: the view calls .values() on the answer.
    ("contributor", "get", "/data/submit", "getFamilies", None, None),
    ("contributor", "get", "/data/specific_export/family/1", "getSamplesByFamilyId", None, None),
    # TypeError: mcrit's clusterLinkHuntResult iterates it.
    ("visitor", "get", "/data/linkhunt/JOB", "getFunctionsBySampleId", None, None),
    # UndefinedError out of the column-table macro, which calls a method on the entry.
    ("visitor", "get", "/explore/functions/1", "getSampleById", None, {"getMatchesForPicHash": {}}),
]

ROUTE_IDS = [f"{method} on {url}" for _, _, url, method, _, _ in UNGUARDED_ROUTES]


@pytest.mark.parametrize(
    "role, verb, url, fake_mcrit, form",
    [(role, verb, url, (method, extra), form)
     for role, verb, url, method, form, extra in UNGUARDED_ROUTES],
    indirect=["fake_mcrit"], ids=ROUTE_IDS,
)
def test_a_page_says_the_backend_returned_nothing(client, as_role, role, verb, url, fake_mcrit, form):
    as_role(role)
    url = url.replace("JOB", job_id_of("matches_for_sample"))

    response = client.post(url, data=form) if verb == "post" else client.get(url)

    assert response.status_code == NO_RESULT_STATUS, "a page built from a missing result is not a success"
    assert "did not return" in response.get_data(as_text=True)


# --- two that failed quietly, which is worse than failing loudly ------------------

@pytest.mark.parametrize(
    "fake_mcrit", [("getStatus", None)], indirect=True, ids=["getStatus"],
)
def test_the_statistics_page_does_not_report_an_empty_collection(client, as_role, fake_mcrit):
    """This one rendered HTTP 200 with an empty table: jinja reads `stats['status']`
    off None as Undefined and iterates nothing. So a backend that could not answer
    looked exactly like a collection with nothing in it, on the one page whose entire
    job is to say how much is in the collection."""
    as_role("visitor")

    response = client.get("/explore/statistics")

    assert response.status_code == NO_RESULT_STATUS


@pytest.mark.parametrize(
    "fake_mcrit", [("modifyFamily", None)], indirect=True, ids=["modifyFamily"],
)
def test_a_change_that_was_not_scheduled_is_not_reported_as_scheduled(client, as_role, fake_mcrit):
    """This one redirected with "Job to modify family was scheduled." after the
    backend had refused it. The flash is unconditional and the job id it ignores was
    the only evidence either way."""
    as_role("contributor")

    response = client.post("/explore/modifyFamily", data=RENAME_FAMILY)

    assert response.status_code == NO_RESULT_STATUS
    assert "was scheduled" not in response.get_data(as_text=True)


# --- what the audit deliberately left alone --------------------------------------

@pytest.mark.parametrize(
    "fake_mcrit", [("getSampleById", None)], indirect=True, ids=["getSampleById"],
)
def test_a_result_page_that_already_tolerates_a_missing_sample_still_does(client, as_role, fake_mcrit):
    """`require_result` is for call sites that cannot carry on without the value. A
    filtered result page can: it hands the entry to a template that copes, and turning
    that into a 502 would replace a working page with an error for no gain.

    Pinned because the tempting next step is to apply the helper to every remaining
    site the audit listed, and this is the evidence that it would be wrong."""
    as_role("visitor")

    response = client.get(f"/data/result/{job_id_of('matches_for_sample')}?samid=1")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "fake_mcrit", [("getJobData", {"deleteJob": None})], indirect=True, ids=["getJobData"],
)
def test_deleting_a_whole_queue_state_still_works_without_a_job_of_its_own(client, as_role, fake_mcrit):
    """`data.delete_job_by_id` accepts the pseudo ids "state_..." and "category_..."
    from the jobs page, which no backend can resolve to a job - so None there is the
    normal case, not a failure, and `require_result` would break bulk deletion
    outright. The audit flagged the call; reading it is what settled it."""
    as_role("contributor")

    response = client.post("/data/jobs/state_failed/delete")

    assert response.status_code == 302


@pytest.mark.parametrize(
    "fake_mcrit", [("getFamilies", None), ("getQueueData", None)],
    indirect=True, ids=["getFamilies", "getQueueData"],
)
def test_the_listing_pages_survive_a_backend_that_answers_nothing(client, as_role, fake_mcrit):
    """This was a marker: `/explore/samples` broke on both of these, and issue #77 was
    going to replace every one of those calls in the same functions, so patching them
    here would have been a merge conflict rather than a fix. #77 has landed (1.5.0) and
    closed both - the listing no longer fetches every family, and a queue read that
    comes back empty-handed is flashed rather than dereferenced - so the marker is now
    the regression test it was waiting to become."""
    as_role("visitor")

    response = client.get("/explore/samples")

    assert response.status_code == 200


# --- the API is a different shape and does not need this -------------------------

@pytest.mark.parametrize(
    "fake_mcrit", [("nothingIsNulledHere", None)], indirect=True, ids=[""],
)
def test_no_api_route_can_produce_a_none_to_check(app, client, make_user, fake_mcrit):
    """`backend_errors.register` puts no handler on the api blueprint, deliberately:
    every route there builds its client with raw_responses=True, which hands back the
    `requests.Response` itself and never passes through `handle_response`. So there is
    no None for `require_result` to catch, and a handler would be dead code.

    That is a property of one line in `api_router`, so it is pinned to that line - and
    the client this hands back is a raw one, so the route is exercised as it would run
    rather than only inspected."""
    make_user(role="visitor")
    asked_for = []

    def recording_factory(**kwargs):
        asked_for.append(kwargs)
        return RawResponseClient()

    app.config["MCRIT_CLIENT_FACTORY"] = recording_factory

    response = client.get("/api/status", headers={"apitoken": "apitoken-visitor"})

    assert response.status_code == 200
    assert asked_for, "the api route did not build a client at all"
    assert all(kwargs.get("raw_responses") is True for kwargs in asked_for)


class RawResponseClient:
    """A client that answers the way McritClient does with raw_responses=True."""

    def __getattr__(self, name):
        def raw(*args, **kwargs):
            response = requests.Response()
            response.status_code = 200
            response._content = b'{"status": "successful", "data": {}}'
            return response
        return raw


if __name__ == "__main__":
    unittest.main()
