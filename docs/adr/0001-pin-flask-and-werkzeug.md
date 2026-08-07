# Pin Flask 2.2.5 and Werkzeug 2.3.3

---
status: reversed on 2026-08-07 by #27 — see "Outcome"
---

`flask==2.2.5` and `werkzeug==2.3.3` are hard-pinned in both `setup.py` and
`requirements.txt` because the Flask-Dropzone integration used for sample upload was
incompatible with newer Flask, and replacing or working around it was more effort
than was available at the time. This is a reluctant, temporary pin, not a preference.

## Consequences

Running a Flask release from 2023 indefinitely is a security exposure, and this is the
main reason to get off the pin rather than any feature we want. It also blocks Python
3.14, since Flask 2.2.5 calls `pkgutil.get_loader`, removed in that version.

Do not upgrade opportunistically as a side effect of unrelated work — the two pins
must move together. The sequence is: get the project on a firmer footing first (a
working test suite, CI, and ruff — #88 and #86), then take #27 with tests to catch
what breaks.

**That precondition was met as of 2026-08-06.** `python -m pytest` runs 191 offline
tests, CI runs them plus `ruff check .` on 3.11 and 3.12, and the suite includes a
route matrix asserting every route's access boundary from both sides and that none
answers a legitimate caller with a 5xx, plus result-page rendering against captured
backend reports. That is the safety net #27 was waiting for.

## Outcome — lifted on 2026-08-07

Both pins became `>=3.0` and the suite stayed green. The upgrade was uneventful: no
application code had to change to accommodate it.

What the environment resolved to, and what was run against it:

- Flask 3.1.3, Werkzeug 3.1.8, Flask-Dropzone 2.0.0, on **Python 3.14.4**
- 191 existing tests green, plus 6 new ones covering the upload path (below)
- `ruff check .` clean

**The recorded blocker was indeed stale.** Flask-Dropzone 2.0.0 declares
`Requires-Dist: Flask` with no upper bound and imports `from markupsafe import Markup`
— the spelling that survives Flask 2.3, which removed `flask.Markup`. Older
Flask-Dropzone used `from flask import Markup`, which is what broke. Its Jinja macros
(`dropzone.create`, `dropzone.style`, `dropzone.config`) render unchanged under
Flask 3.x.

**The Python 3.14 claim above was confirmed, with one correction.** `import flask` on
2.2.5 succeeds on 3.14; it is *app construction* that fails, at
`flask/scaffold.py:112` → `get_root_path()` → `flask/helpers.py:611`, with
`AttributeError: module 'pkgutil' has no attribute 'get_loader'`. So the pin blocked
3.14 at first request, not at import — which is why a smoke import would have been
misleading here.

### Why lower bounds rather than no constraint

`>=3.0` on both, not a bare `flask`. Nothing in the resolver otherwise stops a future
environment from selecting a 2.x that reintroduces exactly the incompatibility this
ADR is about, and the failure mode is a 500 at app construction on a modern
interpreter rather than an install-time error.

### What the static scan found, checked twice

Our own code was clean, both when scanned at v1.4.6 and when re-run before the
upgrade landed. Everything MCRITweb imports from either package survives Flask 3.x
and Werkzeug 3.x:

- **Flask** — `Flask`, `Blueprint`, `Request`, `Response`, `abort`, `current_app`,
  `flash`, `g`, `json`, `redirect`, `render_template`, `request`,
  `send_from_directory`, `session`, `url_for`, and `flask.cli.with_appcontext`.
- **Werkzeug** — `security.check_password_hash`, `security.generate_password_hash`,
  and `middleware.profiler.ProfilerMiddleware` (only under `FLASK_DEBUG` with
  `PROFILER=True`).

Nothing used the removals that break most upgrades of this vintage: no
`before_first_request`, no `flask.Markup` or `flask.escape`, no `safe_str_cmp`, no
`werkzeug.urls` helpers (`url_encode`/`url_decode`/`url_quote`), no `JSONEncoder`
subclassing, no `_app_ctx_stack`/`_request_ctx_stack`, and nothing reads
`flask.__version__`.

### The gap that was closed to trust the result

The suite rendered both dropzone pages and asserted the CSRF header they emit, but
nothing ever posted a file through one — so multipart parsing, `request.files`, and
the file wrapper handed to `json.load` were covered by nothing, in precisely the
integration #27 was blocked on. `tests/testUpload.py` now drives that request.

Writing it surfaced a pre-existing 500: `/data/import` called `json.load` on the
upload and forwarded the result without checking either, so a file that was not JSON,
or was JSON but not an object, took the page down. Unrelated to the upgrade, fixed
alongside it — it now flashes the same message `import_complete` already used for
this case.

### Still true, and still where to look hardest

No test exercises a real backend, and the route matrix is a smoke test — it proves a
page rendered against fixture data, not that it rendered *correctly*. The upgrade
therefore rests on a suite that is broad but shallow. Behavioural changes in Flask
3.x that only show against a live mcrit-server would not have been caught here.

With the pin gone, [ADR-0002](0002-hand-rolled-csrf.md) becomes actionable:
`mcritweb/csrf.py` was written to mirror `flask-wtf`'s public surface so that
adopting the extension is an import change rather than a sweep through every
template.
