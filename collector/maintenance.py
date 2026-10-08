"""Deletion journal and offline restore; journal/checkpoint must outlive database backups."""
import argparse
import fcntl
import hashlib
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from contextlib import closing
from pathlib import Path
from collector.store import CollectorError, credential_token
import pace_remote_contract as c

def _atomic(path,data):
    if path.is_symlink():raise CollectorError('journal_configuration')
    fd,tmp=tempfile.mkstemp(prefix='.journal-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
        directory=os.open(str(path.parent),os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:Path(tmp).unlink(missing_ok=True)

def checkpoint_path(journal):return Path(str(journal)+'.checkpoint')

def _scan(journal):
    digest=hashlib.sha256();items=[]
    try:
        if journal.is_symlink():raise OSError()
        with journal.open('rb') as f:
            for raw in f:
                if len(raw)>4096 or not raw.endswith(b'\n'):raise ValueError()
                item=c.strict_json(raw,max_bytes=4096)
                if set(item)!={'identity','requested','key_version','recovery_digest'} or not c.HEX32.fullmatch(item['identity']) or item['key_version']!=1:raise ValueError()
                datetime.fromisoformat(item['requested'])
                if not c.HEX64.fullmatch(item['recovery_digest']):raise ValueError()
                digest.update(raw);items.append(item)
        return items,digest.hexdigest()
    except (OSError,ValueError,TypeError,KeyError):raise CollectorError('deletion_journal_unavailable') from None

def _verify(journal):
    items,digest=_scan(journal);path=checkpoint_path(journal)
    try:
        if path.is_symlink():raise OSError()
        checkpoint=c.strict_json(path.read_bytes(),max_bytes=4096)
        if checkpoint!={'count':len(items),'digest':digest}:raise ValueError()
    except (OSError,ValueError):raise CollectorError('stale_deletion_journal') from None
    return items

def append_tombstone(journal,identity,requested,recovery_digest):
    journal=Path(journal)
    try:
        if journal.is_symlink():raise OSError()
        journal.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        lock_path=Path(str(journal)+'.lock')
        fd=os.open(str(lock_path),os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'ab') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if journal.exists():items,_=_scan(journal)
            else:items=[]
            if identity not in {x['identity'] for x in items}:
                fd=os.open(str(journal),os.O_CREAT|os.O_APPEND|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
                with os.fdopen(fd,'ab') as f:
                    f.write(c.canonical(dict(identity=identity,requested=requested,key_version=1,recovery_digest=recovery_digest))+b'\n');f.flush();os.fsync(f.fileno())
            elif journal.exists():
                # A prior fsync/checkpoint failure must be repaired durably on retry.
                with journal.open('rb') as f:os.fsync(f.fileno())
            items,digest=_scan(journal)
            _atomic(checkpoint_path(journal),c.canonical(dict(count=len(items),digest=digest)))
    except OSError:raise CollectorError('deletion_journal_unavailable',503) from None

def maintain(store,journal,*,now):
    # Journal every revoked identity before marking any primary deletion completed.
    with store.connect() as db:revoked=db.execute('SELECT identity,requested,recovery FROM installations WHERE revoked=1').fetchall()
    for item in revoked:append_tombstone(journal,item['identity'],item['requested'],item['recovery'])
    cutoff=(now.date()-timedelta(days=89)).isoformat()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        removed=db.execute('DELETE FROM events WHERE identity IN (SELECT identity FROM installations WHERE revoked=1) OR day<?',(cutoff,)).rowcount
        db.execute('UPDATE installations SET completed=coalesce(completed,?) WHERE revoked=1',(now.isoformat(),))
    return {'removed':removed,'completed':len(revoked)}

def restore(database,backup,journal,*,key,now):
    database,backup,journal=Path(database),Path(backup),Path(journal)
    ready=database.with_suffix('.ready');ready.unlink(missing_ok=True)
    items=_verify(journal) # Missing/stale independent journal leaves service unavailable.
    if database==backup or backup.is_symlink() or database.is_symlink():raise CollectorError('restore_configuration')
    fd,tmp=tempfile.mkstemp(prefix='.restore-',dir=database.parent);os.close(fd);stage=Path(tmp)
    try:
        with closing(sqlite3.connect(backup.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as source, closing(sqlite3.connect(str(stage))) as target:
            source.backup(target)
            target.execute('PRAGMA journal_mode=DELETE')
            target.execute('PRAGMA foreign_keys=ON')
            saved=target.execute("SELECT value FROM metadata WHERE name='key'").fetchone()
            if not saved or saved[0]!=hashlib.sha256(key).hexdigest():raise CollectorError('key_configuration')
            for item in items:
                identity=item['identity'];recovery=item['recovery_digest']
                ingestion=hashlib.sha256(credential_token(key,'ingestion',identity,recovery).encode()).hexdigest()
                deletion=hashlib.sha256(credential_token(key,'deletion',identity,recovery).encode()).hexdigest()
                target.execute('INSERT INTO installations(identity,recovery,ingestion,deletion,revoked,created,requested,completed) VALUES (?,?,?,?,1,?,?,?) ON CONFLICT(identity) DO UPDATE SET revoked=1,requested=coalesce(requested,excluded.requested),completed=excluded.completed',
                    (identity,recovery,ingestion,deletion,item['requested'],item['requested'],now.isoformat()))
            target.execute('DELETE FROM events WHERE identity IN (SELECT identity FROM installations WHERE revoked=1) OR day<?',((now.date()-timedelta(days=89)).isoformat(),))
            if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or target.execute('PRAGMA foreign_key_check').fetchall():raise CollectorError('restore_integrity')
            target.commit()
        # Operator must stop server first. Remove old WAL only after checkpoint/close.
        if database.exists():
            with closing(sqlite3.connect(str(database))) as old:
                result=old.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
                if result[0]!=0:raise CollectorError('restore_database_busy')
        for suffix in ('-wal','-shm'):
            path=Path(str(database)+suffix)
            if path.is_symlink():raise CollectorError('restore_configuration')
            path.unlink(missing_ok=True)
        os.replace(stage,database)
        with database.open('rb') as f:os.fsync(f.fileno())
        _atomic(ready,b'ready\n')
        return {'restored':True,'tombstones':len(items)}
    except (sqlite3.Error,OSError):raise CollectorError('restore_storage') from None
    finally:stage.unlink(missing_ok=True)

def main():
    from collector.store import CollectorStore
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['maintain','restore'])
    parser.add_argument('--database',type=Path,required=True);parser.add_argument('--journal',type=Path,required=True)
    parser.add_argument('--key-file',type=Path,required=True);parser.add_argument('--backup',type=Path)
    args=parser.parse_args();now=datetime.now(timezone.utc)
    try:
        key=args.key_file.read_bytes()
        if args.action=='restore':
            if args.backup is None:parser.error('--backup is required for restore')
            result=restore(args.database,args.backup,args.journal,key=key,now=now)
        else:result=maintain(CollectorStore(args.database,key=key,journal=args.journal),args.journal,now=now)
        print(c.canonical(result).decode())
    except (CollectorError,OSError):parser.exit(1,'Maintenance failed; inspect readiness, journal and storage.\n')
if __name__=='__main__':main()
