"""Authenticated USB-loopback interpreter. This service cannot operate the phone."""
import argparse
import hmac
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from compiler import ModelError
from intent import build_request, understand, validate_intent
from workflow_compile import compile_trace
from workflow_contract import compile_evidence
from skill_selection import select_skill, build_request as selection_request, validate_selection
from selection_deadline import SelectionBudget,select_bounded
from parameter_calls import interpret as interpret_parameters,build_request as parameter_request,validate_calls
from semantic_parameter_calls import interpret as interpret_semantics,build_request as semantic_request,validate_calls as validate_semantic_calls


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, token, interpreter=understand, max_calls=20, workflow_compiler=compile_trace, skill_selector=select_skill,
                 bounded_selector=None,selection_seconds=8,parameter_interpreter=interpret_parameters,
                 semantic_interpreter=interpret_semantics,semantic_seconds=None):
        if (address[0] != '127.0.0.1' or not isinstance(token,str) or len(token) < 32
                or type(max_calls) is not int or not 1 <= max_calls <= 100):
            raise ValueError('INVALID_LOCAL_CONFIGURATION')
        if type(selection_seconds) not in (int,float) or not math.isfinite(selection_seconds) or not 0<selection_seconds<=8:
            raise ValueError('INVALID_SELECTION_BUDGET')
        if semantic_seconds is not None and (type(semantic_seconds) not in (int,float)
                or not math.isfinite(semantic_seconds) or not 0<semantic_seconds<=20):
            raise ValueError('INVALID_SEMANTIC_BUDGET')
        self.token, self.interpreter, self.max_calls = token, interpreter, max_calls
        self.workflow_compiler = workflow_compiler
        self.skill_selector = skill_selector
        self.bounded_selector=bounded_selector
        self.selection_seconds=selection_seconds
        self.parameter_interpreter=parameter_interpreter
        self.semantic_interpreter=semantic_interpreter
        self.semantic_seconds=semantic_seconds
        self.input_seconds=5
        self.state_lock=threading.Lock();self.cancelled_ids=set();self.selection_events={}
        self.selection_audit=[]
        self.handler_slots=threading.BoundedSemaphore(8)
        self.seen = set(); self.lock = threading.Lock(); self.count = 0
        super().__init__(address, Handler)

    def process_request(self,request,client_address):
        if not self.handler_slots.acquire(False):
            self.shutdown_request(request)
            return
        try:super().process_request(request,client_address)
        except Exception:
            self.handler_slots.release()
            raise

    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.handler_slots.release()

    def cancel_selection(self,request_id):
        with self.state_lock:
            event=self.selection_events.get(request_id)
            if request_id not in self.cancelled_ids and len(self.cancelled_ids)>=self.max_calls:
                # Known requests already have a bounded, persistent event. Revoke
                # that event even when storage for early/unknown IDs is full.
                if event is None:return False
            else:self.cancelled_ids.add(request_id)
            if event:event.set()
            return True

    def select_with_deadline(self,request_id,text,skills,parameters=False,semantic=False):
        with self.state_lock:
            event=self.selection_events.setdefault(request_id,threading.Event())
            if request_id in self.cancelled_ids:event.set()
        seconds=self.semantic_seconds if semantic and self.semantic_seconds is not None else self.selection_seconds
        budget=SelectionBudget(seconds,cancelled=event.is_set)
        outcome='FAILED'
        try:
            budget.check()
            if semantic:result=self.semantic_interpreter(text,skills,budget)
            elif parameters:result=self.parameter_interpreter(text,skills,budget)
            elif self.bounded_selector is not None:result=self.bounded_selector(text,skills,budget)
            elif self.skill_selector is select_skill:result=select_bounded('G',text,skills,budget)
            else:
                # Legacy injected selectors retain their interface but not unlimited wait.
                result=budget.call(lambda payload,timeout:self.skill_selector(payload['text'],payload['skills']),
                    dict(text=text,skills=skills),'injected-selector')
            validator=validate_semantic_calls if semantic else validate_calls if parameters else validate_selection
            result=validator(result,skills);budget.check();outcome=result['status']
            return result
        except ModelError as error:
            outcome=str(error);raise
        finally:
            with self.state_lock:
                self.selection_audit.append(dict(request_id=request_id,outcome=outcome,
                    calls=len(budget.calls),cancelled=event.is_set()))


class ReceiveDeadline(io.RawIOBase):
    """Bound the entire header/body receive phase, not each arriving chunk."""
    def __init__(self, raw, connection, deadline):
        self.raw,self.connection,self.deadline=raw,connection,deadline

    def readable(self):return True

    def readinto(self, buffer):
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

    def log_message(self, *args): pass  # Never log input text, credentials or headers.

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        try:
            self.connection.settimeout(5)
            self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)
            if code>=400:self.discard_rejected_input()
        except OSError: pass

    def discard_rejected_input(self):
        # Closing a socket with a legitimate unread POST body can send TCP RST
        # (Windows 10053) and hide a just-written 401. Best-effort bounded drain
        # after rejection: never parse it, never call a model, never wait 5s.
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

    def do_POST(self):
        if self.path not in ('/v1/intents','/v1/workflows','/v1/skill-selections','/v1/skill-selection-cancellations','/v1/parameter-calls','/v2/parameter-calls'): return self.reply(404, dict(error='NOT_FOUND'))
        workflow = self.path == '/v1/workflows'
        semantic = self.path == '/v2/parameter-calls'
        parameters = self.path == '/v1/parameter-calls' or semantic
        selection = self.path == '/v1/skill-selections' or parameters
        cancellation = self.path == '/v1/skill-selection-cancellations'
        if any(len(self.headers.get_all(name,[]))>1 for name in ('Authorization','Content-Length','Content-Type')):
            return self.reply(400, dict(error='INVALID_REQUEST'))
        supplied = self.headers.get('Authorization','').encode('utf-8')
        if not hmac.compare_digest(supplied, ('Bearer '+self.server.token).encode()):
            return self.reply(401, dict(error='PAIRING_REQUIRED'))
        if 'Origin' in self.headers or 'Transfer-Encoding' in self.headers:
            return self.reply(400, dict(error='INVALID_REQUEST'))
        try:
            if time.monotonic()>=self.input_deadline:raise TimeoutError('INPUT_DEADLINE')
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= (262144 if workflow else 65536 if semantic else 32768 if selection else 4096): raise ValueError()
            from contracts import load_json
            raw=self.rfile.read(size)
            self.body_received=True
            if len(raw)!=size:raise ValueError('INCOMPLETE_BODY')
            if time.monotonic()>=self.input_deadline:raise TimeoutError('INPUT_DEADLINE')
            body = load_json(raw.decode('utf-8'))
            expected_fields={'request_id'} if cancellation else {'request_id','text','skills'} if selection else {'request_id','trace' if workflow else 'text'}
            if set(body) != expected_fields: raise ValueError()
            request_id = body['request_id']
            if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id): raise ValueError()
            if cancellation:pass
            elif workflow: candidate = compile_evidence(body['trace'])
            elif selection: (semantic_request if semantic else parameter_request if parameters else selection_request)(body['text'],body['skills'])
            else: build_request(body['text'])
        except (ValueError, TypeError, UnicodeError, TimeoutError):
            return self.reply(400, dict(error='INVALID_REQUEST'))
        if cancellation:
            if not self.server.cancel_selection(request_id):return self.reply(429,dict(error='CANCELLATION_LIMIT'))
            return self.reply(200,dict(request_id=request_id,status='cancelled'))
        if not self.server.lock.acquire(False): return self.reply(409, dict(error='BUSY'))
        try:
            if request_id in self.server.seen: return self.reply(409,dict(error='DUPLICATE_REQUEST'))
            if self.server.count >= self.server.max_calls: return self.reply(429,dict(error='SESSION_LIMIT'))
            # Admission and cancellation registration are one atomic operation.
            # An accepted ID must never look unknown to the revocation route.
            with self.server.state_lock:
                self.server.seen.add(request_id); self.server.count += 1
                if selection:
                    event=threading.Event()
                    if request_id in self.server.cancelled_ids:event.set()
                    self.server.selection_events[request_id]=event
            if workflow:
                compiled = self.server.workflow_compiler(body['trace'])
                status = compiled['status']
                if status not in ('candidate','clarify','reject') or compiled['reviewStatus'] != 'UNREVIEWED':
                    raise ValueError('INVALID_COMPILATION')
                if compiled['skill'] != (candidate if status == 'candidate' else None):
                    raise ValueError('EVIDENCE_CHANGED')
                reason = compiled['model']['draft']['reason']
                if not isinstance(reason,str) or not 0 < len(reason) <= 500: raise ValueError('REASON')
                result = dict(status=status,reviewStatus='UNREVIEWED',reason=reason,skill=compiled['skill'])
            elif selection:
                # Preserve the existing three-argument selector boundary for legacy adapters.
                if semantic:result=self.server.select_with_deadline(request_id,body['text'],body['skills'],True,True)
                elif parameters:result=self.server.select_with_deadline(request_id,body['text'],body['skills'],True)
                else:result=self.server.select_with_deadline(request_id,body['text'],body['skills'])
            else: result = validate_intent(self.server.interpreter(body['text']))
            return self.reply(200,dict(request_id=request_id, **result))
        except ModelError as error:
            return self.reply(503,dict(error=str(error)))
        except Exception:
            return self.reply(502,dict(error='INVALID_MODEL_RESPONSE'))
        finally: self.server.lock.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-calls',type=int,default=20)
    parser.add_argument('--semantic-seconds',type=float,default=20,
                        help='Bound semantic planning separately; legacy selection remains 8 seconds.')
    parser.add_argument('--token-file',type=Path,required=True)
    args=parser.parse_args()
    if not os.environ.get('OPENAI_API_KEY'):
        from win_credentials import read_key
        os.environ['OPENAI_API_KEY']=read_key()
    args.token_file.parent.mkdir(parents=True,exist_ok=True)
    if args.token_file.exists(): token=args.token_file.read_text(encoding='ascii').strip()
    else:
        token=secrets.token_hex(24)
        with args.token_file.open('x',encoding='ascii') as handle: handle.write(token)
    server=BridgeServer(('127.0.0.1',8765),token,max_calls=args.max_calls,semantic_seconds=args.semantic_seconds)
    print('USB intent bridge ready on loopback:8765; session call cap='+str(args.max_calls),flush=True)
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__': main()
