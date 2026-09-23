"""Single construction point for the MCRIT backend client.

Views call get_client() rather than building a McritClient themselves. That gives
tests one place to substitute a fake backend - via the MCRIT_CLIENT_FACTORY config
key - instead of patching the McritClient name in every view module, and it
collapses the repeated per-view ServerInfo lookups into one instance per request.

See issue #88.
"""

import inspect

from flask import current_app, g
from mcrit.client.McritClient import McritClient

from mcritweb.views.utility import get_server_token, get_server_url, get_username

#: Whether the installed mcrit's client can raise on a server-side failure instead of
#: answering None (mcrit's `raise_server_errors`, the mcrit half of issue #43). With it,
#: a None from the client means exactly "not found, gone or refused"; without it, None
#: still covers a crashed backend too, and backend_no_result.html says so.
CLIENT_RAISES_SERVER_ERRORS = "raise_server_errors" in inspect.signature(McritClient.__init__).parameters


def default_client_factory(username=None, **kwargs):
    """Build a client from the server settings stored in the local database.

    A server failure is raised as `McritServerError` where the installed mcrit
    supports it, so `backend_errors` can report it as what it is; a refused or unknown
    request keeps answering None, which every view already handles. Raw-response
    clients hand the response through untouched either way.
    """
    if CLIENT_RAISES_SERVER_ERRORS:
        kwargs.setdefault("raise_server_errors", True)
    return McritClient(
        mcrit_server=get_server_url(),
        apitoken=get_server_token(),
        username=get_username() if username is None else username,
        **kwargs
    )


def get_client(**kwargs):
    """Return the MCRIT client to use for this request.

    The no-argument case is cached on `g`, since every view on a page would
    otherwise re-read the server URL and token from SQLite. Callers passing kwargs
    (the API passthrough needs raw_responses=True, and supplies its own username
    resolved from request headers) always get a fresh instance, because those
    clients differ in behaviour and must not be shared.
    """
    factory = current_app.config.get("MCRIT_CLIENT_FACTORY", default_client_factory)
    if kwargs:
        return factory(**kwargs)
    if "mcrit_client" not in g:
        g.mcrit_client = factory()
    return g.mcrit_client
