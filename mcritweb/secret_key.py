"""A stable, random `SECRET_KEY` for deployments that never configured one.

`SECRET_KEY` signs the session cookie, and the session cookie is the entire proof
of who a caller is. With the historical default of `'dev'`, anyone who has read this
source - it is a public repository - can mint a cookie that says `role: admin` and
skip authentication altogether. Every other defence in the application, CSRF tokens
included, sits behind that one signature.

So when the operator has not set a key, generate one and keep it. Keeping it matters
as much as generating it: a fresh key per process would log every user out on each
restart, and break outright across the multiple workers a WSGI server runs.

An explicit key in `instance/config.py` still wins. That remains the right answer for
a multi-host deployment, where all hosts must share one key and a per-host file
cannot provide that.
"""

import os
import secrets

#: Historical default. Its presence in the config means nobody has set a key.
INSECURE_DEFAULT = "dev"

#: Lives beside `mcritweb.sqlite`, which is already git-ignored and already holds
#: the backend token - so this adds no new class of secret to the instance folder.
FILENAME = "secret_key"


def load_or_create_secret_key(instance_path):
    """Return the persisted key for this instance, creating it on first call."""
    path = os.path.join(instance_path, FILENAME)
    try:
        with open(path) as key_file:
            key = key_file.read().strip()
        if key:
            return key
    except FileNotFoundError:
        pass
    key = secrets.token_hex(32)
    # 0o600 from the moment it exists - os.open with the mode, not a chmod after the
    # fact, which would leave a window where the key is world-readable
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as key_file:
        key_file.write(key)
    return key
