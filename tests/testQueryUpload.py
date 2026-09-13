#!/usr/bin/python
"""`/analyze/query` persists the uploaded file under a name it takes from the upload.

For a binary the name is `sha256(bytes)`, which the route computes. For an SMDA report
it is the report's own `sha256` field - a string the uploader wrote, which nothing in
`SmdaReport.fromDict` validates. That string was joined into a path and opened for
writing, so it decided where on disk the upload went. `@visitor_required` is the lowest
role this application has, so the lowest role could write a file of its own choosing
anywhere the server process can reach.

These tests pin the guard. The traversal one fails on the unfixed route.
"""

import io
import json
import logging
import pathlib

import pytest

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

#: The smallest dict `SmdaReport.fromDict` accepts - every field in
#: `smda.common.SmdaReport.REQUIRED_REPORT_FIELDS` and nothing else. The route never
#: disassembles it; the fake backend records the call. `sha256` is what is under test.
MINIMAL_SMDA_REPORT = {
    "architecture": "intel",
    "base_addr": 0x400000,
    "binary_size": 4,
    "bitness": 32,
    "code_areas": [],
    "confidence_threshold": 0.0,
    "disassembly_errors": {},
    "execution_time": 0.0,
    "identified_alignment": 0,
    "message": "Analysis finished regularly.",
    "sha256": "ab" * 32,
    "smda_version": "1.0.0",
    "status": "ok",
    "xcfg": {},
}


@pytest.fixture
def fake_mcrit(recording_mcrit):
    """`requestMatchesForSmdaReport` has to answer, or the route raises before it
    returns and the status code under test never happens."""
    return recording_mcrit


def uploads_dir(app):
    return pathlib.Path(app.instance_path) / "temp" / "uploads"


def query_with_sha256(client, sha256, kind="smda"):
    """POST an SMDA report declaring `sha256`, the way the query page's dropzone does."""
    report = dict(MINIMAL_SMDA_REPORT, sha256=sha256)
    return client.post(
        "/analyze/query",
        data={
            "file": (io.BytesIO(json.dumps(report).encode()), "query.smda"),
            "options": kind,
            "base_addr": "0x400000",
        },
        content_type="multipart/form-data",
    )


def test_a_report_declaring_a_traversal_writes_nothing(client, as_role, app):
    """The finding itself: a visitor picks the path and the content.

    `instance/` sits inside pytest's tmp_path, so a target outside it is a target
    outside the application's whole data directory - not merely the wrong folder.
    """
    as_role("visitor")
    escaped = pathlib.Path(app.instance_path).parent / "PLANTED"
    assert not escaped.exists()

    response = query_with_sha256(client, "../../../PLANTED")

    assert not escaped.exists(), "a visitor wrote a file outside the instance directory"
    assert response.status_code == 400


@pytest.mark.parametrize(
    "sha256",
    [
        "../../../PLANTED",
        "..",
        ".",
        "sub/dir/NESTED",
        "sub\\dir\\NESTED",
        "/tmp/ABSOLUTE",
        "",
        "ab" * 31,          # 62 chars - too short
        "ab" * 32 + "cd",   # 66 chars - too long
        "zz" * 32,          # right length, not hex
        "ab" * 31 + "a\n",  # a trailing newline is not a hexdigest
        "ab" * 31 + "\nab" * 1,
    ],
)
def test_only_a_hexdigest_can_name_the_stored_upload(client, as_role, app, sha256):
    """Everything that is not 64 hex characters is refused before the open()."""
    as_role("visitor")
    before = sorted(p.name for p in uploads_dir(app).iterdir()) if uploads_dir(app).exists() else []

    response = query_with_sha256(client, sha256)

    assert response.status_code == 400
    after = sorted(p.name for p in uploads_dir(app).iterdir()) if uploads_dir(app).exists() else []
    assert after == before, f"{sha256!r} still produced a file"


def test_an_honest_report_is_still_stored_under_its_hash(client, as_role, app):
    """The guard must not cost the feature: a real hexdigest goes through unchanged."""
    as_role("visitor")

    response = query_with_sha256(client, "ab" * 32)

    assert response.status_code == 202
    assert sorted(p.name for p in uploads_dir(app).iterdir()) == ["ab" * 32]


def test_an_uppercase_hash_is_stored_lowercase(client, as_role, app):
    """`SmdaReport` preserves whatever case the report used, and every reader of this
    directory looks the file up lowercase. Storing both spellings would put the same
    upload on disk twice under names that never match a lookup."""
    as_role("visitor")

    response = query_with_sha256(client, "AB" * 32)

    assert response.status_code == 202
    assert sorted(p.name for p in uploads_dir(app).iterdir()) == ["ab" * 32]


def test_a_binary_query_names_the_file_by_its_own_content(client, as_role, app):
    """The non-SMDA kinds never trusted the upload for the name and still do not - the
    route hashes the bytes itself. Here so that the guard above cannot be "fixed" by
    routing the binary kinds through the report field."""
    import hashlib

    as_role("visitor")
    content = b"MZ\x90\x00not a real binary"
    response = client.post(
        "/analyze/query",
        data={
            "file": (io.BytesIO(content), "sample.exe"),
            "options": "unmapped",
            "base_addr": "0x0",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    assert sorted(p.name for p in uploads_dir(app).iterdir()) == [hashlib.sha256(content).hexdigest()]
