# Remote analytics operations

The implementation is available for synthetic validation. Collection is not
configured: `scripts/pace_remote_store.py:RELEASE` contains no endpoint, operator,
or contact. Sharing remains off, opt-in refuses to proceed, and automatic
invitations are hidden until a reviewed collecting release sets those values.

## Client controls

Local recording defaults on; remote sharing defaults off. The first eligible
interactive session offers a short one-time invitation; browser settings provide
Enable sharing, Not now, and Don't ask again. Dismissal persists across sessions,
clear and formatting reset. Revisit through Sharing settings or commands. None
of these choices makes a remote request. Local recording must already be on to
enable sharing. Headless/SDK skips and HUMAN_PACE=0 suppress session invitations.

```text
/pace analytics share
/pace analytics share on
/pace analytics share preview
/pace analytics share upload
/pace analytics share off
/pace analytics share delete
```

Opt-in queues only future successfully recorded observations. No history import,
prompt/reply text, rating notes, raw/local session IDs, paths or project names.
Preview emits exactly the next pending bounded batch; it is not an export of
history. Each manual upload sends at most 100 events/256 KiB. A network worker
exists only for the explicit request and is killed at the remaining 10-second
command deadline, including stalled DNS/headers. No daemon or hook network I/O.

The queue holds at most 10 MiB/10,000 canonical payloads. Incoming events evict
the oldest by insertion order; seven-day-old data expires after the inclusive
UTC-day upload horizon. Status reports evictions/expiry. Evicted in-flight events
may already have reached the server; they are never reconstructed or renumbered.

Off purges pending data and preserves old credentials for deletion. Local
analytics off also disables sharing; re-enabling local recording does not opt in.
Clear purges pending remote data and rotates observation state while preserving
consent and dismissal. Previously received data requires share delete. Requests
in flight can arrive after off; delete revokes ingestion server-side. Delete
covers all saved consent epochs and their original destinations. Rerun it to
check pending deletion or retry failures. Credentials remain until completion.
Losing the private credential ledger prevents client-authenticated deletion;
contact the operator for support. Never request conversation content for recovery.

## Service configuration

Proposed single-process collector: Python 3.9+ standard library, SQLite, internal
HTTP listener on 127.0.0.1. The database, credentials, journal and keys must be
private. Use separate storage for the deletion journal and checkpoint that is
not rolled back with event backups. Key material is a private file containing at
least 32 random bytes, not source code, command arguments or request logs. The
initial implementation uses one key version; retain it for registration recovery
and deletion. Key rotation needs an explicit migration preserving prior keys.

Example paths below are deployment examples, not a provisioned service:

```sh
python3 -m collector.server --database /srv/human-pace/events.sqlite3 --journal /srv/human-pace-deletions/journal.jsonl --key-file /srv/human-pace-secrets/collector.key --port 8080
python3 -m collector.maintenance maintain --database /srv/human-pace/events.sqlite3 --journal /srv/human-pace-deletions/journal.jsonl --key-file /srv/human-pace-secrets/collector.key
python3 -m collector.report --database /srv/human-pace/events.sqlite3 --start 2026-10-01 --end 2026-10-08
```

The public TLS proxy must verify its certificate deployment and enforce body,
header, connection, time and concurrency limits; overwrite or remove forwarded
source headers. The app ignores client-supplied source addresses. Per-source
registration protection is therefore primarily the proxy's responsibility.
The app enforces global ingress/registration, token ingestion limits, 10,000 new
accepted events/day/identity, 100,000 installation identities, and 1 GiB primary
payload storage. Duplicate receipts do not consume the daily new-event budget.
Provision capacity alerts before reaching these limits. Registration is public;
statistics are untrusted and can be fabricated, not verified people counts.

Disable payload, Authorization, recovery-key and token logging in the app,
proxy and provider. IP addresses do not enter analytics tables. Any necessary
security access logs expire within 7 days. Expose no HTTP report endpoint; the
report CLI requires access to the private database. Reports suppress small and
complementary slices and disclose selection bias, manual delays, scope and
identity resets. They measure observations, not comprehension or causality.

## Deletion, retention and backups

DELETE immediately commits revocation and excludes the identity from live
reports, then fsyncs an independent journal and checkpoint before returning a
pending receipt. A journal failure returns an error, leaves ingestion revoked,
and requires retry. The journal retains only pseudonymous identity, request time,
key version and a recovery digest; no events or plaintext tokens. This digest
allows revoked identities created after a backup to be reconstituted during
restore without being reactivated.

Run maintenance hourly and alert on failures. It journals revocations, deletes
primary event rows, and marks primary erasure completed; retention sweep keeps
only the inclusive last 90 UTC days. Meet the 24-hour primary erasure deadline.
Retain minimal revocation/authentication records and the independent journal
while they are needed to prevent reactivation and restore resurrection. No
permanent derived aggregate bypasses deletion; v1 has no report cache.

Back up using SQLite's backup API to immutable, standalone SQLite snapshots.
Do not copy a live database/WAL file pair as the supported backup format. Delete
backup snapshots after 30 days; independently retain the deletion journal and
checkpoint. Verify provider-managed snapshots and replica copies match this
policy. Before restoring, stop the collector and any maintenance/report jobs:

```sh
python3 -m collector.maintenance restore --database /srv/human-pace/events.sqlite3 --backup /srv/human-pace-backups/latest.sqlite3 --journal /srv/human-pace-deletions/journal.jsonl --key-file /srv/human-pace-secrets/collector.key
```

Restore clears readiness, checks journal/checkpoint consistency, replays every
tombstone into an isolated snapshot, removes revoked/expired events, checks
SQLite integrity, and only then replaces the database and creates readiness.
Missing/stale journal or mismatched key fails closed. Never restore both the
journal and its checkpoint to an older event backup. The independent journal's
freshness is an operator custody requirement; file consistency alone cannot
prove that both files were not rolled back together. Do not copy `.ready` from
backups or bypass readiness after a failed restore. Run a restore drill before
collection and after changing backup/storage configuration.

## Verification evidence

| Requirement | Verification |
|---|---|
| Default off, prospective opt-in, dismissal | test_remote_store, test_remote_integration |
| Strict allowlist, identifiers, no free text | test_remote_contract, test_remote_projection |
| Queue bounds and oldest-first eviction | test_remote_store; byte/count caps, batch suffix and in-flight receipt cases |
| No hook networking, failures preserve local behavior | test_remote_integration and existing local hook/settings tests |
| Deduplication, receipt loss, auth and limits | test_remote_transport, test_collector_store, test_collector_service |
| Off/new epochs and actual consent/revoke races | test_remote_integration, test_collector_store |
| Immediate report exclusion, purge, safe restore | test_collector_maintenance; including identities newer than backup |
| Denominators, gaps, cohorts and suppression | test_collector_report |
| Whole-command deadline and HTTPS restrictions | test_remote_transport; stalled child killed, redirects/TLS errors rejected |
| Hook overhead | scripts/benchmark_remote_queue.py --iterations 1000 |

Measured on macOS 26.6.2 ARM, Python 3.9.6, temporary filesystem, 1,000 samples per
case: incremental queue median/p95 ms empty 0.869/1.155, half-full 1.956/2.719,
capacity 3.382/5.005. Proposed budget: median under 5 ms, p95 under 20 ms.

## Collecting release readiness

- [ ] Choose operator, support contact, provider, region, endpoint and budget.
- [ ] Set and review release destination/notice constants; publish the exact schema and recipient notice.
- [ ] Provision TLS proxy and verify limits, source-header handling and certificate chain.
- [ ] Provision private versioned key custody and independent journal/checkpoint storage.
- [ ] Verify app/proxy/provider logging excludes payloads and secrets; security logs expire within 7 days.
- [ ] Schedule hourly maintenance, alerts and 24-hour deletion deadline monitoring.
- [ ] Verify SQLite backup creation, 30-day expiry for all copies, and safe restore drill.
- [ ] Review data access for private reports and raw storage; no public report endpoint.
- [ ] Invite explicitly consenting pilot users and assess main comparison coverage after 30 days.

At least five contributing identities per main comparison is the pilot usefulness
threshold, not a forecast. If manual uploads yield insufficient coverage, design
optional scheduled gathering separately; do not silently change the consent scope.
