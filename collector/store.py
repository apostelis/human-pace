"""Durable authenticated contributions and immediate revocation."""
import hashlib
import hmac
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
import pace_remote_contract as c

class CollectorError(Exception):
    def __init__(self,reason='storage',status=503):
        self.reason,self.status=reason,status
        super().__init__(reason)

MAX_PRIMARY_BYTES=1024**3
class CollectorStore:
    def __init__(self,database,*,key,journal=None):
        if not isinstance(key,bytes) or len(key)<32:raise CollectorError('key_configuration')
        self.database=Path(database);self.key=key
        self.journal=Path(journal) if journal else self.database.with_name('deletions.jsonl')
        self.ready=self.database.with_suffix('.ready')
        for path in (self.database,self.journal,self.ready):
            if path.is_symlink():raise CollectorError('storage')
        fresh=not self.database.exists()
        self.database.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(str(self.database),os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600);os.close(fd)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''CREATE TABLE IF NOT EXISTS installations(identity TEXT PRIMARY KEY, recovery TEXT, ingestion TEXT UNIQUE, deletion TEXT UNIQUE, revoked INTEGER DEFAULT 0, created TEXT, requested TEXT, completed TEXT);
CREATE TABLE IF NOT EXISTS events(identity TEXT REFERENCES installations(identity), event_id TEXT, day TEXT, received TEXT, session TEXT, sequence INTEGER, digest TEXT, body BLOB, PRIMARY KEY(identity,event_id));
CREATE UNIQUE INDEX IF NOT EXISTS event_sequence ON events(identity,session,sequence) WHERE sequence IS NOT NULL;
CREATE INDEX IF NOT EXISTS event_day ON events(day);
CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY,value TEXT);
''')
            digest=hashlib.sha256(key).hexdigest();saved=db.execute("SELECT value FROM metadata WHERE name='key'").fetchone()
            if saved and not hmac.compare_digest(saved[0],digest):raise CollectorError('key_configuration')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('key',?)",(digest,))
        if fresh:
            fd=os.open(str(self.ready),os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'w') as f:f.write('ready\n')
        if not self.ready.exists():raise CollectorError('restore_not_ready')
    @contextmanager
    def connect(self):
        if self.database.is_symlink():raise CollectorError('storage')
        db=sqlite3.connect(str(self.database),timeout=1)
        db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:yield db
        except sqlite3.Error:raise CollectorError('storage') from None
        finally:db.close()
    def _ensure_ready(self):
        if self.ready.is_symlink() or not self.ready.exists():raise CollectorError('restore_not_ready')
    def _token(self,label,identity,recovery):
        return hmac.new(self.key,(label+':v1:'+identity+':'+recovery).encode(),hashlib.sha256).hexdigest()
    @staticmethod
    def digest(token):return hashlib.sha256(token.encode()).hexdigest()
    def _auth(self,db,token,role):
        if not isinstance(token,str) or not c.HEX64.fullmatch(token):raise CollectorError('credentials',401)
        # Role is chosen by our code, never from request input.
        row=db.execute('SELECT * FROM installations WHERE '+role+'=?',(self.digest(token),)).fetchone()
        if row is None or not hmac.compare_digest(row[role],self.digest(token)):raise CollectorError('credentials',401)
        if role=='ingestion' and row['revoked']:raise CollectorError('credentials',401)
        return row
    def register(self,identity,recovery_key,*,now):
        self._ensure_ready()
        if not isinstance(identity,str) or not c.HEX32.fullmatch(identity) or not isinstance(recovery_key,str) or not c.HEX64.fullmatch(recovery_key):raise CollectorError('invalid_registration',400)
        recovery=self.digest(recovery_key);ing=self._token('ingestion',identity,recovery);delete=self._token('deletion',identity,recovery)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT recovery FROM installations WHERE identity=?',(identity,)).fetchone()
            if row and not hmac.compare_digest(row['recovery'],recovery):raise CollectorError('identity_conflict',409)
            if row is None:db.execute('INSERT INTO installations(identity,recovery,ingestion,deletion,created) VALUES (?,?,?,?,?)',(identity,recovery,self.digest(ing),self.digest(delete),now.isoformat()))
        return dict(installation_id=identity,ingestion_token=ing,deletion_token=delete)
    def ingest(self,credential,events,*,now):
        self._ensure_ready()
        if not isinstance(events,list) or len(events)>c.MAX_BATCH_EVENTS:raise CollectorError('oversized',413)
        valid=[];rejected=[]
        for raw in events:
            eid=raw.get('event_id') if isinstance(raw,dict) else None
            if not isinstance(eid,str) or not c.HEX32.fullmatch(eid):raise CollectorError('invalid_envelope',400)
            try:
                e=c.validate_event(raw);day=date.fromisoformat(e['day'])
                if day>now.date():raise c.ContractError('future')
                if day<now.date()-timedelta(days=7):raise c.ContractError('expired')
                valid.append((e,c.encode_event(e)))
            except c.ContractError as error:rejected.append(dict(event_id=eid,reason=error.reason))
        accepted=[];duplicate=[]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');principal=self._auth(db,credential,'ingestion');identity=principal['identity']
            payload_bytes=db.execute('SELECT coalesce(sum(length(body)),0) FROM events').fetchone()[0]
            received=db.execute('SELECT count(*) FROM events WHERE identity=? AND received>=?',(identity,now.date().isoformat())).fetchone()[0]
            if received+len(valid)>10000:raise CollectorError('rate_limit',429)
            for e,body in valid:
                eid=e['event_id']
                if e['installation_id']!=identity:rejected.append(dict(event_id=eid,reason='identity_mismatch'));continue
                digest=hashlib.sha256(body).hexdigest()
                saved=db.execute('SELECT digest FROM events WHERE identity=? AND event_id=?',(identity,eid)).fetchone()
                if saved:
                    if hmac.compare_digest(saved['digest'],digest):duplicate.append(eid)
                    else:rejected.append(dict(event_id=eid,reason='conflicting_id'))
                    continue
                sequence=e.get('prompt_sequence')
                if sequence is not None and db.execute('SELECT 1 FROM events WHERE identity=? AND session=? AND sequence=?',(identity,e['session_key'],sequence)).fetchone():
                    rejected.append(dict(event_id=eid,reason='sequence_conflict'));continue
                if payload_bytes+len(body)>MAX_PRIMARY_BYTES:raise CollectorError('capacity',503)
                db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(identity,eid,e['day'],now.isoformat(),e['session_key'],sequence,digest,body));payload_bytes+=len(body);accepted.append(eid)
        return dict(accepted=accepted,duplicate=duplicate,rejected=rejected)
    def request_delete(self,credential,*,now):
        self._ensure_ready()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=self._auth(db,credential,'deletion')
            db.execute('UPDATE installations SET revoked=1,requested=coalesce(requested,?) WHERE identity=?',(now.isoformat(),row['identity']))
        # Independent durable journal integration is supplied by maintenance module.
        from collector.maintenance import append_tombstone
        append_tombstone(self.journal,row['identity'],row['requested'] or now.isoformat())
        return dict(installation_id=row['identity'],status='completed' if row['completed'] else 'pending')
    def deletion_status(self,credential):
        self._ensure_ready()
        with self.connect() as db:row=self._auth(db,credential,'deletion')
        return dict(installation_id=row['identity'],status='completed' if row['completed'] else 'pending')
    def live_events(self,*,start,end):
        self._ensure_ready()
        with self.connect() as db:
            rows=db.execute('SELECT e.body FROM events e JOIN installations i ON e.identity=i.identity WHERE i.revoked=0 AND e.day>=? AND e.day<=? ORDER BY e.day,e.identity,e.sequence',(start.isoformat(),end.isoformat())).fetchall()
        return [c.validate_event(c.strict_json(row['body'],max_bytes=c.MAX_EVENT_BYTES)) for row in rows]
