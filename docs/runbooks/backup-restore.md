# Backup and restore

## Policy

- Target RPO: 24 hours. Target RTO: 4 hours.
- Keep daily encrypted off-host backups for 35 days and monthly backups for 12 months.
- Back up both PostgreSQL databases, Paperless media, the deployment manifest and the separately
  protected `mfa_encryption_key`. Redis and embeddings alone are not authoritative backups.
- Never copy a live PostgreSQL data directory as a backup.
- Run an isolated restore drill at least quarterly and after migration changes.

## Backup

Run `scripts/backup.sh` from a trusted administration host with `pg_dump`, `tar`, `flock` and
`sha256sum`.
First stop the Paperless web server, task workers and consumers so database and media cannot change;
set `PAPERLESS_QUIESCED=true` only after verifying that state. The script otherwise refuses to run.
Use a mode-0600 `PGSERVICEFILE` plus `PGPASSFILE` and provide the two non-secret service names through
`DATASYNQ_PGSERVICE` and `PAPERLESS_PGSERVICE`; database passwords never enter process arguments.
Restart Paperless in a shell `trap` or equivalent deployment finally-step even when backup fails.
Encrypt the completed directory before transfer to off-site storage. Record image digests and the MFA
secret key version in the external backup inventory.

## Restore drill

1. Run `scripts/restore-check.sh BACKUP_DIRECTORY`.
2. Create two empty temporary PostgreSQL databases with the required pgvector extension.
3. Restore with `pg_restore --clean --if-exists --no-owner` only into those temporary databases.
4. Restore media into an empty temporary directory.
5. Verify `schema_migrations`, user/case/document counts and a vector similarity query.
6. Start the pinned backend image against the restored application database and require `/ready` 200.
7. Start Paperless against the restored database/media and inspect random document originals.
8. Destroy the temporary environment and record duration, backup timestamp and result.

Production restore requires an incident decision. An image rollback is not a database rollback.
