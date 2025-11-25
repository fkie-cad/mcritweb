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


class UserColumnSettings(object):

    # Define the default column configuration template
    _default_settings = {
        "family_table": {
            "active": ["family_id", "family_name", "num_samples", "num_functions", "is_library"],
            "available": []
        },
        "samples_table": {
            "active": ["sample_id", "sha256", "family", "version", "filename", "bitness", "num_functions", "is_library"],
            "available": []
        },
        "functions_table": {
            "active": ["function_id", "family_id", "sample_id", "pic_hash", "has_minhash", "offset", "function_name", "num_instructions", "num_blocks"],
            "available": []
        },
        "result_family_table": {
            "active": ["family_name", "version", "sample_id", "sha256", "filename", "num_functions", "num_minhash", "num_pichash", "direct_score", "direct_nonlib_score", "frequency_score", "frequency_nonlib_score", "uniq_score"],
            "available": []
        },
        "result_function_unfiltered_table": {
            "active": ["matched_function_id", "offset", "num_bytes", "num_matched_families", "num_matched_samples", "num_matched_functions", "best_score", "num_minhash", "num_pichash", "is_library_match", "is_unique_match"],
            "available": []
        },
        "result_function_sample_filtered_table": {
            "active": ["function_id_a", "offset_a", "offset_b", "function_id_b", "num_bytes", "best_score", "is_minhash_match", "is_pichash_match", "is_library_match", "is_unique_match"],
            "available": []
        },
        "result_function_function_filtered_table": {
            "active": ["function_id_a", "offset_a", "offset_b", "function_id_b", "family_name_b", "sample_id_b", "best_score", "is_minhash_match", "is_pichash_match", "is_library_match", "is_unique_match"],
            "available": []
        },
    }

    def __init__(self, user_id=None) -> None:
        self.user_id = user_id if user_id is not None else None

        # Dynamically create attributes based on the template with default positions
        for table_name, columns in self._default_settings.items():
            for position, column in enumerate(columns["active"]):
                attr_name = f"{table_name}_{column}"
                setattr(self, attr_name, position)  # Default to position (0, 1, 2, ...)

    @classmethod
    def fromDb(cls, user_id):
        db = get_db()
        cursor = db.cursor()
        record = cursor.execute("SELECT * FROM user_column_settings WHERE user_id = ?;", (user_id,)).fetchone()
        if record:
            user_column_settings = cls()
            user_column_settings.user_id = user_id
            
            # Set all column attributes from database record
            for table_name, columns in user_column_settings._default_settings.items():
                for default_position, column in enumerate(columns["active"]):
                    attr_name = f"{table_name}_{column}"
                    if attr_name in record.keys():
                        setattr(user_column_settings, attr_name, record[attr_name])
                    else:
                        setattr(user_column_settings, attr_name, default_position)  # Default to position
        else:
            user_column_settings = None
        return user_column_settings
    
    @classmethod
    def fromDict(cls, user_id, settings_dict):
        user_column_settings = cls()
        user_column_settings.user_id = user_id
        
        # Process the column settings dictionary
        if settings_dict and "column_settings" in settings_dict:
            column_settings = settings_dict["column_settings"]

            # Reset all to -1 (not selected) first
            for table_name, columns in user_column_settings._default_settings.items():
                for column in columns["active"]:
                    attr_name = f"{table_name}_{column}"
                    setattr(user_column_settings, attr_name, -1)
            
            # Set active columns with their positions based on input
            for table_name, table_config in column_settings.items():
                if table_name in user_column_settings._default_settings:
                    active_columns = table_config.get("active", [])
                    for position, column in enumerate(active_columns):
                        attr_name = f"{table_name}_{column}"
                        if hasattr(user_column_settings, attr_name):
                            setattr(user_column_settings, attr_name, position)

        else:
            # If no column settings were provided, use defaults
            for table_name, columns in user_column_settings._default_settings.items():
                for default_position, column in enumerate(columns["active"]):
                    attr_name = f"{table_name}_{column}"
                    setattr(user_column_settings, attr_name, default_position)

        return user_column_settings

    def _sanitize_column_settings(self):
        """Sanitize column settings to ensure proper integer positions and ordering"""
        for table_name, columns in self._default_settings.items():
            # Collect all active columns with their positions
            active_positions = []
            
            for default_position, column in enumerate(columns["active"]):
                attr_name = f"{table_name}_{column}"
                current_value = getattr(self, attr_name, default_position)
                
                # Convert None and non-integers to -1
                if current_value is None or not isinstance(current_value, int):
                    setattr(self, attr_name, -1)
                elif current_value >= 0:
                    # Collect positions for reordering
                    active_positions.append((current_value, column))
            
            # Sort by position and reassign sequential positions starting from 0
            active_positions.sort(key=lambda x: x[0])
            
            # Special handling for result_family_table score pairs
            if table_name == "result_family_table":
                active_positions = self._enforce_score_pair_ordering(active_positions)
            
            for new_position, (old_position, column) in enumerate(active_positions):
                attr_name = f"{table_name}_{column}"
                setattr(self, attr_name, new_position)

    def _enforce_score_pair_ordering(self, active_positions):
        """Ensure that score pairs are placed next to each other in result_family_table"""
        # Convert to a list of column names for easier manipulation
        columns = [column for position, column in active_positions]
        
        # Handle direct_score and direct_nonlib_score pair
        if "direct_score" in columns and "direct_nonlib_score" in columns:
            direct_score_idx = columns.index("direct_score")
            direct_nonlib_score_idx = columns.index("direct_nonlib_score")
            
            # If they're not adjacent, move direct_nonlib_score right after direct_score
            if direct_nonlib_score_idx != direct_score_idx + 1:
                # Remove direct_nonlib_score from its current position
                columns.pop(direct_nonlib_score_idx)
                # Insert it right after direct_score (adjust index if we removed from before)
                insert_idx = direct_score_idx + 1
                if direct_nonlib_score_idx < direct_score_idx:
                    insert_idx = direct_score_idx  # direct_score index shifted down
                columns.insert(insert_idx, "direct_nonlib_score")
        
        # Handle frequency_score and frequency_nonlib_score pair
        if "frequency_score" in columns and "frequency_nonlib_score" in columns:
            frequency_score_idx = columns.index("frequency_score")
            frequency_nonlib_score_idx = columns.index("frequency_nonlib_score")
            
            # If they're not adjacent, move frequency_nonlib_score right after frequency_score
            if frequency_nonlib_score_idx != frequency_score_idx + 1:
                # Remove frequency_nonlib_score from its current position
                columns.pop(frequency_nonlib_score_idx)
                # Insert it right after frequency_score (adjust index if we removed from before)
                insert_idx = frequency_score_idx + 1
                if frequency_nonlib_score_idx < frequency_score_idx:
                    insert_idx = frequency_score_idx  # frequency_score index shifted down
                columns.insert(insert_idx, "frequency_nonlib_score")
        
        # Convert back to (position, column) pairs
        return [(position, column) for position, column in enumerate(columns)]

    def toDict(self):
        # Sanitize data before processing
        self._sanitize_column_settings()
        
        result = {
            "user_id": self.user_id,
        }
        
        # Add all column settings with their positions
        for table_name, columns in self._default_settings.items():
            for default_position, column in enumerate(columns["active"]):
                attr_name = f"{table_name}_{column}"
                result[attr_name] = getattr(self, attr_name, default_position)
        
        return result
    
    def toUserColumnSettings(self):
        """Convert to the format expected by the frontend"""
        # Sanitize data before processing
        self._sanitize_column_settings()
        
        result = {}
        
        for table_name, columns in self._default_settings.items():
            result[table_name] = {
                "active": [],
                "available": []
            }
            
            # Create list of (position, column) pairs for active columns
            active_columns_with_positions = []
            
            for default_position, column in enumerate(columns["active"]):
                attr_name = f"{table_name}_{column}"
                position = getattr(self, attr_name, default_position)
                
                if position >= 0:
                    active_columns_with_positions.append((position, column))
                else:
                    result[table_name]["available"].append(column)
            
            # Sort by position and extract column names
            active_columns_with_positions.sort(key=lambda x: x[0])
            result[table_name]["active"] = [column for position, column in active_columns_with_positions]
        
        return result
    
    def saveToDb(self):
        # Sanitize data before saving
        self._sanitize_column_settings()
        
        database = get_db()
        # Query to see if row exists
        record = database.execute("SELECT * FROM user_column_settings WHERE user_id = ?;", (self.user_id,)).fetchone()
        
        # Build column names and values dynamically
        column_names = []
        column_values = []
        
        for table_name, columns in self._default_settings.items():
            for default_position, column in enumerate(columns["active"]):
                attr_name = f"{table_name}_{column}"
                column_names.append(attr_name)
                position = getattr(self, attr_name, default_position)
                column_values.append(position)
        
        if record:
            # Update existing record
            update_clauses = [f"{name} = ?" for name in column_names]
            query = f"UPDATE user_column_settings SET {', '.join(update_clauses)} WHERE user_id = ?;"
            database.execute(query, column_values + [self.user_id])
        else:
            # Insert new record
            placeholders = ', '.join(['?'] * (len(column_names) + 1))  # +1 for user_id
            columns_str = ', '.join(['user_id'] + column_names)
            query = f"INSERT INTO user_column_settings ({columns_str}) VALUES ({placeholders});"
            database.execute(query, [self.user_id] + column_values)
        
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
    with current_app.open_resource('sql' + os.sep + 'create_table_user_column_settings.sql') as f:
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
    # since version v1.4.0, we have user_column_settings, ensure table exists
    try:
        db.execute('SELECT * FROM user_column_settings').fetchone()
    except sqlite3.OperationalError:
        with app_context.open_resource('sql' + os.sep + 'create_table_user_column_settings.sql') as f:
            db.executescript(f.read().decode('utf8'))
        print(f"EXECUTED MIGRATION: CREATED TABLE USER_COLUMN_SETTINGS")


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

def get_user_by_apitoken(apitoken):
    user_id = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("SELECT * FROM user WHERE apitoken = ?;", (apitoken,)).fetchone()
    if record is not None:
        user_id = record["id"]
    return user_id

def get_username_by_apitoken(apitoken):
    username = None
    db = get_db()
    cursor = db.cursor()
    record = cursor.execute("SELECT * FROM user WHERE apitoken = ?;", (apitoken,)).fetchone()
    if record is not None:
        username = record["username"]
    return username