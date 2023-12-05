import os
import datetime

from flask import Flask, render_template, g, redirect, url_for, request
from flask_dropzone import Dropzone

from . import db
from .views import explore, analyze, authentication, administration, data, api
from .views.utility import ensure_local_data_paths, get_mcritweb_version_from_setup, get_server_url, get_server_token, get_username

from mcrit.client.McritClient import McritClient
from mcrit.storage.SampleEntry import SampleEntry

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

    @app.route('/', methods=('GET', 'POST'))
    def index():
        if db.is_first_user():
            return redirect(url_for("authentication.register"))
        if request.method == 'POST':
            return redirect(url_for("explore.search", query=request.form["Search"]))
        else:
            client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
            jobs = client.getQueueData(0, 5, method="getMatchesForSample", state="finished", ascending=False)
            samples_by_id = {}
            for job in jobs:
                if job.sample_ids is not None:
                    for sample_id in [sid for sid in job.sample_ids if sid not in samples_by_id]:
                        samples_by_id[sample_id] = client.getSampleById(sample_id)
            families_by_id = {}
            for job in jobs:
                if job.family_id is not None:
                    families_by_id[job.family_id] = client.getFamily(job.family_id)
            results = client.search_samples("", is_ascending=False, cursor=None, sort_by="sample_id", limit=5)
            latest_samples = []
            for sample_dict in results['search_results'].values():
                latest_samples.append(SampleEntry.fromDict(sample_dict))
            return render_template("index.html", samples=samples_by_id, families=families_by_id, latest_samples=latest_samples, jobs=jobs)

    return app