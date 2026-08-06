"""The access policy of every route, written down so it can be asserted.

This module is data, not tests - `testRoutePolicy.py` reads it. It is deliberately
not named `test*.py` so pytest does not collect it.

**What is recorded here is what the app does today**, derived by exercising every
route in `app.url_map` as each role and observing whether the request was admitted
or rejected. It is a baseline to review and argue with, not a statement that the
current behaviour is correct. Where the observed behaviour looks wrong, the row
carries a comment rather than a corrected value - change the value only together
with the code, so the test stays a description of reality.

Two facts per route:

`role`    the least privileged caller that gets past the gate. Authorization is
          settled before the view body runs, so this is observable without any
          backend or fixture data.

`writes`  whether the view changes state - the local SQLite database or the MCRIT
          backend - and, crucially, whether a plain GET is enough to do it. See
          issue #84. There is no CSRF protection anywhere in this application
          (flask-wtf is not a dependency and no template emits a token), so every
          WRITES_ON_GET row is reachable from any page a logged-in user visits,
          e.g. through an <img> tag.

Adding a route means adding a row here; `testRoutePolicy.py` fails on any endpoint
in the url_map that is missing, and on any row naming an endpoint that no longer
exists.
"""

# --- the least privileged caller a route admits ----------------------------------

PUBLIC = "public"                # no session needed at all
LOGGED_IN = "logged-in"          # any authenticated user, including role 'pending'
VISITOR = "visitor"              # visitor, contributor or admin
CONTRIBUTOR = "contributor"      # contributor or admin
ADMIN = "admin"                  # admin only
APITOKEN = "apitoken"            # not session-based: an `apitoken` request header

ROLE_ORDER = [PUBLIC, LOGGED_IN, VISITOR, CONTRIBUTOR, ADMIN]

# --- what a route changes --------------------------------------------------------

READ_ONLY = "read-only"
WRITES_ON_POST = "writes-on-post"   # the write is behind `if request.method == 'POST'`
WRITES_ON_GET = "writes-on-get"     # a bare GET is enough - issue #84

# Not recorded per route, because it is a property of a shared helper rather than of
# any one view: `utility.get_user_column_setup()` creates the caller's
# user_column_settings row when it is missing, and `authentication.settings` does the
# same for user_filters. Every table-rendering page therefore writes on its first
# visit by a given user. It is idempotent and not caller-controlled, so the write
# detector seeds those rows up front rather than treating each page as a writer.

# McritClient methods that change backend state or queue work. Used to detect a
# route that writes on GET without anyone having declared it, so keep it current
# when the client grows a new verb.
MUTATING_CLIENT_CALLS = {
    "addBinarySample",
    "addImportData",
    "addReport",
    "deleteFamily",
    "deleteJob",
    "deleteSample",
    "modifyFamily",
    "modifySample",
    "rebuildIndex",
    "recalculateMinHashes",
    "recalculateMinHashesForSample",
    "recalculatePicHashes",
    "requestMatchesCross",
    "requestMatchesForMappedBinary",
    "requestMatchesForSample",
    "requestMatchesForSampleVs",
    "requestMatchesForSmdaReport",
    "requestMatchesForUnmappedBinary",
    "requestUniqueBlocksForFamily",
    "requestUniqueBlocksForSample",
    "respawn",
    "updateFamily",
    "updateSample",
}

# Routes whose rejection is performed inside the view instead of by a decorator, so
# an unauthorized caller is redirected to the index rather than to /login. Both
# ratchets below only ever shrink: an entry that is no longer needed is a cleanup,
# a new entry is a regression. Both are empty - keep them that way.
IN_VIEW_GUARD = set()

# `@<role>_required` written above `@bp.route` never runs, because bp.route is
# applied first and registers the undecorated function.
KNOWN_INERT_DECORATORS = set()

ROUTE_POLICY = {
    # --- public surface ----------------------------------------------------------
    # Admits anyone, but index.html gates all content behind `{% if g.user %}` and
    # shows 'pending' only a holding message, so nothing leaks into the HTML. The
    # view does run getQueueData, a getSampleById/getFamily per job and
    # search_samples *before* rendering, so an anonymous hit still costs the backend
    # an N+1 round of queries whose results are discarded. A role decorator cannot
    # fix that on its own: index also performs the first-user redirect to /register,
    # which a gate in front of it would turn into a redirect to /login.
    "index": (PUBLIC, READ_ONLY),
    # /admin/help carries no decorator despite the prefix; it is the user manual.
    # Decided: move it out of the admin blueprint to its own top-level route.
    "admin.help": (PUBLIC, READ_ONLY),
    # send_from_directory over instance/cache/diagrams with no decorator: any cached
    # match diagram is downloadable without a session by anyone who knows a job_id.
    # Decided: gate it, at least visitor_required.
    "data.diagram_file": (PUBLIC, READ_ONLY),
    "authentication.login": (PUBLIC, WRITES_ON_POST),
    # multi_user only blocks registration in single-user mode, it is not an auth gate
    "authentication.register": (PUBLIC, WRITES_ON_POST),
    "static": (PUBLIC, READ_ONLY),
    "dropzone.static": (PUBLIC, READ_ONLY),

    # --- authenticated, any role including 'pending' -----------------------------
    "authentication.logout": (LOGGED_IN, WRITES_ON_GET),   # session teardown, by design
    "authentication.settings": (LOGGED_IN, READ_ONLY),
    "admin.change_username": (LOGGED_IN, WRITES_ON_POST),   # GET raises 400 on request.form
    "admin.change_password": (LOGGED_IN, WRITES_ON_POST),   # GET raises 400 on request.form
    "admin.change_default_filter": (LOGGED_IN, WRITES_ON_POST),
    "admin.change_column_settings": (LOGGED_IN, WRITES_ON_POST),
    "admin.reset_column_settings": (LOGGED_IN, WRITES_ON_POST),

    # --- visitor and above -------------------------------------------------------
    "explore.families": (VISITOR, READ_ONLY),
    "explore.family_by_id": (VISITOR, READ_ONLY),
    "explore.samples": (VISITOR, READ_ONLY),
    "explore.sample_by_id": (VISITOR, READ_ONLY),
    "explore.functions": (VISITOR, READ_ONLY),
    "explore.function_by_id": (VISITOR, READ_ONLY),
    "explore.fetchDotGraph": (VISITOR, READ_ONLY),
    "explore.findLoops": (VISITOR, READ_ONLY),
    "explore.getPicBlockMatches": (VISITOR, READ_ONLY),
    "explore.search": (VISITOR, READ_ONLY),
    "explore.statistics": (VISITOR, READ_ONLY),
    "analyze.compare": (VISITOR, READ_ONLY),
    "analyze.compare_versus": (VISITOR, READ_ONLY),
    "analyze.compare_submit_query": (VISITOR, READ_ONLY),
    "analyze.cross_compare": (VISITOR, READ_ONLY),
    "analyze.cross_compare_from_hash_list": (VISITOR, READ_ONLY),
    # Job submission by GET. Not destructive, but each hit queues backend work.
    "analyze.compare_all": (VISITOR, WRITES_ON_GET),
    "analyze.compare_vs": (VISITOR, WRITES_ON_GET),
    "analyze.blocks_family": (VISITOR, WRITES_ON_GET),
    "analyze.blocks_sample": (VISITOR, WRITES_ON_GET),
    # Also raises UnboundLocalError on `job_id` when no samples are given.
    "analyze.start_cross_compare": (VISITOR, WRITES_ON_GET),
    "analyze.query": (VISITOR, WRITES_ON_POST),
    "data.jobs": (VISITOR, READ_ONLY),
    "data.job_by_id": (VISITOR, READ_ONLY),
    "data.result": (VISITOR, READ_ONLY),
    "data.linkhunt": (VISITOR, READ_ONLY),
    "data.match_functions": (VISITOR, READ_ONLY),

    # --- contributor and above ---------------------------------------------------
    "data.submit": (CONTRIBUTOR, WRITES_ON_POST),
    "data.submit_or_query": (CONTRIBUTOR, WRITES_ON_POST),
    "data.import_view": (CONTRIBUTOR, WRITES_ON_POST),
    "data.import_complete": (CONTRIBUTOR, READ_ONLY),
    "data.export_view": (CONTRIBUTOR, READ_ONLY),
    "data.specific_export": (CONTRIBUTOR, READ_ONLY),
    "data.request_filename_info": (CONTRIBUTOR, READ_ONLY),   # classifies a posted filename
    "data.delete_job_by_id": (CONTRIBUTOR, WRITES_ON_GET),    # deletes a job by GET
    "explore.modifyFamily": (CONTRIBUTOR, WRITES_ON_POST),
    "explore.modifySample": (CONTRIBUTOR, WRITES_ON_POST),

    # --- admin only --------------------------------------------------------------
    "admin.users": (ADMIN, READ_ONLY),
    "admin.server": (ADMIN, READ_ONLY),
    "admin.delete_user": (ADMIN, WRITES_ON_GET),      # deletes a user by GET
    "admin.change_user_role": (ADMIN, WRITES_ON_GET), # grants any role by GET
    "admin.change_server": (ADMIN, WRITES_ON_POST),
    "admin.reset_server": (ADMIN, WRITES_ON_POST),
    "admin.schedule_rebuild_index": (ADMIN, WRITES_ON_GET),
    "admin.schedule_recalc_minhashes": (ADMIN, WRITES_ON_GET),
    "admin.schedule_recalc_pichashes": (ADMIN, WRITES_ON_GET),

    # --- token authenticated -----------------------------------------------------
    # Dispatches an allowlist of ~18 path patterns to the backend, including its
    # write endpoints, gated only by a valid `apitoken` header. The token's owner is
    # looked up but their role is never consulted, so a 'pending' user's token
    # carries the same authority as an admin's.
    # Decided: gate per pattern, mirroring the web policy - reads and query/* at
    # visitor, the addReport POST at contributor, 'pending' refused outright.
    "api.api_router": (APITOKEN, WRITES_ON_POST),
}
