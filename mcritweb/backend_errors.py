"""What to say when a call to the MCRIT backend does not complete.

Issue #43 asks how to handle "all kinds of errors coming from McritClient", and
offers two options: have mcrit raise semantically meaningful exceptions, or test
every result for None and guess. This module covers the case neither option
reaches - the request never completes at all, so there is no result to test and no
guessing required. `requests` raises for that, and until now nothing caught it, so
it escaped the view as an unhandled exception and the page became an HTTP 500.

There is exactly one thing a `requests` exception can mean here: talking to the
backend failed. `views/utility.default_server_probe` is the only other outbound HTTP
call this application makes, and `mcrit_server_required` already wraps it in its own
try/except - so anything reaching these handlers came out of `McritClient`.

Deliberately narrow. It catches `requests.RequestException` and nothing wider: a
handler broad enough to swallow a TypeError in a template would turn every bug in
this application into a false report about someone else's server, and would hide it
from the logs that would otherwise show it.

The second half of #43 - "always test for `result is None` after using McritClient"
- lives here too, as `require_result`. `handle_response` in mcrit maps 400, 404, 410,
500, 501 *and* every status it does not enumerate to the same `None`, so a call site
cannot tell "no such thing" from "the backend is on fire". It can still tell that it
was given nothing, and that is what `require_result` reports. See its docstring for
why that is the honest answer and not a cop-out.

One boundary worth naming: `requests.HTTPError` is also a RequestException, and it
would be reported here as a connection failure, which it is not - it means the
backend answered with an error status. That is unreachable today, because
`raise_for_status` appears nowhere in mcrit; every status it sees goes through
`handle_response` instead. If that ever changes, this is the place that needs a
branch for it.
"""

import requests
from flask import Response, current_app, render_template, request

try:
    from mcrit.client.McritClient import McritClientError, McritGone, McritNotFound, McritRequestError, McritServerError
except ImportError:  # an mcrit before the client learnt to raise (its half of issue #43)
    McritClientError = McritGone = McritNotFound = McritRequestError = McritServerError = None

#: name of the blueprint whose callers get a status code instead of a page. Kept here
#: rather than imported from views/api.py, which imports this module - a test asserts
#: the two still agree.
API_BLUEPRINT_NAME = "api"


def wants_a_status_code():
    """True for a request that cannot read an HTML page - i.e. an API caller."""
    return request.blueprint == API_BLUEPRINT_NAME


class NoResultFromBackend(Exception):
    """McritClient answered `None` where the caller needs a value.

    This is the second half of #43. It is deliberately *one* exception rather than a
    family of them, because the client cannot supply the distinctions a family would
    need: `handle_response` collapses "bad request", "not found", "gone", "internal
    error" and every status it has never heard of into the same `None`. Inventing a
    NotFound here would state as fact something the wire did not say.

    So `what` names the value that is missing rather than the reason it is missing,
    and the page it renders says both possibilities out loud.
    """

    def __init__(self, what):
        super().__init__(f"the MCRIT server did not return {what}")
        #: what the caller asked for, phrased to follow "did not return".
        self.what = what


def require_result(result, what):
    """`result`, or a reported failure if the backend supplied nothing.

    For call sites that cannot carry on without the value. A view that *can* - one
    with a "no such family" branch, or a template that already tests for none - keeps
    its own handling; this is not for it.

    Wrapping the call rather than testing the variable afterwards is what keeps this
    to one line per site, and keeps the check next to the call it belongs to instead
    of three statements later where the next edit can separate them.
    """
    if result is None:
        raise NoResultFromBackend(what)
    return result


def is_timeout(error):
    """A backend that answered too slowly, as opposed to one that did not answer.

    Timeout covers ConnectTimeout and ReadTimeout both; the first means the backend
    never accepted the connection, the second that it accepted and then stopped
    talking. Neither is "the server is down", and saying so would send an operator
    looking in the wrong place.
    """
    return isinstance(error, requests.exceptions.Timeout)


def message_for(error):
    """What to tell a person about a backend call that did not complete."""
    if is_timeout(error):
        return 'The MCRIT server did not respond in time'
    return 'No connection to the MCRIT server'


def status_for(error):
    """What to tell a program. mcritweb is a gateway to mcrit here, so it answers as
    one: 504 for a backend that ran out of time, 502 for one that could not be
    reached or answered unusably."""
    return 504 if is_timeout(error) else 502


def register(app):
    """Answer a failed backend call with a page rather than a stack trace.

    The API's own handler is registered on its blueprint at import time, in
    views/api.py - a blueprint takes handlers only before it is registered, and this
    factory runs once per app.
    """

    @app.errorhandler(requests.RequestException)
    def backend_unavailable(error):
        # Rendered rather than redirected, deliberately. `mcrit_server_required`
        # flashes and redirects to the index, which works because it runs *before* a
        # view and only when its own probe already failed. Doing that here would
        # loop: index() calls getFamily, getSampleById, getQueueData and
        # search_samples itself, so a backend that fails one of those fails the
        # redirect target too, forever. Rendering also keeps the URL the user was on
        # and lets the response carry a status that means what happened.
        current_app.logger.warning("MCRIT backend call failed: %r", error)
        return render_template("backend_unavailable.html", reason=message_for(error)), 503

    if McritClientError is not None:
        # the mcrit half of #43: with `raise_server_errors` the client raises where the
        # server reported a failure of its own, so that case no longer arrives as None
        @app.errorhandler(McritServerError)
        def backend_failed(error):
            current_app.logger.warning("MCRIT backend failed a request: %s", error)
            if wants_a_status_code():
                # unreachable through views/api.py, which uses raw responses, but a
                # future API route on a parsing client should still answer as a gateway
                return Response(status=502)
            return render_template("backend_server_error.html", status_code=error.status_code, message=error.message), 502

        @app.errorhandler(McritRequestError)
        def backend_refused(error):
            # not raised by mcritweb's own clients (they leave `raise_client_errors` off,
            # so a refused request answers None and the view decides); kept so a client
            # built with it never surfaces as a stack trace
            current_app.logger.info("MCRIT backend refused a request: %s", error)
            status = 404 if isinstance(error, (McritNotFound, McritGone)) else 400
            if wants_a_status_code():
                return Response(status=status)
            return render_template("backend_no_result.html", what=f"the requested data ({error.message or 'no detail'})", refusal_only=True), status

    @app.errorhandler(NoResultFromBackend)
    def backend_returned_nothing(error):
        # Rendered in place for the same reason as above. No handler on the api
        # blueprint to match: every route there builds its client with
        # raw_responses=True and forwards the status it got, so nothing under /api/
        # produces a None to check. A test pins that, so the day it stops being true
        # is a test failure rather than an unhandled exception.
        current_app.logger.warning("MCRIT backend returned no %s", error.what)
        # with a client that raises server failures, a None can only mean the request
        # was refused or named something that is not there - and the page says so
        from mcritweb.views.client import CLIENT_RAISES_SERVER_ERRORS

        status = 404 if CLIENT_RAISES_SERVER_ERRORS else 502
        return render_template("backend_no_result.html", what=error.what, refusal_only=CLIENT_RAISES_SERVER_ERRORS), status
