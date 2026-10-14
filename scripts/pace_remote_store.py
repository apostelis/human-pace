"""Private prospective queue and consent state. No network operations."""
import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
import pace_analytics as local
import pace_remote_contract as c
from pace_remote_projection import project

MAX_QUEUE_BYTES = 10 * 1024 * 1024
MAX_QUEUE_EVENTS = 10000
MAX_IDENTITIES = 100
MAX_SESSIONS = 10000
# Configure these in a reviewed collecting release, never from repository settings or env.
RELEASE = {'endpoint':'', 'operator':'', 'contact':'', 'notice_version':1}
class RemoteError(local.AnalyticsError): pass

def valid_release(release):
    try:
        url = urlsplit(release['endpoint'])
        return (url.scheme == 'https' and bool(url.hostname) and url.username is None
                and not url.query and not url.fragment and url.path in ('','/')
                and all(isinstance(release[k], str) and release[k].strip() for k in ('operator','contact'))
                and type(release['notice_version']) is int and release['notice_version'] > 0)
    except (ValueError, TypeError, KeyError): return False

def fingerprint(release): return hashlib.sha256(c.canonical(release)).hexdigest()

def disclosure(release):
    return ("Help improve Human Pace by sharing usage statistics: settings used, command counts, "
            "and numeric ratings. Prompts, replies, and rating notes are excluded. Sharing is optional "
            "and can be stopped anytime. Enabling sharing queues future events on this machine; "
            "upload them manually with /pace analytics share upload. "
            f"Recipient: {release.get('operator', '')}; destination: {release.get('endpoint', '')}; "
            f"contact: {release.get('contact', '')}. Events retained up to 90 days; pseudonymous "
            "installation/session identifiers link events within one consent epoch. Off stops new "
            "uploads; /pace analytics share delete revokes all saved identities, excludes reports "
            "immediately, removes primary events within 24 hours; backups expire within 30 days.")

def fresh_preferences():
    return dict(version=1, enabled=False, generation=0, choice='unset', session_notice=False,
                identity=None, consent_time=None, recipient=None, ledger=[], last_result=None,
                retry_count=0, retry_at=None, suspended=False)

class RemoteStore:
    def __init__(self, root):
        self.local = local.AnalyticsStore(root)
        self.root = self.local.root / 'remote'
    def _check(self):
        if self.root.is_symlink(): raise RemoteError('Sharing storage must not be a symbolic link.')
    def _prefs(self):
        self._check()
        try:
            value=c.strict_json(local._small_read(self.root/'preferences.json',256*1024),max_bytes=256*1024)
        except FileNotFoundError: return fresh_preferences()
        except Exception: raise RemoteError('Sharing preferences are invalid or unreadable.') from None
        try:
            if set(value)!=set(fresh_preferences()) or value['version']!=1 or type(value['enabled']) is not bool or type(value['generation']) is not int or value['generation']<0:
                raise ValueError()
            if value['choice'] not in ('unset','enabled','later','never','off') or type(value['session_notice']) is not bool or type(value['suspended']) is not bool:
                raise ValueError()
            if not isinstance(value['ledger'],list) or len(value['ledger'])>MAX_IDENTITIES: raise ValueError()
            for item in value['ledger']:
                if set(item)!={'identity','secret','recovery_key','credentials','pending_delete','recipient'}: raise ValueError()
                if not c.HEX32.fullmatch(item['identity']) or not c.HEX64.fullmatch(item['secret']) or not c.HEX64.fullmatch(item['recovery_key']) or type(item['pending_delete']) is not bool: raise ValueError()
                if not valid_release(item['recipient']):raise ValueError()
                if item['credentials'] is not None: self._validate_credentials(item['identity'],item['credentials'])
            if value['enabled'] and (value['identity'] not in [x['identity'] for x in value['ledger']] or not value['consent_time'] or not isinstance(value['recipient'],dict)):raise ValueError()
            if value['consent_time']: local.utc(datetime.fromisoformat(value['consent_time']))
            if value['retry_at']: local.utc(datetime.fromisoformat(value['retry_at']))
            if type(value['retry_count']) is not int or not 0<=value['retry_count']<=32:raise ValueError()
        except (KeyError,TypeError,ValueError):raise RemoteError('Sharing preferences are invalid or unreadable.') from None
        return value
    def _save(self,p):
        self._check(); self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        local.AnalyticsStore(self.root)._atomic('preferences.json',c.canonical(p))
    @contextmanager
    def _db(self):
        self._check();self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=self.root/'queue.sqlite3'
        fd=local._open(path,os.O_CREAT|os.O_RDWR);os.close(fd)
        db=sqlite3.connect(str(path),timeout=0)
        try:
            db.executescript('''CREATE TABLE IF NOT EXISTS events (ordinal INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE, identity TEXT, day TEXT, body BLOB, claim TEXT, lease TEXT);
CREATE TABLE IF NOT EXISTS sessions (session TEXT PRIMARY KEY, sequence INTEGER, settings TEXT, observed TEXT, salt TEXT);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER);
''')
            with db: yield db
        finally: db.close()
    def _count(self,db,name,n=1):
        db.execute('INSERT INTO counters VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value',(name,n))
    def _expire(self,db,now):
        cutoff=(local.utc(now).date()-timedelta(days=7)).isoformat()
        n=db.execute('SELECT count(*) FROM events WHERE day<?',(cutoff,)).fetchone()[0]
        db.execute('DELETE FROM events WHERE day<?',(cutoff,));self._count(db,'expired',n)
        db.execute('DELETE FROM sessions WHERE observed<?',((now-timedelta(days=7)).isoformat(),))
    def enable(self,*,now,local_enabled,release):
        if not local_enabled:raise RemoteError('Enable local recording with /pace analytics on first.')
        if not valid_release(release):raise RemoteError('No collecting release destination is configured.')
        with self.local._lock():
            p=self._prefs()
            if p['enabled'] and p['recipient']==release and not p['suspended']:return {'identity':p['identity'],'enabled':True}
            if len(p['ledger'])>=MAX_IDENTITIES:raise RemoteError('Delete prior sharing identities before enabling again.')
            p.update(enabled=False,generation=p['generation']+1)
            self._save(p)
            with self._db() as db: db.execute('DELETE FROM events');db.execute('DELETE FROM sessions')
            identity=secrets.token_hex(16)
            p['ledger'].append(dict(identity=identity,secret=secrets.token_hex(32),recovery_key=secrets.token_hex(32),credentials=None,pending_delete=False,recipient=dict(release)))
            p.update(enabled=True,choice='enabled',session_notice=True,
                     identity=identity,consent_time=local.utc(now).isoformat(),recipient=dict(release),
                     suspended=False,retry_count=0,retry_at=None)
            self._save(p)
            return {'identity':identity,'enabled':True}
    def _disable_locked(self,now):
        p=self._prefs();p.update(enabled=False,generation=p['generation']+1,choice='off',session_notice=True)
        self._save(p) # fail closed before purge; stale queue cannot be uploaded
        if (self.root/'queue.sqlite3').exists():
            with self._db() as db:db.execute('DELETE FROM events');db.execute('DELETE FROM sessions')
        return {'enabled':False}
    def disable(self,*,now):
        with self.local._lock():return self._disable_locked(now)
    def clear_pending_locked(self,*,now):
        if not (self.root/'preferences.json').exists():return
        p=self._prefs();p['generation']+=1
        for item in p['ledger']:
            if item['identity']==p['identity']:item['secret']=secrets.token_hex(32)
        self._save(p)
        if (self.root/'queue.sqlite3').exists():
            with self._db() as db:db.execute('DELETE FROM events');db.execute('DELETE FROM sessions')
    def enqueue_locked(self,events,*,now):
        if not (self.root/'preferences.json').exists():return False
        p=self._prefs()
        if not p['enabled'] or p['suspended'] or not self.local.preferences()['enabled']:return False
        if p['recipient']!=RELEASE:
            p['suspended']=True;self._save(p);return False
        if local.utc(now)<datetime.fromisoformat(p['consent_time']):return False
        item=next(x for x in p['ledger'] if x['identity']==p['identity'])
        with self._db() as db:
            self._expire(db,now)
            for event in events:
                if local.validate_event(event) is None:continue
                if datetime.fromisoformat(event['timestamp'])<datetime.fromisoformat(p['consent_time']):continue
                key=event['session_key'];seq=None;previous=None;session_secret=item['secret']
                if key:
                    state=db.execute('SELECT sequence,settings,salt FROM sessions WHERE session=?',(key,)).fetchone()
                    if state:
                        try:
                            previous=json.loads(state[1]);seq=state[0];session_secret=state[2]
                            if not local.valid_config(previous) or type(seq) is not int or not 0<=seq<2**63-1 or not c.HEX64.fullmatch(session_secret):raise ValueError()
                        except (ValueError,TypeError):
                            db.execute('DELETE FROM sessions WHERE session=?',(key,));state=None;previous=None
                    if not state and db.execute('SELECT count(*) FROM sessions').fetchone()[0]>=MAX_SESSIONS:
                        key=None;event={**event,'session_key':None}
                        if event['event']=='session_observed':continue
                        self._count(db,'unassigned')
                    elif not state:seq=0;session_secret=secrets.token_hex(32)
                if key and event['event']=='prompt_observed':seq+=1
                remote=project(event,identity=item['identity'],secret=bytes.fromhex(session_secret),sequence=seq,previous=previous)
                if key and 'settings' in event and (event['event'] != 'session_observed' or previous is None):
                    db.execute('INSERT INTO sessions VALUES (?,?,?,?,?) ON CONFLICT(session) DO UPDATE SET sequence=excluded.sequence, settings=excluded.settings,observed=excluded.observed,salt=excluded.salt',(key,seq or 0,json.dumps(event['settings']),now.isoformat(),session_secret))
                if remote is None:continue
                body=c.encode_event(remote)
                if len(body)>MAX_QUEUE_BYTES:continue
                size,count=db.execute('SELECT coalesce(sum(length(body)),0),count(*) FROM events').fetchone()
                while count>=MAX_QUEUE_EVENTS or size+len(body)>MAX_QUEUE_BYTES:
                    row=db.execute('SELECT ordinal,length(body) FROM events ORDER BY ordinal LIMIT 1').fetchone()
                    if row is None:break
                    db.execute('DELETE FROM events WHERE ordinal=?',(row[0],));size-=row[1];count-=1;self._count(db,'evicted')
                if MAX_QUEUE_EVENTS<1:continue
                db.execute('INSERT INTO events(event_id,identity,day,body) VALUES (?,?,?,?)',(remote['event_id'],item['identity'],remote['day'],body))
        return True
    def _batch(self,db,now):
        self._expire(db,now)
        db.execute('UPDATE events SET claim=NULL,lease=NULL WHERE lease<=?',(now.isoformat(),))
        events=[]
        for body, in db.execute('SELECT body FROM events WHERE claim IS NULL ORDER BY ordinal LIMIT ?', (c.MAX_BATCH_EVENTS,)):
            e=c.strict_json(body,max_bytes=c.MAX_EVENT_BYTES)
            try:c.encode_batch(events+[e])
            except c.ContractError:break
            events.append(e)
        return events
    def preview(self,*,now):
        if not (self.root/'queue.sqlite3').exists():return c.encode_batch([])
        with self.local._lock(),self._db() as db:return c.encode_batch(self._batch(db,now))
    def claim(self,*,now):
        with self.local._lock():
            p=self._prefs()
            if not p['enabled'] or p['suspended'] or p['recipient']!=RELEASE or not self.local.preferences()['enabled']:raise RemoteError('Sharing is off or suspended.')
            if p['retry_at'] and now<datetime.fromisoformat(p['retry_at']):raise RemoteError('Upload backoff is active; retry later.')
            with self._db() as db:
                events=self._batch(db,now);claim=uuid.uuid4().hex;ids=[e['event_id'] for e in events]
                for eid in ids:db.execute('UPDATE events SET claim=?,lease=? WHERE event_id=?',(claim,(now+timedelta(seconds=30)).isoformat(),eid))
            item=next(x for x in p['ledger'] if x['identity']==p['identity'])
            return dict(claim_id=claim,generation=p['generation'],identity=p['identity'],body=c.encode_batch(events),event_ids=ids,registration=dict(item),retry_count=p['retry_count'])
    def current(self,claim):
        with self.local._lock():
            p=self._prefs()
            return p['enabled'] and not p['suspended'] and p['generation']==claim['generation'] and p['identity']==claim['identity'] and p['recipient']==RELEASE and self.local.preferences()['enabled']
    @staticmethod
    def _validate_credentials(identity,credentials):
        if not isinstance(credentials,dict) or set(credentials)!={'installation_id','ingestion_token','deletion_token'} or credentials['installation_id']!=identity or any(not isinstance(credentials[k],str) or not c.HEX64.fullmatch(credentials[k]) for k in ('ingestion_token','deletion_token')):
            raise RemoteError('Invalid registration receipt.')
    def save_credentials(self,identity,credentials,*,generation):
        self._validate_credentials(identity,credentials)
        with self.local._lock():
            p=self._prefs()
            item=next((x for x in p['ledger'] if x['identity']==identity),None)
            if item is None:raise RemoteError('Registration identity no longer exists.')
            item['credentials']=dict(credentials)
            if p['generation']!=generation or not p['enabled']:item['pending_delete']=True
            self._save(p)
    def finish(self,claim,receipt,*,now):
        with self.local._lock():
            p=self._prefs()
            if p['generation']!=claim['generation']:return {'remaining':self._queued_count()}
            with self._db() as db:
                ids=receipt['accepted']+receipt['duplicate']+[x['event_id'] for x in receipt['rejected']]
                for eid in ids:
                    if eid in claim['event_ids']:db.execute('DELETE FROM events WHERE event_id=? AND claim=?',(eid,claim['claim_id']))
                db.execute('UPDATE events SET claim=NULL,lease=NULL WHERE claim=?',(claim['claim_id'],))
            p.update(last_result='uploaded',retry_count=0,retry_at=None);self._save(p)
            return {'remaining':self._queued_count()}
    def fail(self,claim,*,reason,retry_at,suspended):
        with self.local._lock():
            p=self._prefs()
            if p['generation']!=claim['generation']:return
            p.update(last_result=reason,retry_count=min(32,p['retry_count']+1),retry_at=retry_at.isoformat(),suspended=suspended);self._save(p)
            with self._db() as db:db.execute('UPDATE events SET claim=NULL,lease=NULL WHERE claim=?',(claim['claim_id'],))
    def _queued_count(self):
        if not (self.root/'queue.sqlite3').exists():return 0
        with self._db() as db:return db.execute('SELECT count(*) FROM events').fetchone()[0]
    def status(self,*,now):
        p=self._prefs();count=0;oldest=None;counters={}
        if (self.root/'queue.sqlite3').exists():
            with self.local._lock(),self._db() as db:
                self._expire(db,now);count,oldest=db.execute('SELECT count(*),min(day) FROM events').fetchone();counters=dict(db.execute('SELECT name,value FROM counters'))
        return dict(enabled=p['enabled'],suspended=p['suspended'] or (p['enabled'] and p['recipient']!=RELEASE),queued_count=count,oldest_day=oldest,
                    evicted_count=counters.get('evicted',0),expired_count=counters.get('expired',0),unassigned_count=counters.get('unassigned',0),
                    last_result=p['last_result'],retry_at=p['retry_at'],prior_identities=len(p['ledger']),choice=p['choice'])
    def invitation(self,*,surface,now,local_enabled,release):
        if surface not in ('session','settings'):raise RemoteError('Invalid invitation surface.')
        if not local_enabled or not valid_release(release):return {'visible':False,'choice':'unset','disclosure':''}
        with self.local._lock():
            p=self._prefs();visible=p['choice']=='unset' and not p['enabled']
            if surface=='session':
                visible=visible and not p['session_notice']
                if visible:p['session_notice']=True;self._save(p)
            return dict(visible=visible,choice=p['choice'],disclosure=disclosure(release))
    def choose_invitation(self,choice,*,now,local_enabled,release):
        if choice=='enable':return self.enable(now=now,local_enabled=local_enabled,release=release)
        if choice not in ('later','never'):raise RemoteError('Invalid sharing action.')
        with self.local._lock():
            p=self._prefs();p.update(choice=choice,session_notice=True);self._save(p)
        return {'enabled':p['enabled'],'choice':choice}
    def deletion_targets(self,*,now):
        with self.local._lock():
            self._disable_locked(now);p=self._prefs()
            # Unregistered identities still require recovery: a lost registration reply may have committed.
            for item in p['ledger']:item['pending_delete']=True
            self._save(p);return [dict(x) for x in p['ledger']]
    def deletion_receipt(self,identity,receipt):
        if set(receipt)!={'installation_id','status'} or receipt['installation_id']!=identity or receipt['status'] not in ('pending','completed'):raise RemoteError('Invalid deletion receipt.')
        with self.local._lock():
            p=self._prefs()
            if receipt['status']=='completed':p['ledger']=[x for x in p['ledger'] if x['identity']!=identity]
            if p['identity']==identity and receipt['status']=='completed':p['identity']=None
            p['last_result']='deletion_'+receipt['status'];self._save(p)
