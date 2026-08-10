#!/usr/bin/env bash
set -euo pipefail

: "${1:?Usage: restore-check.sh BACKUP_DIRECTORY}"
backup_dir="$1"

test -f "${backup_dir}/MANIFEST"
test -f "${backup_dir}/SHA256SUMS"
(
  cd "${backup_dir}"
  sha256sum --check SHA256SUMS
)
pg_restore --list "${backup_dir}/datasynq.dump" >/dev/null
pg_restore --list "${backup_dir}/paperless.dump" >/dev/null
tar --list --file="${backup_dir}/paperless-media.tar" >/dev/null

grep -qx 'schema_version=1' "${backup_dir}/MANIFEST"
grep -qx 'required_secret=mfa_encryption_key' "${backup_dir}/MANIFEST"
printf 'Backup artifacts and checksums validated. Perform the scheduled isolated restore drill.\n'
