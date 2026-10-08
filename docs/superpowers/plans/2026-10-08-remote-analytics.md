# Remote Analytics Gathering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Gather prospective, explicitly shared human-pace usage through manual bounded uploads, with trustworthy aggregate reports and deletion controls.

**Architecture:** A shared Python contract validates the separate remote schema. The client queues sanitized events only after successful local recording; explicit commands register, upload, and delete. A single collector service stores authenticated contributions in SQLite and exposes maintainer reports through a local operator CLI; a deployment TLS proxy protects its HTTP listener.

**Tech Stack:** Python 3.9+ standard library, unittest, SQLite, existing Claude hooks and command entry points. No client third-party dependencies. Proposed initial collector uses standard-library HTTP routing behind a production proxy; no public exposure of the internal HTTP listener.

**Spec:** [Remote gathering design](../specs/2026-10-08-remote-analytics-design.md), with [local design](../specs/2026-10-08-local-analytics-design.md) and [local implementation plan](2026-10-08-local-analytics.md).

## Global Constraints

- Sharing defaults to off, independently of local recording.
- Use standard-library Python 3.9+ on the client.
- There is no network I/O in hooks, normal formatting commands, rating writes, or settings saves.
- V1 has no background daemon or scheduler.
- Queue cap: 10 MiB or 10,000 events, whichever is reached first.
- When full, evict the oldest queued events to admit new events; expire unsent events after 7 days.
- Upload limit: one batch per command, up to 100 events and 256 KiB JSON body; individual events remain limited to 16 KiB.
- Set connection/read timeouts and a 10-second total command network deadline.
- Use TLS verification, a fixed release-configured endpoint, and no redirects.
- Enforce persisted exponential backoff from 1 minute to 24 hours.
- Retain received events for at most 90 days from their event day; reject future days and events older than the 7-day upload horizon.
- Remove primary events, contribution tables, and caches within 24 hours of deletion; exclude the identity from reports immediately.
- Backups expire within 30 days; unavoidable security access logs within 7 days.
- Suppress comparative slices with fewer than five distinct installations.
- Every off→on cycle starts a new identity; preserve deletion credentials for previous identities.
- No prompts, replies, notes, paths, raw arguments, raw/local session identifiers, environment dumps, or raw exception messages in remote events.
- All tests use temporary stores and synthetic data. Preserve unrelated working-tree changes.

## Current baseline and execution gates

`scripts/pace_analytics.py`, `scripts/pace_analytics_report.py`, and local integration tests now exist. The local implementation defaults recording to on by owner amendment, while remote sharing remains off. Do not change that local default. The remote spec's statement that the local recorder is absent is historical; inspect the current implementation before execution.

The spec is proposed. This plan uses manual gathering and a single-process SQLite collector as concrete implementation choices for review. Work on contract/client/collector fixtures can proceed without choosing a provider. A shipped collecting release requires actual operator, endpoint, support contact, region, proxy, and backup settings; an unset endpoint must refuse opt-in and upload, never silently select a destination.

At execution, use the worktree skill to create or reuse an isolated checkout. Run the current suite first and record failures before changing code. Do not import historical local JSONL or ratings. No deployment or live pilot is part of implementing this plan.

The subsystems share one contract and coordinated lifecycle, so use one ordered plan with three independently testable milestones: contract/client with fake transport (Tasks 1–5), collector with synthetic requests (Tasks 6–8), and complete gathering/reporting (Tasks 9–11).

## Review Focus

1. Client clock rollback must not send events before consent or silently reset a session sequence (Tasks 2–3).
2. Duplicate JSON object keys, booleans disguised as integers, and deeply nested payloads must be rejected without exposing their contents (Tasks 1 and 7).
3. Process termination after the server commits but before the client saves a receipt must retry the same identity/event IDs (Tasks 4 and 6–7).
4. Clear/off/re-enable while an upload is in flight must not remove new-epoch data or resurrect old claims (Tasks 2, 4, and 5).
5. A report assembled after deletion or restoration must not expose a removed installation through cached totals or complementary slices (Tasks 8–9).

## File map

| File | Responsibility |
|---|---|
| `scripts/pace_remote_contract.py` | Exact remote validation, canonical serialization, constants shared by client and collector |
| `docs/analytics/remote-event-v1.schema.json` | Published seven-event JSON Schema with strict field allowlists |
| `scripts/pace_remote_store.py` | Consent, identities/credential ledger, queue, sequence state, claims, diagnostics |
| `scripts/pace_remote_projection.py` | Local-event to remote-event conversion and epoch baselines |
| `scripts/pace_remote_transport.py` | HTTPS-only client, deadlines, response validation, retries, registration/upload/delete orchestration |
| `scripts/pace_remote_commands.py` | Share commands and bounded human-readable outcomes |
| `scripts/inject.py`, `scripts/preview.py`, `preview/index.html` | One-time session invitation, settings choices, and local consent routing |
| `scripts/pace_analytics.py` | Successful append integration and coordinated off/clear lifecycle |
| `scripts/pace.py` | Route share controls before native mutation restrictions |
| `scripts/pace_analytics_report.py` | Accurate local/remote status disclosure |
| `collector/__init__.py`, `collector/store.py` | Server schema, registration, transactions, revocation, retention |
| `collector/service.py`, `collector/server.py` | Pure request handler and bounded internal HTTP adapter |
| `collector/maintenance.py` | Primary purge, durable deletion journal, backup/restore gate |
| `collector/report.py` | Pure aggregate computation and private CLI rendering |
| `tests/test_remote_contract.py`, `tests/test_remote_store.py` | Remote contract and local queue/lifecycle fixtures |
| `tests/test_remote_projection.py`, `tests/test_remote_transport.py` | Projection, failure/retry/deadline tests |
| `tests/test_remote_integration.py` | Existing entry-point and complete upload lifecycle tests |
| `tests/test_collector_store.py`, `tests/test_collector_service.py` | Collector persistence, authentication, bounds, rate limits |
| `tests/test_collector_maintenance.py`, `tests/test_collector_report.py` | Deletion, restore, metric fixtures |
| `tests/remote_test_support.py` | Deterministic synthetic event/session/clock/transport helpers |
| `docs/analytics/remote-operations.md`, `scripts/benchmark_remote_queue.py` | Operator runbook and isolated latency measurement |
| `commands/pace.md`, `README.md`, `CHANGELOG.md`, `.github/workflows/ci.yml` | User help, unreleased summary, existing Python CI coverage |

Collector imports the contract from `scripts`; its server entry point explicitly adds the repository's `scripts` directory to `sys.path`, following existing test import conventions. Do not duplicate normalization or event enums in server code.

## Interface contract

Use aware UTC datetimes at entry points, injectable clocks and transport in tests, and named bounded errors. The following signatures are the interfaces between tasks; task code supplies their implementations.

```python
# pace_remote_contract.py
encode_event(event: dict) -> bytes
encode_batch(events: list) -> bytes  # envelope keys: schema_version=1, events=list
validate_event(value: object) -> dict  # raises ContractError; never returns unvalidated input
strict_json(data: bytes, *, max_bytes: int) -> object

# pace_remote_store.py
RemoteStore(root: Path)
RemoteStore.enable(*, now: datetime, local_enabled: bool, release: dict) -> dict
RemoteStore.disable(*, now: datetime) -> dict
RemoteStore.clear_pending_locked(*, now: datetime) -> None
RemoteStore.enqueue_locked(events: list, *, now: datetime) -> bool
RemoteStore.claim(*, now: datetime) -> dict  # claim_id, generation, identity, body, event_ids
RemoteStore.current(claim: dict) -> bool
RemoteStore.finish(claim: dict, receipt: dict, *, now: datetime) -> dict
RemoteStore.fail(claim: dict, *, reason: str, retry_at: datetime, suspended: bool) -> None
RemoteStore.save_credentials(identity: str, credentials: dict, *, generation: int) -> None
RemoteStore.deletion_targets(*, now: datetime) -> list
RemoteStore.deletion_receipt(identity: str, receipt: dict) -> None
RemoteStore.status(*, now: datetime) -> dict
RemoteStore.preview(*, now: datetime) -> bytes
RemoteStore.invitation(*, surface: str, now: datetime, local_enabled: bool, release: dict) -> dict
# visible, choice, disclosure; surface is session/settings; session atomically claims one notice
RemoteStore.choose_invitation(choice: str, *, now: datetime, local_enabled: bool, release: dict) -> dict
# choice is enable/later/never; enable delegates to the same locked consent helper as enable()

# pace_remote_projection.py
project(local: dict, *, identity: str, secret: bytes,
        sequence: Optional[int], previous: Optional[dict]) -> Optional[dict]

# pace_remote_transport.py
HttpsTransport(endpoint: str, *, clock: Callable[[], float])
HttpsTransport.request(method: str, path: str, *, body: bytes,
                      credential: Optional[str], deadline: float) -> dict
upload(store: RemoteStore, transport: HttpsTransport, *, now: datetime) -> dict
delete_all(store: RemoteStore, transport: HttpsTransport, *, now: datetime) -> dict

# pace_remote_commands.py
run_share(args: list, *, now: datetime, store: RemoteStore,
          local_enabled: bool, release: dict, transport: Optional[object] = None) -> str

# collector/store.py
CollectorStore(database: Path, *, key: bytes)
CollectorStore.register(identity: str, recovery_key: str, *, now: datetime) -> dict
CollectorStore.ingest(credential: str, events: list, *, now: datetime) -> dict
CollectorStore.request_delete(credential: str, *, now: datetime) -> dict
CollectorStore.deletion_status(credential: str) -> dict
CollectorStore.live_events(*, start: date, end: date) -> list

# collector/service.py
handle(store: CollectorStore, method: str, path: str, *, headers: dict,
       body: bytes, now: datetime, limiter: object) -> tuple  # (status, headers, body)

# collector/maintenance.py
maintain(store: CollectorStore, journal: Path, *, now: datetime) -> dict
restore(database: Path, backup: Path, journal: Path, *, key: bytes, now: datetime) -> dict

# collector/report.py
summarize(events: list, *, start: date, end: date) -> dict
render(summary: dict) -> str
```

`RemoteStore` uses the same `store.lock` as local analytics. Methods ending in `_locked` require that lock already held; they must never reacquire it. Public methods acquire it nonblockingly. Projection sequence/state updates and queue insertion are one local transaction. The collector uses SQLite transactions, unique constraints, foreign keys, and a finite busy timeout. Network calls take place outside filesystem locks.

### Task 1: Publish and enforce the remote contract

**Files:** Create `scripts/pace_remote_contract.py`, `docs/analytics/remote-event-v1.schema.json`, `tests/test_remote_contract.py`, and `tests/remote_test_support.py`.
**Consumes:** `pace_analytics.FIELDS`, `BASE`, `CONFIG`, `config_identity`, and `validate_event`.
**Produces:** Strict serialization/validation functions above and test helper `prompt(identity, session, sequence, cfg=None, day="2026-10-08") -> dict`.

- [x] Write a valid fixture helper using `pace_config.defaults()` and `pace_analytics.config_identity()`. Remote base fields are `schema_version`, `event_id`, `event`, `day`, `installation_id`, `plugin_version`, `integration`, `source`, `session_key`; add `prompt_sequence` only to prompt events (null iff session is null). Config and event-specific fields follow the local event contract. Use 32-character lowercase random hex identity/event IDs and 64-character hex session HMACs.
- [x] Add tests for all seven event types, required/unknown fields, version mismatch, invalid config hashes, boolean scores/sequences, exact canonical day strings, invalid plugin version/source/integration, and oversized/deeply nested input. Include:

```python
def test_unknown_fields_and_duplicate_keys_are_rejected(self):
    event = prompt("a" * 32, "b" * 64, 1)
    with self.assertRaises(contract.ContractError):
        contract.validate_event({**event, "note": "secret"})
    with self.assertRaises(contract.ContractError):
        contract.strict_json(b'{"schema_version":1,"schema_version":2}', max_bytes=16384)
```

- [x] Run `python3 -m unittest discover -s tests -p 'test_remote_contract.py' -v`; expect the new import or validator assertions to fail.
- [x] Implement `ContractError`, constants, duplicate-key rejection with `object_pairs_hook`, bounded recursive depth (16), canonical `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)`, and a validator that reconstructs a synthetic local event for shared checks, substituting a UTC midnight timestamp and removing remote-only fields. Validate remote identifiers and prompt sequence separately with exact integer types. Reject nonfinite numbers and encoded events over 16 KiB.
- [x] Publish JSON Schema with seven `oneOf` branches, explicit `additionalProperties: false`, local config field enums/ranges, and nullable session/sequence rules. Hash consistency remains a documented semantic validator check. Test every branch with positive and negative fixtures against Python validation; check schema branch/field parity without adding client dependencies.
- [x] Rerun the targeted tests; expect PASS. Commit only this task's files with `feat: define remote analytics event contract`.

### Task 2: Consent, epoch identities, private queue, and claims

**Files:** Create `scripts/pace_remote_store.py`, `tests/test_remote_store.py`.
**Consumes:** Contract serialization; existing analytics lock and private file helpers.
**Produces:** `RemoteStore` lifecycle/queue methods and a private `remote/` directory.

- [x] Add temporary-store tests: absent sharing preferences means off; enabling requires local recording and a complete release destination; idempotent on preserves identity; off→on rotates it; off purges pending events and retains deletion ledger. Test 0700/0600 permissions where supported and symlink refusal.
- [x] Test an old upload claim against a new epoch:

```python
def test_old_receipt_cannot_remove_new_epoch_data(self):
    self.enable()
    self.enqueue_prompt()
    old = self.store.claim(now=NOW)
    self.store.disable(now=NOW)
    self.enable()
    self.enqueue_prompt()
    self.store.finish(old, {"accepted": old["event_ids"], "duplicate": [], "rejected": []}, now=NOW)
    self.assertEqual(self.store.status(now=NOW)["queued_count"], 1)
    self.assertFalse(self.store.current(old))
```

Here test-class `enable()` supplies a synthetic release dict; `enqueue_prompt()` holds the local lock and calls `enqueue_locked` with one newly constructed local event. Define both in this task's test class, never against user storage.
- [x] Run `python3 -m unittest discover -s tests -p 'test_remote_store.py' -v`; expect FAIL.
- [x] Implement `remote/preferences.json` (enabled, generation, notice/schema/recipient fingerprint, consent time, invitation choice, session-notice-shown), `remote/identities.json` (current and previous identities, recovery keys, credentials, deletion state), and `remote/queue.sqlite3` (events, session state, diagnostics, claim metadata). Metadata writes are atomic/private under the shared lock. Queue rows store canonical remote event bytes, event day, insertion time, identity, and claim ID. Store bounded counters in the same transaction; cap canonical queued bytes, not SQLite file size. Reclaim SQLite free pages during explicit maintenance, never hooks; bound session-state rows to 10,000 and expire inactive state after 7 days. Reaching that state limit omits session association for additional sessions and discloses it instead of reusing keys.
- [x] Assign monotonically increasing prompt sequences before capacity checks and persist them even when a queued event is evicted. Missing/corrupt sequence state rotates the remote session HMAC salt, creating a baseline instead of resetting a known session sequence. Reject recording before consent time; disclose clock rollback locally. Expiry uses UTC day cutoff `now.date() - timedelta(days=7)` consistently with server acceptance.
- [x] Implement oldest-first eviction and insertion in one queue transaction. Use a monotonic SQLite insertion ordinal, not event time, for ordering; expire stale events first, then delete the oldest rows until each validated incoming event fits both caps. Process incoming events in order so an oversized batch retains its newest suffix. Never evict for a rejected individual event. Increment evicted counters without changing prompt sequences or retained event IDs. Remove empty claims; allow in-flight receipts to reference their original IDs but ignore already-evicted rows. Claims retain metadata only, not a second persistent payload copy.
- [x] Add concrete queue boundary tests:

```python
def test_full_queue_retains_newest_events(self):
    with patch.object(remote_store, "MAX_QUEUE_EVENTS", 2):
        for operation in ("status", "toggle", "rate"):
            event = analytics.make_event("command_invoked", now=NOW,
                integration="unknown", source="pace", operation=operation, outcome="success")
            with self.local._lock():
                self.store.enqueue_locked([event], now=NOW)
        batch = json.loads(self.store.preview(now=NOW))
        self.assertEqual([e["operation"] for e in batch["events"]], ["toggle", "rate"])
        self.assertEqual(self.store.status(now=NOW)["evicted_count"], 1)
```

The fixture starts with consent enabled and a temporary local store; `remote_store.MAX_QUEUE_EVENTS` is the production 10,000-event constant. Repeat with the byte cap, equal insertion timestamps, an over-cap incoming batch, a claimed oldest event, and a malformed incoming event. Retained sequence numbers must have gaps after eviction.
- [x] Implement claim selection of one canonical batch respecting count/body bounds, a 30-second claim lease, and generation-tagged acknowledgements. Expired claims become pending with unchanged event IDs. Bound preview to exactly the next batch, print remaining counts in status separately, and acknowledge only IDs belonging to the claim. Malformed/unwritable preferences fail closed for sharing while local recording continues. Explicit controls surface errors.
- [x] Expire payload queue rows after 7 days, but retain the credential ledger for deletion. Persist a bounded local warning when prior-epoch ledger entries reach 100; refuse another consent epoch until deletion completes rather than silently discarding credentials or letting metadata grow without limit. A never-registered identity can be removed locally without a remote deletion call.
- [x] Test cap equality/overflow, seven-day boundary, partial receipts, killed-claim recovery, corrupt state, full disk, busy lock, expiration, and repeated clear. Rerun targeted tests; expect PASS. Commit with `feat: add opt-in remote analytics queue`.

### Task 3: Project only prospective successfully recorded local events

**Files:** Create `scripts/pace_remote_projection.py`, `tests/test_remote_projection.py`; modify `scripts/pace_analytics.py` (`record`, `observe`, successful append boundary).
**Consumes:** Local validator, remote store and contract.
**Produces:** `project` and exactly one queue attempt for every successfully appended local event batch.

- [x] Add tests using real local store operations with network access patched to fail. Assert default-on local recording produces no remote directory/events; after sharing opt-in, ordinary prompt observations queue once even when no rules are emitted. Historical local records are never scanned.
- [x] Pin epoch baselines and secret exclusion:

```python
def test_projection_does_not_copy_local_identifiers(self):
    local = analytics.make_event("prompt_observed", now=NOW, integration="claude",
        source="hook", session_key="a" * 64, cfg=pc.defaults(),
        config_source="commands", enabled=True)
    remote = projection.project(local, identity="b" * 32, secret=b"c" * 32,
                                sequence=1, previous=None)
    body = contract.encode_event(remote)
    self.assertNotIn(local["event_id"].encode(), body)
    self.assertNotIn(local["session_key"].encode(), body)
    self.assertNotIn(b"timestamp", body)
    self.assertEqual(remote["day"], "2026-10-08")
```

- [x] Run `python3 -m unittest discover -s tests -p 'test_remote_projection.py' -v`; expect FAIL.
- [x] Implement allowlisted copying, new remote IDs, day-only timestamps, HMAC session mapping, and validated fields. For `config_observed_changed`, use remote epoch observation state, never local pre-consent `previous_settings`; skip the event until a baseline exists. For `config_saved`, old/new settings are the prospective edit's own payload. Null sessions stay null. Keep `unknown` integration for commands that do not verify a host; do not infer Claude from their path.
- [x] Add a single `_after_append_locked(events, now)` helper called after `_append` succeeds in both `record` and `observe`, before observation-state writes. It catches remote failures without changing the local return value. Do not instrument `_append` itself or add another call in hooks/preview/commands. Projection/sequence/queue updates share a SQLite transaction. Missing remote preferences return immediately without constructing a store database.
- [x] Test local append failure queues nothing, queue failure preserves local history, state-write failure does not duplicate queue rows, rating notes never enter either projection, `HUMAN_PACE=0` and SDK skip retain current behavior, and native settings snapshots retain existing validation. Rerun targeted and existing analytics tests; expect PASS. Commit with `feat: queue sanitized prospective analytics events`.

### Task 4: Bounded HTTPS transport and upload orchestration

**Files:** Create `scripts/pace_remote_transport.py`, `tests/test_remote_transport.py`.
**Consumes:** Claims and validated batch bytes; response contracts defined here and used by collector tasks.
**Produces:** HTTPS transport, `upload`, `delete_all`, persistent retry outcomes.

- [x] Define wire receipts: registration `{installation_id, ingestion_token, deletion_token}`; ingestion `{accepted: [id], duplicate: [id], rejected: [{event_id, reason}]}`; deletion `{installation_id, status: "pending"|"completed"}`. Validate exact keys, distinct IDs, bounded token lengths, identity match, and per-event disjoint statuses. No ID outside the claim is permitted. Any malformed receipt acknowledges nothing.
- [x] Add fake-transport tests with an injected monotonic clock for 10-second whole-command deadline including registration and upload, slow response reads, TLS errors, redirect refusal, dropped registration responses, 429/5xx backoff, bad credentials/schema suspension, and mixed receipts. Include:

```python
def test_response_loss_retries_identical_batch(self):
    self.transport.responses = [ConnectionError(), self.accept_all]
    first = upload(self.store, self.transport, now=NOW)
    second = upload(self.store, self.transport, now=NOW + timedelta(minutes=2))
    bodies = [r["body"] for r in self.transport.requests if r["path"] == "/v1/events"]
    self.assertEqual(bodies[0], bodies[1])
    self.assertEqual(first["state"], "retry")
    self.assertEqual(second["remaining"], 0)
```

The test fixture initializes registered credentials, one pending event, and a fake `request` implementation that records method/path/body and returns or raises each response. `accept_all` decodes the submitted body and returns its event IDs as accepted.
- [x] Run `python3 -m unittest discover -s tests -p 'test_remote_transport.py' -v`; expect FAIL.
- [x] Implement `http.client.HTTPSConnection` with default TLS context, URL parsing that rejects credentials/query/fragments and non-HTTPS endpoints, no redirect handling, bounded response bodies (64 KiB), `Accept-Encoding: identity`, and remaining-deadline socket timeouts before connect/read operations. Server credentials go in Authorization headers; registration recovery secret is in its bounded JSON body. Use a test fake transport, never a production endpoint environment override.
- [x] Persist client-generated identity and 256-bit recovery key before registration. Save returned credentials only if generation remains current. If consent changed while registration was in flight, retain that old registration in the deletion ledger without activating it. Recheck claims immediately before send; do not hold locks across requests.
- [x] On retryable errors keep IDs and increase `next_attempt_at` from 60 seconds exponentially to 86,400 seconds; parse integer and HTTP-date `Retry-After`, clamp to that range. On invalid auth/schema suspend; permanent per-event rejection removes only returned IDs. Status reports bounded reason codes without responses/secrets. Delete revokes all known registered epochs, polls pending statuses on later explicit calls, removes credentials only after completion, and retains failures for retry. One 10-second command deadline covers all deletion targets; report remaining targets when exhausted.
- [x] Rerun targeted tests; expect PASS. Commit with `feat: add bounded manual analytics transport`.

### Task 5: Expose share controls and coordinate local off/clear

**Files:** Create `scripts/pace_remote_commands.py`, `tests/test_remote_integration.py`; modify `scripts/pace.py`, `scripts/pace_analytics.py`, `scripts/pace_analytics_report.py`, `scripts/inject.py`, `scripts/preview.py`, `preview/index.html`, `commands/pace.md`, `tests/test_pace.py`, `tests/test_native_config.py`, `tests/test_inject.py`, `tests/test_preview.py`.
**Consumes:** Remote store, transport, release constants, existing `_analytics_command` dispatch.
**Produces:** Six sharing controls and truthful status/disclosure across existing entry points.

- [x] Add command/native-mode tests for `share`, `on`, `off`, `preview`, `upload`, `delete`, missing/extra arguments, unchanged formatting settings, and zero self-recording. Patch network methods to raise for status/on/off/preview. Test pending erasure output separately from completed erasure.
- [x] Add the regression:

```python
def test_local_off_revokes_pending_sharing(self):
    pace.run(["analytics", "share", "on"], now=NOW)
    self.record_prompt()
    pace.run(["analytics", "off"], now=NOW)
    self.assertFalse(self.remote.status(now=NOW)["enabled"])
    self.assertEqual(self.remote.status(now=NOW)["queued_count"], 0)
    pace.run(["analytics", "on"], now=NOW)
    self.assertFalse(self.remote.status(now=NOW)["enabled"])
```

Test setup uses isolated local/remote stores and patches release configuration with a synthetic operator/endpoint; `record_prompt()` calls the real local `observe` method.
- [x] Run `python3 -m unittest discover -s tests -p 'test_remote_integration.py' -v`; expect FAIL.
- [x] Route `rest[0] == "share"` inside `_analytics_command` before native formatting restrictions. Return exact command help for invalid syntax. Introduce `release` constants for endpoint/operator/contact/notice version; unset production values refuse `on/upload` with a useful message. `on` displays the recipient, fields, retention, manual nature, deletion behavior, and pseudonymous identity notice; no network call.
- [x] Add invitation persistence/tests before UI changes: first eligible session consumes one notice, settings shows full choices until enable/later/never, later and never suppress automatic invitations, manual settings revisit remains available, and clear/reset/resume/compaction never reset choices. Missing destination, analytics-off, SDK/headless skip, and `HUMAN_PACE=0` suppress automatic notices. If claiming a session notice cannot be persisted, show nothing; storage failure must not cause repeated prompts.

```python
def test_dismissal_survives_new_sessions_and_clear(self):
    self.remote.choose_invitation("later", now=NOW, local_enabled=True, release=self.release)
    self.local.clear(now=NOW)
    notice = self.remote.invitation(surface="session", now=NOW,
                                    local_enabled=True, release=self.release)
    self.assertFalse(notice["visible"])
    self.assertFalse(self.remote.status(now=NOW)["enabled"])
```

- [x] Implement the store invitation interfaces and a shared locked consent helper. `enable` and the Enable sharing button call it; later/never persist only invitation preferences. Make on/explicit off suppress further automatic invitations. Recipient/notice changes suspend sharing and require manual renewed consent while preserving never choice.
- [x] In `inject.main`, after existing skip decisions, append a brief invitation only on SessionStart when `invitation(surface="session")` grants it. Point to the settings page and `/pace analytics share on`; ordinary prompts and drift-guard resends do not repeat it. Displaying invitation preferences does not record an invocation or create identity/queue data.
- [x] In `preview.render`, inject escaped invitation/status data with actual recipient and manual-upload disclosure. Add accessible settings buttons **Enable sharing**, **Not now**, **Don't ask again**, plus an always-available **Sharing settings** control for manual revisit. Use a separate relative `sharing` POST route beside the existing `save` route, accepting exactly `{action: "enable"|"later"|"never"}`. Require the existing tokenized URL, same-origin Host/Origin checks, JSON content type, bounded body, and no extra fields; reject requests to standalone preview mode. No route enables local recording implicitly. Disable buttons while saving, announce persisted outcomes via `role="status"`, and display busy/unwritable errors without claiming opt-in succeeded. Keep formatting Save independent.
- [x] Add real preview-handler tests for each choice, invalid actions/keys, forged Origin/Host/token, oversized bodies, local-off enable refusal, storage failure, repeated settings loads, and zero network calls. Test keyboard-accessible buttons/status text and no consent buttons in standalone rendered previews. Preserve invitation choice through analytics clear and formatting reset. Include the exact disclosure from the spec with recipient/retention/identity/deletion details adjacent to it.
- [x] Coordinate local disable inside `AnalyticsStore.configure` under the existing lock: revoke remote generation and purge queue before committing local `enabled=False`. If purge fails, persist disabled sharing first; fail the explicit command accurately and prevent any upload while local recording is off. Implement local clear to revoke outstanding claims and purge the queue under the same lock while preserving remote consent and deletion ledger; new sequence baseline salt prevents collisions after clear. Never remove the remote credential ledger via local file cleanup.
- [x] Update `recording_notice` and report strings so enabled sharing says events are queued for manual upload and off says retained remote data can remain. Preserve local report calculations. Scope “nothing uploaded” claims to disabled fresh sharing rather than globally asserting them after prior uploads.
- [x] Test consent version/recipient mismatch suspends queuing, reset/native switches preserve consent, concurrent upload/clear/off/new consent preserve generation isolation, and corrupted remote metadata does not block ordinary formatting. Rerun remote integration and local/native tests; expect PASS. Commit with `feat: add explicit analytics sharing controls`.

### Task 6: Collector persistence and recoverable registration

**Files:** Create `collector/__init__.py`, `collector/store.py`, `tests/test_collector_store.py`.
**Consumes:** Shared contract and wire registration format.
**Produces:** Durable installation/event/deletion tables and collector store methods.

- [x] Add temporary-SQLite tests for first registration, same recovery key retry, different key collision refusal, credential role separation, process restart, duplicate events, conflicting payload IDs, and transaction rollback. Include:

```python
def test_registration_response_loss_is_recoverable(self):
    first = self.store.register("a" * 32, "b" * 64, now=NOW)
    reopened = CollectorStore(self.database, key=self.master_key)
    self.assertEqual(first, reopened.register("a" * 32, "b" * 64, now=NOW))
    with self.assertRaises(CollectorError):
        reopened.register("a" * 32, "c" * 64, now=NOW)
```

- [x] Run `python3 -m unittest discover -s tests -p 'test_collector_store.py' -v`; expect FAIL.
- [x] Implement `installations` (identity PK, recovery digest, ingestion/deletion token digests, key version, creation/deletion state), `events` (installation/event compound PK, canonical payload/digest/day/received time), and `deletions` (identity PK, request/status/primary completion). Enable foreign keys and WAL; use transactions for registration and ingestion acknowledgement, a finite 1-second SQLite busy timeout, parameterized SQL, and file permissions.
- [x] Derive recoverable tokens with server-side HMAC using distinct labels, identity, recovery digest, and key version; store only token digests and compare in constant time. An idempotent registration retry must prove the original random recovery secret before returning the same tokens. Keep server key versions available while their identities/deletion credentials exist; no secrets in source or event tables. Revoked identities never re-register.
- [x] Validate all events before opening the ingest transaction; insert valid events with canonical digest, identify duplicates without incrementing usage, reject conflicting IDs, and return committed per-event receipts. Reject forged identity even if event payload is otherwise valid. Recheck revocation inside every transaction.
- [x] Rerun targeted tests; expect PASS. Commit with `feat: add durable collector identities and event storage`.

### Task 7: Collector HTTP contract, authentication, and abuse bounds

**Files:** Create `collector/service.py`, `collector/server.py`, `tests/test_collector_service.py`.
**Consumes:** CollectorStore and shared strict JSON parser.
**Produces:** Four endpoint handlers and internal HTTP adapter with startup configuration validation.

- [x] Add service tests for all endpoints, missing/wrong bearer credentials, deletion tokens used for ingestion, invalid JSON/schema/identity/day, exact size/count limits, unsupported media/encoding, future dates, unknown routes, and malformed Content-Length. Pin JSON duplicate-key and secret-free errors. Use `handle` directly with synthetic headers/body.
- [x] Run `python3 -m unittest discover -s tests -p 'test_collector_service.py' -v`; expect FAIL.
- [x] Implement registration POST body `{installation_id, recovery_key}`, authenticated event POST with shared batch envelope, deletion DELETE, and deletion status GET. Require application/json on body requests, Content-Length, no chunked bodies, no compression; cap reads before parsing. Return 400 for invalid envelope, 401 for wrong credentials, 409 for identity recovery conflict, 413 for oversized body, 429 with bounded Retry-After, 503 for storage unavailable. Return structured per-event rejection for bounded invalid event entries; unsupported batch schema suspends the client's upload.
- [x] Enforce a maximum of 100 events/256 KiB, 16 KiB individual events, date window `[UTC today-7, UTC today]`, and strict exact integer checks. Limit schema-valid plugin metadata length and sequence to signed 64-bit positive integers. Conflicting sequence IDs within a session return `sequence_conflict`; do not produce ambiguous transitions.
- [x] Implement limiter with injected monotonic time: ingress 10 requests/sec burst 20, registration 5/minute per trusted proxy source with 100/minute global cap, ingestion 10 batches/minute and 10,000 accepted events/day per identity, global 1 GiB primary payload cap with 503 backpressure. Use bounded limiter entries and eviction, and reject rather than evict active rate limits under capacity pressure. Source addresses are transient limiter inputs only; never event dimensions. Limit reconnect/registration abuse at the TLS proxy as well.
- [x] Implement an internal single-process HTTP server binding `127.0.0.1` by default, socket read timeouts, suppressed default body/header/access logging, and a synthetic integration test with HTTPConnection to its temporary localhost port. A production reverse proxy must provide TLS, request-size/time/concurrency limits, and trusted source headers; refuse externally bound listener unless explicitly configured by the operator. Do not pretend the stdlib listener alone is the production perimeter.
- [x] Test concurrent revoke/ingest transaction ordering, SQLite busy errors, limiter persistence strategy (proxy limits survive restarts; service per-identity daily counts derive from SQLite), and bounded errors. Rerun targeted tests; expect PASS. Commit with `feat: expose bounded authenticated analytics collector API`.

### Task 8: Deletion, retention, backup journal, and safe restore

**Files:** Create `collector/maintenance.py`, `tests/test_collector_maintenance.py`, `docs/analytics/remote-operations.md`; modify `collector/store.py` and `collector/service.py`.
**Consumes:** Installation revocation state and committed events.
**Produces:** Immediate report exclusion, primary cleanup, independently retained deletion journal, maintenance/restore CLI.

- [x] Add tests for duplicate delete, pre-registration delete, offline client delete retry, immediately excluded events, completion after purge, 90-day retention, revoked ingestion, and replaying a deletion newer than a backup. Test journal append/fsync failure refuses acknowledgement and does not claim completed erasure.
- [x] Run `python3 -m unittest discover -s tests -p 'test_collector_maintenance.py' -v`; expect FAIL.
- [x] In deletion processing, revoke in SQLite before journal append; append a minimal identity/request-time/key-version tombstone to a private journal outside database backup snapshots and fsync before returning pending. If journal append fails, identity remains revoked, return 503, and idempotent retry repairs the journal. Ingestion must never clear that state. Maintain an external monotonic journal checkpoint so restoring a stale/missing journal fails closed.
- [x] `maintain` removes revoked event rows and any contribution/cache rows before marking primary completion; deletes event days older than the inclusive 90-day range `[today-89, today]`; preserves revocation/token digests for deletion status without payloads. No derived cache in v1; report directly from live events.
- [x] `restore` requires server stopped and fresh independently retained journal/checkpoint, restores to a separate file, replays all tombstones transactionally, purges expired/revoked data, validates foreign keys and integrity, then swaps the database. Missing or stale journal keeps reporting/ingestion disabled. Use a readiness marker created only after replay, never copied from backups.
- [x] Implement the following operator CLI forms, using these proposed paths in the runbook example: `python3 -m collector.maintenance maintain --database /srv/human-pace/events.sqlite3 --journal /srv/human-pace-deletions/journal.jsonl --key-file /srv/human-pace-secrets/collector.key` and `python3 -m collector.maintenance restore --database /srv/human-pace/events.sqlite3 --backup /srv/human-pace-backups/latest.sqlite3 --journal /srv/human-pace-deletions/journal.jsonl --key-file /srv/human-pace-secrets/collector.key`. Read key material from private files, never command arguments or logs. Document hourly maintenance with a daily retention sweep, failure alerts, 24-hour primary deadline, backup rotation/deletion at 30 days, journal/key custody, and restoration drills. Verify the example paths and the journal's independent storage against the selected deployment before collecting-release activation.
- [x] Execute the synthetic restore test and targeted tests; expect PASS. Commit with `feat: enforce analytics erasure and retention lifecycle`.

### Task 9: Maintainer aggregation and suppression

**Files:** Create `collector/report.py`, `tests/test_collector_report.py`; modify `collector/store.py` live queries and operations documentation.
**Consumes:** Validated non-revoked retained events; existing normalization semantics.
**Produces:** Pure summaries plus operator CLI `python3 -m collector.report --database PATH --start YYYY-MM-DD --end YYYY-MM-DD`.

- [x] Add deterministic multi-identity fixtures with A,A,B,B,A prompt runs, missing sequence 3, enabled/off settings, unknown sessions, saved/observed changes, ratings, mature and immature cohorts, and uneven prompt volumes. Ensure per-configuration contributor count can differ from whole-report installation count.
- [x] Include an independently checkable fixture:

```python
def test_prompt_weighting_and_installation_adoption_are_distinct(self):
    events = [prompt("a" * 32, "1" * 64, n) for n in range(1, 10)]
    other = {**pc.defaults(), "length": 300}
    events.append(prompt("b" * 32, "2" * 64, 1, cfg=other))
    s = report.summarize(events, start=date(2026, 10, 8), end=date(2026, 10, 8))
    key = analytics.config_identity(pc.defaults())["format_config_id"]
    self.assertEqual(s["configurations"][key]["prompt_share"], (9, 10))
    self.assertEqual(s["configurations"][key]["installation_adoption"], (1, 2))
    self.assertNotIn(key, report.render(s))  # fewer than five contributors
```

- [x] Run `python3 -m unittest discover -s tests -p 'test_collector_report.py' -v`; expect FAIL.
- [x] Compute reporting/active identities, exposure numerator/denominator including off, enabled-only share, distinct installation adoption, separate editing/observation counts, active days, score histograms/means/sample identities, and invocation/error observations. Return raw rational pairs for shares; render no percentage on zero denominator. Session keys combine identity and HMAC; transitions require adjacent sequence values and collapse equal runs. Stop transitions across gaps.
- [x] Implement first-observed cohort day using all retained live history, not only the selected report window. Count follow-up on days 7–13 only when day 13 has elapsed; label first observed rather than first installed. Disclose that history older than retention is unavailable and late uploads may change cohorts. Results never link consent epochs.
- [x] Render a fixed complete-window report with no arbitrary cross-filter or drilldown API. Suppress slices below five identities and apply complementary suppression: if visible totals and siblings would reveal a suppressed count, hide the parent total or an additional sibling. With fewer than five active contributors suppress all comparative metrics; ingestion health counts remain operator-only. Mark fewer than five ratings sparse. No raw events in report output.
- [x] Keep reports a private filesystem CLI, no HTTP report endpoint. `live_events` excludes revoked identities in SQL and requires restore readiness; fresh queries after deletion have no stale cache. Test deletion-before-render and complement/subtraction cases. Rerun tests; expect PASS. Commit with `feat: report remote usage with explicit denominators`.

### Task 10: Complete lifecycle fixtures and latency budget

**Files:** Extend `tests/test_remote_integration.py`, `tests/test_remote_transport.py`, collector tests; create `scripts/benchmark_remote_queue.py`; modify `.github/workflows/ci.yml` only if additional discovery is required.
**Consumes:** Finished client, collector handler, reports and maintenance.
**Produces:** End-to-end synthetic evidence for every spec acceptance criterion.

- [x] Add a service-adapter fake transport that routes the real client requests to `collector.service.handle`, preserving headers/body/receipts and simulating dropped replies. Exercise registration→prompt/rating/config events→preview→upload→duplicate retry→report→off/new epoch→delete all→purge→restore. Assert no local history backfill, no secrets/notes/paths in stored payloads, and every ledger identity receives deletion.
- [x] Test disk/lock/queue corruption failures through real hook/pace/settings entry points. Race claim/off/clear/re-enable and server revoke/ingest using barriers rather than sleeps. Assert functional settings save/rating output remains correct and hooks emit no analytics stdout.
- [x] Run `python3 -m unittest discover -s tests -p 'test_remote_integration.py' -v`; require PASS after fixing any lifecycle defect in its owning module.
- [x] Implement benchmark CLI with `--iterations 1000`, TemporaryDirectory, synthetic events, `perf_counter_ns`, warmup, and paired measurements for local append with sharing off versus on. Report median/p95 incremental queue time, Python version, OS, filesystem, iterations, and dropped count. Do not make any network call. Measure empty, half-full and capped queues; no full history scans on hooks.
- [x] Run `python3 scripts/benchmark_remote_queue.py --iterations 1000`; record evidence against under 5 ms median/20 ms p95 incremental budget on the named machine. If not met, profile queue metadata/locking; do not move networking into hooks.
- [x] Run `python3 -m unittest discover -s tests -v`, `python3 scripts/export_openai.py --check`, and `git diff --check`. CI already discovers `test_*.py` on 3.9/3.12; keep that matrix and ensure collector imports work there. Commit verified changes with `test: verify remote analytics lifecycle and overhead`.

### Task 11: User documentation and deployment readiness handoff

**Files:** Modify `README.md`, `commands/pace.md`, `CHANGELOG.md`, `docs/analytics/remote-operations.md`, and the remote spec's baseline/status notes.
**Consumes:** Actual implemented defaults and verified lifecycle behavior.
**Produces:** Reviewable collecting-release checklist with no live deployment.

- [x] Document the one-time invitation, all three choices, persistent dismissal and manual revisit; document all share commands, local-default-on/remote-default-off distinction, field allowlist, manual cadence, oldest-event eviction/expiry behavior, epoch linkability, current coverage, and off versus deletion versus clear. Include a concrete walkthrough:

```text
/pace analytics share
/pace analytics share on
# Use human-pace normally; existing history is never imported.
/pace analytics share preview
/pace analytics share upload
/pace analytics share off
/pace analytics share delete
# Rerun delete to check pending requests or retry failed identities.
```

- [x] Document receipt-loss recovery, support for pending deletion, and the fact that losing credential files prevents authenticated deletion through the client. Never imply local clear erases server data or preview is a raw historical export.
- [x] Complete the readiness checklist as unchecked deployment actions: choose operator/provider/region/budget; install TLS proxy/limits; provision versioned server keys and separate journal; verify no payload/token logging and 7-day security logs; schedule/alert maintenance; enforce 30-day backup expiry; run restore drill; set actual release endpoint/operator/contact/notice fingerprint; review notice; invite explicit pilot participation. These are operator actions required before real collection, not invented values in code.
- [x] Map spec acceptance criteria 1–10 to test modules and the benchmark output in the operations document. Record the 30-day pilot usefulness assessment: at least five contributing identities in main comparisons; insufficient manual coverage leads to a separate scheduled-upload design.
- [x] Run `git diff --check` and inspect documentation for stale unconditional “nothing is uploaded” guarantees. Leave only statements accurate under sharing state. Commit documentation with `docs: explain remote analytics controls and launch requirements`.

## Completion and handoff

Implementation is review-ready when Tasks 1–11 are checked, the Python suite/export check pass, synthetic receipt-loss/delete/restore fixtures pass, and the latency result is recorded. A collecting release is ready only after the operator checklist has actual verified deployment evidence. No automatic uploads, live registration, deployment, or pilot invitation occurs as part of writing or executing the local implementation tasks.

Recommended execution: subagent-driven after plan review, because client/collector lifecycle boundaries and deletion races benefit from independent review at each task. Native execution is also supported; retain task ordering and complete contract tests before integrating the next subsystem.
