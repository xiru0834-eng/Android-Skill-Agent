"""Normal learning entry: P2 material -> real P3 generator -> candidate inbox.
No Android transport, oracle, publication, or execution tools are imported.
"""
import copy,json,threading,time,sys
from pathlib import Path
from c2_material import from_recording,normalize_read_dependencies,canonical
from c2_inbox import DraftInbox,valid_id
from learning_request import build_request
from draft_generator import DraftGenerator,Budget,check_draft
from model_api import UploadGrant,ModelFailure
sys.path.insert(0,str(Path(__file__).resolve().parent/'runtime-dependencies/p3-2-flow-abstraction'))
from abstraction import analyze

class LearningService:
    def __init__(self,root,*,max_calls=4,config=None,test_mode=False,model=None,public_context=None,runtime_profile_enabled=False,identity_context=None):
        if type(runtime_profile_enabled) is not bool:raise ValueError('RUNTIME_PROFILE_FLAG')
        if runtime_profile_enabled and not callable(public_context):raise ValueError('CURRENT_RUNTIME_PROVIDER_REQUIRED')
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.inbox=DraftInbox(self.root/'candidates.sqlite');self.max_calls=max_calls
        self.config=config;self.test_mode=test_mode;self.model=model;self.active={};self.lock=threading.Lock()
        self.candidates=None  # connected only to the existing trusted lifecycle adapter at deployment
        self.public_context=public_context
        self.runtime_profile_enabled=runtime_profile_enabled
        self.identity_context=identity_context
    def cancel(self,id):
        valid_id(id)
        with self.lock:
            if id in self.active:self.active[id].cancel()
            return self.inbox.cancel(id)
    def generate(self,id,payload):
        deadline=time.monotonic()+120
        valid_id(id)
        if type(payload) is not dict or set(payload)!={'goal','environment','observations','legacy_trace','document','events','upload_confirmed'} or payload['upload_confirmed'] is not True:
            raise ValueError('LEARNING_FIELDS_OR_UPLOAD_PERMISSION')
        identity_snapshot=None
        if self.identity_context is not None and any('identity_association' in o for o in payload['observations']):
            from c2_identity import capture_identity
            identity_snapshot=capture_identity(self.identity_context(),payload['observations'])
        bundle=from_recording(payload['observations'],payload['legacy_trace'],payload['document'],payload['environment'],payload['events'],identity_snapshot=identity_snapshot)
        runtime_snapshot=None
        if self.public_context is not None:
            from c2_material import append_current_context
            context=self.public_context()
            bundle=append_current_context(bundle,context)
            if self.runtime_profile_enabled:
                from c2_runtime_request import capture_snapshot
                runtime_snapshot=capture_snapshot(context,identity_snapshot=identity_snapshot)
        if runtime_snapshot is None:request=build_request(payload['goal'],[bundle])
        else:
            from c2_runtime_request import build_request as current_request
            request=current_request(payload['goal'],[bundle],runtime_snapshot=runtime_snapshot)
        # Reserve the whole finite learning attempt before sending anything, never refunded by restart/cancel.
        with self.lock:
            if self.active:raise ValueError('LEARNING_BUSY')
            self.inbox.begin(id,{'bundle':bundle,'request':request})
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:raise ValueError('LEARNING_DEADLINE')
            generator=DraftGenerator(self.root/'audits',Budget(max_calls=2,max_corrections=1,total_ms=remaining,max_output_tokens=8192,max_cost_usd='10.00'),test_mode=self.test_mode)
            self.active[id]=generator
        try:
            self.inbox.reserve(2,limit=self.max_calls)
            result=generator.run(request,config=self.config,model=self.model,grant=UploadGrant(request['input_digest'],request['environment']))
            if runtime_snapshot is not None:
                from c2_runtime_request import recheck_provider
                recheck_provider(runtime_snapshot,self.public_context())
            if identity_snapshot is not None:
                from c2_identity import recheck_identity
                recheck_identity(identity_snapshot,self.identity_context())
            normalized=None;draft=None;original_status=result.get('status');candidates=[];selection=[]
            if result.get('status')=='KNOWLEDGE_GAP' and result.get('candidate_flow') is None:
                with self.lock:
                    if generator.cancelled.is_set():raise ValueError('CANCELLED_OR_STALE')
                    if time.monotonic()>=deadline:raise ValueError('LEARNING_DEADLINE')
                    return self.inbox.needs_material(id,result)
            if result.get('candidate_flow') is not None:
                draft={k:copy.deepcopy(result[k]) for k in ('candidate_flow','parameter_basis','step_basis','uncertainties','unsupported_capabilities','questions')}
                draft['status']='PROPOSED'
                candidates.append((result['calls'],draft))
            elif result.get('status')=='DRAFT_FORMAT_ERROR' and result.get('audit_directory'):
                # A later format correction can itself regress. Retain every raw
                # attempt and select the FIRST one that passes the same bounded
                # normalization + ALL original checks; never blend two proposals.
                replies=sorted(Path(result['audit_directory']).glob('*-response.json'))
                for number,path in enumerate(replies,1):
                    original=json.loads(path.read_text(encoding='utf-8'))
                    if original.get('finish_reason')=='stop' and not original.get('refusal') and not original.get('redaction_applied'):
                        try:candidates.append((number,json.loads(original['raw_redacted'])))
                        except (ValueError,TypeError):selection.append({'attempt':number,'status':'JSON_INVALID'})
            for number,draft in candidates:
                try:
                    normalized=normalize_read_dependencies(draft['candidate_flow'],allowed={v['name'] for v in request['allowed_capabilities']['definitions']})
                    revised=copy.deepcopy(draft);revised['candidate_flow']=normalized['flow']
                    checked,checks=check_draft(canonical(revised),request)
                    if runtime_snapshot is None:content=analyze(request,canonical(revised),[bundle],input_channel=result['evidence_channel'])
                    else:
                        from c2_runtime_abstraction import analyze as current_analyze
                        content=current_analyze(request,canonical(revised),[bundle],input_channel=result['evidence_channel'],runtime_snapshot=runtime_snapshot,original_goal=payload['goal'])
                    if content['status'] not in {'ANALYZED_DRAFT','ANALYZED_DRAFT_WITH_UNKNOWNS','UNSUPPORTED_BRANCH','REQUIRES_CONDITION_REVIEW'}:
                        raise ValueError('CONTENT_ANALYSIS_REJECTED')
                except (ValueError,TypeError,KeyError) as error:
                    selection.append({'attempt':number,'status':getattr(error,'code',type(error).__name__)})
                    continue
                selection.append({'attempt':number,'status':'SELECTED_CHECKED_DRAFT_NOT_DEVICE_VALIDATED'})
                result.update(checked);result['status']='CHECKED_DRAFT_NOT_DEVICE_VALIDATED'
                result['checks_after_program_normalization']=checks;result['program_normalization']=normalized
                result['content_analysis']=content;result['selected_raw_attempt']=number
                result['candidate_selection']=selection;result['generator_original_status']=original_status
                result['execution_authority']=False;result['ready_for_device_execution']=False
                # Independent artifact BEFORE promotion to a named inbox candidate.
                with (Path(result['audit_directory'])/'c2-normalization.json').open('x',encoding='utf-8') as f:json.dump({'original_envelope':draft,'result':result},f,ensure_ascii=False,indent=2)
                with self.lock:
                    if generator.cancelled.is_set():raise ValueError('CANCELLED_OR_STALE')
                    if time.monotonic()>=deadline:raise ValueError('LEARNING_DEADLINE')
                    return self.inbox.complete(id,result)
            raise ValueError(result.get('status','NO_CANDIDATE'))
        except Exception as error:
            self.inbox.fail(id,str(getattr(error,'code',str(error)))[:128]);raise
        finally:
            with self.lock:self.active.pop(id,None)
