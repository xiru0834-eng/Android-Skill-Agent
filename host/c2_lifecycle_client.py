"""Fixed pure-compiler worker boundary; gateway and P1 own distinct compiler modules."""
import json,subprocess,sys
from pathlib import Path
class LifecycleClient:
    def __init__(self,root,host):self.root=Path(root);self.host=host
    def call(self,operation,id,payload):
        data=json.dumps({'operation':operation,'candidate_id':id,'payload':payload},ensure_ascii=False).encode()
        if len(data)>1048576:raise ValueError('INPUT_LIMIT')
        worker=Path(__file__).with_name('c2_lifecycle_cli.py')
        r=subprocess.run([sys.executable,str(worker),str(self.root),'--host',self.host],input=data,capture_output=True,timeout=12,cwd=worker.parent)
        if len(r.stdout)>1048576:raise ValueError('OUTPUT_LIMIT')
        if r.returncode:
            try:code=json.loads(r.stdout)['error']
            except (ValueError,KeyError):code='LIFECYCLE_UNAVAILABLE'
            raise ValueError(code)
        return json.loads(r.stdout)
    def prepare(self,id,inputs):return self.call('prepare_validation',id,{'inputs':inputs})
    def finish(self,id,attempt):return self.call('finish_validation',id,{'attempt_id':attempt})
    def cancel(self,id,attempt):return self.call('cancel_validation',id,{'attempt_id':attempt})
    def inspect(self,id):return self.call('validation_status',id,{})
    def publish(self,id,*,confirmed):return self.call('publish',id,{'confirmed':confirmed})
    def published(self,id):return self.call('published',id,{})
    def details(self,id):return self.call('candidate_details',id,{})
    def public_context(self):return self.call('public_context','0'*32,{})
    def identity_context(self):return self.call('identity_context','0'*32,{})
    def current_published(self):return self.call('current_published','0'*32,{})
