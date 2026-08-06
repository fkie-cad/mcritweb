#!/usr/bin/python
"""The analyze routes queue work on GET, and repeating one costs nothing - #97.

Five routes in the analyze blueprint queue a backend job on a plain GET. That shape
is deliberate: the URL names a comparison, so it is worth bookmarking and sharing,
and converting it to POST would give that up for a route that destroys nothing.

What makes it safe is that the backend already deduplicates. `QueueRemoteCalls`
hashes the method name and its parameters into a descriptor and returns the job it
already has, unless the caller asked for a recalculation. A crawler, a prefetch or
a double-click therefore costs one lookup, not one job.

That only holds while `force_recalculation` reaches the backend as a real bool.
These routes forwarded the raw query string, and the checkbox in compare.html,
compare_versus.html and cross_compare.html submits `rematch=false` when it is
unticked - a non-empty string, so truthy. Every visit therefore forced a fresh job
and the deduplication never got a chance. `sample_group_only` had the same problem
with a worse consequence: it is not a caching hint but a choice of which comparison
to run, so an unticked box silently ran group-only matching.

These tests assert on what reaches the client, since the flag's whole job is to be
passed through correctly.
"""

import logging
import unittest

import pytest

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

JOB_ID = "0123456789abcdef01234567"

#: (route, the client method it queues through)
SUBMITTERS = [
    ("/analyze/compare/1", "requestMatchesForSample"),
    ("/analyze/compare/1/2", "requestMatchesForSampleVs"),
    ("/analyze/start_cross_compare?samples=1,2", "requestMatchesCross"),
]


@pytest.fixture
def fake_mcrit(recording_mcrit):
    """The permissive fake answers None to everything, which is not a job id the
    redirect can be built from. Answer a plausible one for the queueing calls."""
    for method in ("requestMatchesForSample", "requestMatchesForSampleVs", "requestMatchesCross",
                   "requestUniqueBlocksForFamily", "requestUniqueBlocksForSamples"):
        def _queue(*args, _method=method, **kwargs):
            recording_mcrit._record(_method, *args, **kwargs)
            return JOB_ID
        setattr(recording_mcrit, method, _queue)
    recording_mcrit.getSamplesByFamilyId = lambda *args, **kwargs: [object()]
    return recording_mcrit


def call_to(fake, method):
    return next(call for call in fake.calls if call[0] == method)


@pytest.mark.parametrize("path, method", SUBMITTERS)
def test_an_unticked_rematch_box_does_not_force_a_recalculation(client, as_role, fake_mcrit, path, method):
    """`rematch=false` is the string "false", which is truthy. Forwarding it raw
    forced a fresh job on every visit and defeated the backend's deduplication."""
    as_role("visitor")
    separator = "&" if "?" in path else "?"
    client.get(f"{path}{separator}rematch=false")

    _, _, kwargs = call_to(fake_mcrit, method)
    assert kwargs["force_recalculation"] is False


@pytest.mark.parametrize("path, method", SUBMITTERS)
def test_no_rematch_parameter_does_not_force_a_recalculation(client, as_role, fake_mcrit, path, method):
    as_role("visitor")
    client.get(path)

    _, _, kwargs = call_to(fake_mcrit, method)
    assert kwargs["force_recalculation"] is False


@pytest.mark.parametrize("path, method", SUBMITTERS)
def test_a_ticked_rematch_box_still_forces_a_recalculation(client, as_role, fake_mcrit, path, method):
    """The opt-out has to keep working - it is the only way to redo a comparison."""
    as_role("visitor")
    separator = "&" if "?" in path else "?"
    client.get(f"{path}{separator}rematch=true")

    _, _, kwargs = call_to(fake_mcrit, method)
    assert kwargs["force_recalculation"] is True


@pytest.mark.parametrize("value, expected", [("false", False), ("true", True), (None, False)])
def test_cross_compare_group_only_is_a_real_boolean(client, as_role, fake_mcrit, value, expected):
    """Not a caching hint: sample_group_only picks which comparison runs, so the
    truthy "false" ran group-only matching for someone who had unticked the box."""
    as_role("visitor")
    query = "" if value is None else f"&onlySelected={value}"
    client.get(f"/analyze/start_cross_compare?samples=1,2{query}")

    _, _, kwargs = call_to(fake_mcrit, "requestMatchesCross")
    assert kwargs["sample_group_only"] is expected


@pytest.mark.parametrize("path", ["/analyze/blocks/family/1", "/analyze/blocks/sample/1"])
def test_the_unique_blocks_routes_never_force_a_recalculation(client, as_role, fake_mcrit, path):
    """These take no rematch parameter at all, so the backend's deduplication has
    always applied to them. Pinned so that adding one later is a deliberate act."""
    as_role("visitor")
    response = client.get(path)

    assert response.status_code == 302
    queued = [call for call in fake_mcrit.calls if call[0].startswith("requestUniqueBlocks")]
    assert queued, "no unique-blocks job was queued"
    assert "force_recalculation" not in queued[0][2]


@pytest.mark.parametrize("path, method", SUBMITTERS)
def test_a_repeated_get_queues_through_the_same_parameters(client, as_role, fake_mcrit, path, method):
    """The web layer does not deduplicate and should not: the backend does it by
    descriptor. What this side has to guarantee is that two identical requests
    produce two identical calls, so that the descriptor matches and the second one
    is answered from the cache."""
    as_role("visitor")
    client.get(path)
    client.get(path)

    calls = [call for call in fake_mcrit.calls if call[0] == method]
    assert len(calls) == 2
    assert calls[0] == calls[1], "the same URL reached the backend as two different requests"


if __name__ == "__main__":
    unittest.main()
