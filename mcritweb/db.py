import click
import sqlite3
from flask import current_app, g
from flask.cli import with_appcontext


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()

def init_db():
    db = get_db()

    with current_app.open_resource('create_table.sql') as f:
        db.executescript(f.read().decode('utf8'))

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

def is_first_user():
    db = get_db()
    cursor = db.cursor()
    if len(cursor.execute("select * from user;").fetchall()) > 0:
        return False
    else:
        return True

def get_server_uuid():
    server_uuid = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("select server_uuid from server;").fetchone()
    if record:  
        server_uuid = record["server_uuid"]
    return server_uuid

def get_server_version():
    server_version = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("select server_version from server;").fetchone()
    if record:  
        server_version = record["server_version"]
    return server_version

def get_registration_token():
    registration_token = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("select registration_token from server;").fetchone()
    if record:  
        registration_token = record["registration_token"]
    return registration_token

def get_operation_mode():
    operation_mode = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("select operation_mode from server;").fetchone()
    if record:  
        operation_mode = record["operation_mode"]
    return operation_mode

def set_user_result_filters(user_id, filter_values):
    # init db usage
    db = get_db()
    cursor = db.cursor()
    # check existing entry
    current_filters = get_user_result_filters(user_id)
    print(filter_values)
    if current_filters is None:
        # insert inital values
        db.execute(
            "INSERT INTO user_filters (user_id, filter_direct_min_score, filter_direct_nonlib_min_score, filter_frequency_min_score, filter_frequency_nonlib_min_score, filter_unique_only, filter_exclude_own_family, filter_function_min_score, filter_function_max_score, filter_max_num_families, filter_exclude_library, filter_exclude_pic) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id,
             min(100, max(0, filter_values["filter_direct_min_score"])),
             min(100, max(0, filter_values["filter_direct_nonlib_min_score"])),
             min(100, max(0, filter_values["filter_frequency_min_score"])), 
             min(100, max(0, filter_values["filter_frequency_nonlib_min_score"])), 
             1 if filter_values["filter_unique_only"] else 0, 
             1 if filter_values["filter_exclude_own_family"] else 0, 
             min(100, max(0, filter_values["filter_function_min_score"])),
             min(100, max(0, filter_values["filter_function_max_score"])), 
             max(0, filter_values["filter_max_num_families"]), 
             1 if filter_values["filter_exclude_library"] else 0, 
             1 if filter_values["filter_exclude_pic"] else 0,
             ))
        db.commit()
    else:
        # update values
        db.execute("UPDATE user_filters SET filter_direct_min_score = ? WHERE user_id = ?", (min(100, max(0, filter_values["filter_direct_min_score"])), user_id))
        db.execute("UPDATE user_filters SET filter_direct_nonlib_min_score = ? WHERE user_id = ?", (min(100, max(0, filter_values["filter_direct_nonlib_min_score"])), user_id))
        db.execute("UPDATE user_filters SET filter_frequency_min_score = ? WHERE user_id = ?", (min(100, max(0, filter_values["filter_frequency_min_score"])), user_id))
        db.execute("UPDATE user_filters SET filter_frequency_nonlib_min_score = ? WHERE user_id = ?", (min(100, max(0, filter_values["filter_frequency_nonlib_min_score"])), user_id))
        db.execute("UPDATE user_filters SET filter_unique_only = ? WHERE user_id = ?", (1 if filter_values["filter_unique_only"] else 0, user_id))
        db.execute("UPDATE user_filters SET filter_exclude_own_family = ? WHERE user_id = ?", (1 if filter_values["filter_exclude_own_family"] else 0, user_id))
        db.execute("UPDATE user_filters SET filter_function_min_score = ? WHERE user_id = ?", (min(100, max(0, filter_values["filter_function_min_score"])), user_id))
        db.execute("UPDATE user_filters SET filter_function_max_score = ? WHERE user_id = ?", (min(100, max(0, filter_values["filter_function_max_score"])), user_id))
        db.execute("UPDATE user_filters SET filter_max_num_families = ? WHERE user_id = ?", (min(100, max(0, filter_values["filter_max_num_families"])), user_id))
        db.execute("UPDATE user_filters SET filter_exclude_library = ? WHERE user_id = ?", (1 if filter_values["filter_exclude_library"] else 0, user_id))
        db.execute("UPDATE user_filters SET filter_exclude_pic = ? WHERE user_id = ?", (1 if filter_values["filter_exclude_pic"] else 0, user_id))
        db.commit()

def get_user_result_filters(user_id):
    filter_values = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("SELECT * FROM user_filters WHERE user_id = ?;", (user_id,)).fetchone()
    if record:
        filter_values = {
        "filter_direct_min_score": None if record["filter_direct_min_score"] == 0 else record["filter_direct_min_score"],
        "filter_direct_nonlib_min_score": None if record["filter_direct_nonlib_min_score"] == 0 else record["filter_direct_nonlib_min_score"],
        "filter_frequency_min_score": None if record["filter_frequency_min_score"] == 0 else record["filter_frequency_min_score"],
        "filter_frequency_nonlib_min_score": None if record["filter_frequency_nonlib_min_score"] == 0 else record["filter_frequency_nonlib_min_score"],
        "filter_unique_only": True if record["filter_unique_only"] else False,
        "filter_exclude_own_family": True if record["filter_exclude_own_family"] else False,
        "filter_function_min_score": None if record["filter_function_min_score"] == 0 else record["filter_function_min_score"],
        "filter_function_max_score": None if record["filter_function_max_score"] == 100 else record["filter_function_max_score"],
        "filter_max_num_families": None if record["filter_max_num_families"] == 0 else record["filter_max_num_families"],
        # we don't store filter_max_num_samples separately but instead duplicate from family value
        "filter_max_num_samples": None if record["filter_max_num_families"] == 0 else record["filter_max_num_families"],
        "filter_exclude_library": True if record["filter_exclude_library"] else False,
        "filter_exclude_pic": True if record["filter_exclude_pic"] else False
    }
    return filter_values
