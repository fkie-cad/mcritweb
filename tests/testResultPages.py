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


def test_the_match_diagram_is_cached_per_theme(app, client, as_role):
    """Diagrams are rendered once into instance/cache/diagrams and never invalidated,
    so the theme has to be part of the name (#70) - otherwise whichever palette
    reached a job first is the palette everyone gets for it, permanently."""
    from mcritweb.db import UserInfo

    user_id = as_role("visitor")
    job_id = job_id_of("matches_for_sample")

    light = client.get(f"/data/result/{job_id}").get_data(as_text=True)
    assert f"{job_id}.png" in light
    assert "-dark.png" not in light

    with app.app_context():
        user_info = UserInfo.fromDb(user_id=user_id)
        user_info.theme = "dark"
        user_info.saveToDb()

    dark = client.get(f"/data/result/{job_id}").get_data(as_text=True)
    assert f"{job_id}-dark.png" in dark
    # both are on disk, so switching back does not re-render or serve the other one
    assert client.get(f"/data/diagrams/{job_id}-dark.png").status_code == 200
    assert client.get(f"/data/diagrams/{job_id}.png").status_code == 200


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


if __name__ == "__main__":
    unittest.main()
