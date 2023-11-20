DROP TABLE IF EXISTS server;

CREATE TABLE server (
  url VARCHAR NOT NULL,
  operation_mode VARCHAR NOT NULL,
  registration_token VARCHAR NOT NULL,
  server_token VARCHAR NOT NULL,
  server_uuid VARCHAR NOT NULL,
  server_version VARCHAR NOT NULL
);