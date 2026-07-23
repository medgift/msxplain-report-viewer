-- Runs once on first initialization of the Postgres data volume.
-- GoTrue connects with search_path=auth and migrates into the `auth` schema,
-- but it does not create that schema itself, so we create it up front.
CREATE SCHEMA IF NOT EXISTS auth;
