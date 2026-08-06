"""Loads tests/fixtures/ and serves it as a backend.

This module is data plumbing, not tests. It is deliberately not named `test*.py` so
pytest does not collect it.

The fixtures are real reports from a live MCRIT instance - three malware families
across seven samples, plus six MSVC library samples, all dated pre-2015 - captured
by `tests/fixtures/regenerate.py`. They are the backend's wire format, so this
module deserializes them exactly the way `McritClient` does. If a shape here drifts
from the real client, the fixtures are still right and this file is wrong.

`CorpusMcritClient` inherits the strict fake's failure mode on purpose: a method
nobody has taught it still raises NotImplementedError naming itself, so the next gap
is a message rather than a silently empty page.
"""

import json
import pathlib

from mcrit.queue.LocalQueue import Job
from mcrit.storage.FamilyEntry import FamilyEntry
from mcrit.storage.FunctionEntry import FunctionEntry
from mcrit.storage.SampleEntry import SampleEntry

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# fixture name -> the job method it was produced by, for tests that want to say
# "the cross compare report" instead of carrying an instance-specific job id
REPORTS = (
    "matches_for_sample",
    "matches_for_sample_vs",
    "matches_for_query",
    "cross_compare",
    "unique_blocks",
)


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def job_id_of(report):
    """The job id a report fixture was captured under."""
    return load(f"{report}.job")["_id"]["$oid"]


class CorpusMcritClient:
    """Serves the captured corpus in the types the real client returns."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self._samples = {int(k): SampleEntry.fromDict(v) for k, v in load("samples").items()}
        self._families = {int(k): FamilyEntry.fromDict(v) for k, v in load("families").items()}
        # two pools: reference-sample functions keep their control flow graph, the
        # by-id lookup pool does not. See tests/fixtures/regenerate.py.
        self._functions_by_sample = {}
        for path in sorted(FIXTURES.glob("functions_reference_*.json")):
            sample_id = int(path.stem.rsplit("_", 1)[1])
            entries = {int(k): FunctionEntry.fromDict(v) for k, v in json.loads(path.read_text()).items()}
            self._functions_by_sample[sample_id] = entries
        self._functions = {fid: entry for pool in self._functions_by_sample.values() for fid, entry in pool.items()}
        self._functions.update({int(k): FunctionEntry.fromDict(v) for k, v in load("functions_matched").items()})
        self._jobs = {job_id_of(report): (load(f"{report}.job"), load(f"{report}.result")) for report in REPORTS}
        self._queue = load("queue")

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    # --- server ------------------------------------------------------------------

    def getStatus(self, *args, **kwargs):
        self._record("getStatus", *args, **kwargs)
        return load("status")["status"]

    def getVersion(self, *args, **kwargs):
        self._record("getVersion", *args, **kwargs)
        return load("version")["version"]

    # --- families ----------------------------------------------------------------

    def getFamilies(self, *args, **kwargs):
        self._record("getFamilies", *args, **kwargs)
        return self._families

    def getFamily(self, family_id, *args, **kwargs):
        self._record("getFamily", family_id, *args, **kwargs)
        return self._families.get(int(family_id))

    def isFamilyId(self, family_id, *args, **kwargs):
        self._record("isFamilyId", family_id, *args, **kwargs)
        return int(family_id) in self._families

    # --- samples -----------------------------------------------------------------

    def getSamples(self, *args, **kwargs):
        self._record("getSamples", *args, **kwargs)
        return self._samples

    def getSampleById(self, sample_id, *args, **kwargs):
        self._record("getSampleById", sample_id, *args, **kwargs)
        return self._samples.get(int(sample_id))

    def isSampleId(self, sample_id, *args, **kwargs):
        self._record("isSampleId", sample_id, *args, **kwargs)
        return int(sample_id) in self._samples

    def getSampleBySha256(self, sha256, *args, **kwargs):
        self._record("getSampleBySha256", sha256, *args, **kwargs)
        for sample in self._samples.values():
            if sample.sha256 == sha256:
                return sample
        return None

    # --- functions ---------------------------------------------------------------

    def getFunctionsBySampleId(self, sample_id, *args, **kwargs):
        self._record("getFunctionsBySampleId", sample_id, *args, **kwargs)
        # only the reference pool, so callers that rebuild a graph get entries that
        # still have one
        return list(self._functions_by_sample.get(int(sample_id), {}).values())

    def getFunctionsByIds(self, function_ids, *args, **kwargs):
        self._record("getFunctionsByIds", function_ids, *args, **kwargs)
        return {int(fid): self._functions[int(fid)] for fid in function_ids if int(fid) in self._functions}

    def getFunctionById(self, function_id, *args, **kwargs):
        self._record("getFunctionById", function_id, *args, **kwargs)
        return self._functions.get(int(function_id))

    def isFunctionId(self, function_id, *args, **kwargs):
        self._record("isFunctionId", function_id, *args, **kwargs)
        return int(function_id) in self._functions

    # --- jobs and results --------------------------------------------------------

    def getJobData(self, job_id, *args, **kwargs):
        self._record("getJobData", job_id, *args, **kwargs)
        entry = self._jobs.get(job_id)
        return Job(entry[0], None) if entry else None

    def getResultForJob(self, job_id, *args, **kwargs):
        self._record("getResultForJob", job_id, *args, **kwargs)
        entry = self._jobs.get(job_id)
        return entry[1] if entry else None

    def getQueueData(self, *args, **kwargs):
        self._record("getQueueData", *args, **kwargs)
        return [Job(entry, None) for entry in self._queue]

    def getQueueStatistics(self, *args, **kwargs):
        self._record("getQueueStatistics", *args, **kwargs)
        return load("queue_statistics")

    # --- search ------------------------------------------------------------------
    # The cursor protocol is not modelled: these return the empty shape so pages that
    # merely embed a search box render. A test that asserts on search results needs a
    # real implementation here first.

    @staticmethod
    def _empty_search():
        return {"search_results": {}, "cursor": {"forward": None, "backward": None}, "id_match": None, "sha_match": None}

    def search_samples(self, *args, **kwargs):
        self._record("search_samples", *args, **kwargs)
        return self._empty_search()

    def search_families(self, *args, **kwargs):
        self._record("search_families", *args, **kwargs)
        return self._empty_search()

    def search_functions(self, *args, **kwargs):
        self._record("search_functions", *args, **kwargs)
        return self._empty_search()

    def __getattr__(self, name):
        def _unimplemented(*args, **kwargs):
            raise NotImplementedError(
                f"CorpusMcritClient has no '{name}'. Add it to tests/fixtureData.py, "
                f"returning whatever shape the real McritClient returns."
            )
        return _unimplemented
