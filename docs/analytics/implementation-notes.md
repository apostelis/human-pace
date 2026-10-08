# Remote analytics implementation record

Branch: `codex/remote-analytics`. Base: `294e1ed`.

Final verification: 287 Python tests pass; rule export check and whitespace check
pass. Both rendered settings JavaScript blocks pass Node syntax checks. Synthetic
queue benchmarks meet the proposed overhead budget. No collecting endpoint,
operator, hosting or live user data has been configured.

Independent review identified a maintenance/journal race and sparse adoption
numerator/complement disclosure. Each was reproduced with failing tests, fixed,
and included in the green full suite. No deferred minor findings were reported.
The first reviewer hit an account usage limit; the successful replacement review
was read-only. Its deployment-related exclusions remain explicit operator launch
gates in the runbook; no public reporting service is exposed.

The execution record below preserves task progress, decisions and their costs.

# SDD ledger — plan: docs/superpowers/plans/2026-10-08-remote-analytics.md
Baseline: 294e1ed; 225 tests pass (socket tests require unsandboxed execution).
Pre-flight: Tasks 1→2/3/6/7 share contract; exact fields consistent. Tasks 2→4/5 share claims/consent; generation checks mandatory. Tasks 6→8/9 share deletion/read state; reports must query live revocation.
Ruling: Use native execution in this session — user requested implementation without selecting per-task delegation — cost if wrong: fewer independent review gates; final fresh review remains required.
Ruling: Use one server key version initially; key rotation requires preserving the original key for recoverable registrations — spec requires recovery, plan does not specify a rotation CLI — cost if wrong: operator migration needed for later key rotation.
Task 1: complete — missing-module RED → 4 contract tests GREEN; strict JSON, seven event types, canonical serialization and published schema.
Task 2: complete — missing-module RED → 7 queue tests GREEN. Projection unit cases also GREEN.
Ruling: Consent and deletion ledger share one bounded private preferences file — avoid cross-file partial metadata commits — cost if wrong: migration if separate files are later required.
Ruling: Projection introduced with queue to satisfy enqueue's exact local-event interface; Task 3 covers append integration — cost if wrong: task commit boundaries differ, behavior unchanged.
Ruling: Lost registration replies require recovery even for identities without saved credentials — delete must attempt recovery, not discard those credentials — cost if wrong: an unused identity may be registered solely to delete it.
Task 3: complete — integration 0 prompts RED → 3 recorder lifecycle cases GREEN; existing 46 local analytics tests pass. Command routing case awaits Task 5.
Task 4: complete — missing-module RED → 6 transport tests GREEN; same-ID retry, malformed receipts, auth suspension, registration and deletion tested. Deadline socket scenarios expanded in final verification.
Task 5: complete — command/session/settings assertions RED → 7 integration tests GREEN; full suite 251/251. No release endpoint configured, so production invitations/opt-in are unavailable pending deployment configuration.
Correction: Task 3 existing analytics suite had 48 tests, not 46.
Task 6: complete — missing-module RED → 5 collector persistence cases GREEN. Immediate revocation journal seam introduced with store; retention/restore follow Task 8.
Task 7: complete — missing-module RED → 5 HTTP/service cases GREEN including real loopback server. Source-based limits on reverse-proxy traffic intentionally remain the proxy responsibility; app ignores untrusted forwarded source headers.
Task 8: complete — missing maintenance API RED → 4 deletion/restore cases GREEN, including failed fsync and stale checkpoint. Root cause of initial restore error: readonly WAL snapshot required sidecar creation; use immutable SQLite backup snapshots and explicitly close/checkpoint restore connections before swapping files.
Ruling: Restore consumes immutable standalone snapshots made with SQLite backup API, not live WAL file copies — required for consistent sidecar-free replay — cost if wrong: unsupported backup methods refuse or require conversion.
Task 9: complete — missing-module RED → 5 deterministic metric cases GREEN. Comparisons suppress entire related tables if any complementary slice is sparse, instead of allowing arbitrary drilldowns.
Ruling: Conservative whole-table suppression — prevents subtraction across sparse configurations without a complex disclosure engine — cost if wrong: useful large slices may be hidden until all peers meet threshold.
Ruling: Explicit HTTPS requests run in short-lived worker processes — socket timeouts do not bound libc DNS or trickled HTTP headers — cost if wrong: additional process startup overhead on manual uploads only. No daemon or hook network work.
Task 10: complete — lifecycle retry/delete across epochs GREEN; expired session HMAC, resumed changes, hard network worker timeout, quota duplicate handling, newer-than-backup revocation and failed activation all reproduced RED then GREEN. Full suite 281 before final activation regression; updated suite follows final verification. Benchmark 1000 iterations: incremental median/p95 ms empty 0.869/1.155, half 1.956/2.719, capped 3.382/5.005 on macOS26.6.2 ARM Python3.9.6, temporary filesystem; under 5/20 budget.
Ruling: Keep original recipient snapshot with every identity and delete against that destination — avoid sending old deletion credentials to a changed recipient — cost if wrong: operator must retain support for old endpoints.
Ruling: Keep recovery digest in minimal deletion tombstones — recreate revoked identities absent from older backups without event payloads — cost if wrong: retained pseudonymous authentication digest outlives event retention.
Task 11: complete — runbook and user help include invitation, manual gathering, newest-event retention, deletion/restore and unchecked operator readiness gates; full suite 284/284; export check and diff check pass. Concurrent off/registration and revoke/ingest tests GREEN.
Final review: first reviewer unavailable due usage cap; second reviewer running on available model.
Final: fixed maintenance completing newly revoked unjournaled identities — test_maintenance_does_not_complete_revocation_after_journal_snapshot RED→GREEN; maintenance now finalizes only successfully journaled snapshot identities. Full suite follows once review finishes.
Final: fixed sparse adoption numerator/complement disclosure — two adoption regression fixtures RED→GREEN; renderer suppresses entire adoption column if a numerator or complement has 1–4 active contributors. Full suite 287/287, exports and diff check pass.
Final review: fresh read-only reviewer found two concrete issues; both fixed in one regression-tested pass. No deferred minors reported. Reviewer declined deployed provider/proxy/TLS/permissions/scheduling/backup custody/load/public disclosure and exhaustive schema reconciliation; deployment is unconfigured and no public report exists, so these remain explicit launch gates rather than assumed verification.
Final: Ruling: Deployment/provider verification remains an operator launch gate — no endpoint or service has been provisioned — cost if wrong: collecting release must not activate without those checks.
