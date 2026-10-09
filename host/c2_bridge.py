"""Separate candidate-only paired USB endpoint. Existing execution bridge stays untouched."""
import hmac,json,re,sys,time
from c2_http_transport import Handler
from http.server import ThreadingHTTPServer
from c2_learning import LearningService
from c2_inbox import valid_id

class LearningServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,token,service):
        if address[0]!='127.0.0.1' or not re.fullmatch('[a-f0-9]{48}',token):raise ValueError('INVALID_LOCAL_CONFIGURATION')
        self.token=token;self.input_seconds=5;self.learning=service
        super().__init__(address,LearningFlowHandler)

class LearningFlowHandler(Handler):
    def do_POST(self):
        if self.path!='/v3/learning':return self.reply(404,{'error':'NOT_FOUND'})
        if any(len(self.headers.get_all(n,[]))!=1 for n in ('Authorization','Content-Length','Content-Type')) or 'Origin' in self.headers or 'Transfer-Encoding' in self.headers:
            return self.reply(400,{'error':'INVALID_REQUEST'})
        if not hmac.compare_digest(self.headers['Authorization'].encode(),('Bearer '+self.server.token).encode()):return self.reply(401,{'error':'PAIRING_REQUIRED'})
        if self.headers['Content-Type'].split(';')[0].strip().lower()!='application/json':return self.reply(400,{'error':'CONTENT_TYPE'})
        try:
            n=int(self.headers['Content-Length'])
            if not 0<n<=1048576:raise ValueError('INPUT_LIMIT')
            raw=self.rfile.read(n);self.body_received=True
            if len(raw)!=n or time.monotonic()>=self.input_deadline:raise ValueError('INPUT_LIMIT')
            def unique(rows):
                out={}
                for k,v in rows:
                    if k in out:raise ValueError('DUPLICATE_FIELD')
                    out[k]=v
                return out
            body=json.loads(raw,object_pairs_hook=unique)
            if type(body) is not dict or set(body)!={'request_id','operation','payload'}:raise ValueError('REQUEST_FIELDS')
            id=valid_id(body['request_id']);op=body['operation'];payload=body['payload'];service=self.server.learning
            if op=='generate':result=service.generate(id,payload)
            elif op=='cancel' and payload=={}:result=service.cancel(id)
            elif op=='inspect' and payload=={}:result=service.inbox.inspect(id)
            elif op=='name' and type(payload) is dict and set(payload)=={'name'}:result=service.inbox.name(id,payload['name'])
            elif op in {'prepare_validation','finish_validation','cancel_validation','validation_status','publish','published','candidate_details'}:
                if service.candidates is None:raise ValueError('CANDIDATE_SERVICE_UNAVAILABLE')
                if type(payload) is not dict:raise ValueError('REQUEST_FIELDS')
                with service.lock:
                    if service.active:raise ValueError('LEARNING_BUSY')
                    c=service.candidates
                    if op=='prepare_validation' and set(payload)=={'inputs'}:result=c.prepare(id,payload['inputs'])
                    elif op=='finish_validation' and set(payload)=={'attempt_id'}:result=c.finish(id,payload['attempt_id'])
                    elif op=='cancel_validation' and set(payload)=={'attempt_id'}:result=c.cancel(id,payload['attempt_id'])
                    elif op=='validation_status' and payload=={}:result=c.inspect(id)
                    elif op=='publish' and set(payload)=={'confirmed'}:result=c.publish(id,confirmed=payload['confirmed'])
                    elif op=='published' and payload=={}:result=c.published(id)
                    elif op=='candidate_details' and payload=={}:result=c.details(id)
                    else:raise ValueError('REQUEST_FIELDS')
            elif op=='status' and payload=={}:
                result={'bridge_connected':True,'model_configured':service.config is not None,
                    'model_api_usable':'NOT_PROBED','learning_busy':bool(service.active),
                    'candidate_execution':'EXPLICIT_UI_CONFIRMATION_REQUIRED' if service.candidates is not None else 'CANDIDATE_SERVICE_UNAVAILABLE','execution_authority':False}
            else:raise ValueError('OPERATION_UNSUPPORTED')
            return self.reply(200,{'request_id':id,'result':result,'execution_authority':False})
        except (ValueError,TypeError,KeyError,UnicodeError) as error:
            code=str(getattr(error,'code',str(error)))
            if not re.fullmatch('[A-Z_]{1,128}',code):code='LEARNING_CONTRACT_ERROR'
            return self.reply(422,{'error':code,'execution_authority':False})
        except Exception:return self.reply(503,{'error':'LEARNING_UNAVAILABLE','execution_authority':False})

if __name__=='__main__':
    import argparse,xml.etree.ElementTree as ET
    from pathlib import Path
    from lab_transport import adb
    from model_api import ModelConfig
    # The credential reader is a separate, fixed trusted dependency. Do not
    # import the legacy interpreter just to reuse HTTP framing.
    sys.path.insert(0,'C:/Users/zz/Documents/ChatGPT/毕设/model-gateway')
    from win_credentials import read_key
    from c2_lifecycle_client import LifecycleClient
    p=argparse.ArgumentParser();p.add_argument('learning_root');p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=8766);p.add_argument('--max-calls',type=int,default=4)
    p.add_argument('--current-runtime-profile',action='store_true',help='Versioned metadata contract; requires exact verified Probe107/Room6 and local catalog')
    a=p.parse_args();key=read_key()
    settings=ET.fromstring(adb(a.host,'shell','run-as','edu.sydney.probe','cat','shared_prefs/language_connection.xml'))
    pairing=next(x.text for x in settings if x.attrib.get('name')=='pairing')
    if not re.fullmatch('[a-f0-9]{48}',pairing or ''):raise ValueError('PAIRING_REQUIRED')
    lifecycle=LifecycleClient(a.learning_root,a.host)
    service=LearningService(a.learning_root,max_calls=a.max_calls,config=ModelConfig('gpt-6-sol',key,'2.00','10.00','Existing approved C1 configuration; conservative budget reservation not invoice'),public_context=lifecycle.public_context,runtime_profile_enabled=a.current_runtime_profile,identity_context=lifecycle.identity_context if a.current_runtime_profile else None)
    service.candidates=lifecycle
    server=LearningServer(('127.0.0.1',a.port),pairing,service)
    print('Paired C2 learning endpoint; candidates only, no implicit publication',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
