#!/usr/bin/python
"""Values crossing into JavaScript must be escaped for a script context.

Two tests with different reach, and they are not redundant:

`test_no_safe_filter_inside_a_script_block` is a lint over the template tree. It is the
ratchet issue #85 asked for - `|safe` disables autoescaping, and Jinja's autoescaping is
*HTML* escaping anyway, which is not what a `<script>` body needs. `|tojson` is the only
filter that escapes correctly there, and it is what AGENTS.md mandates. The lint exists
because the alternative is an exception list in the documentation that grows back.

`test_a_family_name_cannot_break_out_of_a_script_string` is a render, and it is the one
that would have caught the actual bug: family names are backend data, a contributor
chooses them, and two templates dropped them into a quoted JS string literal. A lint
alone would not have shown that the value was attacker-controlled rather than an id.
"""

import logging
import os
import re

import pytest
from mcrit.storage.FamilyEntry import FamilyEntry

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

PACKAGE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcritweb")
TEMPLATE_ROOT = os.path.join(PACKAGE_ROOT, "templates")

#: `|safe`, `| safe`, `|  safe` - the spacing is why a grep for "|safe" found only eight
#: of the fifteen sites that existed when #85 was written.
SAFE_FILTER = re.compile(r"\|\s*safe\b")
SCRIPT_BLOCK = re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)

#: A name that terminates a double-quoted JS string, closes the script element and opens
#: its own. Flask's `|tojson` escapes `"` and `<`, so none of it survives as markup.
BREAKOUT_NAME = 'evil" </script><script>alert(1)</script>'


def template_files():
    for directory, _, filenames in os.walk(TEMPLATE_ROOT):
        for filename in sorted(filenames):
            if filename.endswith(".html"):
                yield os.path.join(directory, filename)


def script_block_safe_filters():
    """Every `|safe` occurring inside a `<script>` block, as `path:line` strings."""
    for path in sorted(template_files()):
        with open(path, encoding="utf-8") as template:
            source = template.read()
        relative = os.path.relpath(path, TEMPLATE_ROOT)
        for block in SCRIPT_BLOCK.finditer(source):
            for hit in SAFE_FILTER.finditer(block.group()):
                line = source.count("\n", 0, block.start() + hit.start()) + 1
                yield f"{relative}:{line}"


def test_the_script_block_scan_still_sees_something():
    """A guard on the guard: if the regexes stop matching any script block at all, the
    lint below silently passes on an empty parameter set."""
    blocks = 0
    for path in template_files():
        with open(path, encoding="utf-8") as template:
            blocks += len(SCRIPT_BLOCK.findall(template.read()))
    assert blocks > 10, f"only {blocks} script blocks found - the scan is not watching the tree"


def test_no_safe_filter_inside_a_script_block():
    """One assertion rather than a parametrized case per site, because the healthy state
    is *no* sites: an empty parameter set reports as a skip, which reads like the lint
    ran when it had nothing to run on."""
    offenders = sorted(script_block_safe_filters())
    assert not offenders, (
        "|safe inside a <script> block at: " + ", ".join(offenders) + ". Use |tojson: "
        "autoescaping is HTML escaping, which a browser does not decode in script "
        "content, so |safe and plain autoescaping are both wrong there. See AGENTS.md."
    )


@pytest.fixture
def fake_mcrit(corpus_mcrit):
    """Result and explore pages need real rows, so serve the captured corpus."""
    return corpus_mcrit


@pytest.mark.parametrize("path", ["/explore/families", "/explore/samples", "/data/submit"])
def test_a_family_name_cannot_break_out_of_a_script_string(client, as_role, fake_mcrit, path):
    """A family name is chosen by whoever submits or renames a family, so it is user
    input arriving by way of the backend - exactly what AGENTS.md says must never reach
    `|safe`.

    `/data/submit` is the remaining page that embeds the names in its source, through
    `table/submit_or_query_dropzone.html`. The two explore listings used to do the same
    through `js/ac_family_names.html`; #77 moved them onto `explore.family_names`, which
    the test below covers. They stay in this list so that re-embedding a name there
    would have to pass this again.
    """
    family_id, family_entry = next(iter(fake_mcrit._families.items()))
    fake_mcrit._families[family_id] = FamilyEntry.fromDict(
        dict(family_entry.toDict(), family_name=BREAKOUT_NAME)
    )
    as_role("contributor")

    response = client.get(path)

    assert response.status_code == 200
    assert b"<script>alert(1)</script>" not in response.data, (
        f"a crafted family name broke out of the JS string literal on {path}"
    )


def test_a_family_name_stays_a_string_in_the_type_ahead_response(client, as_role, fake_mcrit):
    """Where those names travel since #77: JSON, fetched by `js/ac_family_names.html`.

    A JSON body is not a script context and is not served as one, so what this pins is
    that the endpoint stays JSON and the name stays a string *value* in it - never
    concatenated into a document. Note what it does not cover: the widget that receives
    it, `Autocomplete.createItem` in `static/autocomplete.js`, builds its dropdown by
    interpolating the label into an HTML string. That injection point predates #77 and
    is unchanged by it - the names reached exactly the same call when they were embedded
    in the page - but it is not made safe by anything here.
    """
    family_id, family_entry = next(iter(fake_mcrit._families.items()))
    fake_mcrit._families[family_id] = FamilyEntry.fromDict(
        dict(family_entry.toDict(), family_name=BREAKOUT_NAME)
    )
    as_role("visitor")

    response = client.get("/explore/familyNames?q=evil")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.json["family_names"] == [BREAKOUT_NAME]
