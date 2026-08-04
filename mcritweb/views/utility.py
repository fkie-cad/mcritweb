"""Server, session and local-path plumbing shared across the view modules.

Request-parameter parsing lives in params.py; the function-diff block comparison
lives in functiondiff.py. See issue #88.
"""

import os
import re
import shutil
import requests
import functools

from flask import redirect, url_for, flash, session, g

from mcritweb import db
from mcritweb.db import ServerInfo, UserColumnSettings


def get_server_url():
    server_info = ServerInfo.fromDb()
    return server_info.url


def get_server_token():
    server_info = ServerInfo.fromDb()
    return server_info.server_token


def mcrit_server_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        try:
            result = requests.get(f"{get_server_url()}/", headers={"username":"mcritweb", "apitoken": get_server_token()})
            if result.status_code == 401:
                flash('Connected to MCRIT server but could not authenticate - Did you configure a token in the server settings?', category='error')
                return redirect(url_for('index'))
        except:
            flash('No connection to the MCRIT server', category='error')
            return redirect(url_for('index'))
        return view(**kwargs)
    return wrapped_view


def get_session_user_id():
    try:
        user_id = int(session['user_id'])
        if user_id > 0:
            return user_id
    except:
        return None


def get_username(request=None):
    username = "guest"
    if g.user is not None:
        username =  g.user.username
    elif request and "apitoken" in request.headers:
        provided_token = request.headers.get("apitoken", "")
        username_by_token = db.get_username_by_apitoken(provided_token)
        if username_by_token is not None:
            username = username_by_token
    elif request and "username" in request.headers:
        username = request.headers.get("username")
    return username


def get_user_column_setup(table_type:str):
    if table_type not in UserColumnSettings._default_settings.keys():
        raise Exception(f"Unknown table type for user column settings: {table_type}")
    # load user column setup from database
    user_id = get_session_user_id()
    user_column_settings = UserColumnSettings.fromDb(user_id)
    # if we don't have them yet, create them
    if user_column_settings is None:
        user_column_settings = UserColumnSettings(user_id)
        user_column_settings.saveToDb()
    ucs_dict = user_column_settings.toUserColumnSettings()
    return ucs_dict[table_type]["active"]

def ensure_local_data_paths(app, clear_data=False):
    # nuke both cache and temp folders
    nuke_paths = [
        app.instance_path + os.sep + "cache",
        app.instance_path + os.sep + "temp"
    ]
    # ensure the instance and cache folders exists
    ensure_paths = [
        app.instance_path + os.sep + "cache" + os.sep + "diagrams",
        app.instance_path + os.sep + "cache" + os.sep + "results",
        app.instance_path + os.sep + "temp" + os.sep + "reports",
        app.instance_path + os.sep + "temp" + os.sep + "diagrams",
        app.instance_path + os.sep + "temp" + os.sep + "uploads",
    ]
    if clear_data:
        for path in nuke_paths:
            shutil.rmtree(path)
    for path in ensure_paths:
        try:
            os.makedirs(path)
        except FileExistsError:
            pass


def get_mcritweb_version_from_setup():
    this_file_path = str(os.path.abspath(__file__))
    project_root = str(os.path.abspath(os.sep.join([this_file_path, "..", "..", ".."])))
    setup_path = os.path.abspath(os.sep.join([project_root, "setup.py"]))
    mcritweb_version = None
    with open(setup_path, "r") as fin:
        for line in fin.readlines():
            line = line.strip()
            match = re.search("version=\"(?P<version_str>\d+\.\d+\.\d+)\",", line)
            if match:
                mcritweb_version = match.group("version_str")
    return mcritweb_version
