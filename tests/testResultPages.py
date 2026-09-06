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
from fixtureData import CorpusMcritClient, job_id_of, load
from mcrit.storage.FunctionEntry import FunctionEntry
from mcrit.storage.MatchingResult import MatchingResult

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


# --- the sample-filtered function table ------------------------------------------
#
# `?samid=` narrows a matching report to one matched sample and lists the function
# matches against it. The widget under that table and the table itself have to be
# built from the same list, or the header lies and the tail of the list has no page
# that reaches it.

#: A function entry carrying nothing but its id and an offset, for ids the trimmed
#: corpus does not hold. Shaped for FunctionEntry.fromDict, which is strict about
#: which keys are present.
STAND_IN_FUNCTION_ENTRY = {
    "architecture": "intel",
    "binweight": 0.0,
    "family_id": 0,
    "function_name": "",
    "function_labels": [],
    "matches": {},
    "minhash": "",
    "minhash_shingle_composition": {},
    "num_blocks": 0,
    "num_instructions": 0,
    "offset": 0,
    "pichash": None,
    "picblockhashes": [],
    "sample_id": 0,
    "xcfg": None,
}


class CorpusWithEveryMatchedFunction(CorpusMcritClient):
    """The captured corpus, with the by-id function pool widened to answer any id.

    `tests/fixtures/regenerate.py` trims `functions_matched` to the ids the 1-vs-1
    page looks up and says in as many words that the filtered result views
    (`?famid=` / `?samid=` / `?funid=`) reach past that set. They do: `data.py`
    calls `assign_matched_offsets` on every filtered match, and a single id it
    cannot resolve makes the whole page render as `result_corrupted.html`. With the
    shipped pool that is every sample of every report but one, so there is no table
    left to count.

    A real backend answers every id it is asked for, so this one does too: the
    captured entry where the corpus has it, an offset-only stand-in where it does
    not. The offset is display-only on this page - the tests below count rows and
    never look inside one.
    """

    def getFunctionsByIds(self, function_ids, *args, **kwargs):
        entries = super().getFunctionsByIds(function_ids, *args, **kwargs)
        for function_id in function_ids:
            if int(function_id) not in entries:
                entries[int(function_id)] = FunctionEntry.fromDict(
                    dict(STAND_IN_FUNCTION_ENTRY, function_id=int(function_id))
                )
        return entries


@pytest.fixture
def widened_corpus_mcrit():
    return CorpusWithEveryMatchedFunction()


def matched_sample_ids(report):
    """Every sample a report matched, i.e. every `?samid=` its own page links to."""
    return [sample["sample_id"] for sample in load(f"{report}.result")["matches"]["samples"]]


def matched_family_ids(report):
    """Every family a report matched, i.e. every `?famid=` its own page links to."""
    return sorted({sample["family_id"] for sample in load(f"{report}.result")["matches"]["samples"]})


def report_totals(report):
    """A report's own function totals, in both units the result pages count in.

    Read off the untouched report rather than off a page, so the pages are being
    checked against the data and not against each other.
    """
    matching_result = MatchingResult.fromDict(load(f"{report}.result"))
    return {
        # every (function, matched function) pair the report holds
        "matches": matching_result.num_original_function_matches,
        # every function of the reference sample that matched anything at all
        "functions": len(matching_result.getAggregatedFunctionMatches(unfiltered=True)),
    }


def read_function_table(html):
    """What the function match table says about itself.

    (selection, first row shown, last row shown, filtered-out count, rows drawn) -
    the first four off the header line above the table, which is written from the
    Pagination object, and the last from the table body itself.
    """
    body = html.split('id="function-matches"', 1)[1]
    header = re.search(r"selection: (\d+), showing: (\d+) - (\d+) \(filtered: (-?\d+)\)", body)
    rows = re.search(r"<tbody>(.*?)</tbody>", body, re.S)
    assert header is not None and rows is not None, "the function match table did not render"
    return (*(int(group) for group in header.groups()), rows.group(1).count("<tr "))


@pytest.mark.parametrize("report", ["matches_for_sample", "matches_for_query", "matches_for_sample_vs"])
def test_sample_filtered_page_paginates_the_rows_it_shows(client, as_role, widened_corpus_mcrit, app, report):
    """`?samid=` must page over the list the table draws from.

    The header count, the per-page arithmetic and the rendered rows all come off one
    Pagination. Building it from a different list than the table iterates leaves the
    tail of that list on no page at all, and makes every "showing X - Y" wrong.

    Run over every matched sample of three captured reports, so one fixture whose two
    lists happen to be the same length cannot carry it.
    """
    # the rest of this module wants the corpus exactly as captured, so swap the backend
    # through the same seam conftest uses rather than overriding the fixture module-wide
    app.config["MCRIT_CLIENT_FACTORY"] = lambda **kwargs: widened_corpus_mcrit
    as_role("visitor")
    job_id = job_id_of(report)

    disagreements = []
    for sample_id in matched_sample_ids(report):
        # walk to the widget's own last page. The bound is a runaway guard, not an
        # expected exit - falling out of it means the count ran away from the rows,
        # which is the failure this test is here for, so it is an error and not a
        # quiet end to the loop
        for page in range(1, 51):
            response = client.get(f"/data/result/{job_id}?samid={sample_id}&funp={page}&funl=250")
            assert response.status_code == 200
            assert b"are corrupted" not in response.data, f"{report} samid={sample_id} did not render"
            count, first, last, _filtered, drawn = read_function_table(response.data.decode())
            if drawn != last - first + 1:
                disagreements.append(
                    f"{report} samid={sample_id} funp={page}: widget says {count} in total and "
                    f"{first}-{last} on this page ({last - first + 1} rows), table drew {drawn}"
                )
            if last >= count:
                break
        else:
            raise AssertionError(f"{report} samid={sample_id}: the widget never reached its last page")

    assert not disagreements, "pagination and table disagree:\n  " + "\n  ".join(disagreements)


#: Which of a report's totals each function match table is counted in. The `filtered:`
#: figure beside a table is the rest of the report, so it only means anything when it
#: is the table's own total minus the table's own selection - and a page that changes
#: what one of its rows is has to change its entry here with it.
FUNCTION_TABLE_UNIT = {
    # one row per matched function of the reference sample, aggregated over every
    # sample it matched
    "": "functions",
    "famid": "functions",
    # one row per function match: this table has an Offset B and a Function B, which
    # only an individual match has
    "samid": "matches",
}


@pytest.mark.parametrize("report", ["matches_for_sample", "matches_for_query"])
def test_the_filtered_figure_accounts_for_the_rest_of_the_report(client, as_role, widened_corpus_mcrit, app, report):
    """`selection` and `filtered` have to add up to the report, on every result page.

    Both are printed on one line as if they were two halves of one total, so they have
    to be counted the same way. Subtracting an aggregated selection from a raw match
    total is not a smaller number, it is a different question - it made the unfiltered
    page report a four-figure `filtered:` with no filter applied at all.
    """
    app.config["MCRIT_CLIENT_FACTORY"] = lambda **kwargs: widened_corpus_mcrit
    as_role("visitor")
    job_id = job_id_of(report)
    totals = report_totals(report)

    pages = [("", "")]
    pages += [(f"&famid={family_id}", "famid") for family_id in matched_family_ids(report)]
    pages += [(f"&samid={sample_id}", "samid") for sample_id in matched_sample_ids(report)]

    wrong = []
    for query, kind in pages:
        response = client.get(f"/data/result/{job_id}?funp=1{query}")
        assert response.status_code == 200
        assert b"are corrupted" not in response.data, f"{report} {query} did not render"
        selection, _first, _last, filtered, _drawn = read_function_table(response.data.decode())
        total = totals[FUNCTION_TABLE_UNIT[kind]]
        if selection + filtered != total:
            wrong.append(
                f"{report} {query or '(unfiltered)'}: selection {selection} + filtered {filtered} "
                f"= {selection + filtered}, report holds {total}"
            )

    assert not wrong, "the filtered figure does not account for the report:\n  " + "\n  ".join(wrong)


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
