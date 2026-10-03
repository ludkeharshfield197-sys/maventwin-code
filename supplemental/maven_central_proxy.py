"""Serve Maven Central artifacts over loopback using the host TLS client."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import urllib.request,urllib.error,sys,hashlib,json,threading
ROOT=Path(sys.argv[1]);ROOT.mkdir(parents=True,exist_ok=True);lock=threading.Lock();downloads=threading.Semaphore(2)
class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        rel=self.path.split('?',1)[0].lstrip('/');url='https://repo.maven.apache.org/maven2/'+rel
        try:
            with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=30) as response:
                self.send_response(response.status)
                self.send_header('Content-Length',response.headers.get('Content-Length','0'));self.end_headers()
        except urllib.error.HTTPError as e:self.send_error(e.code)
        except Exception as e:self.send_error(502,str(e))
    def do_GET(self):
        rel=self.path.split('?',1)[0].lstrip('/');url='https://repo.maven.apache.org/maven2/'+rel
        dest=ROOT/rel
        try:
            if dest.is_file():b=dest.read_bytes()
            else:
                with downloads:
                    for attempt in range(3):
                        try:
                            with urllib.request.urlopen(url,timeout=30) as response:b=response.read()
                            break
                        except urllib.error.HTTPError:raise
                        except Exception:
                            if attempt==2:raise
        except urllib.error.HTTPError as e:self.send_error(e.code);return
        except Exception as e:self.send_error(502,str(e));return
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
        with lock:
            with (ROOT/'downloads.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(url=url,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))+'\n')
        self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*args):pass
if __name__=='__main__':
    print('Maven Central loopback relay ready',flush=True)
    ThreadingHTTPServer(('127.0.0.1',int(sys.argv[2])),Handler).serve_forever()
