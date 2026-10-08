"""Internal single-process listener. Deploy behind a configured TLS proxy."""
import argparse
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from collector.store import CollectorStore, CollectorError
from collector.service import handle, Limiter
import pace_remote_contract as c

def create_server(store,*,host='127.0.0.1',port=8080,allow_external=False):
    if host!='127.0.0.1' and not allow_external:raise CollectorError('external_listener_requires_proxy')
    limiter=Limiter()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def log_error(self,*args):pass
        def dispatch(self):
            try:
                raw_length=self.headers.get('Content-Length','0')
                if not raw_length.isdigit() or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))>1:raise ValueError()
                length=int(raw_length)
                if length>c.MAX_BATCH_BYTES:
                    status,headers,body=413,{'Content-Type':'application/json'},b'{"error":"oversized"}'
                else:
                    raw=self.rfile.read(length)
                    if len(raw)!=length:raise ValueError()
                    incoming=dict(self.headers)
                    # Never trust client-supplied source headers on the default loopback listener.
                    # The configured proxy must overwrite this header; dedicated deployment source mapping is documented.
                    incoming['X-Trusted-Source']=self.client_address[0]
                    status,headers,body=handle(store,self.command,self.path,headers=incoming,body=raw,now=datetime.now(timezone.utc),limiter=limiter)
            except (ValueError,OSError):status,headers,body=400,{'Content-Type':'application/json'},b'{"error":"invalid_request"}'
            self.send_response(status)
            for k,v in headers.items():self.send_header(k,v)
            self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers()
            try:self.wfile.write(body)
            except OSError:pass
            self.close_connection=True
        do_POST=dispatch;do_DELETE=dispatch;do_GET=dispatch
    server=HTTPServer((host,port),Handler)
    original=server.get_request
    def request():
        connection,address=original();connection.settimeout(5);return connection,address
    server.get_request=request
    return server

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True);parser.add_argument('--key-file',type=Path,required=True)
    parser.add_argument('--journal',type=Path,required=True);parser.add_argument('--port',type=int,default=8080)
    args=parser.parse_args()
    try:
        store=CollectorStore(args.database,key=args.key_file.read_bytes(),journal=args.journal)
        with create_server(store,port=args.port) as server:server.serve_forever()
    except (CollectorError,OSError):parser.exit(1,'Collector configuration/storage unavailable.\n')
if __name__=='__main__':main()
