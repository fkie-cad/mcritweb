#!/usr/bin/python
"""How often a page asks the backend for one sample or family entry. Issue #191.

mcrit has no batched sample lookup, so each entry a page names costs a `getSampleById`
(or `getFamily`) round trip, one after the other. Several pages paid for the same one
twice: the sample page fetched its own sample again for the job table, the selection
pages fetched samples the search table beside them had just delivered, and the index
fetched samples its "latest samples" list had just delivered. `client.get_sample_entries`
and `get_family_entries` keep what a request has fetched, so each id costs at most one
lookup, and `remember_samples` hands them what the page already holds.

The call counts here are paired with assertions on what the pages still show: a lookup
that stops happening is only a fix while the entry it fed is still rendered.
"""

import copy
import json
import logging
from collections import Counter

import pytest
from fixtureData import job_id_of, load
from mcrit.queue.LocalQueue import Job

import mcritweb.views.data as data_views
from mcritweb.views.client import get_family_entries, get_sample_entries, remember_samples

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


@pytest.fixture
def fake_mcrit(corpus_mcrit):
    return corpus_mcrit


def lookups(fake_mcrit, name="getSampleById"):
    """id -> how often the request asked for it."""
    return Counter(args[0] for called, args, kwargs in fake_mcrit.calls if called == name)


# --- the helper -----------------------------------------------------------------


def test_each_id_is_asked_for_once_per_request(app, fake_mcrit):
    with app.test_request_context():
        first = get_sample_entries([3, 5, 3])
        second = get_sample_entries([5, 7])

    assert lookups(fake_mcrit) == {3: 1, 5: 1, 7: 1}
    assert list(first) == [3, 5] and first[3].sample_id == 3
    assert second[5] is first[5]


def test_an_id_the_backend_does_not_have_is_answered_none_and_asked_for_once(app, fake_mcrit):
    with app.test_request_context():
        assert get_sample_entries([99, 99]) == {99: None}
        assert get_sample_entries([99]) == {99: None}

    assert lookups(fake_mcrit) == {99: 1}


def test_a_remembered_sample_is_not_asked_for(app, fake_mcrit):
    with app.test_request_context():
        known = fake_mcrit._samples[4]
        remember_samples([known])
        assert get_sample_entries([4]) == {4: known}

    assert lookups(fake_mcrit) == {}


def test_families_are_asked_for_once_per_request(app, fake_mcrit):
    with app.test_request_context():
        families = get_family_entries([1, 1, 2])

    assert lookups(fake_mcrit, "getFamily") == {1: 1, 2: 1}
    assert families[1].family_id == 1


def test_nothing_is_kept_beyond_the_request(app, fake_mcrit):
    with app.test_request_context():
        get_sample_entries([3])
    with app.test_request_context():
        get_sample_entries([3])

    assert lookups(fake_mcrit) == {3: 2}


# --- the pages ------------------------------------------------------------------


def test_the_sample_page_does_not_fetch_its_own_sample_again(client, as_role, fake_mcrit):
    """Every job the page lists names the page's sample - that is the filter."""
    as_role("visitor")
    response = client.get("/explore/samples/0")

    assert response.status_code == 200
    asked = lookups(fake_mcrit)
    assert asked[0] == 1, "the page's own sample was fetched again for its job table"
    # the other samples its jobs in the captured queue name: the unique blocks job over
    # 0, 1 and 2 - each asked for once
    assert asked == {0: 1, 1: 1, 2: 1}


@pytest.mark.parametrize("path", ["/analyze/cross_compare", "/analyze/unique_blocks"])
def test_a_selection_listed_in_the_search_table_is_not_looked_up_again(client, as_role, fake_mcrit, path):
    as_role("visitor")
    response = client.get(f"{path}?samples=0,1,2")

    assert response.status_code == 200
    assert lookups(fake_mcrit) == {}, "the search on the same page already delivered these"
    body = response.get_data(as_text=True)
    for sample_id in (0, 1, 2):
        assert fake_mcrit._samples[sample_id].sha256[:8] in body


@pytest.mark.parametrize("path", ["/analyze/cross_compare", "/analyze/unique_blocks"])
def test_a_selection_off_the_search_page_is_looked_up_once_and_shown(client, as_role, fake_mcrit, path):
    """The search shows ten rows, sample_id ascending, so 11 is not among them."""
    as_role("visitor")
    response = client.get(f"{path}?samples=0,11")

    assert response.status_code == 200
    assert lookups(fake_mcrit) == {11: 1}
    assert fake_mcrit._samples[11].sha256[:8] in response.get_data(as_text=True)


def test_an_unknown_selection_is_dropped_from_a_cross_compare_after_one_lookup(client, as_role, fake_mcrit):
    as_role("visitor")
    response = client.get("/analyze/cross_compare?samples=0,99")

    assert response.status_code == 302
    assert "samples=0&" in response.headers["Location"]
    assert lookups(fake_mcrit) == {99: 1}


def flashes(client):
    """(category, message) for everything flashed and not yet rendered."""
    with client.session_transaction() as session:
        return list(session.get("_flashes", []))


def failing_search(*args, **kwargs):
    return None


def test_a_failed_search_still_resolves_the_selection_in_order(client, as_role, fake_mcrit, monkeypatch):
    """The search now runs before the selection is looked up. When it fails there is
    nothing to take the selection from, so every selected sample is looked up, and the
    messages come in the order they did before: the unconfirmed sample, then the search."""
    monkeypatch.setattr(fake_mcrit, "search_samples", failing_search, raising=False)
    as_role("visitor")
    response = client.get("/analyze/unique_blocks?samples=0,99")

    assert response.status_code == 200
    assert lookups(fake_mcrit) == {0: 1, 99: 1}
    body = response.get_data(as_text=True)
    assert fake_mcrit._samples[0].sha256[:8] in body
    unconfirmed = body.index("MCRIT did not confirm sample id 99")
    search_failed = body.index("search for  in MCRIT&#39;s samples failed")
    assert unconfirmed < search_failed


def test_a_failed_search_does_not_add_a_message_to_the_unknown_id_redirect(client, as_role, fake_mcrit, monkeypatch):
    """cross_compare redirects away from an unknown id before it reports the search,
    as it did when the search ran after the lookup - the page it redirects to searches
    again and reports its own outcome."""
    monkeypatch.setattr(fake_mcrit, "search_samples", failing_search, raising=False)
    as_role("visitor")
    response = client.get("/analyze/cross_compare?samples=0,99")

    assert response.status_code == 302
    assert flashes(client) == [("warning", "Sample with Id 99 does not exist and was ignored")]


def test_a_deleted_sample_still_marks_a_cross_compare_corrupted(client, as_role, fake_mcrit, monkeypatch):
    """The cross result now looks up its whole sequence at once, through the helper;
    a sample that is gone still makes the report unrenderable rather than short."""
    ask = fake_mcrit.getSampleById

    def without_sample_4(sample_id, *args, **kwargs):
        entry = ask(sample_id, *args, **kwargs)
        return None if int(sample_id) == 4 else entry

    monkeypatch.setattr(fake_mcrit, "getSampleById", without_sample_4, raising=False)
    as_role("visitor")
    response = client.get(f"/data/result/{job_id_of('cross_compare')}")

    assert response.status_code == 200
    assert "not able to retrieve information for all samples" in response.get_data(as_text=True)
    assert set(lookups(fake_mcrit).values()) == {1}, "a sample of the sequence was asked for twice"


def test_the_job_page_resolves_its_samples_through_the_request_lookup(client, as_role, fake_mcrit, monkeypatch):
    """Two sub-jobs naming one sample cost one lookup, and a sample the request already
    knows costs none - the latter is what going through the helper adds."""
    parent_document = copy.deepcopy(load("cross_compare.job"))
    parent_document["all_dependencies"] = ["a" * 24, "b" * 24, "c" * 24]
    children = {
        "a" * 24: matching_job(3, 40),
        "b" * 24: matching_job(3, 41),
        "c" * 24: matching_job(5, 42),
    }
    parent = Job(parent_document, None)
    monkeypatch.setattr(fake_mcrit, "getJobData", lambda job_id, *args, **kwargs: parent if job_id == "parent" else children.get(job_id), raising=False)
    helper = data_views.get_sample_entries

    def remembering_first(sample_ids):
        remember_samples([fake_mcrit._samples[5]])
        return helper(sample_ids)

    monkeypatch.setattr(data_views, "get_sample_entries", remembering_first)
    as_role("visitor")
    response = client.get("/data/jobs/parent")

    assert response.status_code == 200
    assert lookups(fake_mcrit) == {3: 1}
    body = response.get_data(as_text=True)
    for sample_id in (3, 5):
        assert fake_mcrit._samples[sample_id].sha256[:8] in body


def matching_job(sample_id, number):
    """A finished 1vN job for `sample_id`, in the captured queue's own shape."""
    document = copy.deepcopy(next(entry for entry in load("queue") if entry["payload"]["method"] == "getMatchesForSample"))
    document["_id"] = {"$oid": f"{number:024x}"}
    document["number"] = number
    document["payload"]["params"] = json.dumps({"band_matches_required": 2, "0": sample_id})
    return Job(document, None)


def test_the_index_asks_for_each_matched_sample_once(client, as_role, fake_mcrit, monkeypatch):
    """Two recent jobs for sample 3 and one for sample 12, which is also among the five
    latest samples the index lists anyway."""
    jobs = [matching_job(3, 30), matching_job(12, 31), matching_job(3, 32)]
    monkeypatch.setattr(fake_mcrit, "getQueueData", lambda *args, **kwargs: jobs, raising=False)
    as_role("visitor")
    response = client.get("/")

    assert response.status_code == 200
    assert lookups(fake_mcrit) == {3: 1}, "a latest sample was fetched again, or one sample twice"
    body = response.get_data(as_text=True)
    for sample_id in (3, 12):
        assert fake_mcrit._samples[sample_id].sha256[:8] in body
