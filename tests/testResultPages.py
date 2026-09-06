#!/usr/bin/python
"""Renders every result type against real reports from tests/fixtures/.

Until now nothing here rendered a result page: the strict fake answers with empty
shapes, which proves a route is reachable and nothing about whether the template can
survive the data. These tests run the real dispatch in `data.result()` over captured
reports, so a template that dereferences a field the backend stopped sending, or a
renderer that miscounts a filtered report, fails here rather than in a browser.

The reports come from a live instance - see tests/fixtures/regenerate.py.
"""

import logging
import re
import unittest

import pytest
from fixtureData import job_id_of

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


@pytest.fixture
def fake_mcrit(corpus_mcrit):
    """Wire the app in this module to the captured corpus (see conftest)."""
    return corpus_mcrit


@pytest.mark.parametrize(
    "report",
    ["matches_for_sample", "matches_for_sample_vs", "matches_for_query", "cross_compare", "unique_blocks"],
)
def test_result_page_renders(client, as_role, report):
    as_role("visitor")
    response = client.get(f"/data/result/{job_id_of(report)}")
    assert response.status_code == 200, f"{report} did not render"
    # the h1 of result_corrupted.html - the template's *name* appears nowhere in the
    # rendered page, so asserting on that passed whatever the page actually said
    assert b"are corrupted" not in response.data


@pytest.mark.parametrize("report", ["matches_for_sample", "matches_for_sample_vs", "matches_for_query"])
def test_linkhunt_renders_for_every_matching_report(client, as_role, report):
    as_role("visitor")
    response = client.get(f"/data/linkhunt/{job_id_of(report)}")
    assert response.status_code == 200


def test_result_page_applies_a_score_filter(client, as_role):
    """The filter parameters drive MatchingResult.applyFilterValues, which is where a
    report gets narrowed - rendering it unfiltered proves much less."""
    as_role("visitor")
    unfiltered = client.get(f"/data/result/{job_id_of('matches_for_sample')}")
    filtered = client.get(f"/data/result/{job_id_of('matches_for_sample')}?filter_direct_min_score=99")

    assert unfiltered.status_code == 200
    assert filtered.status_code == 200
    assert filtered.data != unfiltered.data


def test_unique_blocks_page_paginates(client, as_role):
    as_role("visitor")
    first = client.get(f"/data/result/{job_id_of('unique_blocks')}")
    second = client.get(f"/data/result/{job_id_of('unique_blocks')}?blkp=2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.data != second.data


def test_a_job_id_nobody_knows_is_reported_not_crashed(client, as_role):
    as_role("visitor")
    response = client.get("/data/result/ffffffffffffffffffffffff")
    assert response.status_code == 200
    assert b"was not found in the system" in response.data


def test_job_page_renders_for_a_finished_job(client, as_role):
    as_role("visitor")
    response = client.get(f"/data/jobs/{job_id_of('matches_for_sample')}")
    assert response.status_code == 200


# --- #42: ordering of the cross compare matrix ------------------------------------
#
# The five corpus samples of the captured cross compare, and what each ordering has
# to produce out of them:
#
#   id  family       version
#    0  win.citadel  1.3.5.1
#    1  win.citadel  1.3.4.0
#    2  win.citadel  0.0.1.1
#    4  win.vmzeus   3.x
#    6  win.dridex   (none)

#: What the backend clustered, i.e. the order the page shows when nothing is asked for.
CLUSTERED_ORDER = ["6", "4", "2", "0", "1"]
SAMPLE_ID_ORDER = ["0", "1", "2", "4", "6"]
FAMILY_ORDER = ["2", "1", "0", "6", "4"]

#: Every matrix on the page. The order is applied to all of them identically - it is
#: one global order, not a per-tab one - so a test that only looked at the active tab
#: would miss five sixths of the change.
CROSS_METHODS = {
    "unweighted",
    "score_weighted",
    "frequency_weighted",
    "nonlib_unweighted",
    "nonlib_score_weighted",
    "nonlib_frequency_weighted",
}


def cross_compare_page(client, query=""):
    response = client.get(f"/data/result/{job_id_of('cross_compare')}{query}")
    assert response.status_code == 200
    return response.data.decode()


def sortable_order(html):
    """Sample ids of the drag-and-drop list, which has to mirror what is on screen -
    otherwise a drag starts from an order the user is not looking at."""
    block = re.search(r'id="sortable">(.*?)</ul>', html, re.S)
    assert block is not None, "the cross compare page has no drag-and-drop list"
    return [item.split()[0] for item in re.findall(r"<li>(.*?)</li>", block.group(1), re.S)]


def matrix_orders(html):
    """method -> the sample id order of that matrix's rows."""
    panes = re.finditer(r'id="pills-(\w+)" role="tabpanel"(.*?)(?=<div class="tab-pane|\Z)', html, re.S)
    return {
        pane.group(1): re.findall(r'<td class="id clickable"[^>]*>\s*(\d+)\s*</td>', pane.group(2))
        for pane in panes
    }


def active_ordering_button(html):
    """Which of the three ordering buttons is rendered as pressed, by the order its own
    onclick asks for. `None` when none is - which is what a drag order looks like."""
    pressed = re.findall(r"<button onclick=\"[^\"]*[?&;]order=(\w+)[^\"]*\"[^>]*aria-pressed=\"true\"", html)
    assert len(pressed) <= 1, f"more than one ordering button is pressed: {pressed}"
    return pressed[0] if pressed else None


def assert_page_is_ordered(html, expected):
    assert sortable_order(html) == expected
    orders = matrix_orders(html)
    assert set(orders) == CROSS_METHODS, "not every matrix was found on the page"
    for method, order in orders.items():
        assert order == expected, f"matrix {method} is not in the requested order"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", CLUSTERED_ORDER),
        ("?order=clustered", CLUSTERED_ORDER),
        ("?order=sample_id", SAMPLE_ID_ORDER),
        ("?order=family", FAMILY_ORDER),
    ],
)
def test_cross_compare_renders_in_the_requested_named_order(client, as_role, query, expected):
    as_role("visitor")
    assert_page_is_ordered(cross_compare_page(client, query), expected)


def test_the_reset_button_asks_for_the_page_without_an_order(client, as_role):
    """Issue #42 (a), which was already implemented: dropping the parameters is the
    reset, because the view falls back to the backend's clustered_sequence."""
    as_role("visitor")
    html = cross_compare_page(client)
    assert f"window.location.href='/data/result/{job_id_of('cross_compare')}'" in html
    assert_page_is_ordered(html, CLUSTERED_ORDER)


def test_the_named_orderings_are_offered_on_the_page(client, as_role):
    as_role("visitor")
    html = cross_compare_page(client)
    for ordering in ("clustered", "sample_id", "family"):
        assert f"/data/result/{job_id_of('cross_compare')}?order={ordering}" in html
    assert html.count('aria-pressed="true"') == 1, "exactly one ordering is the active one"


def test_a_dragged_order_marks_none_of_the_named_orderings_active(client, as_role):
    """A ?custom= order is none of them, and saying otherwise would tell the user the
    matrix is in an order it is not in."""
    as_role("visitor")
    assert 'aria-pressed="true"' not in cross_compare_page(client, "?custom=1,0,2,4,6")


@pytest.mark.parametrize(
    "value",
    ["", "bogus", "Family", "sample_id%20", "clustered%2Cfamily", "../../etc/passwd", "family%3Bdrop"],
)
def test_an_ordering_nobody_offers_falls_back_to_the_clustered_one(client, as_role, value):
    as_role("visitor")
    html = cross_compare_page(client, f"?order={value}")
    assert_page_is_ordered(html, CLUSTERED_ORDER)
    # the buttons have to agree with the matrix. Falling back silently and then
    # highlighting nothing would tell the user the page is in a drag order it is not in.
    assert active_ordering_button(html) == "clustered"


def test_the_ordering_parameter_never_reaches_the_page(client, as_role):
    """It is a query parameter that decides what a template renders, so the thing to
    check is that its raw value is not one of the things rendered."""
    as_role("visitor")
    response = client.get(
        f"/data/result/{job_id_of('cross_compare')}?order=%22%3E%3Cscript%3Ealert%281%29%3C/script%3E"
    )
    assert response.status_code == 200
    assert b"alert(1)" not in response.data
    assert b"alert%281%29" not in response.data


def test_a_custom_order_still_works(client, as_role):
    """Backward compatibility: ?custom= is what the drag-and-drop list produces and
    what any already-bookmarked link carries."""
    as_role("visitor")
    assert_page_is_ordered(cross_compare_page(client, "?custom=1,0,2,4,6"), ["1", "0", "2", "4", "6"])


def test_a_custom_order_wins_over_a_named_one(client, as_role):
    """A drag is the more specific statement of intent, and it is what `changeorder()`
    sends - it builds a ?custom= link and does not carry the ?order= over."""
    as_role("visitor")
    assert_page_is_ordered(
        cross_compare_page(client, "?order=family&custom=1,0,2,4,6"), ["1", "0", "2", "4", "6"]
    )


def test_a_custom_order_naming_a_sample_outside_the_job_says_which_job(client, as_role):
    """The corrupted page needs the job to offer its "delete job data" button; this
    path used to hand it the report instead, rendering "Results for Job:  " and a
    data-post of /data/jobs//delete."""
    as_role("visitor")
    response = client.get(f"/data/result/{job_id_of('cross_compare')}?custom=1,0,2,4,999")
    assert response.status_code == 200
    assert b"are corrupted" in response.data
    assert job_id_of("cross_compare").encode() in response.data


if __name__ == "__main__":
    unittest.main()
