DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS user_filters;
DROP TABLE IF EXISTS server;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  role VARCHAR NOT NULL,
  registered VARCHAR NOT NULL,
  last_login VARCHAR
);

CREATE TABLE user_filters (
  user_id INTEGER PRIMARY KEY,
  filter_direct_min_score INTEGER,
  filter_direct_nonlib_min_score INTEGER,
  filter_frequency_min_score INTEGER,
  filter_frequency_nonlib_min_score INTEGER,
  filter_unique_only INTEGER,
  filter_exclude_own_family INTEGER,
  filter_function_min_score INTEGER,
  filter_function_max_score INTEGER,
  filter_max_num_families INTEGER,
  filter_exclude_library INTEGER,
  filter_exclude_pic INTEGER
);

CREATE TABLE server (
  url VARCHAR NOT NULL,
  operation_mode VARCHAR NOT NULL,
  registration_token VARCHAR NOT NULL,
  server_uuid VARCHAR NOT NULL,
  server_version VARCHAR NOT NULL
);