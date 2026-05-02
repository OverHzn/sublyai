#!/usr/bin/env bash
# SublyAI container entrypoint.
#
# Bind-mounted directories (downloads/, outputs/, jobs/) inherit their owner
# from the host, which on a fresh `git clone` as root will be root:root. Our
# in-container user is uid 1000 and would not be able to write there, so we
# fix ownership at startup and then drop privileges with gosu.
#
# Setting SUBLYAI_RUN_AS_ROOT=1 in the environment skips the privilege drop
# (useful when bind-mounting filesystems where chown is not allowed, e.g. CIFS).

set -euo pipefail

APP_USER="app"
APP_UID="1000"
APP_GID="1000"

fix_dir() {
    local dir="$1"
    if [[ -d "$dir" ]]; then
        # Only chown when the directory is not already owned by APP_UID.
        local owner
        owner="$(stat -c '%u' "$dir" 2>/dev/null || echo 0)"
        if [[ "$owner" != "$APP_UID" ]]; then
            chown -R "${APP_UID}:${APP_GID}" "$dir" 2>/dev/null || true
        fi
    fi
}

if [[ "$(id -u)" == "0" ]]; then
    fix_dir /app/downloads
    fix_dir /app/outputs
    fix_dir /app/jobs
    fix_dir /home/app/.cache

    if [[ "${SUBLYAI_RUN_AS_ROOT:-0}" == "1" ]]; then
        exec "$@"
    fi

    # Drop to the app user. Prefer gosu, fall back to su -p.
    if command -v gosu >/dev/null 2>&1; then
        exec gosu "$APP_USER" "$@"
    else
        exec su -p "$APP_USER" -c 'exec "$@"' -- bash "$@"
    fi
fi

exec "$@"
