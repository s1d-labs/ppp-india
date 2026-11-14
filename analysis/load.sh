#!/bin/sh
# Copy this family's records from scrape_hub into ws_trideep (schema ppp) for analysis and Metabase. Re-runnable.
set -e
psql -q -d ws_trideep -c "create schema if not exists ppp"
for t in rows docs missing pages old; do psql -q -d ws_trideep -c "drop table if exists ppp.raw_$t cascade"; done
psql -q -d ws_trideep -c "create table ppp.raw_rows (record_id text primary key, data jsonb, scraped_at timestamptz)"
psql -q -d ws_trideep -c "create table ppp.raw_docs (record_id text primary key, data jsonb, scraped_at timestamptz)"
psql -q -d ws_trideep -c "create table ppp.raw_old (record_id text primary key, data jsonb, scraped_at timestamptz)"
psql -d scrape_hub -Atc "copy (select record_id, data, scraped_at from records where project='ppp-india-portal' and data->>'kind'='row') to stdout" | psql -q -d ws_trideep -c "copy ppp.raw_rows from stdin"
psql -d scrape_hub -Atc "copy (select record_id, data, scraped_at from records where project='ppp-india-portal' and data->>'kind' in ('doc','missing','page')) to stdout" | psql -q -d ws_trideep -c "copy ppp.raw_docs from stdin"
psql -d scrape_hub -Atc "copy (select record_id, data, scraped_at from records where project='ppp-india-wayback') to stdout" | psql -q -d ws_trideep -c "copy ppp.raw_old from stdin"
psql -q -d ws_trideep -f "$(dirname "$0")/views.sql"
