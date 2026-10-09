"""Additive normal published-use bridge. Same P4 selection/compiler/policy.
Publication is checked in the existing Store, never granted by imported JSON.
"""
import argparse,copy,json,os,re,xml.etree.ElementTree as ET
from flow_bridge import FlowServer,FlowHandler
from c2_lifecycle_client import LifecycleClient

class C2FlowHandler(FlowHandler):
    def do_POST(self):
        if self.path=='/v3/flow-tasks':
            # Authentication is checked BEFORE the read-only host refresh.
            import hmac
            headers=self.headers.get_all('Authorization',[])
            if len(headers)!=1 or not hmac.compare_digest(headers[0].encode(),('Bearer '+self.server.token).encode()):
                return self.reply(401,{'error':'PAIRING_REQUIRED'})
            try:self.server.refresh_source()
            except Exception:return self.reply(409,{'error':'CURRENT_FORMAL_SOURCE_REQUIRED'})
        return super().do_POST()

class C2FlowServer(FlowServer):
    def __init__(self,address,token,root,audit,host,**kw):
        self.lifecycle=LifecycleClient(root,host)
        # Start before the first publication; an empty catalog is NOT usable knowledge.
        super().__init__(address,token,{},audit,'host.'+host.lower(),**kw)
        self.RequestHandlerClass=C2FlowHandler
    def refresh_source(self):
        # The original handler holds this same lock throughout selection/compile.
        # Never replace its pinned source while an existing request is running.
        if not self.lock.acquire(False):raise ValueError('REMOTE_BUSY')
        try:
            current=self.lifecycle.current_published()
            with self.state_lock:self.knowledge=copy.deepcopy(current)
        finally:self.lock.release()
    def verify_source(self):
        if self.lifecycle.current_published()!=self.knowledge:raise ValueError('CURRENT_FORMAL_SOURCE_CHANGED')

if __name__=='__main__':
    from lab_transport import adb
    from win_credentials import read_key
    p=argparse.ArgumentParser();p.add_argument('learning_root');p.add_argument('audit');p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=8765);p.add_argument('--max-calls',type=int,default=8)
    a=p.parse_args()
    settings=ET.fromstring(adb(a.host,'shell','run-as','edu.sydney.probe','cat','shared_prefs/language_connection.xml'))
    token=next((x.text for x in settings if x.attrib.get('name')=='pairing'),None)
    if not re.fullmatch('[a-f0-9]{48}',token or ''):raise ValueError('PAIRING_REQUIRED')
    os.environ['OPENAI_API_KEY']=read_key()
    server=C2FlowServer(('127.0.0.1',a.port),token,a.learning_root,a.audit,a.host,max_calls=a.max_calls)
    print('C2 published Flow normal-use bridge ready; no implicit execution',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
