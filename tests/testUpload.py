#!/usr/bin/python
"""The Dropzone upload path - issue #27.

Flask-Dropzone was the recorded reason MCRITweb could not leave Flask 2.2.5, and it
was also the one integration nothing exercised: the suite rendered both dropzone
pages and asserted the CSRF header they emit, but no test ever posted a file through
one. That left the half of the path Werkzeug owns - multipart parsing, `request.files`,
the file wrapper handed to `json.load` - covered by nothing.

These tests drive the request the browser actually sends, so lifting the pin is
answered by the suite rather than by hand.
"""

import io
import json
import logging
from urllib.parse import quote

import pytest

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

#: The smallest thing shaped like an MCRIT export. The fake backend only counts the
#: three collections, so nothing here needs to be a real sample.
EXPORT = {
    "config": {"version": "1.5.3"},
    "families": {"1": {"family_name": "test.family"}},
    "samples": {"1": {"sample_id": 1, "family_id": 1}},
    "functions": {"1": {"function_id": 1, "sample_id": 1}},
}


def upload(client, payload, filename="export.json", field="file"):
    """POST a file the way the dropzone does: multipart, one part, XHR."""
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return client.post(
        "/data/import",
        data={field: (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_the_import_page_offers_a_dropzone_posting_to_the_import_route(client, as_role):
    """Flask-Dropzone renders through Jinja macros (`dropzone.create`), which is
    exactly the surface that broke on Flask 2.3 when `flask.Markup` was removed. If
    the extension is incompatible again, this is where it shows first."""
    as_role("contributor")
    page = client.get("/data/import").get_data(as_text=True)
    assert 'action="/data/import"' in page
    assert 'class="dropzone"' in page


def test_an_uploaded_export_reaches_the_backend(client, as_role, fake_mcrit):
    """The whole point of the route: a multipart part named `file`, parsed out of the
    request by Werkzeug and forwarded as a dict."""
    as_role("contributor")
    response = upload(client, EXPORT)

    assert response.status_code == 200
    forwarded = [call for call in fake_mcrit.calls if call[0] == "addImportData"]
    assert len(forwarded) == 1, "the upload never reached the backend"
    assert forwarded[0][1][0] == EXPORT


def test_the_import_report_is_carried_to_the_completion_page(client, as_role):
    """The upload response is not what the user sees - the dropzone redirects to
    `data.import_complete`, which reads the report back out of the session. Two
    requests, so the report has to survive the hop."""
    as_role("contributor")
    upload(client, EXPORT)

    page = client.get("/data/import_complete").get_data(as_text=True)
    assert "Import completed" in page
    assert "num_samples_imported" in page


def test_the_report_is_consumed_once(client, as_role):
    """`import_complete` pops the report. A second visit must not re-report an import
    that already happened - it should fall back to the error path instead."""
    as_role("contributor")
    upload(client, EXPORT)
    client.get("/data/import_complete")

    page = client.get("/data/import_complete").get_data(as_text=True)
    assert "Import completed" not in page
    assert "valid MCRIT data" in page


@pytest.mark.parametrize(
    "payload, reason",
    [
        (b"this is not json", "not JSON at all"),
        (b'["a", "list"]', "JSON, but not the dict the client demands"),
    ],
)
def test_an_unusable_upload_is_reported_rather_than_a_500(client, as_role, payload, reason):
    """Anyone can drop the wrong file into a dropzone, so the wrong file is a normal
    input, not an exceptional one. Whatever the page says, it must not be a traceback."""
    as_role("contributor")
    response = upload(client, payload)
    assert response.status_code < 500, f"upload that is {reason} took the page down"


# --- the sample dropzone: binary payloads, and the fields that ride with them ------

#: Comfortably past the 500 kB `max_form_memory_size` Werkzeug 3.1 began enforcing.
#: That limit is scoped to non-file fields - `formparser.MultiPartParser` sets
#: `field_size = None` for a File part - and this is what holds that to be true, since
#: the whole point of this dropzone is uploading executables.
LARGE_BINARY = b"MZ" + bytes(range(256)) * 8192

#: What the dropzone's `sending` handler appends alongside the file, from
#: `#dropzone-additional-fields-form`.
SUBMIT_FIELDS = {"family": "test.family", "version": "1.0", "options": "unmapped"}


def submit_binary(client, content, filename="sample.exe", **fields):
    """POST to the sample dropzone the way the browser does: one file part plus the
    additional form fields, in a single multipart body."""
    data = dict(SUBMIT_FIELDS, **fields)
    data["file"] = (io.BytesIO(content), filename)
    return client.post("/data/submit", data=data, content_type="multipart/form-data")


def test_a_binary_far_past_the_form_memory_limit_is_still_accepted(client, as_role, fake_mcrit):
    """The upload is a file part, so Werkzeug's non-file field limit must not apply to
    it - and the bytes must arrive intact, not truncated at a buffer boundary."""
    as_role("contributor")
    response = submit_binary(client, LARGE_BINARY)

    assert response.status_code == 202, response.get_data(as_text=True)[:200]
    queued = [call for call in fake_mcrit.calls if call[0] == "addBinarySample"]
    assert len(queued) == 1, "the binary never reached the backend"
    assert queued[0][1][0] == LARGE_BINARY


def test_the_fields_beside_the_file_travel_with_it(client, as_role, fake_mcrit):
    """Family and version are typed into a form that is *not* the dropzone's own; the
    `sending` handler copies them into the multipart body. If that ever stops working
    every upload lands unlabelled.

    What arrives at the client is the wire form, not the typed form: `data.submit`
    percent-encodes all three for the query string McritClient builds by hand, so the
    expectations are written through the same encoder. These particular values happen
    to be invariant under it, and asserting them raw would pass for that reason alone -
    and then confuse whoever first puts a '+' or an '&' in a fixture here. What the
    encoding is *for* is tests/testSubmitMetadata.py."""
    as_role("contributor")
    submit_binary(client, b"MZ small", filename="thing.exe")

    _, _, kwargs = next(c for c in fake_mcrit.calls if c[0] == "addBinarySample")
    assert kwargs["family"] == quote("test.family", safe="")
    assert kwargs["version"] == quote("1.0", safe="")
    assert kwargs["filename"] == quote("thing.exe", safe="")


def test_a_dump_carries_its_bitness_and_base_address(client, as_role, fake_mcrit):
    """The 'dumped' radio reveals two more fields, and the view parses both - base
    address as hex. A memory dump without them cannot be disassembled correctly."""
    as_role("contributor")
    submit_binary(client, b"MZ dumped", options="dumped", bitness="64", base_addr="0x140000000")

    _, _, kwargs = next(c for c in fake_mcrit.calls if c[0] == "addBinarySample")
    assert kwargs["is_dump"] is True
    assert kwargs["bitness"] == 64
    assert kwargs["base_addr"] == 0x140000000


# --- the filename probe the dropzone fires on drop ---------------------------------

def filename_info(client, filename, file_header="", file_metadata=None):
    """The XHR `addedfile` sends: a JSON body, so a header-borne CSRF token and no
    form field at all. `file_metadata` is omitted entirely when None, which is what a
    client older than that field looks like."""
    body = {"filename": filename, "file_header": file_header, "form": []}
    if file_metadata is not None:
        body["file_metadata"] = file_metadata
    response = client.post(
        "/data/request_filename_info", data=json.dumps(body), content_type="application/json"
    )
    return json.loads(response.get_data(as_text=True))


def smda_report_text(family="test.family", version="1.0"):
    """A report serialised the way the smda CLI writes one: `BatchProcessor.py:70` does
    `json.dump(..., indent=1, sort_keys=True)`. That sorting is the whole problem -
    base_addr and bitness sort to the front, while metadata lands after code_areas,
    code_sections and disassembly_errors."""
    report = {
        "architecture": "intel", "abi": "cdecl", "base_addr": 4194304,
        "binary_size": 2371584, "bitness": 64,
        "code_areas": [[4198400, 4300000], [4300000, 4400000], [4400000, 4500000]],
        "code_sections": [["", 4198400, 4300000], ["", 4300000, 4400000]],
        "confidence_threshold": 0.5,
        "disassembly_errors": {str(a): "decode" for a in range(4198400, 4198430)},
        "execution_time": 12.34, "identified_alignment": 16,
        "metadata": {
            "binweight": 1234, "component": "", "family": family, "filename": "sample.exe",
            "is_library": False, "is_buffer": False, "language": "C", "version": version,
        },
        "message": "", "oep": 4198400, "sha256": "ab" * 32, "smda_version": "4.4.4",
        "statistics": {}, "status": "ok", "timestamp": "2026-08-07T12-00-00", "xcfg": {},
    }
    return json.dumps(report, indent=1, sort_keys=True)


def browser_windows(text):
    """The two slices the patched `dropzone.js` cuts and sends: the first 1024 bytes,
    and 1024 bytes from wherever `"metadata"` actually begins."""
    data = text.encode()
    at = data.find(b'"metadata"')
    return data[:1024].decode(), ("" if at < 0 else data[at:at + 1024].decode())


def test_a_dump_filename_yields_bitness_and_base_address(client, as_role):
    """`_0x` plus 8 hex digits means 32-bit, more than 8 means 64-bit - this is what
    pre-fills the form the moment a file is dropped."""
    as_role("contributor")
    assert filename_info(client, "malware_dump_0x140000000.bin") == {
        "dump": True,
        "bitness": 64,
        "base_addr": "0x140000000",
    }


def test_an_smda_report_is_read_out_of_the_uploaded_header(client, as_role):
    """For .smda the answers come from the first bytes of the file itself, which the
    browser reads and sends as text. Regex over a prefix, so a truncated header is
    normal input."""
    as_role("contributor")
    header = '{"family": "test.family", "version": "2.1", "bitness": 32, "base_addr": 4194304'
    result = filename_info(client, "report.smda", header)

    assert result["smda"] is True
    assert result["family"] == "test.family"
    assert result["version"] == "2.1"
    assert result["bitness"] == 32
    assert result["base_addr"] == "0x400000"


def test_an_ordinary_filename_claims_nothing(client, as_role):
    """No pattern matched must mean "not a dump", not a half-filled form."""
    as_role("contributor")
    assert filename_info(client, "sample.exe") == {"dump": False}


def test_a_realistically_serialised_smda_report_fills_every_field(client, as_role):
    """The one that was broken in the live instance: base address filled, family and
    version stayed empty, because a 1024-byte prefix never reaches metadata."""
    as_role("contributor")
    header, metadata = browser_windows(smda_report_text())
    assert '"family"' not in header, "fixture no longer reproduces the bug it exists for"

    assert filename_info(client, "report.smda", header, metadata) == {
        "smda": True,
        "family": "test.family",
        "version": "1.0",
        "bitness": 64,
        "base_addr": "0x400000",
    }


def test_a_client_that_sends_no_metadata_window_still_works(client, as_role):
    """A cached older dropzone.js omits the field entirely. It must degrade to what it
    could always do - base address and bitness - not fail the request."""
    as_role("contributor")
    header, _ = browser_windows(smda_report_text())
    result = filename_info(client, "report.smda", header)

    assert result["bitness"] == 64
    assert result["base_addr"] == "0x400000"
    assert result["family"] is None
