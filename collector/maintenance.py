"""Durable deletion journal, retained separately from event database backups."""
import os
from pathlib import Path
from collector.store import CollectorError
import pace_remote_contract as c

def append_tombstone(journal,identity,requested):
    journal=Path(journal)
    try:
        if journal.is_symlink():raise OSError()
        journal.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(str(journal),os.O_CREAT|os.O_APPEND|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'ab') as f:
            f.write(c.canonical(dict(identity=identity,requested=requested,key_version=1))+b'\n');f.flush();os.fsync(f.fileno())
    except OSError:raise CollectorError('deletion_journal_unavailable',503) from None
