# Remote usage analytics gathering

Date: 2026-10-08
Status: Proposed for review; no collection is enabled by this document
Dependency: [Local usage analytics](2026-10-08-local-analytics-design.md)

## Problem and intended outcome

Local reports explain use on one machine. Maintainers need an aggregate view of
which human-pace configurations consenting installations use, change, return to,
and rate. Without collection, individual reports cannot answer these questions
across installations. This is a product requirement, not evidence of demand or
proof that formatting improves reading.

Build on the local event definitions, with a separate, narrower remote contract.
The local recorder and reports now exist in the checkout, with local recording
on by default under the owner's amendment. Validate that implementation before
integrating remote sharing; remote sharing remains separately off by default.

Success means maintainers can reproduce configuration shares, repeat usage, and
ratings from a known reporting window, while users can inspect sharing, stop it,
and delete their contribution. All numbers describe participating installations,
not people or the entire installed base.

## Scope and user stories

- As a plugin user, I can explicitly enable sharing after seeing exactly what it
  sends, so I can contribute without sharing my conversations.
- As a participating user, I can inspect pending data, stop future uploads, and
  request removal of previously uploaded data.
- As a maintainer, I can compare configuration exposure, changes, repeat use,
  and ratings with denominators and coverage limitations.
- As an offline user, I can continue using formatting and local analytics without
  waiting for the collector or losing settings changes.

V1 covers the instrumented Claude integration only. Codex/ChatGPT custom
instructions and the portable skill lack executable instrumentation; report their
coverage as unavailable. Do not infer usage from installation or skill presence.
The experimental MCP app, accounts, team dashboards, A/B assignment, automatic
formatting changes, reading duration, and comprehension claims are out of scope.

## Proposed collection model

Use explicit local commands to enqueue and upload sanitized events to one
maintainer-operated HTTPS collector. There is no network I/O in hooks, normal
formatting commands, rating writes, or settings saves. V1 has no background
daemon or scheduler. Upload frequency is therefore user-controlled and reports
must disclose delayed and incomplete submissions.

This deliberate first release validates the data contract and collector before
considering unattended upload. Sharing opt-in permits future events to be queued;
it does not import existing local events or the historical rating log. A later
scheduled uploader is P1 and requires a separate design for host execution and
visible controls.

## P0: consent and controls

Sharing defaults to off, independently of local recording. Enabling local
analytics never enables sharing. V1 requires local recording on before sharing
can be enabled; otherwise explain `/pace analytics on` and make no change.
Formatting reset and native configuration changes preserve both preferences.

| Proposed command | Behavior |
|---|---|
| `/pace analytics share` | Show state, destination/operator, schema and notice version, queued count/age, last upload result, and coverage |
| `/pace analytics share on` | Show the concise disclosure and explicitly enable prospective queuing; generate a new remote identity if needed |
| `/pace analytics share off` | Stop queuing and uploads, purge unsent remote events, retain local analytics and remote deletion credentials |
| `/pace analytics share preview` | Print the exact pending event payloads, excluding authentication secrets; no network call |
| `/pace analytics share upload` | Upload a bounded batch while sharing is on; report accepted, duplicate, rejected, remaining, and dropped counts |
| `/pace analytics share delete` | Disable sharing, purge the queue, request deletion of the remote identity and its contribution; retain credentials until acknowledged |

The help/disclosure states fields collected, recipient, retention, manual upload,
identity linkability, and deletion behavior. Explicitly executing `share on` is
a consent action; selecting Enable sharing in the settings page is equivalent.
Merely opening status/help/settings does not enable sharing. Persist the notice
version, remote schema version, consent time, and collection epoch locally.
Any expansion of fields or recipient changes suspends sharing until a new opt-in.

`analytics off` also disables sharing and purges unsent remote data. Turning local
recording back on does not re-enable sharing. `analytics clear` also purges the
remote queue and rotates local observation state, but does not claim to delete
server data; status points to `share delete`. Sharing preferences otherwise
remain unchanged. All control commands work in native mode and never record
their own invocation events.

## P0: one-time opt-in invitation

Show a short invitation once at the first eligible interactive session, and a
full invitation in the browser settings page until the user makes a choice.
Both surfaces share persistent local invitation state. The session notice points
to the settings page or `/pace analytics share on`; it does not attempt to collect
consent through an inferred conversational response. No repeated session notices
on resume, compaction, drift-guard resends, or later sessions.

Suggested settings copy:

> Help improve Human Pace by sharing usage statistics: settings used, command
> counts, and numeric ratings. Prompts, replies, and rating notes are excluded.
> Sharing is optional and can be stopped anytime. Enabling sharing queues future
> events on this machine; upload them manually with `/pace analytics share upload`.

Display the actual recipient, retention, pseudonymous identity, and deletion
information alongside that copy. Provide **Enable sharing**, **Not now**, and
**Don't ask again**, with no preselected choice. Enable sharing uses the same
validated consent operation as the command and reports success only after it is
persisted. If local recording is off, explain how to turn it on first; clicking
Enable sharing does not implicitly change that preference.

Not now dismisses the automatic invitation across both surfaces; users can
revisit sharing through an always-available settings control or the command.
Don't ask again persistently disables automatic invitations. Neither choice
creates a remote identity, queues events, or contacts the collector. A completed
opt-in or explicit sharing-off also suppresses automatic invitations. Manual
revisit remains available even after dismissal. Clearing analytics or resetting
formatting preserves invitation choices; notice changes require explicit renewed
consent without overriding Don't ask again.

Only show automatic invitations when a complete collecting-release destination
is configured. Honor `HUMAN_PACE=0`, headless/SDK skip decisions, and local analytics
off before the automatic session invitation. Standalone previews have no consent
buttons. The settings server uses its existing unguessable URL and validates
origin/host, request size, and exact action values for consent POSTs. No remote
network request occurs when displaying, dismissing, or accepting the invitation.

## P0: remote event contract

Use remote schema version 1 and explicit field allowlists, separate from local
schema version 1. Never upload local JSONL files directly. Construct remote
payloads only at the successful recording boundary for newly recorded events
after opt-in. Queue failure does not invalidate the original user action or the
local record. Failed queue writes are not reconstructed by scanning history.

| Field | Remote representation |
|---|---|
| Event identity | New random remote event ID, stable across retries; never the local event ID |
| Installation | Random 128-bit-or-stronger identity scoped to this sharing epoch; no account, machine, or host-derived ID |
| Time | UTC day only; omit exact timestamps |
| Version/coverage | Remote schema, normalization version, plugin version, integration, source, configuration source |
| Session | Optional epoch-scoped HMAC of the local session key using a separate remote secret; omit raw/local session IDs |
| Ordering | Monotonic per-known-session sequence for prompt observations, assigned before queuing; gaps disclose missing observations |
| Configuration | Validated allowlisted settings and normalized config IDs as defined locally; old/new snapshots only for change events |
| Event-specific data | Allowlisted operation/outcome, changed fields, error category, enabled flag, or rating 1–5 |

Eligible types are the seven events in the local specification: command invoked,
session observed, prompt observed, config saved, config observed changed, rating
submitted, and settings error. Publish their exact JSON schema in the repository
before implementation completion. Server validation rejects unknown fields,
invalid types/ranges, oversized events, or inconsistent configuration IDs.

Exclude prompts, replies, rating notes, paths, project/repository names, raw
arguments, environment variables, native settings documents, raw exceptions,
host identifiers, and local secrets. Do not add operating-system or geographic
dimensions in v1. Identifiers are pseudonymous, not anonymous. A new consent
epoch gets a new session baseline; never transmit a before-opt-in configuration
as the previous value of an observed change.

Each off→on cycle starts a new epoch and remote identity. Preserve a private
ledger of prior identities and deletion credentials until their deletion is
confirmed. `share delete` covers every identity in that ledger, not just the
currently active epoch. Do not link epochs in analytical reports.

## P0: queue and transport

Keep private queue/preferences/credentials under the analytics directory, separate
from local event files. Use standard-library Python 3.9+ on the client. Hooks
perform only bounded local writes under the existing nonblocking locking model.

- Queue cap: 10 MiB or 10,000 events, whichever is reached first. Expire unsent
  events after 7 days. When admitting new events would exceed either cap, evict
  the oldest queued events until the new events fit, using local insertion order
  with a monotonic tie-breaker rather than client timestamps. Retain the newest
  events; for an incoming batch larger than capacity, retain its newest suffix.
  Track evicted and expired counts separately in local status. Do not renumber
  prompt sequences or recreate evicted events from local history.
- Eviction and enqueue are atomic under the queue lock/transaction. Eviction may
  remove a claimed row: an already-sent request can still reach the collector,
  but acknowledgements ignore absent rows and retries never resurrect them.
  Claims do not persist a second copy of payloads outside the bounded queue.
  An invalid or individually oversized incoming event is rejected before eviction.
- Upload limit: one batch per command, up to 100 events and 256 KiB JSON body;
  individual events remain limited to 16 KiB. Report when another upload is needed.
- Use TLS verification, a fixed release-configured endpoint, and no redirects.
  Test endpoint injection must not allow repository config to redirect user data.
- Set connection/read timeouts and a 10-second total command network deadline.
  Never hold a filesystem lock during network I/O. Claim a batch under a short
  lock, then acknowledge/remove it under the lock after receiving the response.
- Retry only on a later explicit upload command, with the same event IDs. For
  network failures, 429, and 5xx, retain events and enforce persisted exponential
  backoff from 1 minute to 24 hours, including bounded `Retry-After` handling.
  No retry loop sleeps inside the command.
- Permanent validation rejection removes only explicitly rejected events and
  reports reason codes; invalid credentials or unsupported schema suspend uploads
  and retain the bounded queue for inspection. Malformed responses acknowledge
  nothing. Never dump bodies or credentials in errors.

Sharing off/delete increments a local generation and clears claims. Uploaders
recheck that generation before sending; stale acknowledgements cannot mutate a
new epoch. An already-sent request may arrive after off is invoked; explain this
limit in help. Off alone retains previously received data; delete revokes the
server identity so racing ingestion cannot restore it.

## P0: collector and deletion

Specify provider-neutral API behavior first; choose hosting before deployment.

| Endpoint | Contract |
|---|---|
| `POST /v1/registrations` | Register the client-generated random identity on first explicit upload, using a persisted idempotency key; return separate ingestion and deletion credentials over TLS |
| `POST /v1/events` | Authenticate installation, validate bounded batch, durably insert valid events, and return per-event accepted/duplicate/rejected status |
| `DELETE /v1/installation` | Authenticate deletion credential, revoke ingestion atomically, and acknowledge an idempotent deletion request |
| `GET /v1/deletion` | Authenticate deletion credential and return pending/completed status for that identity; explicitly rerunning `share delete` polls outstanding requests |

Registration retries must recover the same credentials securely after response
loss without creating multiple identities. Persist credentials privately before
upload. No shared secret embedded in the distributed plugin counts as client
authentication. Public registration still permits fabricated clients: rate-limit
registration and ingestion, bound storage, and treat collected data as untrusted.

Deduplicate by `(installation_id, event_id)` with a unique database constraint.
A success acknowledgement requires a durable commit. Reusing an ID with different
content is a permanent rejection. Validate identity against the authenticated
principal, not an arbitrary payload value. Apply per-installation and ingress
limits; authenticate maintainer reporting separately from ingestion.

Retain received events for at most 90 days from their event day; reject future
days and events older than the 7-day upload horizon. Purge expired data daily.
Retain installation-level contributions only within that same 90-day window so
deletion can remove them from derived metrics. V1 keeps no permanent anonymous
aggregate exempt from deletion.

Deletion immediately revokes ingestion and excludes the identity from reports;
remove primary events, contribution tables, and caches within 24 hours. Return
request status and completion separately; the client must not claim completed
erasure on request acknowledgement alone. Backups expire within 30 days and a
restore must replay deletion tombstones before serving reports. Keep minimal
revocation/deletion tombstones, without event payloads, as long as needed to
prevent ingestion and restore resurrection. Publish this distinction in the notice.

Infrastructure necessarily receives source IPs. Disable request-body and token
logging; exclude IPs from analytics tables and set any unavoidable security access
log retention to at most 7 days. Verify proxy/provider logging and backups before
launch. Restrict raw-event access to the collector operator; no public raw export.

## P0: reports and metric definitions

Report the selected UTC window, schema/integration coverage, latest received day,
and the fact that participation, missed local events, queue expiry, and manual
uploads cause selection bias. No total-install or consent-rate denominator exists
in v1: installations that never share are not observed.

| Metric | Definition |
|---|---|
| Reporting installations | Distinct identities with accepted events in the window; identity resets can inflate counts |
| Active installations | Identities with at least one enabled prompt observation in the window |
| Configuration exposure | Prompts in each formatting configuration / all observed prompts, including off; show enabled-only share separately |
| Installation adoption | Active installations using a configuration / active installations; configurations overlap |
| Editing and observed changes | Count saved changes and observed changes independently, with source and changed fields |
| Repeat usage | Active days per identity/configuration within the window; cohort return on days 7–13 after first observed active day, only for cohorts whose full follow-up window has elapsed |
| Ratings | Score distribution, mean, event count, and distinct contributing identities alongside configuration exposure |
| Invocations/errors | Counts by allowlisted operation/outcome or category, labelled observations rather than unique incidents |

First observed activity is not installation date; missing follow-up uploads are
not proof of churn. Display both prompt-weighted shares and installation adoption
so prolific installations do not silently define popularity. Session IDs are
scoped to the installation/epoch. Null sessions never contribute to session totals.
Only derive within-session transitions from consecutive received prompt sequence
numbers; a gap interrupts the run and must not invent a transition. Rating groups
with fewer than five ratings are sparse; no causal ranking or reading benefit claim.

Restrict v1 reports to maintainers. Suppress comparative slices with fewer than
five distinct installations, including drilldowns that would expose them by
subtraction. Overall ingestion health counts may be visible to the operator.
Public dashboards and stronger disclosure controls require a separate design.

## Acceptance criteria and validation

1. The invitation appears once per the surface rules; Not now and Don't ask
   again persist across sessions, preview reopen, clear, and reset. Enable sharing
   is explicit, uses the command consent path, and makes no network request.
   Busy/unwritable storage cannot produce a success message or repeated notices.
   Queue overflow fixtures retain newest events, count oldest evictions, preserve
   sequence gaps, and handle in-flight acknowledgements without resurrection.
   Fresh installs, local opt-in alone, and historical rating files generate zero
   remote queue events and zero network traffic. Sharing starts prospectively.
2. Preview fixtures match upload bodies exactly apart from authentication; fixture
   secrets, prompts, notes, paths, raw session IDs, and unknown fields never appear.
3. Hook/command/settings tests assert no network calls and unchanged functional
   outcomes when queuing fails, locks are busy, storage is full, or state is corrupt.
4. Duplicate delivery and response loss produce one stored event. Conflicting
   duplicate IDs are rejected. Partial rejection removes only acknowledged IDs.
5. Offline, timeout, 429, 5xx, bad TLS, redirect, invalid credentials, unsupported
   schema, and malformed-response fixtures exercise the specified queue behavior.
6. Off and local-off purge unsent data. Concurrent off/delete/upload and renewed
   consent cannot restore cleared events, cross epochs, or upload revoked data.
7. Deletion removes report contributions immediately and primary data within 24
   hours. A backup-restore drill reapplies tombstones before reporting is enabled.
8. Fixed multi-installation fixtures verify denominators, unknown sessions,
   sequence gaps, off configurations, cohort maturity, suppression, and retention.
9. Registration/ingestion tests reject oversized requests, forged identities,
   invalid fields, and rate-limit violations; secrets and payloads stay out of logs.
10. Run existing Python tests and isolated client/collector contract tests. Use
    synthetic data only until the recipient, notice, deployment, and retention
    implementation have been reviewed. Measure added hook latency with queueing
    enabled; proposed budget is under 5 ms median and 20 ms p95 on a documented
    reference machine, excluding existing hook work.

## Rollout, success criteria, and decisions

Phase 1: finish local analytics and validate metric semantics. Phase 2: implement
queue/schema/collector with synthetic fixtures and deletion tests. Phase 3: invite
explicit pilot opt-ins and validate reports. Phase 4: publish manual gathering
with documented coverage. No release date is assumed.

Launch gates: all acceptance criteria pass; disabled clients make zero analytics
network requests; retry fixtures produce zero duplicates; removal meets stated
deadlines; aggregate fixtures reconcile exactly. After a 30-day pilot, assess
whether at least five distinct installations contribute to the main configuration
comparisons. This is a proposed usefulness threshold, not a forecast or a reason
to weaken consent. If manual uploads yield insufficient coverage, design P1
scheduled gathering before claiming representative usage.

| Decision | Owner | When needed |
|---|---|---|
| Accept manual uploads as v1; assess scheduled uploads later | Product/user | Before implementation scope is finalized |
| Select collector operator, provider, region, endpoint, and budget | Maintainer | Before deployment; schema/client work can proceed with fixtures |
| Confirm notice, support contact, and retention/backups match deployment | Maintainer | Before any real-user collection |
| Choose collector runtime/database with uniqueness and deletion guarantees | Engineering | Before collector implementation |
| Approve proposed queue, retention, timeout, and latency defaults | Maintainer | Before release |

P1: visible optional scheduled uploads, receipt/deletion status UI, and richer
maintainer filtering. P2: additional instrumented integrations and public aggregate
reports. Neither is implicitly authorized by opting into v1.
