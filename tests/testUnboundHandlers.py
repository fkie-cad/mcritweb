"""Fallback request paths must keep their required values in scope."""

from types import SimpleNamespace

import pytest
from fixtureData import RawResponse


@pytest.fixture
def fake_mcrit(recording_mcrit):
    return recording_mcrit


@pytest.mark.parametrize(
    ("body", "expected_ids", "backend_status"),
    [(b"not ids", [], 400), (b"1, 2", [1, 2], 200)],
)
def test_functions_post_forwards_label_flag_on_both_paths(
        client, make_user, fake_mcrit, body, expected_ids, backend_status):
    make_user("visitor")

    def get_functions_by_ids(ids, **kwargs):
        fake_mcrit._record("getFunctionsByIds", ids, **kwargs)
        return RawResponse(backend_status, {})

    fake_mcrit.getFunctionsByIds = get_functions_by_ids

    response = client.post(
        "/api/functions?with_label_only=true",
        headers={"apitoken": "apitoken-visitor"},
        data=body,
    )

    assert response.status_code == backend_status
    assert [call for call in fake_mcrit.calls if call[0] == "getFunctionsByIds"] == [
        ("getFunctionsByIds", (expected_ids,), {"with_label_only": True})
    ]


def test_hash_list_redirect_does_not_search_the_whole_corpus(client, as_role, fake_mcrit):
    as_role("visitor")
    sample_hash = "a" * 64
    fake_mcrit.getSampleBySha256 = lambda value: SimpleNamespace(sample_id=7) if value == sample_hash else None
    fake_mcrit.search_samples = lambda *args, **kwargs: pytest.fail("unneeded sample search")

    response = client.post("/analyze/cross_compare_from_hash_list", data={"hashlist": sample_hash})

    assert response.status_code == 302
    assert "/analyze/cross_compare" in response.headers["Location"]
    assert "samples=7" in response.headers["Location"]
