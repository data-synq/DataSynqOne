# Deploy, migrate and rollback

1. Verify both application images by immutable digest and inspect their SBOM/provenance.
2. Confirm a successful, recent backup and isolated restore drill.
3. Run the one-shot `migrate` service. It obtains a PostgreSQL advisory lock, runs atomically,
   creates/updates the restricted runtime login and records its source checksum.
4. Start the backend only after migration exits successfully. Require `/ready` to return 200 before
   routing traffic or continuing the deployment.
5. Verify the audit chain, scheduler logs and Paperless connectivity.

The backend refuses a database newer than its supported schema or with a changed migration checksum.
Never edit an applied migration. Add a new numbered migration. Prefer expand/migrate/contract changes
that remain compatible with the previous image during rollout.

Digest delivery is claimed and acknowledged per user. SMTP failures remain retryable; an interrupted
delivery remains claimed because SMTP acceptance cannot be determined safely after a process crash.
Inspect and reconcile that row manually rather than risking a duplicate deadline mail.

Rolling back an image is allowed only while that image supports the current schema. Otherwise restore
the complete coordinated backup under the incident procedure and accept the documented data-loss window.
