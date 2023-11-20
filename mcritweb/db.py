import os
import uuid
import hashlib
import datetime

import click
import sqlite3
from flask import current_app, g
from flask.cli import with_appcontext


class UserInfo(object):

    def __init__(self) -> None:
        self.user_id = None
        self.username = None
        # assume password has been hashed already, e.g. via generate_password_hash from werkzeug.security
        self.password = None
        self.role = None
        self.registered = None
        self.last_login = None
        self.apitoken = None

    @classmethod
    def fromDb(cls, user_id=None, username=None):
        db = get_db()
        cursor = db.cursor()
        record = None
        if user_id is not None:
            record = cursor.execute("SELECT * FROM user WHERE id = ?;", (user_id,)).fetchone()
        elif username is not None:
            record = cursor.execute("SELECT * FROM user WHERE username = ?;", (username,)).fetchone()
        if record:
            user_info = cls()
            user_info.user_id = record["id"]
            user_info.username = record["username"]
            user_info.password = record["password"]
            user_info.role = record["role"]
            user_info.registered = datetime.datetime.strptime(record["registered"], "%Y-%m-%d %H:%M:%S.%f")
            user_info.last_login = "no login"
            if record["last_login"] != "no login":
                user_info.last_login = datetime.datetime.strptime(record["last_login"], "%Y-%m-%d %H:%M:%S.%f")
            user_info.apitoken = record["apitoken"]
        else:
            user_info = None
        return user_info
    
    def saveToDb(self, withPassword=False):
        database = get_db()
        # query to see if row exists
        record = database.execute("SELECT * FROM user WHERE id = ?;", (self.user_id,)).fetchone()
        if record:
            database.execute("UPDATE user SET username = ? WHERE id = ?;",(self.username, self.user_id,))
            if withPassword:
                database.execute("UPDATE user SET password = ? WHERE id = ?;",(self.password, self.user_id,))
            database.execute("UPDATE user SET role = ? WHERE id = ?;",(self.role, self.user_id,))
            if isinstance(self.registered, datetime.datetime):
                database.execute("UPDATE user SET registered = ? WHERE id = ?;",(self.registered.strftime("%Y-%m-%d %H:%M:%S.%f"), self.user_id,))
            if isinstance(self.last_login, datetime.datetime):
                database.execute("UPDATE user SET last_login = ? WHERE id = ?;",(self.last_login.strftime("%Y-%m-%d %H:%M:%S.%f"), self.user_id,))
            database.execute("UPDATE user SET apitoken = ? WHERE id = ?;",(self.apitoken, self.user_id,))
        else:
            database.execute(
                "INSERT INTO user (username, password, role, registered, last_login, apitoken) VALUES (?,?,?,?,?,?)",
                (self.username, self.password, self.role, datetime.datetime.utcnow(), 'no login', self.apitoken),
            )
        database.commit()
    
    @property
    def registration_date(self):
        return self.registered.strftime("%Y-%m-%d")
    
def get_all_user_info():
    all_user_infos = []
    database = get_db() 
    # TODO this can be refactored to using cursor results if we add a .fromDict() to UserInfo
    for user in database.execute('SELECT * FROM user').fetchall():
        all_user_infos.append(UserInfo.fromDb(user_id=user["id"]))
    return all_user_infos
    

class ServerInfo(object):

    def __init__(self) -> None:
        self.url = None
        self.operation_mode = None
        self.registration_token = None
        self.server_token = None
        self.server_uuid = None
        self.server_version = None

    def __str__(self) -> str:
        return f"ServerInfo(url='{self.url}', operation_mode='{self.operation_mode}', registration_token='{self.registration_token}', server_token='{self.server_token}', server_uuid='{self.server_uuid}', server_version='{self.server_version}')"

    @classmethod
    def fromDb(cls):
        db = get_db()
        record = db.execute("SELECT * FROM server;").fetchone()
        if record:
            server_info = cls()
            server_info.url = record["url"]
            server_info.operation_mode = record["operation_mode"]
            server_info.registration_token = record["registration_token"]
            server_info.server_token = record["server_token"]
            server_info.server_uuid = record["server_uuid"]
            server_info.server_version = record["server_version"]
        else:
            server_info = None
        return server_info
    
    def saveToDb(self):
        database = get_db()
        # query to see if row exists
        record = database.execute("SELECT * FROM server;").fetchone()
        if record:
            database.execute("UPDATE server SET url = ?",(self.url,))
            database.execute("UPDATE server SET operation_mode = ?",(self.operation_mode,))
            database.execute("UPDATE server SET registration_token = ?",(self.registration_token,))
            database.execute("UPDATE server SET server_token = ?",(self.server_token,))
            database.execute("UPDATE server SET server_uuid = ?",(self.server_uuid,))
            database.execute("UPDATE server SET server_version = ?",(self.server_version,))
        else:
            database.execute(
                "INSERT INTO server (url, operation_mode, registration_token, server_token, server_uuid, server_version) VALUES (?,?,?,?,?,?)",
                (self.url, self.operation_mode, self.registration_token, self.server_token, self.server_uuid, self.server_version),
            )
        database.commit()


class UserFilters(object):

    def __init__(self) -> None:
        self.user_id = None
        self.filter_direct_min_score = None
        self.filter_direct_nonlib_min_score = None
        self.filter_frequency_min_score = None
        self.filter_frequency_nonlib_min_score = None
        self.filter_unique_only = None
        self.filter_exclude_own_family = None
        self.filter_function_min_score = None
        self.filter_function_max_score = None
        self.filter_max_num_families = None
        self.filter_exclude_library = None
        self.filter_exclude_pic = None
        # this is never stored as preference in the DB as its not as generic as the others
        self.filter_family_name = None
        self.filter_function_offset = None
        self.filter_min_num_samples = None
        self.filter_max_num_samples = None

    @classmethod
    def fromDb(cls, user_id):
        db = get_db()
        cursor = db.cursor()
        record = cursor.execute("SELECT * FROM user_filters WHERE user_id = ?;", (user_id,)).fetchone()
        if record:
            user_filter_info = cls()
            user_filter_info.user_id = user_id
            user_filter_info.filter_direct_min_score = record["filter_direct_min_score"]
            user_filter_info.filter_direct_nonlib_min_score = record["filter_direct_nonlib_min_score"]
            user_filter_info.filter_frequency_min_score = record["filter_frequency_min_score"]
            user_filter_info.filter_frequency_nonlib_min_score = record["filter_frequency_nonlib_min_score"]
            user_filter_info.filter_unique_only = record["filter_unique_only"]
            user_filter_info.filter_exclude_own_family = record["filter_exclude_own_family"]
            user_filter_info.filter_function_min_score = record["filter_function_min_score"]
            user_filter_info.filter_function_max_score = record["filter_function_max_score"]
            user_filter_info.filter_max_num_families = record["filter_max_num_families"]
            user_filter_info.filter_exclude_library = record["filter_exclude_library"]
            user_filter_info.filter_exclude_pic = record["filter_exclude_pic"]
            # remainder set implicitly to None
        else:
            user_filter_info = None
        return user_filter_info
    
    @classmethod
    def fromDict(cls, user_id, filter_dict):
        user_filter_info = cls()
        user_filter_info.user_id = user_id
        user_filter_info.filter_direct_min_score = 0 if "filter_direct_min_score" not in filter_dict or filter_dict["filter_direct_min_score"] == 0 else filter_dict["filter_direct_min_score"]
        user_filter_info.filter_direct_nonlib_min_score = 0 if "filter_direct_nonlib_min_score" not in filter_dict or filter_dict["filter_direct_nonlib_min_score"] == 0 else filter_dict["filter_direct_nonlib_min_score"]
        user_filter_info.filter_frequency_min_score = 0 if "filter_frequency_min_score" not in filter_dict or filter_dict["filter_frequency_min_score"] == 0 else filter_dict["filter_frequency_min_score"]
        user_filter_info.filter_frequency_nonlib_min_score = 0 if "filter_frequency_nonlib_min_score" not in filter_dict or filter_dict["filter_frequency_nonlib_min_score"] == 0 else filter_dict["filter_frequency_nonlib_min_score"]
        user_filter_info.filter_unique_only = True if "filter_unique_only" in filter_dict and filter_dict["filter_unique_only"] else False
        user_filter_info.filter_exclude_own_family = True if "filter_exclude_own_family" in filter_dict and filter_dict["filter_exclude_own_family"] else False
        user_filter_info.filter_function_min_score = 0 if "filter_function_min_score" not in filter_dict or filter_dict.get("filter_function_min_score", 0) == 0 else filter_dict["filter_function_min_score"]
        user_filter_info.filter_function_max_score = 100 if "filter_function_max_score" not in filter_dict or filter_dict.get("filter_function_max_score", 100) == 100 else filter_dict["filter_function_max_score"]
        user_filter_info.filter_max_num_families = 0 if "filter_max_num_families" not in filter_dict or filter_dict.get("filter_max_num_families", 0) == 0 else filter_dict["filter_max_num_families"]
        user_filter_info.filter_exclude_library = True if "filter_exclude_library" in filter_dict and filter_dict["filter_exclude_library"] else False
        user_filter_info.filter_exclude_pic = True if "filter_exclude_pic" in filter_dict and filter_dict["filter_exclude_pic"] else False
        # 
        user_filter_info.filter_family_name = None if "filter_family_name" not in filter_dict or filter_dict["filter_family_name"] == "" else filter_dict["filter_family_name"]
        user_filter_info.filter_function_offset = None if "filter_function_offset" not in filter_dict or filter_dict["filter_function_offset"] < 0 else filter_dict["filter_function_offset"]
        user_filter_info.filter_min_num_samples = 0 if "filter_min_num_samples" not in filter_dict or filter_dict.get("filter_min_num_samples", 0) == 0 else filter_dict["filter_min_num_samples"]
        user_filter_info.filter_max_num_samples = 0 if "filter_max_num_samples" not in filter_dict or filter_dict.get("filter_max_num_samples", 0) == 0 else filter_dict["filter_max_num_samples"]
        return user_filter_info

    def toDict(self):
        return {
            "user_id": self.user_id,
            "filter_direct_min_score": self.filter_direct_min_score,
            "filter_direct_nonlib_min_score": self.filter_direct_nonlib_min_score,
            "filter_frequency_min_score": self.filter_frequency_min_score,
            "filter_frequency_nonlib_min_score": self.filter_frequency_nonlib_min_score,
            "filter_unique_only": self.filter_unique_only,
            "filter_exclude_own_family": self.filter_exclude_own_family,
            "filter_function_min_score": self.filter_function_min_score,
            "filter_function_max_score": self.filter_function_max_score,
            "filter_max_num_families": self.filter_max_num_families,
            "filter_exclude_library": self.filter_exclude_library,
            "filter_exclude_pic": self.filter_exclude_pic,
            #
            "filter_family_name": self.filter_family_name,
            "filter_function_offset": self.filter_function_offset,
            "filter_min_num_samples": self.filter_min_num_samples,
            "filter_max_num_samples": self.filter_max_num_samples,
        }
    
    def saveToDb(self):
        database = get_db()
        # query to see if row exists
        record = database.execute("SELECT * FROM user_filters WHERE user_id = ?;", (self.user_id,)).fetchone()
        if record:
            database.execute("UPDATE user_filters SET filter_direct_min_score = ?",(min(100, max(0, self.filter_direct_min_score)),))
            database.execute("UPDATE user_filters SET filter_direct_nonlib_min_score = ?",(min(100, max(0, self.filter_direct_nonlib_min_score)),))
            database.execute("UPDATE user_filters SET filter_frequency_min_score = ?",(min(100, max(0, self.filter_frequency_min_score)),))
            database.execute("UPDATE user_filters SET filter_frequency_nonlib_min_score = ?",(min(100, max(0, self.filter_frequency_nonlib_min_score)),))
            database.execute("UPDATE user_filters SET filter_unique_only = ?",(1 if self.filter_unique_only else 0,))
            database.execute("UPDATE user_filters SET filter_exclude_own_family = ?",(1 if self.filter_exclude_own_family else 0,))
            database.execute("UPDATE user_filters SET filter_function_min_score = ?",(min(100, max(0, self.filter_function_min_score)),))
            database.execute("UPDATE user_filters SET filter_function_max_score = ?",(min(100, max(0, self.filter_function_max_score)),))
            database.execute("UPDATE user_filters SET filter_max_num_families = ?",(max(0, self.filter_max_num_families),))
            database.execute("UPDATE user_filters SET filter_exclude_library = ?",(1 if self.filter_exclude_library else 0,))
            database.execute("UPDATE user_filters SET filter_exclude_pic = ?",(1 if self.filter_exclude_pic else 0,))
        else:
            # insert inital values
            database.execute("INSERT INTO user_filters (user_id, filter_direct_min_score, filter_direct_nonlib_min_score, filter_frequency_min_score, filter_frequency_nonlib_min_score, filter_unique_only, filter_exclude_own_family, filter_function_min_score, filter_function_max_score, filter_max_num_families, filter_exclude_library, filter_exclude_pic) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.user_id,
                min(100, max(0, self.filter_direct_min_score)),
                min(100, max(0, self.filter_direct_nonlib_min_score)),
                min(100, max(0, self.filter_frequency_min_score)), 
                min(100, max(0, self.filter_frequency_nonlib_min_score)), 
                1 if self.filter_unique_only else 0, 
                1 if self.filter_exclude_own_family else 0, 
                min(100, max(0, self.filter_function_min_score)),
                min(100, max(0, self.filter_function_max_score)), 
                max(0, self.filter_max_num_families), 
                1 if self.filter_exclude_library else 0, 
                1 if self.filter_exclude_pic else 0,
            ))
        database.commit()


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
    with current_app.open_resource('sql' + os.sep + 'create_table_user.sql') as f:
        db.executescript(f.read().decode('utf8'))
    with current_app.open_resource('sql' + os.sep + 'create_table_user_filters.sql') as f:
        db.executescript(f.read().decode('utf8'))
    with current_app.open_resource('sql' + os.sep + 'create_table_server.sql') as f:
        db.executescript(f.read().decode('utf8'))

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Clear the existing data and create new tables."""
    print("Starting database initialization.")
    init_db()
    click.echo('Initialized the database.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)


def migrate(app_context):
    # custom connect since we are before app initialization
    db = sqlite3.connect(
            app_context.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
    # check if DB was initialized before taking further action.
    try:
        db.execute('SELECT * FROM user').fetchone()
    except sqlite3.OperationalError:
        print("Database tables not initialized yet, skipping migrations.")
        return
    # since version v0.11.0, users can have default filter, ensure table exists
    table_needs_creation = False
    try:
        user_info = db.execute('SELECT * FROM user_filters').fetchone()
    except:
        table_needs_creation = True
    if table_needs_creation:
        with app_context.open_resource('sql' + os.sep + 'create_table_user_filters.sql') as f:
            db.executescript(f.read().decode('utf8'))
        print(f"EXECUTED MIGRATION: CREATED TABLE USER_FILTERS")
    # since version v0.12.0, users have an apitoken, ensure it exists (initializd)
    cursor = db.cursor()
    user_table_columns = list(map(lambda x: x[0], db.execute('SELECT * FROM user').description))
    if "apitoken" not in user_table_columns:
        db.execute('ALTER TABLE user ADD apitoken VARCHAR')
        cursor = db.cursor()
        user_ids = []
        for record in cursor.execute("select * from user;").fetchall():
            user_ids.append(record[0])
        for user_id in user_ids:
            generated_apitoken = hashlib.md5(uuid.uuid4().bytes).hexdigest()
            db.execute("UPDATE users SET apitoken = ? WHERE user_id = ?", (generated_apitoken, user_id))
            print(f"EXECUTED MIGRATION: ADD APITOKEN {generated_apitoken} TO USER_ID {user_id} FROM TABLE USER")
    # since version v1.2.10, we have an additional server_token field, ensure it exists (empty)
    server_table_columns = list(map(lambda x: x[0], db.execute('SELECT * FROM server').description))
    if "server_token" not in server_table_columns:
        db.execute('ALTER TABLE server ADD server_token VARCHAR')
        db.execute("UPDATE server SET server_token = ?;", ("",))
        print(f"EXECUTED MIGRATION: ADD SERVER_TOKEN TO TABLE SERVER")



def is_first_user():
    db = get_db()
    cursor = db.cursor()
    if len(cursor.execute("select * from user;").fetchall()) > 0:
        return False
    else:
        return True

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
    if has_user_result_filters(user_id):
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
    else:
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

def has_user_result_filters(user_id):
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("SELECT * FROM user_filters WHERE user_id = ?;", (user_id,)).fetchone()
    return True if record else False

def get_user_result_filters(user_id):
    filter_values = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("SELECT * FROM user_filters WHERE user_id = ?;", (user_id,)).fetchone()
    if record:
        record = dict(record)
        filter_values = {
        "filter_direct_min_score": None if record["filter_direct_min_score"] == 0 else record["filter_direct_min_score"],
        "filter_direct_nonlib_min_score": None if record["filter_direct_nonlib_min_score"] == 0 else record["filter_direct_nonlib_min_score"],
        "filter_frequency_min_score": None if record["filter_frequency_min_score"] == 0 else record["filter_frequency_min_score"],
        "filter_frequency_nonlib_min_score": None if record["filter_frequency_nonlib_min_score"] == 0 else record["filter_frequency_nonlib_min_score"],
        "filter_unique_only": True if record["filter_unique_only"] else False,
        "filter_exclude_own_family": True if record["filter_exclude_own_family"] else False,
        # this is never stored as preference in the DB as its not as generic as the others
        "filter_family_name": None,
        "filter_function_min_score": None if record.get("filter_function_min_score", 0) == 0 else record["filter_function_min_score"],
        "filter_function_max_score": None if record.get("filter_function_max_score", 100) == 100 else record["filter_function_max_score"],
        # this is never stored as preference in the DB as its not as generic as the others
        "filter_function_offset": None,
        "filter_max_num_families": None if record.get("filter_max_num_families", 0) == 0 else record["filter_max_num_families"],
        # we don't store filter_max_num_samples separately but instead duplicate from family value
        "filter_min_num_samples": None if record.get("filter_min_num_samples", 0) == 0 else record["filter_min_num_samples"],
        "filter_max_num_samples": None if record.get("filter_max_num_samples", 0) == 0 else record["filter_max_num_samples"],
        "filter_exclude_library": True if record["filter_exclude_library"] else False,
        "filter_exclude_pic": True if record["filter_exclude_pic"] else False
        }
    # we appear to not have default filter values stored due to DB migration, so return empty filter dict instead
    elif user_id:
        filter_values = {
        "filter_direct_min_score": None,
        "filter_direct_nonlib_min_score": None,
        "filter_frequency_min_score": None,
        "filter_frequency_nonlib_min_score": None,
        "filter_unique_only": False,
        "filter_exclude_own_family": False,
        # this is never stored as preference in the DB as its not as generic as the others
        "filter_family_name": None,
        "filter_function_min_score": None,
        "filter_function_max_score": None,
        # this is never stored as preference in the DB as its not as generic as the others
        "filter_function_offset": None,
        "filter_max_num_families": None,
        "filter_min_num_samples": None,
        "filter_max_num_samples": None,
        "filter_exclude_library": False,
        "filter_exclude_pic": False,
        }
    return filter_values

def get_user_by_apitoken(apitoken):
    user_id = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("SELECT * FROM user WHERE apitoken = ?;", (apitoken,)).fetchone()
    if record is not None:
        user_id = record["id"]
    return user_id
