-- Run once as a PostgreSQL superuser (docker compose does this automatically).
-- Creates the two application roles and the dev + test databases with PostGIS.
-- Dev-only passwords; production credentials come from a secrets manager.
CREATE ROLE ps_owner LOGIN PASSWORD 'ps_owner_dev' CREATEDB;
CREATE ROLE ps_api LOGIN PASSWORD 'ps_api_dev';
-- Provider portal: writes provider accounts, homepages, reviews and counts only.
CREATE ROLE ps_portal LOGIN PASSWORD 'ps_portal_dev';
-- Tests switch to the two restricted roles (SET ROLE) so every route is checked
-- with exactly the permissions it has when hosted (2026-11-12).
GRANT ps_api, ps_portal TO ps_owner;
CREATE DATABASE procedurescout OWNER ps_owner;
CREATE DATABASE procedurescout_test OWNER ps_owner;
\c procedurescout
CREATE EXTENSION IF NOT EXISTS postgis;
\c procedurescout_test
CREATE EXTENSION IF NOT EXISTS postgis;
