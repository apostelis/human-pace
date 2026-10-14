#!/usr/bin/env python3
"""Measure incremental queue overhead using temporary synthetic stores only."""
import argparse
import json
import platform
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
import pace_analytics as a
import pace_remote_store as r

def percentile(values,p):return sorted(values)[min(len(values)-1,int(len(values)*p))]
def run(iterations):
    if not 1<=iterations<=10000:raise ValueError('iterations must be 1–10000')
    result={'python':platform.python_version(),'os':platform.platform(),'filesystem_location':'temporary directory','iterations':iterations,'cases':{}}
    original=r.RELEASE
    try:
        r.RELEASE={'endpoint':'https://benchmark.invalid','operator':'synthetic','contact':'synthetic','notice_version':1}
        for name,fill in [('empty',0),('half_full',5000),('capped',10000)]:
            with tempfile.TemporaryDirectory() as tmp:
                now=datetime.now(timezone.utc);local=a.AnalyticsStore(Path(tmp)/'analytics');remote=r.RemoteStore(local.root)
                event=lambda:a.make_event('command_invoked',now=now,integration='unknown',source='pace',operation='status',outcome='success')
                off=[];on=[]
                for _ in range(iterations+10):
                    start=time.perf_counter_ns();local.record([event()],now=now);off.append((time.perf_counter_ns()-start)/1e6)
                remote.enable(now=now,local_enabled=True,release=r.RELEASE)
                if fill:
                    # Seed synthetic validated rows in one transaction, outside timed recording.
                    from pace_remote_projection import project
                    from pace_remote_contract import encode_event
                    with local._lock(),remote._db() as db:
                        prefs=remote._prefs();item=prefs['ledger'][-1]
                        for _ in range(fill):
                            e=project(event(),identity=item['identity'],secret=bytes.fromhex(item['secret']),sequence=None,previous=None)
                            db.execute('INSERT INTO events(event_id,identity,day,body) VALUES (?,?,?,?)',(e['event_id'],e['installation_id'],e['day'],encode_event(e)))
                for _ in range(iterations+10):
                    start=time.perf_counter_ns();local.record([event()],now=now);on.append((time.perf_counter_ns()-start)/1e6)
                deltas=[b-a for a,b in zip(off[10:],on[10:])]
                result['cases'][name]={'incremental_median_ms':round(statistics.median(deltas),3),'incremental_p95_ms':round(percentile(deltas,.95),3),'evicted':remote.status(now=now)['evicted_count']}
    finally:r.RELEASE=original
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--iterations',type=int,default=1000)
    print(json.dumps(run(parser.parse_args().iterations),indent=2))
