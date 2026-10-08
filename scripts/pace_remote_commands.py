"""User-facing sharing controls; transport is constructed only for explicit requests."""
import pace_remote_store as remote
from pace_remote_store import RemoteError, disclosure
from pace_remote_transport import HttpsTransport, upload, delete_all

HELP='Usage: /pace analytics share [on|off|preview|upload|delete]'
def run_share(args,*,now,store,local_enabled,release,transport=None):
    if len(args)>1 or (args and args[0] not in ('on','off','preview','upload','delete')):return HELP
    command=args[0] if args else 'status'
    if command=='on':
        store.enable(now=now,local_enabled=local_enabled,release=release)
        return disclosure(release)+'\nSharing enabled. Future events are queued; upload manually.'
    if command=='off':
        store.disable(now=now)
        return 'Sharing off. Pending events discarded. Previously uploaded data remains; use /pace analytics share delete.'
    if command=='preview':return store.preview(now=now).decode()
    if command=='status':
        s=store.status(now=now)
        return (f"Sharing: {'suspended' if s['suspended'] else 'on' if s['enabled'] else 'off'} (manual uploads).\n"
                f"Recipient: {release.get('operator') or 'not configured'}; {release.get('endpoint') or 'no destination'}\n"
                f"Schema: 1; notice: {release.get('notice_version',1)}\n"
                f"Queued: {s['queued_count']}; oldest UTC day: {s['oldest_day'] or 'none'}; evicted: {s['evicted_count']}; expired: {s['expired_count']}.\n"
                f"Last result: {s['last_result'] or 'none'}; retry after: {s['retry_at'] or 'none'}.\n"
                "Coverage: Claude hook observations and instrumented commands; skill usage unavailable.\n"
                "Sharing is best effort; local clear does not delete server data. /pace analytics share delete requests erasure.")
    # Explicit deletion disables sharing even if no endpoint is currently configured.
    if command=='delete':store.disable(now=now)
    if not remote.valid_release(release):raise RemoteError('No collecting release destination is configured.')
    transport=transport or HttpsTransport(release['endpoint'])
    if command=='upload':
        result=upload(store,transport,now=now)
        if result['state'] not in ('uploaded','empty'):return f"Upload {result['state']}. Queued: {result['remaining']}. Check /pace analytics share."
        s=store.status(now=now)
        return f"Accepted: {result['accepted']}; duplicate: {result['duplicate']}; rejected: {result['rejected']}; remaining: {result['remaining']}; evicted: {s['evicted_count']}; expired: {s['expired_count']}."
    result=delete_all(store,transport,now=now)
    return f"Sharing off. Deletion completed: {result['completed']}; pending: {result['pending']}; failed: {result['failed']}. Rerun /pace analytics share delete for pending or failed identities. Backups expire within 30 days."
