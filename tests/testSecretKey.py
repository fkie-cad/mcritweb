#!/usr/bin/python
"""`SECRET_KEY` is generated and kept, not left at 'dev'.

The session cookie is signed with `SECRET_KEY` and is the whole proof of who a
caller is. With the historical default, anyone reading this public repository could
sign a cookie saying `role: admin` and never authenticate at all - which also makes
the CSRF token of issue #83 decorative, since a forged session can carry whatever
token it likes.

Persisting the generated key matters as much as generating it. A fresh key per
process would log every user out on each restart and break outright across the
several workers a WSGI server runs.
"""

import logging
import os
import stat

from mcritweb.secret_key import FILENAME, INSECURE_DEFAULT, load_or_create_secret_key

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")
logging.disable(logging.CRITICAL)


def test_a_key_is_generated_when_none_exists(tmp_path):
    key = load_or_create_secret_key(str(tmp_path))
    assert key != INSECURE_DEFAULT
    assert len(key) >= 32, "a guessable key is no better than the default"


def test_the_same_key_comes_back_on_the_next_call(tmp_path):
    """Restarting the process, or starting a second worker, must not change it."""
    assert load_or_create_secret_key(str(tmp_path)) == load_or_create_secret_key(str(tmp_path))


def test_two_instances_do_not_share_a_key(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    assert load_or_create_secret_key(str(first)) != load_or_create_secret_key(str(second))


def test_the_key_file_is_not_readable_by_others(tmp_path):
    load_or_create_secret_key(str(tmp_path))
    mode = os.stat(tmp_path / FILENAME).st_mode
    assert not mode & stat.S_IRGRP, "the group can read the session signing key"
    assert not mode & stat.S_IROTH, "the world can read the session signing key"


def test_an_empty_file_is_replaced_rather_than_used(tmp_path):
    """A truncated write must not leave the application signing with the empty
    string, which would accept any cookie an attacker signs the same way."""
    (tmp_path / FILENAME).write_text("   \n")
    assert load_or_create_secret_key(str(tmp_path)).strip() != ""


def test_the_app_does_not_run_on_the_insecure_default(app):
    """The `app` fixture sets its own key, so this checks the factory honoured it
    rather than overwriting a configured value."""
    assert app.config["SECRET_KEY"] == "test-secret"


def test_an_unconfigured_app_gets_a_generated_key(tmp_path, fake_mcrit):
    from mcritweb import create_app

    instance_path = tmp_path / "instance"
    instance_path.mkdir()
    application = create_app(
        {
            "DATABASE": str(tmp_path / "mcritweb.sqlite"),
            "TESTING": True,
            "MCRIT_CLIENT_FACTORY": lambda **kwargs: fake_mcrit,
        },
        instance_path=str(instance_path),
    )
    assert application.config["SECRET_KEY"] != INSECURE_DEFAULT
    assert (instance_path / FILENAME).exists(), "the key was generated but not kept"
