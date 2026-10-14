"""Explicit HTTPS requests only. Imports and recorder paths never send data."""
import http.client
import ssl
import subprocess
import sys
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
import pace_remote_contract as c
from pace_remote_store import RemoteError, valid_release

class TransportError(RemoteError):
    def __init__(self,reason='network',*,status=0,retry_after=None):
        super().__init__('Sharing request failed: '+reason+'.')
        self.reason,self.status,self.retry_after=reason,status,retry_after

class HttpsTransport:
    def __init__(self,endpoint,*,clock=time.monotonic):
        if not valid_release(dict(endpoint=endpoint,operator='operator',contact='contact',notice_version=1)):
            raise RemoteError('Invalid HTTPS collection destination.')
        self.url=urlsplit(endpoint);self.clock=clock
    def request(self,method,path,*,body,credential,deadline):
        # A short-lived worker enforces a hard deadline across libc DNS and trickling
        # HTTP headers, which socket timeouts alone cannot bound.
        remaining=deadline-self.clock()
        if remaining<=0:raise TransportError('timeout')
        payload=c.canonical(dict(endpoint=self.url.geturl(),method=method,path=path,
            body=body.hex(),credential=credential,timeout=remaining))
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--request-worker'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            raw,_=child.communicate(payload,timeout=max(.001,deadline-self.clock()))
            result=c.strict_json(raw,max_bytes=65536)
            if not isinstance(result,dict):raise TransportError('invalid_response')
            if 'transport_error' in result:
                raise TransportError(result['transport_error'],status=result.get('status',0),retry_after=result.get('retry_after'))
            return result
        except subprocess.TimeoutExpired:
            child.kill();child.communicate()
            raise TransportError('timeout') from None
        except (OSError,c.ContractError):raise TransportError('network') from None
        finally:
            if child.poll() is None:child.kill();child.communicate()
    def _request(self,method,path,*,body,credential,deadline):
        if path not in ('/v1/registrations','/v1/events','/v1/installation','/v1/deletion'):raise TransportError('route')
        def remaining():
            seconds=deadline-self.clock()
            if seconds<=0:raise TransportError('timeout')
            return seconds
        connection=None
        try:
            connection=http.client.HTTPSConnection(self.url.hostname,self.url.port or 443,timeout=remaining(),context=ssl.create_default_context())
            headers={'Content-Type':'application/json','Accept-Encoding':'identity','Content-Length':str(len(body))}
            if credential:headers['Authorization']='Bearer '+credential
            connection.connect();connection.sock.settimeout(remaining())
            connection.request(method,path,body=body,headers=headers)
            connection.sock.settimeout(remaining());response=connection.getresponse()
            if not 200<=response.status<300:
                reason='credentials' if response.status in (401,403) else 'unsupported_schema' if response.status==426 else 'http'
                raise TransportError(reason,status=response.status,retry_after=response.getheader('Retry-After'))
            if response.getheader('Content-Encoding','identity')!='identity':raise TransportError('invalid_response')
            raw=bytearray()
            while True:
                sock=connection.sock or getattr(getattr(response.fp,'raw',None),'_sock',None)
                if sock:sock.settimeout(remaining())
                else:remaining()
                chunk=response.read1(min(8192,65537-len(raw)))
                if not chunk:break
                raw.extend(chunk)
                if len(raw)>65536:raise TransportError('invalid_response')
            remaining()
            return c.strict_json(bytes(raw),max_bytes=65536)
        except (OSError,http.client.HTTPException,c.ContractError,ValueError):
            raise TransportError('network') from None
        finally:
            if connection is not None:connection.close()

def retry_seconds(count,retry_after,now):
    delay=min(86400,60*2**min(11,count))
    if retry_after:
        try:wait=int(retry_after)
        except (ValueError,TypeError):
            try:wait=int((parsedate_to_datetime(retry_after)-now).total_seconds())
            except (ValueError,TypeError,OverflowError):wait=0
        delay=max(delay,max(60,min(86400,wait)))
    return delay

def validate_receipt(receipt,ids):
    try:
        if not isinstance(receipt,dict) or set(receipt)!={'accepted','duplicate','rejected'}:raise ValueError()
        if not all(isinstance(receipt[k],list) for k in receipt):raise ValueError()
        rejected=[]
        reasons={'invalid_event','expired','future','identity_mismatch','conflicting_id','sequence_conflict'}
        for item in receipt['rejected']:
            if not isinstance(item,dict) or set(item)!={'event_id','reason'} or item['reason'] not in reasons:raise ValueError()
            rejected.append(item['event_id'])
        returned=receipt['accepted']+receipt['duplicate']+rejected
        if any(not isinstance(x,str) or x not in ids for x in returned) or len(set(returned))!=len(returned):raise ValueError()
    except (ValueError,TypeError,KeyError):raise TransportError('invalid_response') from None
    return receipt

def upload(store,transport,*,now):
    deadline=time.monotonic()+10
    claim=store.claim(now=now)
    if not claim['event_ids']:return dict(state='empty',accepted=0,duplicate=0,rejected=0,remaining=0)
    try:
        if not store.current(claim):raise TransportError('consent_changed')
        item=claim['registration'];creds=item['credentials']
        if creds is None:
            creds=transport.request('POST','/v1/registrations',body=c.canonical({'installation_id':claim['identity'],'recovery_key':item['recovery_key']}),credential=None,deadline=deadline)
            store.save_credentials(claim['identity'],creds,generation=claim['generation'])
        if not store.current(claim):raise TransportError('consent_changed')
        receipt=transport.request('POST','/v1/events',body=claim['body'],credential=creds['ingestion_token'],deadline=deadline)
        validate_receipt(receipt,claim['event_ids'])
        result=store.finish(claim,receipt,now=now)
        return dict(state='uploaded',accepted=len(receipt['accepted']),duplicate=len(receipt['duplicate']),rejected=len(receipt['rejected']),**result)
    except (OSError,RemoteError,c.ContractError):
        import sys
        error=sys.exc_info()[1]
        reason=error.reason if isinstance(error,TransportError) else 'network'
        suspended=reason in ('credentials','unsupported_schema')
        delay=retry_seconds(claim['retry_count'],getattr(error,'retry_after',None),now)
        store.fail(claim,reason=reason,retry_at=now+timedelta(seconds=delay),suspended=suspended)
        return dict(state='suspended' if suspended else 'retry',reason=reason,remaining=store.status(now=now)['queued_count'])

def delete_all(store,transport,*,now):
    deadline=time.monotonic()+10;targets=store.deletion_targets(now=now);completed=0;pending=0;failed=0
    for item in targets:
        if time.monotonic()>=deadline:failed+=1;continue
        try:
            target_transport = HttpsTransport(item['recipient']['endpoint']) if transport is None or isinstance(transport, HttpsTransport) else transport
            creds=item['credentials']
            if creds is None:
                creds=target_transport.request('POST','/v1/registrations',body=c.canonical({'installation_id':item['identity'],'recovery_key':item['recovery_key']}),credential=None,deadline=deadline)
                store.save_credentials(item['identity'],creds,generation=-1)
            receipt=target_transport.request('DELETE','/v1/installation',body=b'',credential=creds['deletion_token'],deadline=deadline)
            store.deletion_receipt(item['identity'],receipt)
            if receipt['status']=='pending':
                receipt=target_transport.request('GET','/v1/deletion',body=b'',credential=creds['deletion_token'],deadline=deadline)
                store.deletion_receipt(item['identity'],receipt)
            if receipt['status']=='completed':completed+=1
            else:pending+=1
        except (OSError,RemoteError,c.ContractError,TypeError,KeyError):failed+=1
    return dict(completed=completed,pending=pending,failed=failed)


def _worker():
    try:
        data=c.strict_json(sys.stdin.buffer.read(1024*1024+1),max_bytes=1024*1024)
        transport=HttpsTransport(data['endpoint'])
        result=transport._request(data['method'],data['path'],body=bytes.fromhex(data['body']),
            credential=data['credential'],deadline=time.monotonic()+data['timeout'])
    except TransportError as error:result=dict(transport_error=error.reason,status=error.status,retry_after=error.retry_after)
    except Exception:result=dict(transport_error='network',status=0,retry_after=None)
    sys.stdout.buffer.write(c.canonical(result))

if __name__=='__main__' and sys.argv[1:]==['--request-worker']:_worker()
