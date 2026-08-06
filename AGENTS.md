# AGENTS.md — MCRITweb (Flask front-end)

MCRITweb is the **browser front-end and user management layer** for [MCRIT](https://github.com/danielplohmann/mcrit) (MinHash-based Code Relationship & Investigation Toolkit). It is a Flask application that renders server-side Jinja2 templates and talks to an **existing** MCRIT backend over its REST API via `McritClient` from the `mcrit` package.

This repository owns **no analysis data of its own**. Families, samples, functions, jobs, and matching results all live in the MCRIT backend; the local SQLite database only holds users, their preferences, and the backend connection settings. For the matching methodology (PicHash/MinHash, LSH banding) see the [mcrit `AGENTS.md`](../mcrit/AGENTS.md).

## Repository layout

- `mcritweb/` — package source.
  - `__init__.py` — the **app factory** (`create_app`), blueprint registration, Jinja filters/globals, and the `/` index route.
  - `db.py` — SQLite access layer: `UserInfo`, `ServerInfo`, `UserFilters`, `UserColumnSettings`, plus `init_db()`, `migrate()`, and the `flask init-db` CLI command.
  - `sql/` — `CREATE TABLE` scripts for the four tables (`user`, `user_filters`, `user_column_settings`, `server`).
  - `views/` — one module per blueprint plus helpers.
    - `explore.py` (`/explore`) — families/samples/functions browsing, search, single-entry pages, CFG dot-graph endpoints.
    - `analyze.py` (`/analyze`) — job creation: 1vsN, 1vs1, cross-compare, unique blocks, query-by-upload.
    - `data.py` (`/data`) — jobs, result rendering + filtering, import/export, submit, link hunt, diagram serving. Largest module.
    - `authentication.py` (`/`) — login/register/logout/settings and **all authorization decorators**.
    - `administration.py` (`/admin`) — user management, server settings, per-user filter/column settings, maintenance jobs.
    - `api.py` (`/api`) — token-authenticated **passthrough** to the MCRIT backend REST API.
    - `pagination.py` / `cursor_pagination.py` — the two pagination models (see "Key concepts").
    - `utility.py` — client construction helpers, request-param parsers, CFG node coloring, path setup.
    - `MatchReportRenderer.py` — PIL-based rendering of the stacked match diagram PNGs.
    - `ScoreColorProvider.py`, `cross_compare.py`, `cfg_explorer_detector.py` — presentation helpers.
  - `templates/` — Jinja2 templates. `base.html` is the layout; `table/` holds reusable row/header macros; `js/` holds script partials.
  - `static/` — **vendored** front-end assets (Bootstrap 5.0.2, jQuery, jQuery-UI, DataTables, Dropzone, Font Awesome, SortableJS, `trace_CFG/` from CFGExplorer) plus project CSS/JS.
- `instance/` — runtime state, **git-ignored**: `mcritweb.sqlite`, `cache/` (results + diagrams), `temp/` (uploads, reports). Optional `instance/config.py` overrides app config.
- `tests/` — a single unittest module (see "Testing" — it is currently stale).
- `docs/manual/` — the user manual (markdown + screenshots), for readers on GitHub.
- `docs/agents/` — configuration read by the agent skills: issue tracker, triage labels, domain-doc layout.
- `mcritweb/templates/help.html` — a **hand-maintained duplicate** of `docs/manual/README.md`, served at `/admin/help`, with the same screenshots copied to `static/images/help/`. Edit both or they drift.
- `setup.py`, `requirements.txt`, `flask_env.sh`, `Makefile` — build/run config.

## Development setup

The README states Python 3.8+; the reference deployment (`docker-mcrit`) runs **Python 3.12**. Target 3.11/3.12 for anything new.

```bash
pip install -r requirements.txt
```

A running MCRIT backend (server + worker + MongoDB) is required for essentially every page beyond login/register. Without it, `mcrit_server_required` flashes an error and redirects to the index.

## Common commands

```bash
source ./flask_env.sh     # sets FLASK_APP=mcritweb, FLASK_DEBUG=1
flask init-db             # once, before first use — creates instance/mcritweb.sqlite
flask run                 # http://127.0.0.1:5000/
python -m pytest          # the offline suite, no backend needed
ruff check .              # config in ruff.toml; CI runs exactly this
```

The first browser visit redirects to `/register`; the first registered user automatically becomes `admin` and configures the backend URL/token in the same form.

Optional: set `PROFILER=True` in `instance/config.py` while `FLASK_DEBUG=1` to enable Werkzeug's `ProfilerMiddleware` (output in `instance/profiler/`).

## Architecture primer

- **App factory + blueprints.** `create_app()` builds the app, calls `db.init_app` and `db.migrate`, then registers the six blueprints. There is no ORM and no Flask extension for auth — everything is hand-rolled around `sqlite3` and `flask.session`.
- **Every view builds its own client.** The recurring one-liner is:
  ```python
  client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
  ```
  The username is forwarded so the backend can attribute jobs. Keep this pattern — do not cache a module-level client, since the server URL/token are read from the DB per request.
- **Request → job → result.** Long-running operations (matching, cross-compare, unique blocks, submissions) return a `job_id`; views redirect to `data.job_by_id` with a `refresh=N` parameter, and the job page polls until the result is ready. Result rendering dispatches on the `job_info.parameters` prefix in `data.result()`.
- **Result caching.** Fetched result JSON is written to `instance/cache/results/`, and match diagrams are rendered once to `instance/cache/diagrams/<job_id>[-famid_N|-samid_N|-funid_N].png`. Both are keyed by `job_id` and never invalidated — a changed renderer needs the cache cleared to be visible.
- **Filtering happens client-of-backend side.** `MatchingResult.setFilterValues()` / `.applyFilterValues()` (from `mcrit`) are driven by query parameters, falling back to the user's stored `UserFilters` when no filter params are present.

## Key concepts

**The domain vocabulary lives in [`CONTEXT.md`](CONTEXT.md)** — Family, Sample, Function, Query, Job, MinHash, PicHash, Band, Library, the three tokens, roles and operation mode. Read it before naming anything. What follows is the mechanism behind those terms, not their definitions.

- **Role enforcement** — decorators in `authentication.py`: `login_required`, `visitor_required`, `contributor_required`, `admin_required`, plus `token_required` (API) and `multi_user`. `mcrit_server_required` (in `utility.py`) checks backend reachability. Apply the **narrowest** role a route needs, and place the role decorator **before** `mcrit_server_required` so authorization is settled without a backend round-trip.
- **Where the settings live** — operation mode, both server-side tokens and the backend URL are columns on the single-row `server` table; per-user tokens are `user.apitoken`. `multi_user` blocks registration in single-user mode.
- **Two paginations** — `CursorPagination` (cursor-based, for backend `search_*` endpoints; supports prefixes so several tables can paginate on one page) and `Pagination` (offset-based, for slicing in-memory result lists). Use `CursorPagination` for anything backed by a backend search.
- **User column settings** — `UserColumnSettings` lets each user pick and order the columns of seven tables. Positions are integers, `-1` meaning "not active".
- **User filters** — `UserFilters` stores the defaults; `MatchingResult.setFilterValues()` / `.applyFilterValues()` apply them.

## Code conventions

- **Python:** 4-space indent, no linter or formatter is configured in this repo (no `ruff.toml`, no `.pylintrc`). Match the surrounding style rather than reformatting; do **not** introduce a repo-wide reformat as a side effect of a change.
- **Templates:** Jinja2 with Bootstrap 5 markup. Put reusable table rows/headers in `templates/table/` as macros and import them; do not copy row markup between pages.
- **Front-end:** no build step, no npm, no bundler. All libraries are vendored under `static/` and included via `url_for('static', ...)` in `base.html`. Do not add a CDN link (deployments are expected to work offline) and do not add a toolchain without being asked.
- **Route naming:** blueprint + snake_case function; always build URLs with `url_for(...)`, never string concatenation.
- **User feedback:** `flash(msg, category=...)` with categories `error` / `warning` / `success` / `info` — `base.html` maps these to Bootstrap alert classes.
- **Request parsing:** use the `parse_*_query_param` / `parse_*_post_param` helpers in `utility.py` instead of ad-hoc `request.args.get` + `int()`.
- **Logging:** the codebase uses bare `print()` in several places. Prefer `current_app.logger` for anything new; don't mass-convert existing calls.
- **License:** GPL-3.0-only.

## Web-specific guardrails

- **Autoescaping is your safety net — `|safe` disables it.** Existing uses (`node_colors|safe`, `params_list|safe`, `selected_ids|safe`) inject server-side JSON into `<script>` blocks. For any *new* value crossing into JavaScript, use `{{ value|tojson }}`, which escapes correctly for a script context. Never pass user- or backend-supplied strings through `|safe`.
- **There is no CSRF protection.** No `flask-wtf`, no CSRF tokens. State-changing routes are plain `POST` forms (`modifySample`, `modifyFamily`, `change_user_role`, `delete_user`, `change_server`, …). Be aware of this when adding destructive endpoints, and keep them `POST`-only rather than making them reachable by `GET`. Note that a few existing delete/role routes are `GET` — do not copy that pattern for new ones.
- **`SECRET_KEY` defaults to `'dev'`** and is only overridden if the operator ships an `instance/config.py`. Session cookies are signed with it. Do not add features that store anything sensitive in the session on top of this default.
- **Never log or render secrets:** user API tokens, the server token, password hashes. `ServerInfo.__str__` contains tokens — do not `print` or flash it.
- **Uploads** land in `instance/temp/uploads/` named by SHA-256. The `visitor` role is capped at 1 MiB per query upload (`analyze.query`); keep that check in place when touching the upload paths.
- **The `/api` blueprint is a passthrough, not an API of its own.** When the backend `McritClient` gains a method, extend the router in `api.py` by adding a regex branch — keep paths and parameter names aligned with the backend's REST API rather than inventing new ones.
- **Validate IDs before use.** Route converters use `<int(signed=True):...>` where negative IDs are meaningful (query samples have negative `sample_id`). Check `client.isSampleId` / `isFamilyId` / `isFunctionId` before acting on user-supplied IDs.

## Database changes

The SQLite schema is versioned by hand — there is no migration framework. Adding or changing a column means touching **all** of:

1. `mcritweb/sql/create_table_*.sql` — the fresh-install schema.
2. The corresponding class in `mcritweb/db.py` (`fromDb` / `fromDict` / `toDict` / `saveToDb`).
3. `db.migrate()` — an idempotent `ALTER TABLE` / `CREATE TABLE` guarded by a check, so existing deployments upgrade on next start.
4. The README "Version History" entry, flagging the DB change (existing entries use `BREAKS DB -> ...`).

Adding a **table column setting** additionally means updating `UserColumnSettings._default_settings`, `create_table_user_column_settings.sql`, and the relevant row/header macros in `templates/table/`. The `sql/` scripts start with `DROP TABLE IF EXISTS` — they are for initialization only and must never be run against a populated database.

## Testing

`python -m pytest` runs the suite with **no backend and no network** — pagination, user filters, the app-factory fixtures in `tests/conftest.py`, and `testMigrations.py`, which upgrades databases built in historical schemas (transcribed from release tags, not read from git — a CI checkout has no tags). `pytest.ini` maps the existing `test*.py` naming; keep it rather than renaming to `test_foo.py`. The `Makefile` targets reference `nose` (dead on modern Python) and a `.pylintrc` that does not exist — treat the `Makefile` as stale.

**Adding a route means adding a row to `tests/routePolicy.py`** — who may call it, and whether it writes. `testRoutePolicy.py` fails on any endpoint in the url_map without one. That table is the record of the current access policy; change a value only together with the code, so it keeps describing reality.

Coverage is thin and nothing exercises a real backend, so for anything touching views or templates still **verify by exercising the app**: `flask run` against a reachable MCRIT backend and walk the affected pages. When changing shared template macros (`table/*.html`), check every page that imports them — a macro is typically used by 3–5 templates. Results are cached under `instance/cache/` and never invalidated, so clear it when validating result rendering.

CI (`.github/workflows/test.yml`) runs `ruff check .` plus the suite on Python 3.11 and 3.12. There is deliberately **no `ruff format` check** — this codebase has never been formatted and reflowing it would bury the history of every file. Keep `ruff check .` clean; the rule set in `ruff.toml` mirrors mcrit's.

## Versioning & releases

- The version lives in `setup.py` and is **parsed at runtime** by `get_mcritweb_version_from_setup()` (regex on `version="X.Y.Z",`) — keep that literal format intact.
- A release adds a dated entry at the top of the README "Version History" (` * YYYY-MM-DD vX.Y.Z: <summary>`) and bumps `setup.py`. Historic commit message for this: `bump X.Y.Z`.
- **Do not bump the version unless explicitly asked.**
- MCRITweb is **deployed from a checkout** — a container image or a local clone — and no wheel or sdist is ever built or published. `setup.py` exists for the runtime version string and for `pip install -e .`; its `packages` list is not a distribution concern.
- `mcrit>=1.5.3` is pinned in both `setup.py` and `requirements.txt` — the two must stay in sync. MCRITweb consumes backend data classes (`MatchingResult`, `SampleEntry`, `FunctionEntry`, `UniqueBlocksResult`, …) directly, so a backend release can break rendering; when a fix depends on new backend behavior, raise the floor in both files and say so in the changelog entry.
- `flask==2.2.5` and `werkzeug==2.3.3` are **hard-pinned**. Do not upgrade them opportunistically — the codebase uses APIs that later versions changed.

## Agent guardrails

- **Never** run `git commit`, `git push`, or open a PR unless explicitly instructed.
- **Never** commit anything from `instance/` (SQLite DB, uploads, cached results/diagrams) or an `instance/config.py`.
- **Do not** modify vendored assets under `static/` (Bootstrap, jQuery, DataTables, Dropzone, Font Awesome, SortableJS, `trace_CFG/`); they carry their own licenses.
- **Do not** change matching or scoring semantics here — MCRITweb only presents what the backend computes. Score→color mappings (`ScoreColorProvider`, `cross_compare.score_to_color`) are presentation and may change; scores themselves may not.
- When work depends on backend behavior, read `../mcrit` rather than guessing at `McritClient`'s surface.
- Clear `instance/cache/` when validating changes to result rendering or diagram generation — otherwise you will be looking at stale output.

## Agent skills

### Issue tracker

GitHub Issues on `fkie-cad/mcritweb`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical labels, used as-is; `wontfix` already exists in the repo. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — the glossary is [`CONTEXT.md`](CONTEXT.md), decisions are in [`docs/adr/`](docs/adr/). See `docs/agents/domain.md` for how the skills consume them.

## Related repositories (reference only)

- [mcrit](https://github.com/danielplohmann/mcrit) — core server, worker, Python client, CLI. MCRITweb is a client of it.
- [docker-mcrit](https://github.com/danielplohmann/docker-mcrit) — the recommended deployment: MongoDB + mcrit-server + mcrit-worker + mcritweb behind NGINX.
- [mcrit-plugins](https://github.com/danielplohmann/mcrit-plugin) — IDA Pro integration plugin (a sibling client of the same backend).
- [smda](https://github.com/danielplohmann/smda) — the disassembler producing the `SmdaReport` format handled in submit/query.
- [mcrit-data](https://github.com/danielplohmann/mcrit-data) — ready-to-use reference data.
