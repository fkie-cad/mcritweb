import re
from werkzeug.security import check_password_hash, generate_password_hash
from flask import current_app, Blueprint, render_template, g, request, flash, redirect, url_for, session

from mcrit.client.McritClient import McritClient

from mcritweb.views.utility import get_server_url, get_username
from mcritweb import db
from mcritweb.db import UserInfo
from mcritweb.views.authentication import admin_required, login_required, multi_user
from mcritweb.views.utility import get_server_url, set_server_url, get_mcritweb_version_from_setup, parse_integer_post_param, parse_checkbox_post_param, get_session_user_id


bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.route('/change_username' , methods=('GET', 'POST'))
@login_required
def change_username():
    # validate user_id:
    try:
        user_id = int(session['user_id'])
        if user_id < 1:
            raise ValueError
    except:
        return redirect(url_for('index'))
    new_username = request.form['username']
    password = request.form['inputPassword1']
    database = db.get_db()
    error = None
    user = database.execute('SELECT * FROM user WHERE id = ?', (session['user_id'],)).fetchone()
    if re.match("^(?=[a-zA-Z0-9._]{3,20}$)(?!.*[_.]{2})[^_.].*[^_.]$", new_username) is None:
        error = "Username has invalid format."
    if not check_password_hash(user['password'], password):
        error = 'Incorrect Password!'
    if not database.execute('SELECT * FROM user WHERE username = ?', (new_username,)).fetchone() is None:
        error = 'Username is already taken!'
    if error is None:
        database.execute("UPDATE user SET username = ? WHERE id = ?",(new_username, user['id']),)
        database.commit()
        flash('Username successfully changed', category='success')
        return redirect(url_for('index'))
    flash(error, category='error')
    user_info = UserInfo.fromDb(user_id)
    return render_template('settings.html', user_info=user_info)


@bp.route('/change_password' , methods=('GET', 'POST'))
@login_required
def change_password():
    # validate user_id:
    try:
        user_id = int(session['user_id'])
        if user_id < 1:
            raise ValueError
    except:
        return redirect(url_for('index'))
    new_password = request.form['inputPassword3']
    old_password = request.form['inputPassword2']
    database = db.get_db()
    error = None
    user = database.execute('SELECT * FROM user WHERE id = ?', (session['user_id'],)).fetchone()
    if not check_password_hash(user['password'], old_password):
        error = 'Incorrect password!'
    if not new_password == request.form['inputPassword4']:
        error = 'The entered passwords do not match!'
    if error is None:
        database.execute("UPDATE user SET password = ? WHERE id = ?",(generate_password_hash(new_password), user['id']),)
        database.commit()
        flash('Password successfully changed', category='success') 
        return redirect(url_for('index'))
    flash(error, category='error')
    user_info = UserInfo.fromDb(user_id)
    return render_template('settings.html', user_info=user_info)


@bp.route('/change_default_filter' , methods=('GET', 'POST'))
@login_required
def change_default_filter():
    user_id = get_session_user_id()
    if user_id is None:
        flash('User ID was not recognized', category='error') 
        return redirect(url_for('index'))
    # generic filtering on family/sample results
    filter_direct_min_score = parse_integer_post_param(request, "filter_direct_min_score")
    filter_direct_nonlib_min_score = parse_integer_post_param(request, "filter_direct_nonlib_min_score")
    filter_frequency_min_score = parse_integer_post_param(request, "filter_frequency_min_score")
    filter_frequency_nonlib_min_score = parse_integer_post_param(request, "filter_frequency_nonlib_min_score")
    filter_unique_only = parse_checkbox_post_param(request, "filter_unique_only")
    filter_exclude_own_family = parse_checkbox_post_param(request, "filter_exclude_own_family")
    # generic filtering of function results
    filter_function_min_score = parse_integer_post_param(request, "filter_function_min_score")
    filter_function_max_score = parse_integer_post_param(request, "filter_function_max_score")
    filter_max_num_families = parse_integer_post_param(request, "filter_max_num_families")
    filter_exclude_library = parse_checkbox_post_param(request, "filter_exclude_library")
    filter_exclude_pic = parse_checkbox_post_param(request, "filter_exclude_pic")
    filter_values = {
        "filter_direct_min_score": 0 if filter_direct_min_score is None else filter_direct_min_score,
        "filter_direct_nonlib_min_score": 0 if filter_direct_nonlib_min_score is None else filter_direct_nonlib_min_score,
        "filter_frequency_min_score": 0 if filter_frequency_min_score is None else filter_frequency_min_score,
        "filter_frequency_nonlib_min_score": 0 if filter_frequency_nonlib_min_score is None else filter_frequency_nonlib_min_score,
        "filter_unique_only": filter_unique_only,
        "filter_exclude_own_family": filter_exclude_own_family,
        "filter_function_min_score": 0 if filter_function_min_score is None else filter_function_min_score,
        "filter_function_max_score": 100 if filter_function_max_score is None else filter_function_max_score,
        "filter_max_num_families": 0 if filter_max_num_families is None else filter_max_num_families,
        "filter_exclude_library": filter_exclude_library,
        "filter_exclude_pic": filter_exclude_pic,
    }
    # store user filter values in database
    db.set_user_result_filters(user_id, filter_values)
    flash('Default filters successfully changed', category='success') 
    user_info = UserInfo.fromDb(user_id)
    return render_template('settings.html', user_info=user_info, filters=filter_values)

@bp.route('/users/')
@bp.route('/users/<tab>')
@admin_required
@multi_user
def users(tab = None):
    g.all_users = get_users()
    if tab is None:
        return render_template("users.html", active='all')    
    return render_template("users.html", active=tab)


def get_users():
    database = db.get_db() 
    users = database.execute('SELECT * FROM user').fetchall()
    return users


@bp.route('/change_user_role/<int:id>/<role>/<tab>')
@admin_required
def change_user_role(id, role, tab):
    # root user is always admin
    if id == 1:
        return redirect(url_for('admin.users', tab=tab))
    # others can be changed
    database = db.get_db() 
    database.execute("UPDATE user SET role = ? WHERE id = ?",(role, id),)
    database.commit()
    return redirect(url_for('admin.users', tab=tab))


@bp.route('/delete_user/<int:id>')
@bp.route('/delete_user/<int:id>/<tab>')
@admin_required
def delete_user(id, tab = None):
    # root user is not deletable
    if id == 1:
        return redirect(url_for('admin.users', tab=tab))
    # others can be deleted
    database = db.get_db() 
    database.execute("DELETE FROM user WHERE id = ?",(id),)
    database.commit()
    return redirect(url_for('admin.users', tab=tab))


@login_required
@bp.route('/server')
@admin_required
def server():
    server_uuid = db.get_server_uuid()
    registration_token = db.get_registration_token()
    operation_mode = db.get_operation_mode()
    operation_mode_str = "Multi-User" if operation_mode == "multi" else "Single-User"
    db_server_version = db.get_server_version()
    running_server_version = get_mcritweb_version_from_setup()
    client = McritClient(mcrit_server=get_server_url(), username=get_username())
    mcrit_version = client.getVersion()
    return render_template('admin_server.html', current_url=get_server_url(), server_uuid=server_uuid, registration_token=registration_token, operation_mode=operation_mode_str, db_version=db_server_version, running_version=running_server_version, mcrit_version=mcrit_version)


@bp.route('/change_server' , methods=('GET', 'POST'))
@admin_required
def change_server():
    new_url = request.form.get('mcrit_server_url', '')
    if new_url:
        current_url = get_server_url()
        if new_url != current_url:
            set_server_url(new_url)
        flash('Server URL successfully changed', category='success')
        return redirect(url_for('index'))


@bp.route('/reset_server' , methods=('GET', 'POST'))
@admin_required
def reset_server():
    reset_confirmation = request.form.get('reset_server', '')
    if reset_confirmation and reset_confirmation == "RESET":
        client = McritClient(mcrit_server=get_server_url(), username=get_username())
        client.respawn()
        from mcritweb.views.utility import ensure_local_data_paths
        ensure_local_data_paths(current_app, clear_data=True)
        # TODO also clean all locally cached data.
        flash('A reset of MCRIT was successfully performed.', category='success')
        return redirect(url_for('index'))
