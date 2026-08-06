#!/usr/bin/python
"""The settings write routes: reachable only by POST, and landing somewhere real.

Each of these routes used to accept GET and act on it. `admin.change_server` blanked
the backend URL and both tokens; `admin.change_default_filter` reset every stored
filter to its default. Neither needed a single form field, and with no CSRF token
anywhere in the application at the time, any page an admin visited could fire them.
Both defences are in place now; the token itself is covered by testCsrf.py.

They also rendered `settings.html` without the context that template needs, so the
page 500'd immediately after the write went through. They redirect to the settings
view now, which is the one place that assembles it.
"""

import logging
import unittest

import pytest

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)

POST_ONLY = [
    ("/admin/change_default_filter", "admin"),
    ("/admin/change_server", "admin"),
    ("/admin/reset_server", "admin"),
]


@pytest.mark.parametrize("path,role", POST_ONLY)
def test_a_get_cannot_reach_a_settings_write(client, as_role, path, role):
    as_role(role)
    response = client.get(path)
    assert response.status_code == 405, f"GET {path} is still routed"


def test_changing_default_filters_lands_on_a_page_that_renders(client, as_role):
    as_role("admin")
    response = client.post("/admin/change_default_filter", data={"filter_direct_min_score": "42"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings")
    assert client.get("/settings").status_code == 200


def test_a_rejected_username_change_lands_on_a_page_that_renders(client, as_role):
    as_role("admin")
    response = client.post(
        "/admin/change_username",
        data={"username": "no", "inputPassword1": "password"},   # too short to be valid
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/settings")
    assert client.get("/settings").status_code == 200


def test_an_unconfirmed_reset_changes_nothing_and_still_answers(client, as_role):
    """The view used to fall off the end without returning, so Flask raised."""
    as_role("admin")
    response = client.post("/admin/reset_server", data={"reset_server": "not the word"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/server")


def test_changing_the_server_still_works_by_post(app, client, as_role):
    as_role("admin")
    response = client.post(
        "/admin/change_server",
        data={"mcrit_server_url": "http://127.0.0.1:9999", "mcrit_server_token": "newtoken"},
    )

    assert response.status_code == 200
    with app.app_context():
        from mcritweb.db import ServerInfo
        assert ServerInfo.fromDb().url == "http://127.0.0.1:9999"


if __name__ == "__main__":
    unittest.main()
