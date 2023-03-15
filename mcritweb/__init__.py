import os
from . import db
from .views import explore, analyze, authentication, administration, data, api
from flask import Flask, render_template, g, redirect, url_for, request
from flask_dropzone import Dropzone

from .views.utility import ensure_local_data_paths, get_mcritweb_version_from_setup


dropzone = Dropzone()
def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'mcritweb.sqlite'),
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
    db.init_app(app)
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
    dropzone = Dropzone(app)

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

    @app.route('/', methods=('GET', 'POST'))
    def index():
        if db.is_first_user():
            return redirect(url_for("authentication.register"))
        if request.method == 'POST':
            return redirect(url_for("explore.search", query=request.form["Search"]))
        else:
            return render_template("index.html")

    return app