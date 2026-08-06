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

Do not upgrade opportunistically as a side effect of unrelated work — the two pins
must move together. The sequence is: get the project on a firmer footing first (a
working test suite, CI, and ruff — #88 and #86), then take #27 with tests to catch
what breaks.

**That precondition is met as of 2026-08-06.** `python -m pytest` runs 191 offline
tests, CI runs them plus `ruff check .` on 3.11 and 3.12, and the suite includes a
route matrix asserting every route's access boundary from both sides and that none
answers a legitimate caller with a 5xx, plus result-page rendering against captured
backend reports. That is the safety net #27 was waiting for.

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

### Static surface, checked 2026-08-06

Our own code turns out to be clean. Everything MCRITweb imports from either package
survives Flask 3.x and Werkzeug 3.x:

- **Flask** — `Flask`, `Blueprint`, `Request`, `Response`, `abort`, `current_app`,
  `flash`, `g`, `json`, `redirect`, `render_template`, `request`,
  `send_from_directory`, `session`, `url_for`, and `flask.cli.with_appcontext`.
- **Werkzeug** — `security.check_password_hash`, `security.generate_password_hash`,
  and `middleware.profiler.ProfilerMiddleware` (only under `FLASK_DEBUG` with
  `PROFILER=True`).

Nothing uses the removals that break most upgrades of this vintage: no
`before_first_request`, no `flask.Markup` or `flask.escape`, no `safe_str_cmp`, no
`werkzeug.urls` helpers (`url_encode`/`url_decode`/`url_quote`), no `JSONEncoder`
subclassing, no `_app_ctx_stack`/`_request_ctx_stack`, and nothing reads
`flask.__version__`. Flask-Dropzone's `from markupsafe import Markup` was verified
against the installed 2.0.0, not inferred from a changelog.

So the remaining risk is **behavioural, not API-level** — changed defaults and
semantics rather than missing names, which a static scan cannot find and the test
suite can. Re-run this scan before trusting it; it describes the tree at v1.4.6.

The two places the suite is thinnest, and therefore where to look hardest by hand:
no test exercises a real backend, and the route matrix is a smoke test — it proves a
page rendered against fixture data, not that it rendered *correctly*.

Practical note: the checked-out virtualenv is managed by `uv`, so a throwaway
environment is `uv venv` plus `uv pip install`, and a package can be added to the
existing one with `uv pip install --python .venv/bin/python <package>`.

Once the pin is lifted, [ADR-0002](0002-hand-rolled-csrf.md) becomes actionable:
`mcritweb/csrf.py` was written to mirror `flask-wtf`'s public surface so that
adopting the extension is an import change rather than a sweep through every
template.
