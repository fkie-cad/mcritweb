#!/usr/bin/python
"""The API passthrough honours the role behind the token.

`token_required` used to check only that a token matched *some* user. Since the
router forwards to the backend's write endpoints, that made a 'pending' account's
token as powerful as an admin's, and turned the API into the cheapest way around
every role check in the web UI.

Roles now mirror the UI: reads and job submission at visitor, adding a report at
contributor, 'pending' refused outright.

These tests assert on the gate and nothing else. The router builds its client with
`raw_responses=True` and hands the result to `handle_raw_response`, which wants a
real `requests.Response`; the fakes return plain values, so anything that gets past
authorization dies downstream. That distinction is exactly what `_verdict` encodes -
a request that dies downstream is a request that was allowed through.
"""

import logging
import unittest

import pytest

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

ALLOWED = "allowed"


def token_for(role):
    """make_user in conftest gives every account a predictable token."""
    return {"apitoken": f"apitoken-{role}"}


def _verdict(call):
    """403 when authorization refused, ALLOWED when the request got past it."""
    try:
        response = call()
    except Exception:
        return ALLOWED
    return response.status_code if response.status_code == 403 else ALLOWED


def test_a_request_without_a_token_is_refused(client, as_role):
    as_role("admin")
    assert _verdict(lambda: client.get("/api/version")) == 403


def test_an_unknown_token_is_refused(client, as_role):
    as_role("admin")
    assert _verdict(lambda: client.get("/api/version", headers={"apitoken": "not-a-token"})) == 403


def test_a_pending_token_is_refused(client, make_user):
    make_user("pending")
    assert _verdict(lambda: client.get("/api/version", headers=token_for("pending"))) == 403


@pytest.mark.parametrize("role", ["visitor", "contributor", "admin"])
def test_a_role_bearing_token_can_read(client, make_user, role):
    make_user(role)
    assert _verdict(lambda: client.get("/api/version", headers=token_for(role))) == ALLOWED


def test_a_visitor_token_cannot_add_a_report(client, make_user):
    """POST /api/samples reaches addReport, which data.submit puts behind
    contributor_required."""
    make_user("visitor")
    assert _verdict(lambda: client.post("/api/samples", headers=token_for("visitor"), json={})) == 403


@pytest.mark.parametrize("role", ["contributor", "admin"])
def test_a_contributor_token_may_add_a_report(client, make_user, role):
    make_user(role)
    assert _verdict(lambda: client.post("/api/samples", headers=token_for(role), json={})) == ALLOWED


def test_a_visitor_token_can_still_read_samples(client, make_user):
    """The same path by GET is a read, and stays visitor-level."""
    make_user("visitor")
    assert _verdict(lambda: client.get("/api/samples", headers=token_for("visitor"))) == ALLOWED


def test_a_visitor_token_can_still_submit_a_job(client, make_user):
    """Job submission is visitor-level in the UI (analyze.query), so it stays so here."""
    make_user("visitor")
    assert _verdict(lambda: client.get("/api/matches/sample/1", headers=token_for("visitor"))) == ALLOWED


if __name__ == "__main__":
    unittest.main()
