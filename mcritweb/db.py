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
