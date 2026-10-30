#!/bin/sh
# Versioned SQL migrations for PostgreSQL, independent of the language of the project.
#
#   migrate.sh            apply every pending migrations/NNN_name.sql in order
#   migrate.sh --to 005   stop after version 005 (lab 6: expand without contract)
#   migrate.sh --list     show applied and pending versions
#
# Runs in the postgres image (it has psql): see the `migrate` service in compose.yaml.
# Environment: DATABASE_URL (postgresql://user:pass@host:5432/db), MIGRATIONS_DIR (/migrations).
# Applied versions are kept in schema_migrations. Each file runs in ONE transaction together
# with its row in schema_migrations, so a file is applied completely or not at all.
# A file named NNN_name.notx.sql runs without the wrapping transaction (for statements that
# cannot run in one, such as CREATE INDEX CONCURRENTLY); keep such a file to one statement.
set -eu

DIR="${MIGRATIONS_DIR:-/migrations}"
URL="${DATABASE_URL:?set DATABASE_URL}"
TO=""
LIST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --to) TO="$2"; shift 2 ;;
    --list) LIST=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

sql() { psql "$URL" -X -q -v ON_ERROR_STOP=1 "$@"; }

sql -c "CREATE TABLE IF NOT EXISTS schema_migrations (
          version text PRIMARY KEY, name text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"

applied="$(sql -At -c "SELECT version FROM schema_migrations")"
found=0
for file in "$DIR"/[0-9][0-9][0-9]_*.sql; do
  [ -e "$file" ] || continue
  found=1
  name="$(basename "$file")"
  version="$(printf '%s' "$name" | cut -c1-3)"
  if printf '%s\n' "$applied" | grep -qx "$version"; then
    state=applied
  else
    state=pending
  fi
  if [ -n "$LIST" ]; then
    echo "$state  $name"
    continue
  fi
  if [ -n "$TO" ] && [ "$version" -gt "$TO" ]; then  # versions are three digits
    break
  fi
  [ "$state" = applied ] && continue
  record="INSERT INTO schema_migrations (version, name) VALUES ('$version', '$name')"
  case "$name" in
    *.notx.sql) sql -f "$file" && sql -c "$record" ;;
    *) sql --single-transaction -f "$file" -c "$record" ;;
  esac
  echo "applied  $name"
done
[ "$found" = 1 ] || echo "no migrations in $DIR"
