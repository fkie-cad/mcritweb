# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) over what a deployment sees:
the routes, the configuration keys in `instance/config.py`, and the SQLite schema. A release that
changes the schema, adds a dependency or changes a default that affects an existing deployment says
so in its entry, under **Upgrading**, because MCRITweb is deployed from a checkout and a pull that
only brings code is not the release that was tested.

Add your entry to `[Unreleased]` when the change merges, while the reasoning is still at hand,
rather than reconstructing it from the commit log at release time.

## [Unreleased]

### Added

- Pushing a `vX.Y.Z` tag now cuts the release. The workflow refuses to continue unless the tag
  matches `pyproject.toml`, `CHANGELOG.md` has a section for it, the commit is on `master` and CI
  passed there; it then builds the sdist and wheel, checks their metadata, installs the wheel into a
  clean environment to prove the templates, static assets and schema ship with the package, and
  creates the GitHub release from that version's changelog section with the generated contributor
  list appended and the artifacts attached. Nothing is published to PyPI: MCRITweb is deployed from
  a checkout. Pre-release tags (`v1.5.0rc1`) are marked as such. See `RELEASING.md`.
- A pull request that changes `mcritweb/` or `pyproject.toml` has to add a `CHANGELOG.md` entry or
  carry the `no-changelog` label; CI checks it.

### Changed

- Packaging metadata moved from `setup.py` to `pyproject.toml` (PEP 621), which is now the only
  place the version is declared: the running version shown on the server page and stored in the
  `server` table is read from it, through `get_mcritweb_version()`. `ruff.toml` and `pytest.ini`
  folded into the same file. `requirements.txt` stays, for `docker-mcrit` and anyone installing
  from a checkout without building the package, and a test keeps it identical to the declared
  dependencies. **Upgrading:** `pip install -r requirements.txt` still works; `pip install -e .`
  is now equivalent, and `pip install -e ".[dev]"` brings the test and lint tooling, which used
  to arrive as a side effect of `mcrit` and no longer does since MCRIT 1.8.0.
- The release history moved out of `README.md` into this file; the entries below are unchanged.

### Removed

- **Python 3.11 is no longer supported**; `requires-python` is `>=3.12`, and CI runs 3.12 to
  3.14. Nothing in MCRITweb needed 3.12 - the MCRIT ecosystem now shares a 3.12 floor so one
  interpreter serves every component, and the reference `docker-mcrit` deployment already runs it.

## Older releases

Recorded as they were written in the README at the time, newest first.

 * 2026-08-10 v1.4.8: Hardening, plus one bug older than the issue that found it. **One change affects existing deployments:** the session cookie is now `Secure`, so it is only sent over HTTPS. The reference `docker-mcrit` deployment terminates TLS in NGINX and is unaffected, and a local `flask run` is unaffected because the flag is off while `FLASK_DEBUG` is set - but an instance served over plain HTTP in production will not be able to log in until `SESSION_COOKIE_SECURE = False` is set in `instance/config.py`. Values crossing into JavaScript are now escaped for a script context (#85). That issue named eight `|safe` sites; there were fifteen, because a search for `|safe` does not find `| safe`, and two of the seven it missed were a real injection rather than hardening: family names went into a quoted JavaScript string literal on the family, sample and submit pages, so a family named with a quote in it could run script in another user's browser. Family names are chosen by whoever submits or renames a family, and are not validated here. Two new request-size ceilings, both configurable: `MAX_CONTENT_LENGTH` (1 GiB, enough for a whole-corpus import) makes an oversized body a 413 before it is buffered, where previously there was no limit at all; and `QUERY_UPLOAD_LIMITS` replaces the 1 MiB visitor cap that was hardcoded in `analyze.query`, as a `{role: bytes}` mapping with the same default (#19). Cross compare works again from the sample selection page: the sample list was built by joining two halves with a comma, so an empty half left a leading or trailing one, which `/analyze/start_cross_compare` has refused since v1.4.5 - it reported "select at least one sample" on a page where samples were plainly selected. The API passthrough's router branches are anchored, so a path merely *beginning* with a known one no longer dispatches to it, and it no longer prints the caller's username to stdout on every request. Adds 34 tests, for 239 in total.
 * 2026-08-07 v1.4.7: Lifts the Flask and Werkzeug pins that had held the project on a 2023 release (#27) - now `flask>=3.0` and `werkzeug>=3.0`, resolved against Flask 3.1.3 and Werkzeug 3.1.8. **Dependencies changed, so `pip install -r requirements.txt` has to be re-run and a container image rebuilt against this tag** - a deployment that pulls only code keeps the old Flask and is not running what this release was tested as. No application code needed changing to accommodate the upgrade. Python 3.13 and 3.14 join the CI matrix; 3.14 had been unreachable because Flask 2.2.5 calls `pkgutil.get_loader`, removed there. Two fixes to the upload paths, both older than this release: `/data/import` returned a server error for a file that was not JSON, or was JSON but not an object, and now reports it the way the completion page already did; and dropping an `.smda` report on the submit dropzone filled the base address but never family or version, because smda writes reports sorted and indented, which puts `metadata` past the 1024-byte window the browser sends - the browser now also sends a window cut from around `metadata`. Adds 14 tests over the upload paths, which nothing had exercised further than "the page renders", for 205 in total. Also points the Makefile at pytest and ruff instead of nose and pylint, and drops a deprecated positional `re.sub` count.
 * 2026-08-06 v1.4.6: **This release adds a dependency - `markdown` - so `pip install -r requirements.txt` has to be re-run, and a container image has to be rebuilt against this tag.** The app imports it at startup, so an environment that skips this will not boot. Fixes a crash that took down `/explore/search` for any query matching a sample, which had been there since the search page was written. Three more server errors fixed: editing a family or a sample with an empty form, and `/data/specific_export/<type>/<id>` for any type other than `family` or `samples`. The user manual is no longer maintained twice - `docs/manual/README.md` is the only copy and `/help` renders it, so the two can no longer drift, and the screenshots are stored once instead of twice (#91). It also now documents LinkHunt and Unique Blocks, neither of which had been described anywhere (#92).
 * 2026-08-06 v1.4.5: Bugfixes, no feature changes. **One affects results you may already have looked at:** cross compare passed the "only selected samples" checkbox to the backend as a string, and `"false"` is truthy, so an unticked box silently ran group-only matching - a different comparison from the one requested. The same bug set `force_recalculation` on nearly every job submission, which is why a repeated or double-clicked comparison queued a duplicate instead of reusing the finished job the backend already had (#97). Three crashes fixed: `/analyze/start_cross_compare` with no samples, or with a non-numeric sample list (#94); changing the role of a user who no longer exists, or to a role that does not exist (#95); and a 1-vs-1 or filtered result page whose matched functions have since been deleted, which now shows the "results are corrupted" page the cross-compare view already used instead of a server error (#96). That page's "Delete job data" button also worked again - it had pointed at a route that became POST-only in v1.4.3.
 * 2026-08-06 v1.4.4: Closes the CSRF hole (#83). Every state-changing request now needs a token bound to the session, so a page on another site can no longer act with a logged-in user's privileges - deleting samples or families, repointing the MCRIT backend, promoting an account or changing a password. **Two changes affect existing deployments:** `SECRET_KEY` no longer defaults to `'dev'` - an unset key is generated once and kept in `instance/secret_key`, which logs everyone out on the first start after upgrading; and the session cookie is now `SameSite=Lax`. Operators who set `SECRET_KEY` in `instance/config.py` are unaffected, and that remains the right answer for a multi-host deployment. Adds 38 tests and `docs/adr/0002-hand-rolled-csrf.md`, which records why the check is hand-rolled today and how it is meant to become `flask-wtf` when the Flask pin lifts (#27).
 * 2026-08-06 v1.4.3: Hardening and test foundation, no feature changes. **Four changes affect existing usage:** deleting a user, changing a role, deleting a job and the three maintenance jobs now require POST, so they can no longer be fired by anything that merely makes a browser fetch a URL; the API passthrough applies the role behind the token, refusing `pending` accounts entirely and requiring contributor to add a report; cached match diagrams need a session; and the documentation moved from `/admin/help` to `/help`. Fixed along the way: the settings page returned a server error after changing a username, password or default filter, an unconfirmed server reset raised instead of answering, and `/settings` carried an authorization decorator that never ran. Also adds an offline test suite (82 tests, no backend required) plus ruff and GitHub Actions CI.
 * 2026-08-04 v1.4.2: Adjusted for mcrit >= 1.5.3, where a matching report shares its entry objects between the full and the filtered match lists: the match diagram renderer no longer writes the negated query-report function_id back onto those shared entries, which would have corrupted the function_ids of query report tables. Also fixed a missing comma that merged the fastcluster and networkx requirements into one invalid entry.
 * 2025-12-10 v1.4.1: Can now start cross jobs where only selected samples are matched among each other (faster), minor fixes
 * 2025-12-09 v1.4.0: Customizable column setup for all tables per user, QoL improvements for cross jobs (start from SHA256 list, edit meta data in results view), minor fixes
 * 2025-08-22 v1.3.7: Bugfix for function compare page not rendering.
 * 2025-07-30 v1.3.6: Preselect sample in 1:N job, show matching score on function compare pages (if available), documentation accessible directly in mcritweb.
 * 2025-07-30 v1.3.5: Documentation now available within MCRITweb, links to search syntax besides the search fields. Function 1v1 shows match score.
 * 2025-01-21 v1.3.4: Fixed a bug in the job overview, where in-progress cross compare jobs would cause a server error (500)
 * 2024-03-19 v1.3.3: It is now possible to submit and query with SMDA reports through the WebUI. 
 * 2024-03-04 v1.3.2: Added safety checks for when there are no jobs to be rendered. 
 * 2024-01-26 v1.3.1: Fixed redundant queries in sample detail pages. Also minor convenience updates. 
 * 2024-01-26 v1.3.0: Adaptions for the 1.3.0 milestone release. It is now possible to trigger the PicHash/MinHash and Index rebuild jobs from the Server/Admin page.
 * 2024-01-09 v1.2.22: API passthrough for results can now also use compact flag (THX: @yankovs!).
 * 2024-01-02 v1.2.21: YARA rule generation for UniqueBlocks now uses the respective data class from backend, which fixes rendering bugs.
 * 2024-01-02 v1.2.20: Extended API passthrough for queue status, fixed username annotation for calls (THX: @yankovs!).
 * 2023-12-28 v1.2.19: Enabled API passthrough for binary query matching (THX: @yankovs!).
 * 2023-12-13 v1.2.18: Fixed special case with unique blocks job for empty sample list.
 * 2023-12-12 v1.2.17: Function Diff view should now work better for obfuscated functions with lots of unique instruction tokens.
 * 2023-12-05 v1.2.16: More expressive job tables, now showing recent data on index page.
 * 2023-12-01 v1.2.13: Contributor and above can now delete jobs, jobs also filterable by state.
 * 2023-11-29 v1.2.11: Ensure user filters exist when using them the first time (THX: @rootbsd!).
 * 2023-11-20 v1.2.10: Supporting back end API token via server settings. Now also using proper ORM for all SQLite interactions.
 * 2023-10-17 v1.2.9: Fix for empty job pages (THX: @yankovs!).
 * 2023-10-17 v1.2.8: Rewrite of Job view which should now perform much better on larger collections.
 * 2023-10-03 v1.2.2: Result can now filter to min number of samples as well.
 * 2023-10-02 v1.2.0: Milestone release for Virus Bulletin 2023.
 * 2023-09-18 v1.1.7: It's now possible to actually deactivate Minhash matching in jobs.
 * 2023-09-15 v1.1.6: Quality of Life improvements in several UI elements.
 * 2023-09-08 v1.0.21: All McritClient calls are now passing on usernames/apitokens to the backend.
 * 2023-08-30 v1.0.19: Clustering functions by ICFG connectivity when doing link hunt.
 * 2023-08-25 v1.0.15: Integrated link hunt to result display.
 * 2023-06-06 v1.0.7: Extended result filters for family name, function offsets, and unique family function hits.
 * 2023-06-06 v1.0.6: Bugfix for use of new MatchingResult methods when showing 1v1 results.
 * 2023-06-02 v1.0.5: Fixed ResultView for Query results. Slight improvement to Jobs table. Adjusted API passthrough for function collections.
 * 2023-05-12 v1.0.4: Extended API passthrough for creation of matching jobs in MCRIT.
 * 2023-05-08 v1.0.3: More consistent result filter behavior.
 * 2023-04-14 v1.0.2: Started working on documentation. Fixed minor things.
 * 2023-04-10 v1.0.0: Milestone release for Botconf 2023.
 * 2023-04-10 v0.15.0: Shaping user role visitor more towards a demo account: limited visibility of menus/content, disallowed username/password change, but allowing them to upload files for query, up to size 1MB.
 * 2023-03-24 v0.14.2: API forward for adding / updating SmdaReports.
 * 2023-03-23 v0.14.1: UserInfo database object introduced and exposing apitoken in the UI.
 * 2023-03-21 v0.14.0: API forward for querying multiple function_entries by function_id.
 * 2023-03-19 v0.12.3: API forward for single SmdaFunction queries.
 * 2023-03-17 v0.12.1: Fix for special case of not rendering function graph, fix for default filters if no DB entry found.
 * 2023-03-15 v0.12.0: User now have apitokens that can be used to interact with the MCRIT instance behind mcritweb via api-passthrough (BREAKS DB -> ALTER TABLE user ADD apitoken VARCHAR).
 * 2023-03-14 v0.11.1: API calls are now shown on rendered graphs
 * 2023-03-14 v0.11.0: Users may now store a preference for default result filters (BREAKS DB -> CREATE TABLE user_filters).
 * 2023-03-13 v0.10.6: Filtering of family/sample result table is now possible.
 * 2023-02-27 v0.10.5: Now showing if function matches are unique in a family.
 * 2023-02-21 v0.10.4: More fixes and usability improvements on match result pages.
 * 2023-02-17 v0.10.2: Various usability improvements on match result pages.
 * 2023-01-15 v0.9.13: Allow filtering matching results by score, number of family matches, and exclude library matches.
 * 2022-12-15 v0.9.10: Allow setting Minhash fuzziness for candidate selection.
 * 2022-12-13 v0.9.7: Allow matching of arbitrary functions by their IDs.
 * 2022-11-18 v0.9.5: Modify and Delete functions for samples and families.
 * 2022-11-03 v0.9.1: Improved Unique Blocks Isolation and added YARA generation.
 * 2022-10-14 v0.9.0: Initial public beta release.

[Unreleased]: https://github.com/fkie-cad/mcritweb/compare/v1.4.8...HEAD
