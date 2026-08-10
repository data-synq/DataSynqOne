#!/bin/sh
set -eu

read_required_secret() {
    variable=$1
    file=$2
    if [ ! -r "$file" ]; then
        printf 'Required Paperless secret is not readable: %s\n' "$file" >&2
        exit 1
    fi
    value=$(cat "$file")
    if [ -z "$value" ]; then
        printf 'Required Paperless secret is empty: %s\n' "$file" >&2
        exit 1
    fi
    export "$variable=$value"
}

read_optional_secret() {
    variable=$1
    file=$2
    [ -r "$file" ] || return 0
    value=$(cat "$file")
    export "$variable=$value"
}

read_required_secret PAPERLESS_DBPASS /run/secrets/paperless_db_password
read_required_secret PAPERLESS_SECRET_KEY /run/secrets/paperless_secret_key
read_optional_secret PAPERLESS_ADMIN_PASSWORD /run/secrets/paperless_admin_password

exec /init
