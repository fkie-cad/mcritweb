import functools
import os
import re
import sqlite3
import uuid
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from mcritweb import db
from mcritweb.db import ServerInfo, UserColumnSettings, UserFilters, UserInfo, generate_apitoken
from mcritweb.views.utility import get_session_user_id

bp = Blueprint('authentication', __name__, url_prefix='/')

#: Every role this application recognises, weakest first - the ladder described in
#: CONTEXT.md. The decorators below and `token_required` compare against these
#: names, so a value outside the list fails every check: an account holding one can
#: reach nothing and no page explains why. Anything writing `user.role` validates
#: against this first. See issue #95.
KNOWN_ROLES = ('pending', 'visitor', 'contributor', 'admin')

#: The roles whose API token is worth anything. `token_required` is the authority; the
#: settings page reads it too, so the page cannot show a token to someone whose token
#: does not work, or - the way it went wrong - hide one that does. `pending` gets
#: nothing, as in the web UI.
API_ROLES = ('visitor', 'contributor', 'admin')


@bp.before_app_request
def set_is_first_user():
    g.first_user = db.is_first_user()


@bp.before_app_request
def set_operation_mode():
    if not g.first_user:
        server_info = ServerInfo.fromDb()
        g.operation_mode = server_info.operation_mode


def multi_user(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not g.first_user and g.operation_mode == 'single':
            flash('You are in single user mode, no need to register a user.', category='error')
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view


@bp.route('/register', methods=('GET','POST'))
@multi_user
def register():
    user_id = session.get("user_id", None)
    if user_id is not None and not g.first_user:
        error = 'You already have a registered account.'
        flash(error, category='error')
        return redirect(url_for('index'))
    server_info = ServerInfo.fromDb()
    is_registration_token_required = False
    if server_info:
        is_registration_token_required = server_info.registration_token not in [None, ""]
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['inputPassword1']
        provided_registration_token = ""
        if 'registrationToken' in request.form:
            provided_registration_token = request.form['registrationToken']
        error = None
        if not username:
            error = 'Username is required.'
        elif re.match(r"^(?=[a-zA-Z0-9._]{3,20}$)(?!.*[_.]{2})[^_.].*[^_.]$", username) is None:
            error = "Username has wrong format. Must be 3-20 characters, alphanumeric with dots and underscores allowed, but cannot start or end with dots/underscores, nor contain two of them in a row."
        elif username.lower() in ["guest", "mcritweb", "mcrit", "admin", "root", "system", "test", "demo"]:
            error = "Username is reserved."
        elif not password:
            error = 'Password is required.'
        elif not password == request.form['inputPassword2']:
            error = 'The passwords do not match. No new user was created.'
        elif is_registration_token_required and server_info.registration_token != provided_registration_token:
            error = 'Invalid registration token provided. No new user was created.'
        if error is None:
            user_info = UserInfo()
            user_info.username = username
            user_info.password = generate_password_hash(password)
            # TODO make it configurable what the default role for new users should be, but stick with pending for now
            user_info.role = "pending"
            if g.first_user:
                user_info.role = "admin"
                server_info = ServerInfo()
                server_info.url = request.form['url']
                server_info.operation_mode = request.form['operationMode']
                server_info.registration_token = request.form['setRegistrationToken'] if request.form['setRegistrationToken'] else ""
                server_info.server_token = request.form['mcritServerToken'] if request.form['mcritServerToken'] else ""
                server_info.server_uuid = str(uuid.uuid4())
                server_info.server_version = current_app.config['MCRITWEB_VERSION']
                try:
                    server_info.saveToDb()
                except Exception:
                    # never surface the exception text: /register is unauthenticated and the
                    # message can carry the database path or SQL fragments
                    current_app.logger.exception("Failed to persist server settings during first-user registration")
                    error = "Server values invalid. Please check the server settings and try again."
            if error is None:
                user_info.registered = datetime.utcnow()
                user_info.last_login = 'no login'
                user_info.apitoken = generate_apitoken()
                try:
                    user_info.saveToDb()
                except sqlite3.IntegrityError:
                    error = f"User {username} is already registered."
                else:
                    return redirect(url_for("authentication.login"))
        flash(error, category='error')
    proposed_registration_token = ""
    if g.first_user:
        proposed_registration_token = str(uuid.uuid4())
    query_token = request.args.get('token')
    if query_token is None or not re.match(r"^[a-zA-Z0-9._\-]{3,36}$", query_token):
        query_token = ""
    default_server = os.environ.get('MCRIT_DEFAULT_SERVER', "http://127.0.0.1:8000")
    return render_template("register.html", default_mcrit_server=default_server, is_registration_token_required=is_registration_token_required, proposed_registration_token=proposed_registration_token, query_token=query_token)


@bp.route('/login', methods=('GET', 'POST'))
def login():
    user_id = session.get("user_id", None)
    if user_id is not None and not g.first_user:
        error = 'You are logged in.'
        flash(error, category='info')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['inputPassword']

        user_info = UserInfo.fromDb(username=username)
        error = None
        if user_info is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user_info.password, password):
            error = 'Incorrect password.'
        if error is None:
            session.clear()
            session['user_id'] = user_info.user_id
            user_info.last_login = datetime.utcnow()
            user_info.saveToDb()
            return redirect(url_for('index'))
        flash(error, category='error')
    return render_template('login.html')


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        user_info = UserInfo.fromDb(user_id=user_id)
        g.user = user_info


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        return view(**kwargs)
    return wrapped_view


@bp.route('/settings')
@login_required
def settings():
    user_id = get_session_user_id()
    if user_id is None:
        return redirect(url_for('index'))
    user_info = UserInfo.fromDb(user_id=user_id)
    user_filters = UserFilters.fromDb(user_id)
    user_column_settings = UserColumnSettings.fromDb(user_id)
    # if we don't have them yet, create them
    if user_filters is None:
        user_filters = UserFilters.fromDict(user_id, {})
        user_filters.saveToDb()
    if user_column_settings is None:
        user_column_settings = UserColumnSettings.fromDict(user_id, {})
        user_column_settings.saveToDb()
    return render_template('settings.html', user_info=user_info, user_filters=user_filters, user_column_settings=user_column_settings.toUserColumnSettings(), can_use_api=user_info is not None and user_info.role in API_ROLES)

def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        if g.user.role != 'admin':
            abort(403)
        return view(**kwargs)
    return wrapped_view


def contributor_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        if g.user.role != 'admin' and g.user.role != 'contributor':
            abort(403)
        return view(**kwargs)
    return wrapped_view


def visitor_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        if g.user.role != 'admin' and g.user.role != 'contributor' and g.user.role != 'visitor':
            abort(403)
        return view(**kwargs)
    return wrapped_view


def token_required(view):
    """Authenticate an API caller by its `apitoken` header, and apply its role.

    The API is a passthrough to the backend, so a token has to carry the same
    authority the web UI grants the same person - otherwise the quickest way past a
    role check is to stop using the browser. The token's owner lands on `g.api_user`
    for the router to narrow further; `pending` gets nothing, as in the web UI.
    """
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        # requests -> {'apitoken': '{}'.format(apitoken)})
        provided_token = request.headers.get("apitoken", "")
        # check for valid token via DB
        user_id = db.get_user_by_apitoken(provided_token)
        if user_id is None:
            abort(403)
        g.api_user = UserInfo.fromDb(user_id=user_id)
        if g.api_user is None or g.api_user.role not in API_ROLES:
            abort(403)
        return view(**kwargs)
    return wrapped_view


@bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You\'re logged out now', category='success')
    return redirect(url_for('index'))
