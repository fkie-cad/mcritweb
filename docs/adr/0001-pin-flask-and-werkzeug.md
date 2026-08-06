# Pin Flask 2.2.5 and Werkzeug 2.3.3

---
status: accepted — intended to be reversed, see #27
---

`flask==2.2.5` and `werkzeug==2.3.3` are hard-pinned in both `setup.py` and
`requirements.txt` because the Flask-Dropzone integration used for sample upload was
incompatible with newer Flask, and replacing or working around it was more effort
than was available at the time. This is a reluctant, temporary pin, not a preference.

## Consequences

Running a Flask release from 2023 indefinitely is a security exposure, and this is the
main reason to get off the pin rather than any feature we want. It also blocks Python
3.14, since Flask 2.2.5 calls `pkgutil.get_loader`, removed in that version.

Do not upgrade opportunistically as a side effect of unrelated work — the codebase
uses APIs that later versions changed, and the two pins must move together. The
sequence is: get the project on a firmer footing first (a working test suite, CI, and
ruff — #88 and #86), then take #27 with tests to catch what breaks.

## When picking up #27, start here

The originally recorded blocker looks stale. Flask-Dropzone **2.0.0** declares
`Requires-Dist: Flask` with no upper bound, and its source imports
`from markupsafe import Markup` — the spelling that survives Flask 2.3, which removed
`flask.Markup`. Older Flask-Dropzone used `from flask import Markup`, which is what
broke. So the specific incompatibility described in #27 appears to be fixed upstream
already.

That is not proof MCRITweb runs on Flask 3.x — our own code may use other removed
APIs, and Werkzeug 2.3 → 3.0 has its own changes. But the named cause no longer holds,
so the first step is to try the upgrade in a throwaway environment and see what
actually fails, rather than assuming Flask-Dropzone is still the obstacle.
