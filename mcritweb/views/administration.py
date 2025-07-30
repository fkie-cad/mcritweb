import re
from werkzeug.security import check_password_hash, generate_password_hash
from flask import current_app, Blueprint, render_template, g, request, flash, redirect, url_for, session

from mcrit.client.McritClient import McritClient

from mcritweb.views.utility import get_server_url, get_server_token, get_username
from mcritweb import db
from mcritweb.db import UserInfo, ServerInfo, UserFilters
from mcritweb.views.authentication import admin_required, login_required, multi_user
from mcritweb.views.utility import get_server_url, get_mcritweb_version_from_setup, parse_integer_post_param, parse_checkbox_post_param, get_session_user_id


bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/help' , methods=('GET', 'POST'))
def help():
    return render_template('help.html')

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
    error_msg = None
    user_info = UserInfo.fromDb(user_id=session['user_id'])
    if re.match("^(?=[a-zA-Z0-9._]{3,20}$)(?!.*[_.]{2})[^_.].*[^_.]$", new_username) is None:
        error_msg = "Username has invalid format."
    if  not check_password_hash(user_info.password, password):
        error_msg = 'Incorrect Password!'
    user_with_name = UserInfo.fromDb(username=new_username)
    if user_with_name is not None:
        error_msg = 'Username is already taken!'
    if error_msg is None:
        user_info.username = new_username
        user_info.saveToDb()
        flash('Username successfully changed', category='success')
        return redirect(url_for('index'))
    flash(error_msg, category='error')
    user_filters = UserFilters.fromDb(user_info.user_id)
    # if we don't have them yet, create them
    if user_filters is None:
        user_filters = UserFilters.fromDict(user_info.user_id, {})
        user_filters.saveToDb()
    return render_template('settings.html', user_info=user_info, user_filters=user_filters)


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
    error_msg = None
    user_info = UserInfo.fromDb(user_id=session['user_id'])
    if not check_password_hash(user_info.password, old_password):
        error_msg = 'Incorrect password!'
    if not new_password == request.form['inputPassword4']:
        error_msg = 'The entered passwords do not match!'
    if error_msg is None:
        user_info.password = generate_password_hash(new_password)
        user_info.saveToDb(withPassword=True)
        flash('Password successfully changed', category='success') 
        return redirect(url_for('index'))
    flash(error_msg, category='error')
    user_filters = UserFilters.fromDb(user_info.user_id)
    # if we don't have them yet, create them
    if user_filters is None:
        user_filters = UserFilters.fromDict(user_info.user_id, {})
        user_filters.saveToDb()
    return render_template('settings.html', user_info=user_info, user_filters=user_filters)


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
    user_filters = UserFilters.fromDict(user_id, filter_values)
    user_filters.saveToDb()
    flash('Default filters successfully changed', category='success') 
    user_info = UserInfo.fromDb(user_id)
    user_filters = UserFilters.fromDb(user_info.user_id)
    return render_template('settings.html', user_info=user_info, user_filters=user_filters)

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
    user_infos = db.get_all_user_info()
    return user_infos


@bp.route('/change_user_role/<int:user_id>/<role>/<tab>')
@admin_required
def change_user_role(user_id, role, tab):
    # root user is always admin
    if user_id == 1:
        return redirect(url_for('admin.users', tab=tab))
    # others can be changed
    user_info = UserInfo.fromDb(user_id=user_id)
    user_info.role = role
    user_info.saveToDb()
    return redirect(url_for('admin.users', tab=tab))


@bp.route('/delete_user/<int:user_id>')
@bp.route('/delete_user/<int:user_id>/<tab>')
@admin_required
def delete_user(user_id, tab = None):
    # root user is not deletable
    if user_id == 1:
        return redirect(url_for('admin.users', tab=tab))
    # others can be deleted
    database = db.get_db() 
    print(user_id)
    database.execute("DELETE FROM user WHERE id = ?;", (user_id,))
    database.commit()
    return redirect(url_for('admin.users', tab=tab))


@login_required
@bp.route('/server')
@admin_required
def server():
    server_info = ServerInfo.fromDb()
    print(server_info)
    operation_mode_str = "Multi-User" if server_info.operation_mode == "multi" else "Single-User"
    running_server_version = get_mcritweb_version_from_setup()
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    mcrit_version = client.getVersion()
    return render_template('admin_server.html', operation_mode=operation_mode_str, server_info=server_info, running_version=running_server_version, mcrit_version=mcrit_version)


@bp.route('/change_server' , methods=('GET', 'POST'))
@admin_required
def change_server():
    server_info = ServerInfo.fromDb()
    new_url = request.form.get('mcrit_server_url', '')
    new_token = request.form.get('mcrit_server_token', '')
    if server_info.url != new_url or server_info.server_token != new_token:
        server_info.url = new_url
        server_info.server_token = new_token
        server_info.saveToDb()
        flash('Server information successfully changed', category='success')
    else:
        flash('No information needed change', category='success')
    operation_mode_str = "Multi-User" if server_info.operation_mode == "multi" else "Single-User"
    running_server_version = get_mcritweb_version_from_setup()
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    mcrit_version = client.getVersion()
    return render_template('admin_server.html', operation_mode=operation_mode_str, server_info=server_info, running_version=running_server_version, mcrit_version=mcrit_version)


@bp.route('/reset_server' , methods=('GET', 'POST'))
@admin_required
def reset_server():
    reset_confirmation = request.form.get('reset_server', '')
    if reset_confirmation and reset_confirmation == "RESET":
        client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
        client.respawn()
        from mcritweb.views.utility import ensure_local_data_paths
        ensure_local_data_paths(current_app, clear_data=True)
        # TODO also clean all locally cached data.
        flash('A reset of MCRIT was successfully performed.', category='success')
        return redirect(url_for('index'))


@bp.route('/schedule_rebuild_index' , methods=('GET', 'POST'))
@admin_required
def schedule_rebuild_index():
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    job_id = client.rebuildIndex()
    flash('A job for rebuilding the MinHash Index has been scheduled.', category='success')
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))


@bp.route('/schedule_recalc_pichashes' , methods=('GET', 'POST'))
@admin_required
def schedule_recalc_pichashes():
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    job_id = client.recalculatePicHashes()
    flash('A job for recalculating all PicHashes has been scheduled.', category='success')
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))


@bp.route('/schedule_recalc_minhashes' , methods=('GET', 'POST'))
@admin_required
def schedule_recalc_minhashes():
    client = McritClient(mcrit_server=get_server_url(), apitoken=get_server_token(), username=get_username())
    job_id = client.recalculateMinHashes()
    flash('A job for recalculating and indexing all MinHashes has been scheduled.', category='success')
    return redirect(url_for('data.job_by_id', job_id=job_id, refresh=3))
