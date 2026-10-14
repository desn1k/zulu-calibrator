#!/bin/sh
# Online backup of the SQLite database with `sqlite3 .backup` (safe while the app is running).
# Runs once at start and then every BACKUP_INTERVAL_SECONDS; keeps the newest BACKUP_KEEP copies.
# `backup.sh --once` makes a single backup and exits (used before a restore).
set -eu

DB="${DB_PATH:-/data/app.db}"
DIR="${BACKUP_DIR:-/backups}"
KEEP="${BACKUP_KEEP:-14}"
INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"

backup_once() {
    if [ ! -f "$DB" ]; then
        echo "backup: $DB not found yet, skipping"
        return 0
    fi
    ts=$(date -u +%Y%m%dT%H%M%SZ)
    tmp="$DIR/.app-$ts.db.tmp"
    out="$DIR/app-$ts.db"

    # Check explicitly: in the loop set -e is off (backup_once || true), and integrity_check on a
    # missing $tmp would create an empty database that passes the check.
    if ! sqlite3 "$DB" ".backup '$tmp'"; then
        rm -f "$tmp"
        echo "backup: sqlite3 .backup failed"
        return 1
    fi
    if [ "$(sqlite3 "$tmp" 'PRAGMA integrity_check;')" != "ok" ]; then
        rm -f "$tmp"
        echo "backup: integrity check failed, backup discarded"
        return 1
    fi
    mv "$tmp" "$out"
    echo "backup: wrote $out"

    # File names sort by time; delete everything older than the newest $KEEP.
    ls -1 "$DIR"/app-*.db 2>/dev/null | sort -r | tail -n +"$((KEEP + 1))" | while read -r old; do
        rm -f -- "$old"
        echo "backup: removed $old"
    done
}

if [ "${1:-}" = "--once" ]; then
    backup_once
    exit $?
fi

while true; do
    backup_once || true
    sleep "$INTERVAL"
done
