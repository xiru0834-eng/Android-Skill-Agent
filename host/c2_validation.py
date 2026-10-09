"""C2 product adapter over the EXISTING checked/validated/published lifecycle.
No model/oracle/Android input tools. A configured host-only reader obtains native
receipts; HTTP clients cannot submit receipt bodies or durable authority.
"""
import copy,hashlib,json,sqlite3,sys,threading,time,uuid
from contextlib import contextmanager
from pathlib import Path
from c2_material import canonical,digest
from c2_inbox import valid_id
sys.path.insert(0,str(Path(__file__).parent/'store'))
from device_knowledge import KnowledgeLibrary
from device_deps import compiler,records

def need(ok,code):
    if not ok:raise ValueError(code)

def checked_receipt(r,plan,candidate_id,attempt_id):
    need(type(r) is dict,'NATIVE_EVIDENCE_MISMATCH')
    raw=r.get('native_plan_raw');need(type(raw) is str and len(raw.encode())<=131072,'NATIVE_PLAN_MISSING')
    need(canonical(json.loads(raw))==canonical(plan),'NATIVE_PLAN_MISMATCH')
    expected={'request_id':attempt_id,'candidate_id':candidate_id,'plan_raw_hash':digest(plan),
        'flow_plan_hash':hashlib.sha256(raw.encode()).hexdigest(),'task_id':plan['task_id'],'host_device_id':plan['host_device_id'],
        'transport_channel':'NORMAL_USER_CANDIDATE_UI','channel':'ANDROID_NATIVE','mode':'CANDIDATE_VALIDATION',
        'service_entry_hit':True,'flow_hash':plan['flow_hash'],'package_hash':plan['source_package_raw_hash'],
        'verification_result':True,'completed_steps':len(plan['steps']),'final_observation_complete':True}
    need(all(type(r.get(k)) is type(v) and r[k]==v for k,v in expected.items()),'NATIVE_EVIDENCE_MISMATCH')
    need(r.get('final_status') in {'SUCCESS','NO_ACTION_REQUIRED'} and type(r.get('process_session')) is str and 0<len(r['process_session'])<=128,'NATIVE_EVIDENCE_MISMATCH')
    start,end=r.get('initial_state'),r.get('final_observed_state')
    need(type(start) is dict and type(end) is dict and set(start)==set(end)==set(plan['readable_properties']),'FINAL_STATE_INCOMPLETE')
    for key in plan['preserve_unmentioned']+plan['must_preserve']:
        need(type(start[key]) is type(end[key]) and start[key]==end[key],'FORBIDDEN_SIDE_EFFECT')
    steps=r.get('steps');need(type(steps) is list and len(steps)==len(plan['steps']),'NATIVE_STEPS_INCOMPLETE')
    phases=['ENTRY']
    for spec in plan['steps']:
        phases.append(spec['id'])
        if spec['op']=='CALL':phases.append('AFTER.'+spec['id'])
    phases.append('FINAL');observations=r.get('observations')
    need(type(observations) is list and [o.get('phase') for o in observations]==phases,'NATIVE_OBSERVATION_SEQUENCE')
    session=observations[0].get('observation_session_id');need(type(session) is str and bool(session),'NATIVE_OBSERVATION_SESSION')
    last_time=-1
    for i,o in enumerate(observations,1):
        need(o.get('sequence')==i and o.get('observation_session_id')==session
             and o.get('kind')=='semantic_state_read_v1' and o.get('channel')=='ANDROID_NATIVE'
             and o.get('task_id')==plan['task_id'] and o.get('host_device_id')==plan['host_device_id']
             and o.get('environment_hash')==plan['environment_hash'],'NATIVE_OBSERVATION_IDENTITY')
        now=o.get('captured_elapsed_ms');need(type(now) is int and now>=last_time,'NATIVE_OBSERVATION_CLOCK');last_time=now
        need(type(o.get('values')) is dict and set(o['values'])<=set(start),'NATIVE_OBSERVATION_FIELDS')
    by_phase={o['phase']:o for o in observations}
    need(by_phase['ENTRY']['values']==start and by_phase['FINAL']['values']==end
         and by_phase['ENTRY'].get('complete') is True and by_phase['FINAL'].get('complete') is True,'FINAL_OBSERVATION_MISSING')
    reads={};calls=[];all_actions=[];expected_state=copy.deepcopy(start)
    def value(v,state):
        kind=v['kind']
        if kind=='literal':return v['value']
        if kind=='state':return state[v['key']]
        if kind=='initial':return start[v['key']]
        if kind=='read':return reads[v['step_id']]
        raise ValueError('NATIVE_VALUE_UNRESOLVED')
    def predicates(rows,state):
        for p in rows:
            if p['op']=='known':need(value(p['value'],state) is not None,'GOAL_NOT_VERIFIED')
            else:
                a,b=value(p['left'],state),value(p['right'],state)
                need(type(a) is type(b) and a==b,'GOAL_NOT_VERIFIED')
    predicates(plan['preconditions'],start)
    for spec,step in zip(plan['steps'],steps):
        need(step.get('id')==spec['id'] and step.get('op')==spec['op'] and step.get('status')=='VERIFIED','NATIVE_SEQUENCE_MISMATCH')
        state=by_phase[spec['id']]['values']
        need(all(type(v) is type(expected_state[k]) and v==expected_state[k] for k,v in state.items()),'FORBIDDEN_INTERMEDIATE_CHANGE')
        if spec['op']=='READ':
            need(spec['target_key'] in state,'NATIVE_READ_MISSING');reads[spec['id']]=state[spec['target_key']]
        elif spec['op']=='ASSERT':predicates([spec['predicate']],state)
        if spec['op']=='CALL':
            need(set(state)==set(start),'NATIVE_CALL_CONTEXT_INCOMPLETE')
            child=step.get('runtime_receipt',{})
            wanted=value(spec['value'],state)
            expected_call={'skill':spec['skill'],'args':{'device':spec['entity_id'],spec['argument']:wanted}}
            need(child.get('calls')==[expected_call] and child.get('verification_result') is True,'NATIVE_CALL_MISMATCH')
            need(child.get('final_status') in {'SUCCESS','NO_ACTION_REQUIRED'} and child.get('final_observation_complete') is True,'NATIVE_CHILD_INCOMPLETE')
            after=by_phase['AFTER.'+spec['id']]
            expected_state[spec['target_key']]=wanted
            need(after.get('complete') is True and canonical(after['values'])==canonical(expected_state)
                 and canonical(child.get('final_observed_state'))==canonical(expected_state),'GOAL_NOT_VERIFIED')
            need(type(child.get('execution_actions')) is list and len(child['execution_actions'])<=1,'NATIVE_ACTION_AUDIT_MISSING')
            for action in child['execution_actions']:
                need(action.get('property')==spec['target_key'] and type(action.get('value')) is type(wanted) and action['value']==wanted
                     and action.get('method')==('CLICK' if spec['skill']=='SetPower' else 'SET_PROGRESS')
                     and action.get('effect_verified') is True,'NATIVE_ACTION_MISMATCH')
                effect=action.get('effect_observed_state')
                if action.get('effect_observation_complete') is True:
                    need(canonical(effect)==canonical(expected_state),'NATIVE_ACTION_MISMATCH')
                else:
                    # Original native runtime emits a target-local effect read,
                    # followed by full child and AFTER snapshots (checked above).
                    # A local read is not relabelled complete or used as FINAL.
                    need(action.get('effect_observation_complete') is False and type(effect) is dict
                         and spec['target_key'] in effect and set(effect)<=set(expected_state)
                         and all(type(v) is type(expected_state[k]) and v==expected_state[k] for k,v in effect.items())
                         and action.get('accepted') is True and action.get('sdk_acknowledged') is True
                         and type(action.get('ms')) is int and type(action.get('effect_observation_ms')) is int
                         and action['ms']<=action['effect_observation_ms']<=after['captured_elapsed_ms'],
                         'NATIVE_ACTION_MISMATCH')
            all_actions+=child['execution_actions']
            if child['execution_actions']:calls.append(expected_call)
    need(canonical(end)==canonical(expected_state),'GOAL_NOT_VERIFIED');predicates(plan['goals'],end)
    need(r.get('execution_actions')==all_actions,'NATIVE_ACTION_AUDIT_MISSING')
    scope=r.get('event_scope_after',{})
    need(scope.get('sdk_available') is True and scope.get('active') is False and scope.get('original_filter_restored') is True,'NATIVE_SCOPE_NOT_RESTORED')
    boundary=r.get('completion_boundary',{})
    need(boundary.get('stage')=='SERVICE_RECEIPT_READY' and boundary.get('final_status')==r['final_status']
         and type(boundary.get('finished_ms')) is int and type(boundary.get('deadline_ms')) is int
         and last_time<=boundary['finished_ms']<=boundary['deadline_ms'],'NATIVE_COMPLETION_BOUNDARY')
    return calls

class CandidateService:
    def __init__(self,root,inbox,host_device_id,package,*,receipt_reader=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.inbox=inbox;self.host=host_device_id;self.package=copy.deepcopy(package)
        self.reader=receipt_reader;self.lock=threading.RLock()
        compiler.old.validate_document(self.package) if hasattr(compiler,'old') else None
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS links(id TEXT PRIMARY KEY,key TEXT NOT NULL,flow_hash TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,candidate TEXT NOT NULL,state TEXT NOT NULL,body TEXT NOT NULL,digest TEXT NOT NULL)')
        if not (self.root/'knowledge'/KnowledgeLibrary.FILENAME).exists():
            lib=KnowledgeLibrary.create(self.root/'knowledge',approved_roots=[self.root]);lib.close()
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.root/'lifecycle.sqlite',timeout=2)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        finally:db.close()
    @contextmanager
    def library(self):
        lib=KnowledgeLibrary.open(self.root/'knowledge',approved_roots=[self.root])
        try:yield lib
        finally:lib.close()
    def _link(self,id):
        with self.db() as db:row=db.execute('SELECT key,flow_hash FROM links WHERE id=?',(valid_id(id),)).fetchone()
        need(row is not None,'NOT_CHECKED');return row
    def _attempt(self,db,id,attempt):
        row=db.execute('SELECT candidate,state,body,digest FROM attempts WHERE id=?',(valid_id(attempt),)).fetchone()
        need(row is not None and row[0]==valid_id(id),'ATTEMPT_MISMATCH')
        body=json.loads(row[2]);need(digest(body)==row[3],'ATTEMPT_CORRUPT');return row[1],body
    def _expire_pending(self,db):
        now=time.time()
        for attempt,raw,sha in db.execute("SELECT id,body,digest FROM attempts WHERE state='PREPARED'").fetchall():
            body=json.loads(raw);need(digest(body)==sha,'ATTEMPT_CORRUPT')
            if not body['created_unix']<=now<=body['expires_unix']:
                db.execute("UPDATE attempts SET state='EXPIRED' WHERE id=?",(attempt,))
    def prepare(self,id,inputs):
        with self.lock:
            draft=self.inbox.inspect(id);need(draft['state']=='DRAFT','NOT_A_DRAFT')
            generation=draft['body']['generation']
            need(generation.get('evidence_channel')=='REAL_OPENAI_API','REAL_MODEL_ORIGIN_REQUIRED')
            flow=generation['candidate_flow'];package=copy.deepcopy(self.package)
            package['flow_refs']=[{'id':flow['id'],'version':flow['version']}]
            existing={row['id'] for row in package['evidence']}
            package['evidence'] += [{'id':ref,'kind':'AUDIT_REFERENCE','ref':'material:'+ref,
                'description':'Learning evidence reference, not execution authority'} for ref in flow['evidence_refs'] if ref not in existing]
            attempt=uuid.uuid4().hex
            task={'kind':'Task','schema_version':'1.0','id':'task.'+attempt,
                'flow_ref':package['flow_refs'][0],'package_ref':{'id':package['id'],'version':package['version']},
                'inputs':copy.deepcopy(inputs),'host_device_id':self.host,
                'authorization_ref':'local.user.candidate.confirmation.required',
                'budget':{'duration_ms':8000,'max_actions':32,'max_model_calls':0},'cancellation_token_ref':'cancel.'+attempt}
            plan=compiler.compile_flow(flow,package,task,None).to_dict()
            need(plan['status']=='COMPILED' and plan['blocking_unknowns']==[],'EXECUTION_UNKNOWN_BLOCKED')
            with self.db() as db:
                self._expire_pending(db)
                need(db.execute("SELECT 1 FROM attempts WHERE state='PREPARED'").fetchone() is None,'VALIDATION_PENDING')
                link=db.execute('SELECT key,flow_hash FROM links WHERE id=?',(id,)).fetchone()
            with self.library() as lib:
                if link is None:
                    origin=self.root/('source-'+id+'.json')
                    with origin.open('x',encoding='utf-8') as f:json.dump(draft,f,ensure_ascii=False,indent=2)
                    supplement={'source_mode':'REAL_MODEL_CANDIDATE','model_original':canonical(flow),
                        'human_revisions':[],'human_cost':{'actions':None,'minutes':None},
                        'model_cost':{'calls':generation.get('calls'),'reported_usd':None},
                        'learning_materials':{'pages':[],'navigation':[],'documents':[{'ref':origin.name}]},
                        'failures':[],'limitations':['ASSISTED_LEARNING','POINT_VALIDATION_NOT_WHOLE_DOMAIN'], 'historical_reports':[]}
                    head=[r for r in lib.flows.list_versions() if r['flow']['id']==flow['id']]
                    expected=len(head)  # head revision counts versions, not per-version lifecycle transitions
                    row=lib.save_draft(canonical(flow),package,supplement,expected,source_paths=[origin])
                    lib.flows.check(row['key'],row['flow_revision'],task)
                    with self.db() as db:db.execute('INSERT INTO links VALUES(?,?,?)',(id,row['key'],digest(flow)))
                    link=(row['key'],digest(flow))
                need(link[1]==digest(flow),'CANDIDATE_CHANGED')
                row=lib.inspect(link[0]);need(row['flow_state'] in {'CHECKED','VALIDATED_SCOPE'},'NOT_CHECKED')
                need(row['package']==package and row['integrity']=='PASS','CANDIDATE_DEPENDENCY_CHANGED')
            body={'candidate_id':id,'attempt_id':attempt,'plan':plan,'task':task,'flow_key':link[0],
                'created_unix':time.time(),'expires_unix':time.time()+120,'flow_hash':digest(flow),
                'plan_raw_hash':digest(plan),'execution_authority':False}
            with self.db() as db:db.execute('INSERT INTO attempts VALUES(?,?,?,?,?)',(attempt,id,'PREPARED',canonical(body),digest(body)))
            return body
    def inspect(self,id):
        with self.lock:
            key,_=self._link(id)
            with self.library() as lib:row=lib.inspect(key)
            with self.db() as db:
                self._expire_pending(db)
                pending=db.execute("SELECT id FROM attempts WHERE candidate=? AND state='PREPARED'",(id,)).fetchone()
            return {'id':id,'flow_key':key,'state':row['flow_state'],'revision':row['flow_revision'],
                'actual_points':row['actual_points'],'formal_retrievable':row['formal_retrievable'],
                'pending_attempt':pending[0] if pending else None,'execution_authority':False}
    def details(self,id):
        draft=self.inbox.inspect(id);need(draft['state']=='DRAFT','NOT_A_DRAFT')
        flow=draft['body']['generation']['candidate_flow'];entities={}
        for spec in flow['inputs']:
            if spec['type']=='entity':entities[spec['name']]=[e['entity_id'] for e in self.package['entities'] if set(spec['required_capabilities'])<=set(e['capabilities'])]
        try:lifecycle=self.inspect(id)
        except ValueError as e:
            if str(e)!='NOT_CHECKED':raise
            lifecycle={'state':'DRAFT','pending_attempt':None,'execution_authority':False}
        return {'draft':draft,'entities':entities,'lifecycle':lifecycle,'execution_authority':False}
    def cancel(self,id,attempt):
        with self.lock,self.db() as db:
            state,body=self._attempt(db,id,attempt)
            if state=='PREPARED':db.execute("UPDATE attempts SET state='CANCELLED' WHERE id=?",(attempt,))
            return {'state':'CANCELLED' if state=='PREPARED' else state,'execution_authority':False}
    def finish(self,id,attempt):
        need(callable(self.reader),'TRUSTED_RECEIPT_READER_REQUIRED')
        with self.lock:
            with self.db() as db:state,body=self._attempt(db,id,attempt)
            need(state=='PREPARED','CANCELLED_OR_STALE')
            if not body['created_unix']<=time.time()<=body['expires_unix']:
                with self.db() as db:db.execute("UPDATE attempts SET state='EXPIRED' WHERE id=?",(attempt,))
                raise ValueError('VALIDATION_EXPIRED')
            result=self.reader(attempt)  # fixed paired host + fixed filename, not a client receipt/path
            evidence_path=self.root/('receipt-'+attempt+'.json')
            with evidence_path.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
            try:
                calls=checked_receipt(result,body['plan'],id,attempt)
                with self.library() as lib:
                    row=lib.flows.load(body['flow_key']);plan=body['plan']
                    proof=records._issue_evidence({'evidence_id':'execution.'+attempt,'channel':'REAL_ANDROID_FLOW_VALIDATION',
                        'version_sha256':row['sha256'],'flow_hash':plan['flow_hash'],'package_hash':plan['package_hash'],
                        'plan_hash':digest(plan),'registry_hash':plan['registry_hash'],'environment_hash':plan['environment_hash'],
                        'environment':plan['environment'],'source_package_raw_hash':plan['source_package_raw_hash'],
                        'host_device_id':plan['host_device_id'],'inputs':body['task']['inputs'],
                        'initial_state':result['initial_state'],'final_state':result['final_observed_state'],
                        'ordered_calls':calls,'sequence_verified':True,'verifier':'G1_CURRENT_PUBLIC_REOBSERVE_AFTER_EACH_CALL',
                        'read_only_target_satisfied':not calls,'parameter_domain_verified':False,'device_execution_verified':True,
                        'execution_authority':False,'native_request_id':attempt,'native_process_session':result['process_session']})
                    lib.record_validation(body['flow_key'],row['revision'],proof)
            except Exception:
                with self.db() as db:db.execute("UPDATE attempts SET state='FAILED' WHERE id=?",(attempt,))
                raise
            with self.db() as db:db.execute("UPDATE attempts SET state='RECORDED' WHERE id=?",(attempt,))
            return self.inspect(id)
    def publish(self,id,*,confirmed):
        need(confirmed is True,'PUBLICATION_AUTHORITY_REQUIRED')
        with self.lock:
            draft=self.inbox.inspect(id);need(draft['name'] is not None,'NAME_REQUIRED')
            key,sha=self._link(id);need(digest(draft['body']['generation']['candidate_flow'])==sha,'CANDIDATE_CHANGED')
            with self.db() as db:need(db.execute("SELECT 1 FROM attempts WHERE state='PREPARED'").fetchone() is None,'VALIDATION_PENDING')
            with self.library() as lib:
                row=lib.inspect(key)
                need(row['flow_state']=='VALIDATED_SCOPE' and row['eligible_points'],'REAL_FLOW_VERIFICATION_REQUIRED')
                authority=records.PublishAuthority(key,'LOCAL_PAIRED_USER_CONFIRMATION',row['eligible_points'][-1]['environment_hash'],'REAL_ANDROID_FLOW_VALIDATION',True)
                lib.publish_formal(key,row['flow_revision'],authority)
            return self.inspect(id)
    def published(self,id):
        from make_native_knowledge import build
        with self.lock:
            key,_=self._link(id)
            with self.library() as lib:
                row=lib.inspect(key);need(row['formal_retrievable'],'REAL_FLOW_VERIFICATION_REQUIRED')
                point=row['eligible_points'][-1]
                task={'kind':'Task','schema_version':'1.0','id':'task.c2_published_template',
                    'flow_ref':{'id':row['flow']['id'],'version':row['flow']['version']},
                    'package_ref':{'id':row['package']['id'],'version':row['package']['version']},
                    'inputs':point['inputs'],'host_device_id':self.host,
                    'authorization_ref':'local.user.confirmation.required',
                    'budget':{'duration_ms':8000,'max_actions':32,'max_model_calls':0},'cancellation_token_ref':'cancel.template'}
                envelope=build(row['flow'],row['package'],task,row)
                envelope['source_origin']='REAL_MODEL_ASSISTED_C2_WITH_AUDITED_PROGRAM_NORMALIZATION'
                envelope['display_name']=self.inbox.inspect(id)['name']
                return envelope
