import datetime
import os

from flask import Flask, g, redirect, render_template, request, send_from_directory, url_for
from markupsafe import escape


def create_app(test_config=None, instance_path=None):
    # NOTE: these are imported here rather than at module scope on purpose. Importing any
    # mcritweb submodule executes this file first, so module-level blueprint imports would
    # drag the entire application stack (mcrit, smda, numpy, PIL, networkx) into every
    # import - including a test that only wants a pure-python helper. See issue #88.
    from flask_dropzone import Dropzone
    from mcrit.storage.SampleEntry import SampleEntry

    from . import db, manual
    from .csrf import CsrfProtect
    from .secret_key import INSECURE_DEFAULT, load_or_create_secret_key
    from .views import administration, analyze, api, authentication, data, explore
    from .views.client import get_client
    from .views.utility import ensure_local_data_paths, get_mcritweb_version_from_setup

    # create and configure the app
    # instance_path is overridable so tests get their own cache/temp/uploads tree
    # instead of writing into the deployment's instance folder
    app = Flask(__name__, instance_relative_config=True, instance_path=instance_path)
    app.config.from_mapping(
        SECRET_KEY=INSECURE_DEFAULT,
        DATABASE=os.path.join(app.instance_path, 'mcritweb.sqlite'),
        # the session cookie is not needed by any script we ship, and a cross-site
        # navigation has no business carrying it. Defence in depth behind the CSRF
        # token, not a replacement for it - "Lax" still permits top-level GET.
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_HTTPONLY=True,
        # the session cookie is the entire proof of identity, and the reference
        # deployment (docker-mcrit) terminates TLS in NGINX in front of the app, so it
        # should never travel in the clear. Not while debugging, though: `flask_env.sh`
        # sets FLASK_DEBUG=1 for a local run over plain HTTP, where a secure-only cookie
        # is never sent back and login fails with nothing to point at. Set it explicitly
        # in instance/config.py to override either way.
        SESSION_COOKIE_SECURE=not app.debug,
        # Werkzeug rejects a larger body with 413 before buffering it. This is a ceiling
        # on absurdity rather than a tuned limit: it applies to every route uniformly,
        # and /data/import takes whole-corpus exports, so it has to clear those. The
        # per-role cap below is the fine-grained control.
        MAX_CONTENT_LENGTH=1024 * 2**20,
        # Per-role ceiling on a query upload, in bytes. A role absent from the mapping is
        # uncapped beyond MAX_CONTENT_LENGTH. Issue #19: this was hardcoded at 1 MiB for
        # visitors, which is the right default but the wrong place for it.
        QUERY_UPLOAD_LIMITS={'visitor': 1 * 2**20},
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)

    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # To enable profiling, put "PROFILER=True" in your config.py (stored in instance folder)
    profiling = False
    try:
        profiling = app.config.get("PROFILER")
    except KeyError:
        pass

    if app.debug and profiling:
        from werkzeug.middleware.profiler import ProfilerMiddleware
        app.config["PROFILE"] = True
        profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "instance", "profiler")
        os.makedirs(profile_dir, exist_ok=True)
        app.wsgi_app = ProfilerMiddleware(
            app.wsgi_app,
            restrictions=[30],
            profile_dir=profile_dir,
            filename_format="{method}-{path}-{time:.0f}-{elapsed:.0f}ms.prof",
        )

    # ensure the instance and cache folders exists
    ensure_local_data_paths(app)

    # after the config has loaded, so an explicit key in instance/config.py wins
    if app.config['SECRET_KEY'] == INSECURE_DEFAULT:
        app.config['SECRET_KEY'] = load_or_create_secret_key(app.instance_path)

    csrf = CsrfProtect(app)
    # authenticates by `apitoken` header, never by the session cookie, so a
    # cross-site request has nothing to ride on. See mcritweb/csrf.py.
    csrf.exempt(api.bp)

    db.init_app(app)
    db.migrate(app)
    app.register_blueprint(explore.bp)
    app.register_blueprint(analyze.bp)
    app.register_blueprint(authentication.bp)
    app.register_blueprint(administration.bp)
    app.register_blueprint(data.bp)
    app.register_blueprint(api.bp)
    app.config['MCRITWEB_VERSION'] = get_mcritweb_version_from_setup()
    app.config['DROPZONE_DEFAULT_MESSAGE'] = "Drop file or click here to import"
    app.config['DROPZONE_REDIRECT_VIEW'] = 'data.import_complete'
    app.config['DROPZONE_ALLOWED_FILE_CUSTOM'] = True
    app.config['DROPZONE_ALLOWED_FILE_TYPE'] = ""
    # sends the token as an X-CSRF-Token header on every upload; it reads the token
    # through app.extensions["csrf"], which CsrfProtect registered above
    app.config['DROPZONE_ENABLE_CSRF'] = True
    Dropzone(app)

    # The family type-ahead (static/autocomplete.js) builds every suggestion as an HTML
    # string and hands it to innerHTML, so a name that *is* markup becomes script in the
    # reader's browser as soon as they type a matching character. That file is vendored
    # upstream code and is not ours to patch (see AGENTS.md), so the escaping happens on
    # the way in and the widget only ever sees escaped names.
    #
    # |tojson is not a substitute and never was: it makes the name a correct JS *string*,
    # and the sink is one innerHTML further on. Both fields matter and both are escaped
    # here - the label is written into the button's text, and the same value is also
    # interpolated into data-label="..." / data-value="...", where a bare quote is an
    # event handler and needs no angle bracket at all.
    #
    # Round-tripping is unaffected: the browser decodes the entities when it parses the
    # attribute, so the name the widget writes into the field on select, and the form
    # then posts, is the original. *Display* is not unaffected, and saying otherwise
    # would be wrong. The widget slices the escaped label at offsets it measured in that
    # same escaped string (autocomplete.js:70-77), so a lookup ending inside an entity
    # cuts it in half and the suggestion reads "R&amp;D" for a family named "R&D".
    # Matching degrades the same way - a lookup containing one of the five escaped
    # characters no longer substring-matches. Neither can be fixed from here:
    # `item.label` (:110) is the one value the matcher (:114), the highlighter (:70-77)
    # and the attribute (:90) all read, so there is no field to point at raw text for
    # matching and escaped text for rendering. tests/testAutocompleteEscaping.py pins
    # the behaviour rather than leaving it to this comment.
    #
    # `escape` stringifies, so a non-string name would arrive as e.g. "None" where the
    # loop this replaced passed it through. Family names are always strings off the
    # backend, and the old code handed `null` to removeDiacritics(), which threw and took
    # the whole type-ahead with it - so this is not a regression, but it is a change.
    @app.template_filter('autocomplete_items')
    def autocomplete_items(names):
        return [{'label': str(escape(name)), 'value': str(escape(name))} for name in names]

    @app.template_filter('silent')
    def silent(input):
        return ""

    @app.template_filter('capitalize_all')
    def capitalize_all(input):
        return " ".join(map(str.capitalize, input.split(" ")))

    @app.template_filter('getattr')
    def _getattr(obj, attr, default):
        return getattr(obj, attr, default)

    @app.template_filter('date')
    def date(input):
        if isinstance(input, datetime.datetime):
            return input.strftime("%Y-%m-%d")
        elif isinstance(input, str):
            return input[:10]

    @app.template_filter('time')
    def time(input):
        return input[11:19]

    @app.template_filter('date_time')
    def date_time(input):
        return input[:10] + ' ' + input[11:19]
    

    @app.template_global()
    def join_hint_strings(list_of_strings):
        return "\n".join(sorted(list_of_strings))

    # the user manual. Public, and deliberately not under /admin: it was the only
    # route in that blueprint without an admin gate, which made the prefix a lie.
    # Rendered from docs/manual/README.md, which is the only copy - see issue #91.
    @app.route('/help')
    def help():
        return render_template('help.html', manual=manual.render(url_for('help_image', filename='')))

    # the manual's screenshots stay next to the markdown so its relative links work
    # for readers on GitHub, which is that copy's whole purpose
    @app.route('/help/images/<path:filename>')
    def help_image(filename):
        return send_from_directory(manual.IMAGE_DIRECTORY, filename)

    @app.route('/', methods=('GET', 'POST'))
    def index():
        if db.is_first_user():
            return redirect(url_for("authentication.register"))
        if request.method == 'POST':
            return redirect(url_for("explore.search", query=request.form["Search"]))
        elif g.user is None or g.user.role == 'pending':
            # index.html shows these callers nothing, so querying the backend for
            # them only spends its time. A role decorator cannot do this job: index
            # is also the first-user entry point and has to reach the redirect above.
            return render_template("index.html", samples={}, families={}, latest_samples=[], jobs=[])
        else:
            client = get_client()
            jobs = client.getQueueData(0, 5, method="getMatchesForSample", state="finished", ascending=False)
            samples_by_id = {}
            families_by_id = {}
            latest_samples = []
            if jobs:
                for job in jobs:
                    if job.sample_ids is not None:
                        for sample_id in [sid for sid in job.sample_ids if sid not in samples_by_id]:
                            samples_by_id[sample_id] = client.getSampleById(sample_id)
                for job in jobs:
                    if job.family_id is not None:
                        families_by_id[job.family_id] = client.getFamily(job.family_id)
            
            sample_results = client.search_samples("", is_ascending=False, cursor=None, sort_by="sample_id", limit=5)
            if sample_results:
                for sample_dict in sample_results['search_results'].values():
                    latest_samples.append(SampleEntry.fromDict(sample_dict))
            return render_template("index.html", samples=samples_by_id, families=families_by_id, latest_samples=latest_samples, jobs=jobs)

    return app