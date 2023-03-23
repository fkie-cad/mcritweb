import os 
import re
import uuid
import hashlib
import functools 
from datetime import datetime
from flask import Blueprint, render_template, g, request, flash, redirect, url_for, session, abort, current_app
from werkzeug.security import check_password_hash, generate_password_hash


from mcritweb import db
from mcritweb.db import UserInfo
from mcritweb.views.utility import parse_integer_query_param, parse_checkbox_query_param, get_session_user_id


bp = Blueprint('authentication', __name__, url_prefix='/')


@bp.before_app_request
def set_is_first_user():
    g.first_user = db.is_first_user()


@bp.before_app_request
def set_operation_mode():
    if not g.first_user:
        database = db.get_db()
        operation_mode = database.execute('SELECT operation_mode FROM server',).fetchone()
        g.operation_mode = operation_mode['operation_mode']


def multi_user(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not g.first_user and g.operation_mode == 'single':
            flash('You are in single user mode', category='error')
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
    registration_token = db.get_registration_token()
    is_registration_token_required = registration_token not in [None, ""]
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['inputPassword1']
        provided_registration_token = ""
        if 'registrationToken' in request.form:
            provided_registration_token = request.form['registrationToken']
        database = db.get_db()
        error = None
        if not username:
            error = 'Username is required.'
        elif re.match("^(?=[a-zA-Z0-9._]{3,20}$)(?!.*[_.]{2})[^_.].*[^_.]$", username) is None:
            error = "Username has wrong format."
        elif not password:
            error = 'Password is required.'
        elif not password == request.form['inputPassword2']:
            error = 'The passwords do not match. No new user was created.'
        elif is_registration_token_required and registration_token != provided_registration_token:
            error = 'Invalid registration token provided. No new user was created.'
        if error is None:
            apitoken = hashlib.md5(uuid.uuid4().bytes).hexdigest()
            try:
                if g.first_user:
                    database.execute(
                        "INSERT INTO user (username, password, role, registered, last_login, apitoken) VALUES (?,?,?,?,?,?)",
                        (username, generate_password_hash(password), 'admin', datetime.utcnow(), 'no login', apitoken),
                    )
                    server_url = request.form['url']
                    operation_mode = request.form['operationMode']
                    registration_token = request.form['setRegistrationToken']
                    server_uuid = str(uuid.uuid4())
                    initial_server_version = current_app.config['MCRITWEB_VERSION']
                    database.execute(
                        "INSERT INTO server (url, operation_mode, registration_token, server_uuid, server_version) VALUES (?,?,?,?,?)",
                        (server_url, operation_mode, registration_token, server_uuid, initial_server_version),
                    )
                else:
                    database.execute(
                        "INSERT INTO user (username, password, role, registered, last_login, apitoken) VALUES (?,?,?,?,?,?)",
                        (username, generate_password_hash(password), 'pending', datetime.utcnow(), 'no login', apitoken),
                    )
                database.commit()
            except database.IntegrityError:
                error = f"User {username} is already registered."
            else:
                return redirect(url_for("authentication.login"))
        flash(error, category='error')
    proposed_registration_token = ""
    if g.first_user:
        proposed_registration_token = str(uuid.uuid4())
    query_token = request.args.get('token')
    if query_token is None or not re.match("^[a-zA-Z0-9._\-]{3,36}$", query_token):
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
        database = db.get_db()
        error = None
        user = database.execute(
            'SELECT * FROM user WHERE username = ?', (username,)
        ).fetchone()
        if user is None:
            error = 'Incorrect username.'
        elif not check_password_hash(user['password'], password):
            error = 'Incorrect password.'
        if error is None:
            session.clear()
            session['user_id'] = user['id']
            database.execute("UPDATE user SET last_login = ? WHERE id = ?",(datetime.now(), user['id']),)
            database.commit()
            return redirect(url_for('index'))
        flash(error, category='error')
    return render_template('login.html')


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = db.get_db().execute(
            'SELECT * FROM user WHERE id = ?', (user_id,)
        ).fetchone()


def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        return view(**kwargs)
    return wrapped_view


@login_required
@bp.route('/settings')
def settings():
    user_id = get_session_user_id()
    if user_id is None:
        return redirect(url_for('index'))
    user_info = UserInfo.fromDb(user_id)
    filter_values = db.get_user_result_filters(user_id)
    return render_template('settings.html', user_info=user_info, filters=filter_values)
    
    
def admin_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        if g.user['role'] != 'admin':
            abort(403)
        return view(**kwargs)
    return wrapped_view


def contributor_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        if g.user['role'] != 'admin' and g.user['role'] != 'contributor':
            abort(403)
        return view(**kwargs)
    return wrapped_view


def visitor_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for('authentication.login'))
        if g.user['role'] != 'admin' and g.user['role'] != 'contributor' and g.user['role'] != 'visitor':
            abort(403)
        return view(**kwargs)
    return wrapped_view


def token_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        # requests -> {'apitoken': '{}'.format(apitoken)})
        provided_token = request.headers.get("apitoken", "")
        # check for valid token via DB
        valid_token = db.get_user_by_apitoken(provided_token) is not None
        if not valid_token:
            abort(403)
        return view(**kwargs)
    return wrapped_view


@bp.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You\'re logged out now', category='success')
    return redirect(url_for('index'))
