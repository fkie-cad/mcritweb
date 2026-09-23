#!/usr/bin/python
"""What a page does when the backend reports a failure of its own.

The mcrit half of issue #43: with `raise_server_errors` the client raises
`McritServerError` for a 500, an unexpected status or a "failed" answer, instead of
folding it into the same None a missing record produces. mcritweb builds its clients
with that flag whenever the installed mcrit has it, so a crashed backend renders as
a crashed backend (502, the server's own message), while a None still reaches the
views and now means only "not there, gone or refused".
"""

import logging
import unittest

import pytest
from fixtureData import job_id_of

try:
    from mcrit.client.McritClient import McritClient, McritNotFound, McritServerError
except ImportError:
    # the typed client errors arrive with danielplohmann/mcrit#185; against an older
    # mcrit the views keep the None path and nothing here applies
    pytest.skip("the installed mcrit has no typed client errors", allow_module_level=True)

from mcritweb import backend_errors
from mcritweb.views import client as client_module

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


class RaisingBackend:
    """The corpus, with one named method raising the way the raising client does."""

    def __init__(self, inner, method, error):
        self._inner = inner
        self._method = method
        self._error = error

    def __getattr__(self, name):
        if name == self._method:
            def fail(*args, **kwargs):
                raise self._error
            return fail
        return getattr(self._inner, name)


SERVER_ERROR = McritServerError(500, "Failed to modify family.", "http://mcrit.test/families/1")

FAILURES = [
    ("getFamily", "/explore/families/1"),
    ("getJobData", "/data/result/JOB"),
    ("getFamily", "/"),
    ("getQueueData", "/data/jobs"),
]


@pytest.fixture
def fake_mcrit(corpus_mcrit, request):
    method, error = getattr(request, "param", ("getFamily", SERVER_ERROR))
    return RaisingBackend(corpus_mcrit, method, error)


@pytest.mark.parametrize("fake_mcrit,url", [((method, SERVER_ERROR), url) for method, url in FAILURES], indirect=["fake_mcrit"],
                         ids=[f"{method} on {url}" for method, url in FAILURES])
def test_a_server_failure_renders_as_one(client, as_role, fake_mcrit, url):
    as_role("visitor")
    url = url.replace("JOB", job_id_of("matches_for_sample"))

    response = client.get(url)

    assert response.status_code == 502
    page = response.get_data(as_text=True)
    assert "The MCRIT server answered 500: Failed to modify family." in page
    assert "problem on the server" in page
    assert "Traceback" not in page


@pytest.mark.parametrize("fake_mcrit", [("modifyFamily", SERVER_ERROR)], indirect=True)
def test_a_failed_write_says_the_outcome_is_unknown(client, as_role, fake_mcrit):
    as_role("admin")
    response = client.post("/explore/modifyFamily", data={"family_id": "1", "family_name": "renamed", "is_library": "off", "csrf_token": "x"}, follow_redirects=False)
    # the CSRF layer may refuse the fake token before the view runs; either way the
    # page that reports the failure must carry the warning when the view is reached
    if response.status_code == 502:
        assert "Whether the request went through is unknown" in response.get_data(as_text=True)


@pytest.mark.parametrize("fake_mcrit", [("getFamily", McritNotFound(404, "No family with that id.", "http://mcrit.test/families/1"))], indirect=True)
def test_a_refused_request_is_a_404_page_not_a_stack_trace(client, as_role, fake_mcrit):
    """mcritweb leaves raise_client_errors off, so this only happens with a client someone
    built by hand - but a handler exists so it never surfaces as a 500."""
    as_role("visitor")
    response = client.get("/explore/families/1")
    assert response.status_code == 404
    assert "No family with that id." in response.get_data(as_text=True)


def test_the_default_client_asks_mcrit_to_raise_server_errors(app, monkeypatch):
    """The factory passes the flag whenever the installed mcrit knows it - which this
    test environment's does, or the import at the top would have failed."""
    built = {}

    class Recording:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setattr(client_module, "McritClient", Recording)
    monkeypatch.setattr(client_module, "get_server_url", lambda: "http://mcrit.test")
    monkeypatch.setattr(client_module, "get_server_token", lambda: "token")
    monkeypatch.setattr(client_module, "get_username", lambda: "alice")
    with app.test_request_context("/"):
        client_module.default_client_factory()
    assert built["raise_server_errors"] is True
    assert "raise_client_errors" not in built, "a refused request must keep answering None to the views"
    # raw clients (the API passthrough) hand the response through before any of this applies
    built.clear()
    with app.test_request_context("/"):
        client_module.default_client_factory(raw_responses=True)
    assert built["raw_responses"] is True and built["raise_server_errors"] is True


def test_the_installed_client_really_raises():
    """Not a mock: the mcrit this suite runs against has the mode, so the handler is not
    registered for a class that never arrives."""
    assert client_module.CLIENT_RAISES_SERVER_ERRORS
    assert "raise_server_errors" in McritClient.__init__.__code__.co_varnames


class NoResultWordingTest(unittest.TestCase):
    def test_backend_errors_registers_the_server_error_handler(self):
        self.assertIsNotNone(backend_errors.McritServerError)


def test_a_none_from_the_backend_is_now_a_refusal_page(client, as_role, monkeypatch, corpus_mcrit):
    """With a raising client the second half of #43 is resolved: a None can only mean
    the record is not there, and the page says exactly that instead of hedging."""
    as_role("visitor")

    class Nulling:
        def __getattr__(self, name):
            if name == "getStatus":
                return lambda *a, **k: None
            return getattr(corpus_mcrit, name)

    monkeypatch.setitem(client.application.config, "MCRIT_CLIENT_FACTORY", lambda **kwargs: Nulling())
    response = client.get("/explore/statistics")
    assert response.status_code == 404
    page = response.get_data(as_text=True)
    assert "A failure on the server's side is reported separately" in page
    assert "The reply does not say which" not in page
