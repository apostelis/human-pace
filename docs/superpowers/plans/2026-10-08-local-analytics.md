# Local Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Record local usage and compare configurations using the approved event definitions, before adding remote gathering.

**Architecture:** A local analytics module owns validated events, settings identities, storage, and session observation state. A separate report module computes metrics without filesystem side effects. Existing hook, command, and preview entry points call the recorder after resolving their actual outcomes.

**Tech Stack:** Python 3.9+ standard library, unittest, JSONL, existing Claude hooks and command entry points.

**Spec:** `docs/superpowers/specs/2026-10-08-local-analytics-design.md` (approved).

## Global Constraints

- Use Python 3.9+ standard library only.
- Local recording is explicitly enabled with `/pace analytics on`; it defaults to off.
- Retention accepts 1–365 days; default 90. Report windows accept 1–365 days; default 30.
- Bound each serialized event to 16 KiB and each UTC day's event file to 10 MiB.
- Create private directories/files where supported (0700/0600).
- No collection endpoint, uploader, account identity, or remote dashboard is part of phase one.
- Reports and analytics control/export commands do not record themselves.
- No prompts, responses, notes, paths, raw session IDs, environment dumps, or exception text in events.
- Keep current formatting, native options, rating persistence, and rule exports functional.
- The experimental MCP app is outside this change.
- All tests use temporary analytics directories, including existing tests that invoke instrumented entry points.
- Preserve unrelated working-tree files, including `experimental/` and `.github/ISSUE_TEMPLATE/`.

## Review Focus

1. A malformed or future-schema local record must be skipped without crashing or exporting unknown fields (Task 1/2).
2. A concurrent clear, append, or maintenance operation must not corrupt records or leave inconsistent session state (Task 2).
3. Missing IDs, resumed sessions, and timestamps spanning midnight must not invent sessions or transitions (Tasks 3/4).
4. Native settings failures, repeated identical saves, and notes resembling secrets must not cause false changes or data leakage (Task 5).
5. Existing test runners and preview subprocesses must not read/write real analytics storage or double-count an operation (Tasks 5/6).

## File map and execution order

| File | Responsibility |
|---|---|
| `scripts/pace_analytics.py` (new) | Schema, normalization, local preferences, storage, recording, maintenance |
| `scripts/pace_analytics_report.py` (new) | Pure metric aggregation and text rendering |
| `scripts/inject.py` | Eligible hook observations |
| `scripts/pace.py` | Command outcomes, ratings, analytics controls/report routing |
| `scripts/preview.py` | Preview/settings invocation outcomes and saves |
| `tests/test_analytics.py` (new) | Contract, storage, observation, concurrency tests |
| `tests/test_analytics_report.py` (new) | Deterministic metric fixtures |
| `tests/test_analytics_integration.py` (new) | Real command/hook/preview flows with isolated stores |
| Existing entry-point test modules | Temporary analytics isolation and intentional report-output updates |
| `commands/pace.md`, `README.md`, `CHANGELOG.md` | Help, guarantees, limitations, unreleased change summary |

Tasks are sequential: schema → storage → reports → hooks → commands/preview → final verification.
At execution time use the worktree skill to create/reuse an isolated checkout; do not copy unrelated untracked files.
Record the approved spec and plan paths in that checkout before starting implementation.

## Shared interfaces

Use `from __future__ import annotations` and standard `typing` imports as needed.
`now` is an aware datetime normalized to UTC; defaulting to the current time happens at entry points.

```python
# scripts/pace_analytics.py
def normalize_config(cfg: dict, *, include_delivery: bool = False) -> dict: ...
def config_identity(cfg: dict) -> dict: ...
# returns {settings, format_config_id, config_id, normalization_version}
def make_event(kind: str, *, now: datetime, integration: str, source: str,
               session_key: Optional[str] = None, cfg: Optional[dict] = None,
               config_source: Optional[str] = None, **fields) -> dict: ...
def validate_event(value: object) -> Optional[dict]: ...
class AnalyticsStore:
    def __init__(self, root: Path): ...
    def preferences(self) -> dict: ...  # enabled, retention_days
    def configure(self, *, enabled: Optional[bool] = None,
                  retention_days: Optional[int] = None) -> dict: ...
    def record(self, events: List[dict], *, now: datetime) -> bool: ...
    def observe(self, *, event: str, cfg: dict, config_source: str,
                session_id: object, now: datetime) -> bool: ...
    def read(self, *, now: datetime, days: int) -> dict: ...
    # {events: list, diagnostics: dict}; validated, retained, deduplicated
    def maintain(self, *, now: datetime) -> None: ...
    def clear(self, *, now: datetime) -> None: ...
def default_store(env: Optional[Mapping[str, str]] = None) -> AnalyticsStore: ...

# scripts/pace_analytics_report.py
def summarize(events: List[dict], *, now: datetime, days: int) -> dict: ...
def render_usage(summary: dict, diagnostics: dict, *, compact: bool = False) -> str: ...
def render_compare(summary: dict, diagnostics: dict) -> str: ...
```

`record`/`observe` catch recording failures and return false; explicit controls/read/maintenance
raise bounded actionable errors. Callers performing best-effort session maintenance catch those
errors separately. `default_store` selects the override directory or the documented default.
Avoid global instances so imports and pure config reads have no filesystem effects.

### Task 1: Event contract and configuration identities

**Files:** Create `scripts/pace_analytics.py`, `tests/test_analytics.py`.
**Consumes:** `pace_config.DEFAULTS`, `pace_config.validate`, plugin manifest version.
**Produces:** `normalize_config`, `config_identity`, `make_event`, `validate_event`.

- [x] Add table-driven unittest cases for inactive fields, delivery changes, invalid booleans/numbers,
  unknown event fields, bad timestamps, future schemas, and missing settings on settings events.
  Use this concrete normalization assertion:

```python
def test_inactive_bionic_fields_do_not_split_groups(self):
    a = {**pc.defaults(), "bionic": False}
    b = {**a, "bionicApproach": "vowels", "anchorTrigger": 3}
    self.assertEqual(analytics.config_identity(a)["format_config_id"],
                     analytics.config_identity(b)["format_config_id"])
    c = {**a, "driftGuard": 0}
    self.assertEqual(analytics.config_identity(a)["format_config_id"],
                     analytics.config_identity(c)["format_config_id"])
    self.assertNotEqual(analytics.config_identity(a)["config_id"],
                        analytics.config_identity(c)["config_id"])
```

- [x] Run `python3 -m unittest discover -s tests -p 'test_analytics.py' -v`; expect missing-module/API failure.
- [x] Implement canonical identities using these exact normalization rules:

```python
normalized = {key: cfg[key] for key in pc.DEFAULTS if key != "driftGuard"}
if not cfg["bionic"]:
    for key in ("bionicApproach", "anchorTrigger", "bionicGradient"):
        normalized.pop(key, None)
elif cfg["bionicApproach"] != "third+anchor":
    normalized.pop("anchorTrigger", None)
if include_delivery:
    normalized["driftGuard"] = cfg["driftGuard"]
payload = json.dumps({"normalization_version": 1, "settings": normalized},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=True)
digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [x] Define explicit per-event field allowlists from the spec. Require validated full snapshots
  for current/previous settings and derive changed fields internally. Reject unrecognized fields,
  types, schema versions, and invalid scores rather than serializing caller dictionaries blindly.
  Use `uuid.uuid4().hex` event IDs, timezone-aware ISO timestamps, and the actual manifest version
  or `unknown`. Validate recorded identities against snapshots when reading.
- [x] Re-run the task tests; require all passing. Commit the two task files as
  `feat: define local analytics event contract`.

### Task 2: Bounded local storage and observation state

**Files:** Extend `scripts/pace_analytics.py`, `tests/test_analytics.py`.
**Consumes:** Task 1 contract functions.
**Produces:** `AnalyticsStore`, `default_store`, all shared storage methods.

- [x] Add tests with a `TemporaryDirectory`, fixed aware time, and this basic control invariant:

```python
def test_disabled_store_creates_no_events(self):
    store = analytics.AnalyticsStore(self.root)
    event = analytics.make_event("command_invoked", now=self.now,
        integration="unknown", source="pace", operation="status", outcome="success")
    self.assertFalse(store.record([event], now=self.now))
    self.assertFalse(self.root.exists())
    store.configure(enabled=True)
    self.assertTrue(store.record([event], now=self.now))
    self.assertEqual(len(store.read(now=self.now, days=30)["events"]), 1)
```

- [x] Add tests for a truncated multibyte line followed by a valid append; duplicate IDs; file caps;
  16 KiB limit; invalid/future records; expired files; preference corruption; missing secret;
  explicit busy errors; and clear preserving preferences and the external rating log.
- [x] Run the task test command; expect storage API failures.
- [x] Implement nonblocking lock acquisition on a permanent `store.lock` file using `fcntl.flock`
  on macOS/Linux. If locking support is unavailable, recording fails open and explicit controls
  explain the limitation. Never delete the lock inode during clear. Under the lock re-read enabled
  preferences to prevent a stale recorder writing after disable.

```python
fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
try:
    # Validate and size the whole batch before writing; update state only afterward.
    append_batch()
finally:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

  `append_batch` here denotes the internal append routine to implement: open the UTC day's file
  in append/binary mode, inspect its last byte, add a separator if needed, check the entire new
  size, then write the serialized batch. A failed/partial write never advances observation state.
- [x] Write preferences/secret/state using private temporary files and atomic replacement under
  the same lock. Create the secret once on enable. A missing secret creates a fresh secret and
  resets only derived session state; old event keys stay historical. Use HMAC-SHA256 for validated
  host IDs. Track each session's last snapshot and observation timestamp in its own state file.
- [x] Implement `observe`: known sessions emit `session_observed` at baseline/session-start;
  ordinary prompts emit `prompt_observed`; differing full snapshots emit observed-change events.
  Missing IDs permit prompt observations only. Build/append each observation batch under one lock.
  Treat `enabled` as `any(cfg[k] for k in pc.SWITCHES) or cfg['length'] > 0`.
- [x] Implement lazy retention and owned-file-only clear. Reader diagnostics include malformed,
  unsupported, duplicate, capped-day counts and first/last retained timestamps. A bounded reader
  discards overlong lines incrementally; hand-edited huge lines cannot allocate unbounded memory.
  Skip symlinked owned data files and never follow them during deletion or writes.
- [x] Run simultaneous append processes against a temporary store; verify every successful batch
  is parseable, failed lock attempts return false, and clear cannot interleave with a locked append.
  Also test a symlink to a sentinel file and verify the sentinel survives clear/maintenance.
- [x] Re-run task tests and commit as `feat: add bounded local analytics storage`.

### Task 3: Deterministic usage and comparison reports

**Files:** Create `scripts/pace_analytics_report.py`, `tests/test_analytics_report.py`.
**Consumes:** Validated events and reader diagnostics from Task 2.
**Produces:** `summarize`, `render_usage`, `render_compare`.

- [x] Build fixtures with a fixed UTC clock and `make_event`; pin this sequence:

```python
# Each event has session_key="s1"; A is defaults, B is defaults with bionic=False.
events = [analytics.make_event("prompt_observed", now=now + timedelta(seconds=i),
    integration="claude", source="hook", session_key="s1", cfg=cfg,
    config_source="commands", enabled=True)
    for i, cfg in enumerate([a, a, b, b, a])]
result = reports.summarize(events, now=now + timedelta(seconds=10), days=30)
aid = analytics.config_identity(a)["format_config_id"]
bid = analytics.config_identity(b)["format_config_id"]
self.assertEqual(result["configurations"][aid]["prompts"], 3)
self.assertEqual(result["configurations"][bid]["prompts"], 2)
self.assertEqual(result["transitions"], {(aid, bid): 1, (bid, aid): 1})
```

- [x] Add fixtures for off prompts, null IDs, duplicate session observations, UTC midnight,
  events exactly at the window start, future timestamps, sparse ratings, and overlapping sessions.
  The window is `[now - timedelta(days=days), now]`; sort equal-time events by original input order.
- [x] Run `python3 -m unittest discover -s tests -p 'test_analytics_report.py' -v`; expect missing module.
- [x] Implement one pure aggregation pass with sets/counters. Define result keys: `invocations`,
  `observed_sessions`, `active_sessions`, `active_prompts`, `prompts`, `unassigned_prompts`,
  `configurations`, `transitions`, `editing`, `changes_per_active_session`, `ratings`, `errors`,
  `associations`, `coverage`. Configuration rows include prompt/session/day counts, both shares,
  readable normalized settings, and per-version/integration/delivery breakdowns.
- [x] Collapse consecutive formatting IDs per known session for transitions. Keep full-settings
  observed-change counts separate, including inactive-field edits, and include only sessions with
  enabled prompts in the changes-per-active-session denominator and numerator.
- [x] Compute boolean co-occurrence and categorical setting breakdowns using prompt exposure;
  exclude inactive bionic dimensions from denominators. Report numerators/denominators, rating
  distributions, and a sparse label below five ratings. No p-values or “best configuration” claim.

```python
def ratio(numerator, denominator):
    return None if denominator == 0 else numerator / denominator
```

- [x] Render readable text with UTC window, enabled/off counts, best-effort disclaimer, available
  coverage, null-session exclusions, and malformed/capped diagnostics. Keep usage and rating-only
  configurations visible. Exact preset labels require full current preset matches; otherwise show
  custom settings. Rank usage rows by prompts with a deterministic ID tie-breaker.
- [x] Re-run both analytics test modules; commit as `feat: report local usage and configuration comparisons`.

### Task 4: Instrument eligible hook observations

**Files:** Modify `scripts/inject.py`, `tests/test_inject.py`; create `tests/test_analytics_integration.py`.
**Consumes:** `AnalyticsStore.observe`, `maintain`, `make_event`.
**Produces:** Recorded hook/session/configuration/error observations without changed hook output.

- [x] Add a temporary analytics override to every hook test environment and subprocess environment.
  Explicitly enable it only for analytics integration cases. Pin this user-visible invariant:

```python
self.send("SessionStart", session="s1")
self.send("UserPromptSubmit", session="s1")
second = self.send("UserPromptSubmit", session="s1")
self.assertIsNone(second)  # Existing rules are still not resent.
self.send("SessionStart", session="s1")
events = self.store.read(now=self.now, days=30)["events"]
self.assertEqual(sum(e["event"] == "prompt_observed" for e in events), 2)
self.assertEqual(len({e["session_key"] for e in events if e["session_key"]}), 1)
```

  The event discriminator in every Task 1 record is `event`; use it consistently in all tests.
  Integration helpers freeze the recorder's clock and redirect hook stdout exactly like current tests.
- [x] Add tests for off configuration, native changes, malformed config fallbacks, environment kill
  switch, SDK skip, missing session IDs, and analytics exceptions with byte-identical hook output.
- [x] Run `python3 -m unittest discover -s tests -p 'test_*inject*.py' -v` plus the new integration module;
  expect new event assertions to fail.
- [x] Insert recording after the existing skip decision and resolved config, before rule emission:

```python
try:
    store = analytics.default_store(env)
    if event == "SessionStart":
        store.maintain(now=now)
    store.observe(event=event, cfg=cfg, config_source=config_source,
                  session_id=hook_input.get("session_id"), now=now)
except Exception:
    pass
```

  Obtain `now` with `datetime.now(timezone.utc)`. Keep maintenance failure separate from `observe`
  so a failed cleanup does not skip a record. Construct only allowlisted error categories, using
  `config_read_or_validation` if the existing loader exposes only a free-text error. Never parse
  a path or serialize that message into analytics.
- [x] Exclude exact plugin commands `/pace`, `/pace-settings`, `/pace-preview` and their namespaced
  forms from analytics prompt counts without broadening formatting's existing skip behavior.
  Do not suppress similarly prefixed unrelated commands.
- [x] Run hook and analytics tests; commit as `feat: record local hook usage without affecting formatting`.

### Task 5: Wire commands, ratings, and settings previews

**Files:** Modify `scripts/pace.py`, `scripts/preview.py`, `tests/test_pace.py`,
`tests/test_settings_panel.py`, `tests/test_native_config.py`, `tests/test_preview.py`,
`tests/test_analytics_integration.py`.
**Consumes:** Storage, contract, and report APIs above.
**Produces:** Specified `/pace analytics` and report commands plus save/rating/invocation events.

- [x] Add isolated analytics roots to existing entry-point tests before instrumenting them.
  Add command integration tests for this save sequence:

```python
pace.run(["analytics", "on"], now=self.now)
pace.run(["bionic", "off"], now=self.now)
pace.run(["bionic", "off"], now=self.now)
events = self.store.read(now=self.now, days=30)["events"]
self.assertEqual(sum(e["event"] == "command_invoked" for e in events), 2)
self.assertEqual(sum(e["event"] == "config_saved" for e in events), 1)
```

- [x] Add tests that native mode allows analytics/report/rate, blocks formatting changes, labels
  blocked commands correctly, and records no successful save on subprocess failure. A rating note
  containing a sentinel secret must appear only in the existing rating log, never export.
- [x] Run relevant tests; expect new command routing and recording assertions to fail.
- [x] Route analytics/report commands before native-mode formatting rejection. Use strict ASCII
  integer parsing and 1–365 validation. Implement all commands listed in the approved spec;
  reject trailing arguments. Export JSONL only; errors go to stderr with a nonzero CLI exit.
  Keep `run(args, now=None)` usable by existing callers; have `main` handle explicit analytics errors.
- [x] Refactor ordinary command dispatch to return an internal structured outcome rather than
  inferring success from rendered text. Define a small internal `CommandResult` dataclass with
  `text`, `operation`, `outcome`, and `events` fields. `run` returns its text after best-effort
  recording. Allowed operations are `status`, `toggle`, `approach`, `gradient`, `anchor_trigger`,
  `length`, `drift_guard`, `preset`, `reset`, `rate`, `preview`, `settings_open`, `settings_save`,
  and `unknown`; raw invalid arguments are never retained.
- [x] At successful saves compare old/new full snapshots; at successful rating-log writes create
  the rating event. Failed log/save operations receive command outcome `error`. Use null session
  IDs for commands/previews unless an explicit verified host ID is actually supplied.
- [x] Preserve `pace.report()` as the existing ratings-only function. `/pace report` appends compact
  usage text in `run`; update exact-output tests to assert the preserved rating block plus the
  new summary. Detailed comparisons read analytics events only.
- [x] Instrument preview parent startup once; the `--serve` child emits no settings-open event.
  Authenticated save requests record one `settings_save` invocation and successful changed save;
  foreign/unauthorized HTTP requests produce neither event. Keep browser tokens/URLs out of events.
- [x] Test reports/control/export self-exclusion, failed analytics writes preserving successful
  saves, invalid payloads, reset preserving analytics preferences, and exact save/new-observation
  separation through real command and hook calls. Run affected tests and commit as
  `feat: expose local analytics controls and instrument settings actions`.

### Task 6: Documentation, end-to-end validation, and overhead measurement

**Files:** Modify `README.md`, `commands/pace.md`, `CHANGELOG.md` and integration tests as needed.
**Consumes:** Complete local analytics implementation.
**Produces:** Documented feature and recorded verification results.

- [x] Update command hint/help with the implemented analytics/report grammar. Add README examples:

```text
/pace analytics on
/pace report usage 30
/pace report compare 30
/pace analytics retention 90
/pace analytics export
/pace analytics off
/pace analytics clear
```

- [x] Document configured-use semantics, hook-delivery counts, native change observation latency,
  overlapping session counts, sparse ratings, UTC windows, lazy retention, size limits, unsupported
  integration coverage, local data exclusion, and future gathering as a separate phase.
- [x] Add an end-to-end fixture: enable → session → A,A → save B twice → B,B → save A → A → rate →
  reports → export → disable → attempted prompt → clear. Assert 3/5 vs 2/5 usage, two transitions,
  two saves, one rating, no analytics self-events, valid exports, and preserved rating log.
- [x] Run `python3 -m unittest discover -s tests -v` and `python3 scripts/export_openai.py --check`.
  Review failures against intentional output changes; do not regenerate formatting exports unless
  a legitimate formatting change is identified (none is expected).
- [x] Benchmark 200 warm hook calls each with analytics off/on in temporary stores; collect median
  and p95 using `time.perf_counter`. Suppress hook stdout. Verify prompt recording invokes no
  network operations or history reader. Report measurements rather than inventing a latency limit.
- [x] Run `git diff --check`, inspect the final diff for forbidden fields, accidental user-data paths,
  unbounded reads, and network imports. Confirm unrelated untracked files are untouched.
- [x] Commit documentation/tests as `docs: document local analytics and validate full workflow`.
  Request the execution method's final review, resolve concrete findings, and report test results,
  overhead, coverage limits, and the command to start recording. Do not enable the user's real
  analytics store merely to verify implementation.

## Coverage self-review

All approved spec sections map to tasks: controls and legacy compatibility (5), event contract and
identity (1), metric denominators/comparisons (3), storage/failure/retention (2), hook coverage (4),
preview/native/ratings integration (5), documentation and complete acceptance workflow (6).
Each Review Focus condition has a named test in its owning task. Remote gathering stays deferred.

## Execution recommendation

Recommend native execution in this chat: the six tasks share a small set of tightly coupled APIs,
and one implementer can keep event semantics consistent throughout. Use a fresh final reviewer
after the complete branch is passing. The alternative is subagent-driven execution with fresh
implementation and review contexts for each task. Implementation begins after plan review and
execution-method selection.

## Execution results — 2026-10-08

- Implemented in `codex/local-analytics` in the app-managed worktree.
- Full verification: 223 unittest tests passed; `scripts/export_openai.py --check`
  and `git diff --check` passed.
- 200 warm in-process hook calls per mode: recording off median 0.376 ms / p95
  0.419 ms; recording on median 1.065 ms / p95 1.307 ms. These measurements exclude
  Python startup and use temporary local storage.
- Independent review found stale native-save snapshots and malformed-state recovery
  issues; the first reviewer hit a provider limit and an available reviewer finished
  the remaining review. All actionable findings were reproduced and fixed, including
  analytics-directory failures affecting formatting and snapshot reads blocking saves.
- Additional regressions cover daily-cap enforcement and direct test-runner isolation.
- Tests exercise native configuration through a simulated CLI writing real temporary
  settings files. A live Claude installation was not used for verification.
- Personal analytics recording was not enabled; remote gathering remains deferred.
