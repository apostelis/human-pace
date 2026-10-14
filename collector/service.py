"""Pure bounded collector HTTP contract. No request body or token logging."""
import time
from collector.store import CollectorError
import pace_remote_contract as c

class Limiter:
    def __init__(self,*,clock=time.monotonic,max_entries=10000):self.clock=clock;self.entries={};self.max_entries=max_entries
    def allow(self,key,*,rate,burst):
        now=self.clock()
        if key not in self.entries and len(self.entries)>=self.max_entries:
            # Reclaim only fully replenished idle entries, never erase an active limit.
            for old,(tokens,stamp,r,b) in list(self.entries.items()):
                if tokens+(now-stamp)*r>=b:self.entries.pop(old)
            if len(self.entries)>=self.max_entries:return False
        tokens,stamp,_,_=self.entries.get(key,(burst,now,rate,burst))
        tokens=min(burst,tokens+max(0,now-stamp)*rate)
        accepted=tokens>=1
        self.entries[key]=(tokens-1 if accepted else tokens,now,rate,burst)
        return accepted

def handle(store,method,path,*,headers,body,now,limiter):
    headers={k.lower():v for k,v in headers.items()}
    def answer(status,data):
        h={'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
        if status==429:h['Retry-After']='60'
        return status,h,c.canonical(data)
    try:
        if not limiter.allow('ingress',rate=10,burst=20):raise CollectorError('rate_limit',429)
        if path not in ('/v1/registrations','/v1/events','/v1/installation','/v1/deletion'):return answer(404,{'error':'route'})
        if len(body)>c.MAX_BATCH_BYTES:raise CollectorError('oversized',413)
        if headers.get('transfer-encoding') or headers.get('content-encoding','identity')!='identity':raise CollectorError('invalid_request',400)
        if method=='POST':
            if headers.get('content-type')!='application/json' or not headers.get('content-length','').isdigit() or int(headers['content-length'])!=len(body):raise CollectorError('invalid_request',400)
            data=c.strict_json(body,max_bytes=c.MAX_BATCH_BYTES)
        else:
            if body:raise CollectorError('invalid_request',400)
            data=None
        if path=='/v1/registrations' and method=='POST':
            source=headers.get('x-trusted-source','local')
            if len(source)>128:raise CollectorError('invalid_request',400)
            if not limiter.allow('registration:global',rate=100/60,burst=100) or not limiter.allow('registration:'+source,rate=5/60,burst=5):raise CollectorError('rate_limit',429)
            if not isinstance(data,dict) or set(data)!={'installation_id','recovery_key'}:raise CollectorError('invalid_request',400)
            return answer(200,store.register(data['installation_id'],data['recovery_key'],now=now))
        auth=headers.get('authorization','')
        if not auth.startswith('Bearer '):raise CollectorError('credentials',401)
        credential=auth[7:]
        if path=='/v1/events' and method=='POST':
            if not isinstance(data,dict) or set(data)!={'schema_version','events'}:raise CollectorError('invalid_request',400)
            if type(data['schema_version']) is not int or data['schema_version']!=1:raise CollectorError('unsupported_schema',426)
            events=data['events']
            if not isinstance(events,list):raise CollectorError('invalid_request',400)
            if len(events)>c.MAX_BATCH_EVENTS:raise CollectorError('oversized',413)
            ids=[e.get('event_id') if isinstance(e,dict) else None for e in events]
            if any(not isinstance(eid,str) or not c.HEX32.fullmatch(eid) for eid in ids) or len(set(ids))!=len(ids):raise CollectorError('invalid_request',400)
            if not limiter.allow('ingestion:'+credential,rate=10/60,burst=10):raise CollectorError('rate_limit',429)
            return answer(200,store.ingest(credential,events,now=now))
        if path=='/v1/installation' and method=='DELETE':return answer(200,store.request_delete(credential,now=now))
        if path=='/v1/deletion' and method=='GET':return answer(200,store.deletion_status(credential))
        return answer(405,{'error':'method'})
    except c.ContractError:return answer(400,{'error':'invalid_request'})
    except CollectorError as error:return answer(error.status,{'error':error.reason})
    except (OSError,ValueError,TypeError):return answer(503,{'error':'storage'})
