# Local usage analytics

Date: 2026-10-08
Status: Proposed for review

## Purpose and scope

Establish useful, trustworthy metrics on one machine before adding collection
from other installations. The approved direction is to measure invocations,
configuration frequency, configuration relationships, repeat usage, and ratings.
Success means a user can explain which settings they actually use, how often
they change them, and how those choices relate to their own ratings.

Phase one uses local storage and reports. Phase two may add opt-in collection
using the same versioned event definitions. No collection endpoint, uploader,
account identity, or remote dashboard is part of phase one.

Initial automatic prompt coverage is the Claude hook integration. The existing
Codex/ChatGPT skill has no executable session hook or prompt counter; its usage
is unavailable rather than zero. The experimental MCP app is outside this change.

## Current integration points

- `scripts/inject.py` receives session-start and prompt hooks, resolves settings,
  and sends rules at session start, after changes, and at drift-guard intervals.
- `scripts/pace.py` handles commands, saves preferences, logs ratings with a
  settings snapshot, and groups ratings by effective formatting configuration.
- `scripts/preview.py` opens previews/settings and saves either command-managed
  preferences or native Claude options.
- `scripts/pace_config.py` validates and resolves configurations. Keep ordinary
  config reads free of recording side effects.

## User controls

Local recording is explicitly enabled with `/pace analytics on`; it defaults to
off. This is a proposed default, intended to make the recording period explicit.
Analytics preferences are separate from formatting preferences, so `/pace reset`
and native formatting options do not reset analytics choices.

| Command | Behavior |
|---|---|
| `/pace analytics` | Show recording status, storage location, retention, coverage, and retained date range |
| `/pace analytics on` | Enable future local recording |
| `/pace analytics off` | Stop future recording; retain existing records |
| `/pace analytics retention <days>` | Set retention to 1–365 days; default 90 |
| `/pace analytics export` | Print validated retained events as JSONL on stdout |
| `/pace analytics clear` | Delete analytics events and derived state, rotate the local session secret, preserve recording preferences and the existing rating log |
| `/pace report` | Preserve existing ratings output and append a compact 30-day usage summary |
| `/pace report usage [days]` | Show detailed usage and configuration rankings; default 30 days |
| `/pace report compare [days]` | Show setting associations, transitions, and configuration ratings; default 30 days |

Report windows accept 1–365 days and disclose when retained data covers less.
Reports and analytics control/export commands do not record themselves. They
must work in native configuration mode as well as command configuration mode.
Empty reports explain how to enable recording and show coverage limitations.

## Event contract

Every event contains `schema_version` (initially 1), a unique `event_id`, UTC
timestamp, plugin version, integration, source, and an optional local session key.
Events involving settings contain a validated allowlisted settings snapshot,
configuration source (`commands` or `native`), and normalized configuration IDs.
Unknown integration/version values are explicit; do not infer the host from the
presence of a settings file.

Session keys are HMACs of valid host session IDs using a locally generated secret.
Raw session IDs are never written to analytics. Missing IDs remain null; never
merge all unknown sessions into one session. Commands and previews without a
verified host session ID remain unassigned.

| Event | Definition and fields |
|---|---|
| `command_invoked` | One actual execution of an instrumented command; allowlisted operation and outcome (`success`, `invalid`, `error`), never raw arguments |
| `session_observed` | A valid session seen by a hook; report distinct session keys, so resume/compaction observations do not increase the session total |
| `prompt_observed` | One eligible ordinary prompt hook with current settings and `enabled`; records even when unchanged rules produce no output |
| `config_saved` | A successful save whose validated full settings differ from the prior snapshot; includes old/new settings and changed field names |
| `config_observed_changed` | Consecutive observations in the same known session differ; includes old/new settings and changed fields |
| `rating_submitted` | A successful existing rating-log write; contains score 1–5 and settings, excluding the note |
| `settings_error` | An observed read/validation/save failure; allowlisted error category and known invalid field names only |

The initial configuration observed in a session is a baseline, not a change.
Saving identical values is a command invocation but not a configuration change.
`config_saved` measures editing; `config_observed_changed` measures observed use.
Never add these counts together. Native-panel or manual-file changes become
visible at the next hook observation; intermediate changes are unobservable.

`prompt_observed.enabled` is true when any formatting switch is enabled or
`length > 0`. This measures configured usage, not proof the model followed the
rules. Drift guard alone does not enable formatting. All-off configurations are
still observed, allowing an off share and transitions to off to be measured.

Honor `HUMAN_PACE=0` and the existing SDK skip logic before hook recording.
Exclude plugin command prompts from ordinary-prompt counts; executable command
handlers own their invocation event. A hook firing and a rule resend are not
additional invocations. Do not retain or hash prompt text for deduplication.
Without a host event identifier, separate hook deliveries cannot reliably be
deduplicated: label prompt counts as observed hook deliveries. Event IDs prevent
duplicate records from being counted twice when reporting/exporting retained data.

## Configuration identity

Use deterministic canonical JSON and SHA-256, with a normalization version
included in the hash input. Store readable fields alongside IDs.

- `format_config_id`: all behaviorally relevant formatting settings; excludes
  drift guard. With bionic off, omit approach, anchor trigger, and gradient.
  With an approach other than `third+anchor`, omit anchor trigger.
- `config_id`: the normalized formatting settings plus drift guard.
- Preserve the full validated snapshot to identify inactive-option edits and
  reconstruct normalization later. Never accept arbitrary additional fields.

Default reports group by formatting identity and show drift guard separately.
Presets are labels inferred from exact matches to current preset definitions;
custom combinations retain their own identity. Version and integration remain
available filters/dimensions because the same setting may behave differently.
Gradient values describe requested settings; they do not prove a surface rendered
the gradient.

## Metrics and denominators

All usage metrics use the selected UTC time window. Display UTC explicitly for
daily buckets. Counts describe one local store, not unique people or installations.

| Metric | Computation |
|---|---|
| Invocations | Count `command_invoked`, grouped by operation and outcome |
| Observed sessions | Distinct non-null session keys in session/prompt observations |
| Active sessions | Distinct session keys with at least one enabled prompt |
| Active prompts | Enabled `prompt_observed` count |
| Configuration share | Prompts using a configuration / all eligible observed prompts, including off |
| Active configuration share | Enabled prompts using a configuration / all enabled prompts |
| Sessions per configuration | Distinct known sessions using it on a prompt; rows may overlap |
| Editing frequency | `config_saved` count and changed-field counts, grouped by source |
| Changes per active session | Observed configuration changes in sessions with active prompts / active sessions |
| Transitions | Adjacent prompt configuration runs within each known session; collapse consecutive equal IDs |
| Repeat usage | Number of distinct UTC days and sessions with prompts for each configuration |
| Ratings | Mean, distribution, and sample count for each formatting identity |
| Settings errors | Observations by category/source; repeated observations are not unique incidents |

Zero denominators display “not enough data,” never a fabricated percentage.
Exclude null-session events from session and transition metrics but include
eligible events in prompt totals. Show the number excluded from session analysis.
Transitions are constructed from prompts within the window; do not infer a
transition from a saved setting that was never used.

Comparisons show pairwise co-occurrence for boolean formatting switches and
categorical breakdowns for bionic approach, gradient, length, and drift guard.
For example, report the share of prompts with chunks enabled for each bionic
approach, with numerator and denominator. Treat inapplicable bionic settings as
inapplicable rather than as selected options.

Show ratings alongside prompt exposure and active days. Mark groups with fewer
than five ratings as sparse; avoid declaring a winner or computing causal claims.
Frequent use, short sessions, and high ratings are not evidence of reading speed
or comprehension. Phase one does not measure duration because session ends and
idle time are not reliably observed.

Existing `/pace report` ratings continue to come from the existing rating log.
Windowed analytics comparisons use only `rating_submitted` events from the
recording period. Label that distinction and never merge both sources, avoiding
double-counting and any implicit historical backfill.

## Local storage and failure behavior

Use Python 3.9+ standard library only. Place analytics under
`~/.claude/human-pace-analytics/`, overridable by `HUMAN_PACE_ANALYTICS_DIR` for
tests and explicit local configuration. Use daily JSONL event files, a small
preferences file, a session secret, and separate observation state. Keep this
state independent of injection/drift-guard state.

Create private directories/files where supported (0700/0600). Records exclude
prompts, responses, free-text notes, filesystem paths, project names, environment
dumps, native settings documents, and raw exception messages.

Use a nonblocking process lock for append/state updates and maintenance. On lock
contention or recording failure, skip recording and continue the original action.
Do not retry, make network calls, launch a daemon, or scan event history in the
prompt path. Reports disclose that recording is best effort; missing events are
not reconstructed. Advance observation state only after its event batch appends
successfully. If state is lost, establish a new baseline without inventing changes.

Bound each serialized event to 16 KiB and each UTC day's event file to 10 MiB.
Once capped, skip further records for that day and expose a best-effort capped-day
marker in status/reports. Append records under the lock; tolerate and skip malformed
or truncated lines during reads. If a prior crash left an unterminated line, insert
a newline before the next record so corruption cannot consume it.

Prune expired daily files and inactive observation state during status, reports,
control commands, and session-start maintenance, not on every prompt. Retention
is lazy: files are removed on the next maintenance operation. Readers always
exclude expired events even before files have been pruned. Clear and maintenance
use the same lock; explicit commands report busy/unwritable errors rather than
claiming success. Clear removes only known analytics-owned files.

The formatter and settings save remain successful if analytics fails. Recording
adds no stdout output to hooks. Explicit analytics commands return useful errors.
An analytics recording error must never recursively generate an analytics event.

## Implementation boundaries

- Add `scripts/pace_analytics.py` for preferences, event validation, normalization,
  storage, observation state, and maintenance.
- Add `scripts/pace_analytics_report.py` for pure aggregation and text reports.
- Instrument hook orchestration in `inject.py` after skip decisions and config
  resolution, independently of whether rules are emitted.
- Instrument command outcomes and successful ratings in `pace.py`; route analytics
  controls before native mode rejects formatting mutations.
- Instrument preview/settings entry and successful saves in `preview.py`. The
  spawned `--serve` process does not duplicate the parent's settings-open event.
- Keep `pace_config` validation and persistence reusable without automatic events;
  save callers supply the source and old/new snapshots.
- Update command help and README with definitions, storage controls, coverage,
  best-effort behavior, and the local-only recording guarantee.

## Acceptance and verification

1. With recording off, invoking normal plugin flows creates no analytics events.
2. With recording on, two eligible prompts create two observations even when the
   second emits no rules. A resume/compaction keeps the distinct session count at one.
3. A save A→B creates one save event; the next observed prompt creates one observed
   change. Reports show each metric independently. Saving B again adds no change.
4. Native option changes are detected at hooks. Invalid values produce allowlisted
   errors and record the fallback settings actually resolved.
5. Normalization merges inactive bionic differences, separates effective formatting
   changes, and exposes drift guard independently.
6. A fixture with prompts A,A,B,B,A yields transitions A→B and B→A, with shares
   3/5 and 2/5. Unknown sessions do not create false transitions.
7. Ratings appear once, notes never enter analytics, and the original rating report
   remains available when analytics is disabled or cleared.
8. Lock contention, disk errors, corrupt lines/state, and size caps preserve normal
   formatting/settings behavior. Concurrent successful appends remain parseable.
9. Retention, window boundaries, off configurations, empty denominators, exports,
   clear, and capped/partial coverage have deterministic fixture tests.
10. Run the existing Python suite plus meaningful event/report/integration tests in
    isolated temporary stores; no test may write to real user analytics storage.
11. Measure hook overhead with recording off and on using a temporary store and
    report the result; recording does no network I/O or event-history scans.

## Later gathering phase

Validate these reports during local use first. Then design explicit sharing
preferences, collection transport, batch/retry limits, deduplication, and server
retention around the stable event schema. Revisit fields and identifiers before
uploading anything: local session keys and existing local history are not
automatically approved for sharing. Longitudinal identifiers are pseudonymous,
not guaranteed anonymous. Cross-platform coverage needs executable instrumentation
before totals can be compared across integrations.
