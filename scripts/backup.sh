#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_DIR:?Set BACKUP_DIR to a protected destination}"
: "${PGSERVICEFILE:?Set PGSERVICEFILE to a protected PostgreSQL service file}"
: "${PGPASSFILE:?Set PGPASSFILE to a protected PostgreSQL password file}"
: "${DATASYNQ_PGSERVICE:?Set DATASYNQ_PGSERVICE}"
: "${PAPERLESS_PGSERVICE:?Set PAPERLESS_PGSERVICE}"
: "${PAPERLESS_MEDIA_DIR:?Set PAPERLESS_MEDIA_DIR}"
: "${PAPERLESS_QUIESCED:?Set PAPERLESS_QUIESCED=true after stopping all Paperless writers}"

if [[ "${PAPERLESS_QUIESCED}" != "true" ]]; then
  printf 'Refusing inconsistent backup: stop Paperless writers first.\n' >&2
  exit 1
fi
test -f "${PGSERVICEFILE}"
test -f "${PGPASSFILE}"
test -d "${BACKUP_DIR}"

umask 077
exec 9>"${BACKUP_DIR%/}/.datasynq-backup.lock"
if ! flock --nonblock 9; then
  printf 'Another DataSynq backup is already running.\n' >&2
  exit 1
fi
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${BACKUP_DIR%/}/${timestamp}"
mkdir "${destination}"

PGSERVICE="${DATASYNQ_PGSERVICE}" pg_dump --format=custom --no-owner --no-acl --file="${destination}/datasynq.dump"
PGSERVICE="${PAPERLESS_PGSERVICE}" pg_dump --format=custom --no-owner --no-acl --file="${destination}/paperless.dump"
tar --create --file="${destination}/paperless-media.tar" --directory="${PAPERLESS_MEDIA_DIR}" .

(
  cd "${destination}"
  sha256sum datasynq.dump paperless.dump paperless-media.tar > SHA256SUMS
)

cat > "${destination}/MANIFEST" <<EOF
created_at=${timestamp}
schema_version=1
format=postgres-custom+tar
required_secret=mfa_encryption_key
EOF

printf 'Backup created: %s\n' "${destination}"
