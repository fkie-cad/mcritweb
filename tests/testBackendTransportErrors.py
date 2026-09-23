#!/usr/bin/python
"""What a page does when the backend fails to answer at all.

Issue #43 asks how mcritweb should handle "all kinds of errors coming from
McritClient" and offers two options: make mcrit raise semantically meaningful
exceptions, or test every result for None and guess what went wrong. There is a
third kind of failure neither option covers, and it is the one that takes pages
down: the request never completes. `requests` raises then - ConnectionError if the
backend is gone, ReadTimeout if it stops answering mid-request - and nothing in
mcritweb catches it, so it escapes the view as an unhandled exception.

`mcrit_server_required` is not a defence. It probes `/` before the view runs, so it
catches a backend that was already down; it cannot catch one that goes down between
the probe and the call, nor an endpoint that hangs while `/` still answers.

These tests use the corpus with exactly one method replaced by the failure, so the
request reaches a real view with real data and fails only where a real backend would.
"""

import logging
import unittest

import pytest
import requests
from fixtureData import job_id_of

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

UNREACHABLE = "No connection to the MCRIT server"
TIMED_OUT = "did not respond in time"


class FailingBackend:
    """The corpus, with one named method failing the way a real backend can."""

    def __init__(self, inner, method, exception):
        self._inner = inner
        self._method = method
        self._exception = exception

    def __getattr__(self, name):
        if name == self._method:
            def fail(*args, **kwargs):
                raise self._exception
            return fail
        return getattr(self._inner, name)

    def raw_variant(self):
        """The raw-response client, still failing the same way.

        Named explicitly rather than left to __getattr__ above. A conftest that hands
        out `fake_mcrit.raw_variant()` when a view asks for raw responses - which every
        /api/ route does - would otherwise fall through to the *inner* client and get a
        healthy one back, and the /api/ tests below would quietly stop exercising a
        failing backend while still passing.

        The fake on this branch has no raw_variant, so this wraps whatever is there
        rather than assuming one exists. The lookup is on the *class*: the corpus fake
        answers every unknown attribute with a stub that raises when called, so
        getattr(inner, "raw_variant", None) never returns None and cannot be used to
        tell "has one" from "does not".
        """
        if hasattr(type(self._inner), "raw_variant"):
            inner = self._inner.raw_variant()
        else:
            inner = self._inner
        return FailingBackend(inner, self._method, self._exception)


def test_the_raw_variant_of_a_failing_backend_still_fails(corpus_mcrit):
    """Pins the above, because nothing on this branch exercises it yet.

    conftest here hands the app `fake_mcrit` directly, so the /api/ tests do reach the
    injected failure. The moment a conftest asks for `raw_variant()` instead, this is
    the only thing standing between those tests and a backend that never fails.
    """
    boom = requests.exceptions.ConnectionError("connection refused")
    backend = FailingBackend(corpus_mcrit, "getStatus", boom)

    with pytest.raises(requests.exceptions.ConnectionError):
        backend.raw_variant().getStatus()


TRANSPORT_FAILURES = [
    (requests.exceptions.ConnectionError("connection refused"), UNREACHABLE),
    (requests.exceptions.ConnectTimeout("connect timed out"), TIMED_OUT),
    (requests.exceptions.ReadTimeout("read timed out"), TIMED_OUT),
    (requests.exceptions.ChunkedEncodingError("truncated"), UNREACHABLE),
    (requests.exceptions.TooManyRedirects("redirect loop"), UNREACHABLE),
]

FAILURE_IDS = [type(exception).__name__ for exception, _ in TRANSPORT_FAILURES]


@pytest.fixture
def fake_mcrit(corpus_mcrit, request):
    method, exception = request.param
    return FailingBackend(corpus_mcrit, method, exception)


def failing(method):
    """Parameters for the fake_mcrit fixture: this method, each failure in turn."""
    return [(method, exception) for exception, _ in TRANSPORT_FAILURES]


def expected_messages():
    return [message for _, message in TRANSPORT_FAILURES]


# --- a page that cannot reach the backend says so -------------------------------

@pytest.mark.parametrize(
    "fake_mcrit, expected",
    list(zip(failing("getJobData"), expected_messages())),
    indirect=["fake_mcrit"], ids=FAILURE_IDS,
)
def test_a_result_page_says_the_backend_is_unreachable(client, as_role, fake_mcrit, expected):
    """Before this change every one of these was an unhandled exception - HTTP 500
    and a stack trace, for a condition the application already knows how to report."""
    as_role("visitor")

    response = client.get(f"/data/result/{job_id_of('matches_for_sample')}")

    assert response.status_code == 503, "a page that could not reach its backend is not a success"
    assert expected in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "fake_mcrit, expected",
    list(zip(failing("getFamily"), expected_messages())),
    indirect=["fake_mcrit"], ids=FAILURE_IDS,
)
def test_an_explore_page_says_the_backend_is_unreachable(client, as_role, fake_mcrit, expected):
    """A second blueprint, so this is the app's answer rather than one view's."""
    as_role("visitor")

    response = client.get("/explore/families/1")

    assert response.status_code == 503
    assert expected in response.get_data(as_text=True)


# --- the index page is not a safe place to send a failure ------------------------

#: every backend call index() makes for a signed-in, non-pending user. Each one is a
#: way for the index page itself to be the thing that cannot reach the backend.
#: Not getFamily, although index() has a line for it: it asks the queue for finished
#: getMatchesForSample jobs only, and mcrit derives a family_id for family-level
#: methods alone, so that line never runs. It used to look reachable because the
#: corpus fake answered getQueueData with every job whatever the filter.
INDEX_CALLS = ["getQueueData", "getSampleById", "search_samples"]


@pytest.mark.parametrize(
    "fake_mcrit",
    [(method, requests.exceptions.ConnectionError("connection refused")) for method in INDEX_CALLS],
    indirect=True, ids=INDEX_CALLS,
)
def test_the_index_page_reports_a_failure_instead_of_looping(client, as_role, fake_mcrit):
    """The obvious handler flashes and redirects to the index, the way
    mcrit_server_required does. That works there because it runs before a view and
    only when the probe has already failed.

    Here it does not: index() calls all four of these itself, so a backend that fails
    one of them fails the redirect target too - and the redirect target redirects
    again. The first version of this change did exactly that, and the werkzeug test
    client caught it as "Loop detected: A 302 redirect to / was already made".

    Rendering in place has no such failure mode, which is the reason for it. Asserted
    on the index itself so the property is pinned where it would break."""
    as_role("visitor")

    response = client.get("/", follow_redirects=True)

    assert response.status_code == 503
    assert UNREACHABLE in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "fake_mcrit",
    [("getFamily", requests.exceptions.ConnectionError("connection refused"))],
    indirect=True, ids=["getFamily"],
)
def test_the_failing_page_keeps_its_own_url(client, as_role, fake_mcrit):
    """A redirect would also throw away the address the user was on, so a reload
    after the backend comes back would land somewhere else."""
    as_role("visitor")

    response = client.get("/explore/families/1")

    assert response.status_code == 503
    assert response.headers.get("Location") is None


# --- the API answers with a status code, not a redirect to an HTML page ----------

@pytest.mark.parametrize(
    "fake_mcrit", failing("getStatus"), indirect=True, ids=FAILURE_IDS,
)
def test_the_api_answers_a_gateway_error(client, app, make_user, fake_mcrit):
    """An API client gets JSON or a status code; a 302 to an HTML page it cannot read
    would be worse than the 500 this replaces. mcritweb is a gateway to mcrit here,
    so it answers as one: 504 when the backend timed out, 502 otherwise."""
    make_user(role="visitor")

    response = client.get("/api/status", headers={"apitoken": "apitoken-visitor"})

    assert response.status_code in (502, 504)


@pytest.mark.parametrize(
    "fake_mcrit", [("getStatus", requests.exceptions.ReadTimeout("read timed out"))],
    indirect=True, ids=["ReadTimeout"],
)
def test_the_api_distinguishes_a_timeout_from_an_unreachable_backend(client, make_user, fake_mcrit):
    make_user(role="visitor")

    assert client.get("/api/status", headers={"apitoken": "apitoken-visitor"}).status_code == 504


@pytest.mark.parametrize(
    "fake_mcrit", [("getStatus", requests.exceptions.ConnectionError("refused"))],
    indirect=True, ids=["ConnectionError"],
)
def test_the_api_reports_an_unreachable_backend_as_a_bad_gateway(client, make_user, fake_mcrit):
    make_user(role="visitor")

    assert client.get("/api/status", headers={"apitoken": "apitoken-visitor"}).status_code == 502


# --- what the page and the log are allowed to say --------------------------------

@pytest.mark.parametrize(
    "fake_mcrit", [("getFamily", requests.exceptions.ReadTimeout("read timed out"))],
    indirect=True, ids=["ReadTimeout"],
)
def test_the_page_does_not_claim_a_timed_out_request_was_not_received(client, as_role, fake_mcrit):
    """The tempting reassurance is "nothing was changed". On a read timeout that is a
    claim we cannot make: the backend may have received the request and acted on it,
    and we merely stopped waiting for the answer. A reader who believes it resubmits
    a job, a delete or a rename that already went through.

    This route also pins the second half of the change. `modifyFamily` wrapped its
    `getFamily` call in `except Exception` and flashed "No valid family_id received"
    - so a backend that was simply unreachable was reported as the user having typed
    a bad id. That is the "guess what the error is and flash a probably appropriate
    message" approach issue #43 offers as an option, guessing wrong. Both sites that
    did it now let a RequestException through to the handler."""
    as_role("contributor")   # modifyFamily is gated above visitor

    page = client.post("/explore/modifyFamily", data={"family_id": "1", "family_new_name": "x"})

    assert page.status_code == 503
    assert "nothing was changed" not in page.get_data(as_text=True).lower()
    assert "unknown" in page.get_data(as_text=True).lower()


def test_a_transport_failure_carries_no_credentials():
    """The handler logs `repr(error)` so an operator can see what failed. A requests
    exception names the URL it could not reach - and must not name the token or the
    username sent with it, because that is a credential in a logfile.

    Checked against the real library rather than assumed: the repr is built by
    urllib3 from the connection, and what it chooses to include is not this
    application's decision to make."""
    try:
        requests.get("http://127.0.0.1:59999/whatever",
                     headers={"apitoken": "SUPERSECRETTOKEN", "username": "someuser"},
                     timeout=1)
    except requests.RequestException as error:
        rendered = repr(error)

    assert "SUPERSECRETTOKEN" not in rendered
    assert "someuser" not in rendered
    # and the handler logs exactly this string - `%r` of the same exception object
    assert "127.0.0.1" in rendered, "the repr must still say what could not be reached"


# --- an admin sees the page too, and the probe answers the API the same way -------

@pytest.mark.parametrize(
    "fake_mcrit", [("getFamily", requests.exceptions.ConnectionError("refused"))],
    indirect=True, ids=["ConnectionError"],
)
def test_an_admin_gets_the_page_and_not_a_build_error(client, as_role, fake_mcrit):
    """The page links an admin to the server settings, and only an admin, because
    that route is admin-gated. The first version of this named the blueprint
    `administration` - it is registered as `admin` - so `url_for` raised BuildError
    while rendering, and an admin got a 500 for the one condition the page exists to
    report. Every other test here signs in as a visitor and none of them saw it."""
    as_role("admin")

    response = client.get("/explore/families/1")

    assert response.status_code == 503
    assert url_for_admin_server() in response.get_data(as_text=True)


def url_for_admin_server():
    return "/admin/server"


@pytest.mark.parametrize(
    "fake_mcrit", [("getFamily", requests.exceptions.ConnectionError("refused"))],
    indirect=True, ids=["ConnectionError"],
)
def test_a_visitor_is_not_pointed_at_a_page_they_cannot_open(client, as_role, fake_mcrit):
    as_role("visitor")

    body = client.get("/explore/families/1").get_data(as_text=True)

    assert url_for_admin_server() not in body


@pytest.mark.parametrize(
    "probe, expected",
    [
        (lambda: (_ for _ in ()).throw(requests.exceptions.ConnectionError("refused")), 502),
        (lambda: (_ for _ in ()).throw(requests.exceptions.ReadTimeout("timed out")), 504),
        (lambda: False, 502),
    ],
    ids=["probe raises ConnectionError", "probe raises ReadTimeout", "probe refuses our token"],
)
@pytest.mark.parametrize(
    "fake_mcrit", [("nothingFailsHere", RuntimeError("unused"))], indirect=True, ids=[""],
)
def test_the_probe_answers_the_api_with_a_status_too(app, client, make_user, fake_mcrit, probe, expected):
    """mcrit_server_required runs before the view, so when the backend is fully down
    the probe fails first and the blueprint's own handler never gets a chance. It
    used to redirect an API caller to an HTML page - the same wrong-shape answer this
    change fixes for the call itself, one layer earlier.

    Every other API test here has the probe stubbed to succeed, which is exactly why
    none of them saw it."""
    make_user(role="visitor")
    app.config["MCRIT_SERVER_PROBE"] = probe

    response = client.get("/api/status", headers={"apitoken": "apitoken-visitor"})

    assert response.status_code == expected
    assert response.headers.get("Location") is None


@pytest.mark.parametrize(
    "fake_mcrit", [("nothingFailsHere", RuntimeError("unused"))], indirect=True, ids=[""],
)
def test_a_page_still_gets_the_redirect_when_the_probe_fails(app, client, as_role, fake_mcrit):
    """The API split must not change what a page does: mcrit_server_required's flash
    and redirect to the index is right there, because it runs before the view and the
    index has not been reached yet."""
    as_role("visitor")
    app.config["MCRIT_SERVER_PROBE"] = lambda: False

    response = client.get("/explore/families")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_the_api_blueprint_name_the_split_keys_on_is_the_real_one():
    """backend_errors names the blueprint as a string rather than importing api.py,
    which imports it. If the blueprint were ever renamed, every API caller would
    quietly start getting HTML redirects again - so the two are pinned together."""
    from mcritweb import backend_errors as errors
    from mcritweb.views import api

    assert api.bp.name == errors.API_BLUEPRINT_NAME


# --- the handler must not become a catch-all --------------------------------------

@pytest.mark.parametrize(
    "fake_mcrit", [("getJobData", ValueError("a bug in a view, not a transport failure"))],
    indirect=True, ids=["ValueError"],
)
def test_a_programming_error_is_not_dressed_up_as_a_backend_outage(client, as_role, fake_mcrit):
    """The whole value of this handler is that "the backend is unreachable" means
    exactly that. A handler broad enough to swallow a TypeError in a template would
    turn every bug in this application into a false report about someone else's
    server - and would hide it from the logs that would otherwise show it."""
    as_role("visitor")

    with pytest.raises(ValueError):
        client.get(f"/data/result/{job_id_of('matches_for_sample')}")


@pytest.mark.parametrize(
    "fake_mcrit", [("nothingFailsHere", RuntimeError("unused"))], indirect=True, ids=["baseline"],
)
def test_the_test_client_does_not_swallow_the_exception_by_itself(app, fake_mcrit):
    """The premise of the test above, checked rather than assumed: this app is built
    with TESTING=True, which makes Flask propagate *unhandled* exceptions to the
    caller. If it swallowed them into a 500 page instead, `pytest.raises` there would
    be testing the harness rather than the handler."""
    assert app.config["TESTING"] is True
    assert app.config.get("PROPAGATE_EXCEPTIONS") in (None, True)


if __name__ == "__main__":
    unittest.main()
