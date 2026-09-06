#!/usr/bin/python
"""The search-backed pages, rendered against results that actually contain rows.

Until now the fake answered every search with an empty result set. Every page that
embeds a search returned 200, and none of them proved anything: an empty list
renders as an empty table whatever the row markup does with an entry. That is the
gap issue #88 left open, and closing it is what these tests are for.

`fixtureData._page` models the cursor protocol - opaque token, a forward cursor only
while results remain, a backward one only off the first page - so the paging links
can be followed rather than merely rendered.

The corpus holds 5 families, 13 samples and 609 functions, which is enough for a
second page at a limit of 10.
"""

import logging
import re
import unittest

import pytest

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

#: (path, the id of a row that must appear). Ids are rendered as links, so their
#: presence is evidence the row macro ran over a real entry.
LISTING_PAGES = [
    ("/explore/families", "/explore/families/"),
    ("/explore/samples", "/explore/samples/"),
    ("/explore/functions", "/explore/functions/"),
]


@pytest.fixture
def fake_mcrit(corpus_mcrit):
    return corpus_mcrit


def row_ids(response, pattern):
    return sorted(set(re.findall(pattern, response.get_data(as_text=True))))


# --- the listings render rows ----------------------------------------------------

def test_the_family_listing_renders_the_families(client, as_role, fake_mcrit):
    as_role("visitor")
    page = client.get("/explore/families").get_data(as_text=True)

    for family in fake_mcrit._families.values():
        assert family.family_name in page, f"{family.family_name} is missing from the listing"


def test_the_sample_listing_renders_the_samples(client, as_role, fake_mcrit):
    """Rows are identified by their id link - the filename column is shortened for
    display, so asserting on the whole filename would be asserting on the CSS."""
    as_role("visitor")
    response = client.get("/explore/samples?page=1&limit=25")

    rendered = set(row_ids(response, r"/explore/samples/(\d+)"))
    assert rendered == {str(sample_id) for sample_id in fake_mcrit._samples}


def test_the_function_listing_renders_rows(client, as_role):
    """Function rows link by pichash rather than by function id, so that is what
    proves the row macro ran over real entries."""
    as_role("visitor")
    response = client.get("/explore/functions?page=1&limit=10")

    assert response.status_code == 200
    assert len(row_ids(response, r"query=pichash:(0x[0-9a-f]+)")) >= 5


@pytest.mark.parametrize("path, _marker", LISTING_PAGES)
def test_a_query_that_matches_nothing_still_renders(client, as_role, path, _marker):
    as_role("visitor")
    assert client.get(f"{path}?query=nothingmatchesthis").status_code == 200


# --- paging ----------------------------------------------------------------------

def test_the_sample_listing_pages_forward_to_different_rows(client, as_role):
    """Two pages of ten over thirteen samples. If the cursor were ignored, the
    second page would repeat the first."""
    as_role("visitor")
    first = client.get("/explore/samples?page=1&limit=10")
    second = client.get(follow_cursor(first, "/explore/samples"))

    first_ids = row_ids(first, r"/explore/samples/(\d+)")
    second_ids = row_ids(second, r"/explore/samples/(\d+)")
    assert first_ids and second_ids
    assert not set(first_ids) & set(second_ids), "the second page repeated rows from the first"


def test_paging_forward_then_back_returns_the_first_page(client, as_role):
    as_role("visitor")
    first = client.get("/explore/samples?page=1&limit=10")
    second = client.get(follow_cursor(first, "/explore/samples"))
    back = client.get(follow_cursor(second, "/explore/samples", backward=True))

    assert row_ids(back, r"/explore/samples/(\d+)") == row_ids(first, r"/explore/samples/(\d+)")


def follow_cursor(response, path, backward=False):
    """The next- or previous-page URL the pagination macro rendered."""
    page = response.get_data(as_text=True)
    links = re.findall(rf'href="({re.escape(path)}\?[^"]*cursor=[^"]*)"', page)
    links = [link.replace("&amp;", "&") for link in links]
    wanted = [link for link in links if ("b%3A" in link or "b:" in link) == backward]
    assert wanted, f"no {'backward' if backward else 'forward'} paging link on {path}"
    return wanted[0]


# --- the combined search page ----------------------------------------------------

def test_the_search_page_renders_a_sample_hit(client, as_role, fake_mcrit):
    """This was a 500. `search()` iterated `results['search_results'].values()` and
    read `.sample_id` off each one, but those are dicts off the wire - the very next
    line calls `SampleEntry.fromDict` on the same value. Any query that matched a
    sample took the page down, which the empty-result fake could never show."""
    as_role("visitor")
    sample = next(iter(fake_mcrit._samples.values()))
    response = client.get(f"/explore/search?query={sample.filename}")

    assert response.status_code == 200
    assert str(sample.sample_id) in row_ids(response, r"/explore/samples/(\d+)")


def test_the_search_page_renders_an_id_match(client, as_role, fake_mcrit):
    """The id_match branch had the same defect one line earlier."""
    as_role("visitor")
    sample = next(iter(fake_mcrit._samples.values()))
    response = client.get(f"/explore/search?query={sample.sample_id}")

    assert response.status_code == 200
    assert str(sample.sample_id) in row_ids(response, r"/explore/samples/(\d+)")


def test_the_search_page_renders_a_sha256_match(client, as_role, fake_mcrit):
    """A sha256 is unique, so this one names exactly the sample it should."""
    as_role("visitor")
    sample = next(iter(fake_mcrit._samples.values()))
    response = client.get(f"/explore/search?query={sample.sha256}")

    assert response.status_code == 200
    assert row_ids(response, r"/explore/samples/(\d+)") == [str(sample.sample_id)]


def test_the_search_page_renders_a_family_hit(client, as_role, fake_mcrit):
    as_role("visitor")
    family = next(iter(fake_mcrit._families.values()))
    response = client.get(f"/explore/search?query={family.family_name}&type=family")

    assert response.status_code == 200
    assert family.family_name in response.get_data(as_text=True)


@pytest.mark.parametrize("types", ["family", "sample", "function", "family,sample,function"])
def test_the_search_page_renders_for_every_type_selection(client, as_role, fake_mcrit, types):
    as_role("visitor")
    sample = next(iter(fake_mcrit._samples.values()))
    assert client.get(f"/explore/search?query={sample.filename}&type={types}").status_code == 200


# --- the analyze pages, which share one search-result reader ---------------------

#: (path, the query parameter that reaches `get_unique_samples_from_search_result`)
ANALYZE_PAGES = [
    ("/analyze/compare", "query"),
    ("/analyze/cross_compare", "query"),
    ("/analyze/compare_versus", "query_a"),
]


@pytest.mark.parametrize("path, query_param", ANALYZE_PAGES)
def test_the_analyze_pages_render_entries_rather_than_wire_dicts(client, as_role, fake_mcrit, path, query_param):
    """All three read their sample list through the same helper, and nothing pinned
    what it hands the row macro - the route matrix asserts these pages answer 200, but
    it does not distinguish a page of rows from the "no samples available" placeholder.

    The evidence is the short sha column: `getShortSha256` is a method on `SampleEntry`
    with no key of that name in the wire dict, so a raw dict renders as an
    `UndefinedError` rather than as a slightly wrong cell. Issue #64.
    """
    as_role("visitor")
    sample = next(iter(fake_mcrit._samples.values()))

    response = client.get(f"{path}?{query_param}={sample.sample_id}")

    assert response.status_code == 200
    assert sample.getShortSha256() in response.get_data(as_text=True)


# --- the fake's own contract -----------------------------------------------------

def test_the_forward_cursor_is_absent_on_the_last_page(corpus_mcrit):
    assert corpus_mcrit.search_samples("", limit=100)["cursor"]["forward"] is None


def test_the_backward_cursor_is_absent_on_the_first_page(corpus_mcrit):
    assert corpus_mcrit.search_samples("", limit=10)["cursor"]["backward"] is None


def test_a_forward_cursor_yields_the_next_slice(corpus_mcrit):
    first = corpus_mcrit.search_samples("", limit=10)
    second = corpus_mcrit.search_samples("", cursor=first["cursor"]["forward"], limit=10)

    assert not set(first["search_results"]) & set(second["search_results"])
    assert second["cursor"]["backward"] is not None


def test_a_backward_cursor_returns_the_previous_slice(corpus_mcrit):
    first = corpus_mcrit.search_samples("", limit=10)
    second = corpus_mcrit.search_samples("", cursor=first["cursor"]["forward"], limit=10)
    back = corpus_mcrit.search_samples("", cursor=second["cursor"]["backward"], limit=10)

    assert list(back["search_results"]) == list(first["search_results"])


def test_search_results_are_dicts_not_entries(corpus_mcrit):
    """The views call `.fromDict` on every value. Handing back entry objects here
    would let code that forgot to do that pass, which is exactly the bug this
    module's search-page tests exist to catch."""
    results = corpus_mcrit.search_samples("", limit=1)["search_results"]

    assert all(isinstance(value, dict) for value in results.values())


def test_descending_order_reverses_the_page(corpus_mcrit):
    ascending = corpus_mcrit.search_samples("", limit=100, is_ascending=True)
    descending = corpus_mcrit.search_samples("", limit=100, is_ascending=False)

    assert list(descending["search_results"]) == list(reversed(list(ascending["search_results"])))


if __name__ == "__main__":
    unittest.main()
