"""Single construction point for the MCRIT backend client.

Views call get_client() rather than building a McritClient themselves. That gives
tests one place to substitute a fake backend - via the MCRIT_CLIENT_FACTORY config
key - instead of patching the McritClient name in every view module, and it
collapses the repeated per-view ServerInfo lookups into one instance per request.

See issue #88.
"""

from flask import current_app, g
from mcrit.client.McritClient import McritClient

from mcritweb.views.utility import get_server_token, get_server_url, get_username


def default_client_factory(username=None, **kwargs):
    """Build a client from the server settings stored in the local database."""
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


def get_sample_entries(sample_ids):
    """{sample_id: SampleEntry, or None if the backend answered none} for the distinct
    ids in `sample_ids`, asking the backend for each id at most once per request.

    mcrit's client and REST API have no batched sample lookup - `getSamples(start,
    limit)` pages through the collection by position rather than by id, and
    `search_samples` takes a query, not a list of ids - so every id not yet known is
    still one `getSampleById`. What this removes are the repeats: one sample named by
    several jobs on a page, or one the page already holds for another reason, which it
    hands over with `remember_samples`. See issue #191.
    """
    return _entries_by_id("samples", sample_ids, get_client().getSampleById)


def get_family_entries(family_ids):
    """`get_sample_entries` for families: one `getFamily` per id not yet known."""
    return _entries_by_id("families", family_ids, get_client().getFamily)


def remember_samples(sample_entries):
    """Make entries this request already fetched another way - the rows of a sample
    search, the sample a page is about - known to `get_sample_entries`."""
    known = _known_entries("samples")
    for sample_entry in sample_entries:
        known[sample_entry.sample_id] = sample_entry


def _known_entries(kind):
    # on `g`, like the client itself: a lookup lasts as long as the request that made it
    if "known_entries" not in g:
        g.known_entries = {"samples": {}, "families": {}}
    return g.known_entries[kind]


def _entries_by_id(kind, entry_ids, fetch):
    known = _known_entries(kind)
    entries = {}
    for entry_id in entry_ids:
        if entry_id not in known:
            known[entry_id] = fetch(entry_id)
        entries[entry_id] = known[entry_id]
    return entries
