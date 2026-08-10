# Database unavailable

1. Confirm `/live` remains 200 and `/ready` is 503.
2. Inspect PostgreSQL health, disk space, connection count and the backend pool without exposing DSNs.
3. Stop repeated deploy attempts if migration lock or checksum errors are present.
4. Restore connectivity; do not delete `schema_migrations` or bypass its checksum.
5. Require `/ready` 200 and verify recent audit sequence continuity before reopening traffic.
