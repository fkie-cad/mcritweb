DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS server;

CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  role VARCHAR NOT NULL,
  registered VARCHAR NOT NULL,
  last_login VARCHAR
);

CREATE TABLE server (
  url VARCHAR NOT NULL,
  operation_mode VARCHAR NOT NULL,
  registration_token VARCHAR NOT NULL,
  server_uuid VARCHAR NOT NULL,
  server_version VARCHAR NOT NULL
);