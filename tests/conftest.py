"""Shared fixtures for the mcritweb test suite.

Every fixture here is offline: the app runs against a throwaway SQLite database and
a fake MCRIT backend substituted through the MCRIT_CLIENT_FACTORY config key, so no
test needs a running mcrit-server. See issue #88.
"""

import pytest
from werkzeug.security import generate_password_hash

from mcritweb import create_app
from mcritweb.db import ServerInfo, UserInfo, init_db


class FakeMcritClient:
    """Stand-in for McritClient.

    Deliberately not a MagicMock: an auto-mock returns further mocks, which render
    happily in Jinja and let template tests pass without asserting anything real.
    This returns the same shapes the backend does, and raises a named
    NotImplementedError for anything a test has not taught it yet, so gaps surface
    as actionable failures rather than silent success.
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    # --- shapes the views expect -------------------------------------------------

    @staticmethod
    def empty_search_result():
        return {
            "search_results": {},
            "cursor": {"forward": None, "backward": None},
            "id_match": None,
            "sha_match": None,
        }

    # --- the handful of methods the default pages touch --------------------------

    def getQueueData(self, *args, **kwargs):
        self._record("getQueueData", *args, **kwargs)
        return []

    def search_samples(self, *args, **kwargs):
        self._record("search_samples", *args, **kwargs)
        return self.empty_search_result()

    def search_families(self, *args, **kwargs):
        self._record("search_families", *args, **kwargs)
        return self.empty_search_result()

    def search_functions(self, *args, **kwargs):
        self._record("search_functions", *args, **kwargs)
        return self.empty_search_result()

    def getFamilies(self, *args, **kwargs):
        self._record("getFamilies", *args, **kwargs)
        return {}

    def getSampleById(self, *args, **kwargs):
        self._record("getSampleById", *args, **kwargs)
        return None

    def getFamily(self, *args, **kwargs):
        self._record("getFamily", *args, **kwargs)
        return None

    def getStatus(self, *args, **kwargs):
        self._record("getStatus", *args, **kwargs)
        return {}

    def __getattr__(self, name):
        def _unimplemented(*args, **kwargs):
            raise NotImplementedError(
                f"FakeMcritClient has no '{name}'. Add it to tests/conftest.py, "
                f"returning whatever shape the real McritClient returns."
            )
        return _unimplemented


class RecordingMcritClient(FakeMcritClient):
    """A fake that never raises: unknown methods record the call and return None.

    The strict fake above is the right default, because a raised NotImplementedError
    names the gap. It is the wrong tool for asking "did this request write anything",
    since a view that would have written can abort on the raise before it gets there
    and then look innocent. This variant lets the view run on and records what it
    reached for, at the cost of telling you nothing about response shapes.
    """

    def __getattr__(self, name):
        def _permissive(*args, **kwargs):
            self._record(name, *args, **kwargs)
            return None
        return _permissive


@pytest.fixture
def fake_mcrit():
    """The fake backend instance the app under test will hand to its views."""
    return FakeMcritClient()


@pytest.fixture
def recording_mcrit():
    """The permissive fake. Override `fake_mcrit` with it to wire up the app."""
    return RecordingMcritClient()


@pytest.fixture
def app(tmp_path, fake_mcrit):
    """A configured app on a throwaway database, wired to the fake backend."""
    instance_path = tmp_path / "instance"
    instance_path.mkdir()

    application = create_app(
        {
            "DATABASE": str(tmp_path / "mcritweb.sqlite"),
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "WTF_CSRF_ENABLED": False,
            "MCRIT_CLIENT_FACTORY": lambda **kwargs: fake_mcrit,
            # mcrit_server_required otherwise makes a real HTTP call to the backend
            "MCRIT_SERVER_PROBE": lambda: True,
        },
        instance_path=str(instance_path),
    )

    with application.app_context():
        init_db()
        # views reach for the server settings on nearly every request
        server_info = ServerInfo()
        server_info.url = "http://127.0.0.1:8000"
        server_info.operation_mode = "multi"
        server_info.registration_token = ""
        server_info.server_token = ""
        server_info.server_uuid = "test-uuid"
        server_info.server_version = "test"
        server_info.saveToDb()

    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    """Create a user with the given role and return its id."""
    def _make_user(role="admin", username=None):
        username = username or f"{role}user"
        with app.app_context():
            user_info = UserInfo()
            user_info.username = username
            user_info.password = generate_password_hash("password")
            user_info.role = role
            user_info.apitoken = f"apitoken-{role}"
            user_info.saveToDb()
            return UserInfo.fromDb(username=username).user_id
    return _make_user


@pytest.fixture
def as_role(client, make_user):
    """Log the test client in as a user with the given role.

    Note that a user must exist for anything to be reachable at all: with an empty
    user table the app treats the instance as unconfigured and redirects to
    registration.
    """
    def _as_role(role="admin", username=None):
        user_id = make_user(role=role, username=username)
        with client.session_transaction() as test_session:
            test_session["user_id"] = user_id
        return user_id
    return _as_role
