"""Model-free HTTP framing for the candidate-only learning entrance.

Extracted unchanged from the existing gateway's framing implementation. Importing
this module cannot import an interpreter, select a Flow, or acquire input rights.
Authentication and endpoint authorization remain in LearningFlowHandler.
"""
import io,json,time
from http.server import BaseHTTPRequestHandler

class ReceiveDeadline(io.RawIOBase):
    """Bound the entire header/body receive phase, not each arriving chunk."""
    def __init__(self,raw,connection,deadline):
        self.raw,self.connection,self.deadline=raw,connection,deadline
    def readable(self):return True
    def readinto(self,buffer):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('INPUT_DEADLINE')
        self.connection.settimeout(remaining)
        return self.raw.readinto(buffer)
    def close(self):
        try:self.raw.close()
        finally:super().close()

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.input_deadline=time.monotonic()+self.server.input_seconds
        self.rfile.close()
        self.rfile=io.BufferedReader(ReceiveDeadline(
            self.connection.makefile('rb',buffering=0),self.connection,self.input_deadline))
        self.connection.settimeout(self.server.input_seconds)
    def log_message(self,*args):pass
    def reply(self,code,body):
        data=json.dumps(body,ensure_ascii=False).encode('utf-8')
        try:
            self.connection.settimeout(5)
            self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
            if code>=400:self.discard_rejected_input()
        except OSError:pass
    def discard_rejected_input(self):
        # A bounded best-effort drain prevents TCP RST hiding the rejection.
        headers=getattr(self,'headers',None)
        if headers is None or getattr(self,'body_received',False):return
        lengths=headers.get_all('Content-Length',[])
        if len(lengths)!=1 or 'Transfer-Encoding' in headers:return
        if len(lengths[0])>6 or not lengths[0].isascii() or not lengths[0].isdigit():return
        size=int(lengths[0])
        if not 0<size<=262144:return
        deadline=time.monotonic()+.05
        raw=getattr(self.rfile,'raw',None)
        if isinstance(raw,ReceiveDeadline):raw.deadline=min(raw.deadline,deadline)
        try:
            while size and time.monotonic()<deadline:
                part=self.rfile.read1(min(size,4096))
                if not part:break
                size-=len(part)
        except OSError:pass
