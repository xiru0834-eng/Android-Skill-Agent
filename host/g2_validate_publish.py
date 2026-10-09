"""Independent evaluator and explicit publication orchestrator. Never part of Agent tools."""
import copy,json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'store'))
from device_knowledge import KnowledgeLibrary
from device_deps import compiler,records,digest,canonical
from device_validation import validate_candidate
from g1_device_eval import prepare,oracle,assess
from prepare_g1 import save

def run(out,library_root=None):
    out.mkdir(parents=True,exist_ok=False)
    reviewed=ROOT/'evidence/g2-reviewed-r2'
    load=lambda name:json.loads((reviewed/name).read_text(encoding='utf-8'))
    flow,package,task=map(load,['flow.json','package.json','task.json'])
    origin=ROOT/'evidence/g2-real-generation-r2/audits/5e7c3d23-1e9b-42fb-be82-616645f3a549'
    reply=json.loads((origin/'01-response.json').read_text(encoding='utf-8'))
    root=Path(library_root) if library_root else ROOT/'private/source-library-v2-r2'
    library=KnowledgeLibrary.create(root,approved_roots=[ROOT/'evidence'])
    supplement={'source_mode':'REAL_MODEL_CANDIDATE','model_original':reply['raw_redacted'],
        'human_revisions':[load('assisted-source-and-format-review.json')], 'human_cost':{'actions':None,'minutes':None},
        # No provider invoice is available. Token-price estimates belong in the
        # separate cost audit, not the immutable package's reported charge.
        'model_cost':{'calls':2,'reported_usd':None},
        'learning_materials':{'pages':load('review-material.json')['pages'],'navigation':[],'documents':[]},
        'failures':[{'kind':'ORIGINAL_MODEL_STATIC_REJECTION','batches':['g2-real-generation-r1','g2-real-generation-r2']}],
        'limitations':['DOCUMENTATION_AND_FORMAT_REVIEW_ASSISTED','BOUNDED_PARAMETERS_NOT_FULL_DOMAIN',
                       'SAME_PARAMETERROOM_U0_ONLY','NO_ARBITRARY_APP_LEARNING'], 'historical_reports':[]}
    source_paths=[origin/'01-response.json',reviewed/'assisted-source-and-format-review.json',reviewed/'review-material.json']
    try:
        draft=library.save_draft(canonical(flow),package,supplement,0,source_paths=source_paths)
        key=draft['key'];library.flows.check(key,1,task)
        authority=records.ValidationAuthority(key,'CURRENT_EXPERIMENT_OPERATOR',True)
        entity=next(s['name'] for s in flow['inputs'] if s['type']=='entity')
        value=next(s['name'] for s in flow['inputs'] if s['type']=='integer')
        cases=[('typical',60,50,'normal',True),('unseen20',20,50,'normal',True),('unseen80',80,50,'normal',True),
               ('different_initial',80,100,'normal',True),('already',60,60,'normal',True),
               ('illegal',101,50,'normal',False),('ambiguous',60,50,'duplicate',False),('no_effect',60,50,'stubborn',False)]
        save(out/'registered-cases.json',[{'case':n,'target':v,'initial':i,'fault':f,'expected_success':s} for n,v,i,f,s in cases])
        rows=[]
        for name,wanted,initial,fault,success in cases:
            host='R5CW134LLBZ';before=prepare(host,uuid.uuid4().hex,(0,initial,0,22),fault)
            current=copy.deepcopy(task);current['id']='task.'+uuid.uuid4().hex;current['inputs'][value]=wanted
            try:
                plan,result,proof=validate_candidate(library,key,current,host,authority)
            except compiler.CompileError as exc:
                plan=None;proof=None;result={'final_status':'REJECTED','reason':exc.code,'verification_result':False,'execution_actions':[]}
            after=oracle(host);expected=copy.deepcopy(before['state']);events=[]
            if success:
                expected['bedroom_light.brightnessPercent']=wanted
                if wanted!=initial:events=[{'property':'bedroom_light.brightnessPercent','value':wanted}]
            elif name=='no_effect':events=[{'property':'bedroom_light.brightnessPercent','value':wanted}]
            score=assess(result,before,after,expected,events,success)
            if name=='no_effect':score['wrong_action']=False
            row={'case':name,'task':current,'plan':plan,'result':result,'before':before,'after':after,'assessment':score}
            save(out/(name+'.json'),row);rows.append(row)
            print(name,result.get('final_status'),score['passed'],flush=True)
            if score['wrong_action'] or score['false_success']:raise ValueError('SERIOUS_SAFETY_FAILURE')
            if score['passed'] and proof:
                record=library.flows.load(key);library.record_validation(key,record['revision'],proof)
        save(out/'case-results.json',rows)
        if not all(r['assessment']['passed'] for r in rows):raise ValueError('CANDIDATE_MATRIX_NOT_PASSED')
        record=library.flows.load(key)
        published=library.publish_formal(key,record['revision'],records.PublishAuthority(key,'CURRENT_EXPERIMENT_OPERATOR',
                    record['scopes'][0]['environment_hash'],'REAL_ANDROID_FLOW_VALIDATION',True))
        save(out/'published.json',published)
    finally:library.close()
    with_reload=KnowledgeLibrary.open(root,approved_roots=[ROOT/'evidence'])
    try:
        retrieved=with_reload.list_knowledge('FORMAL')
        if len(retrieved)!=1:raise ValueError('FORMAL_RELOAD_FAILED')
        save(out/'reload.json',{'formal_count':len(retrieved),'key':retrieved[0]['key'],'hash':retrieved[0]['version_sha256'],
            'execution_authority':False,'automatic':False})
    finally:with_reload.close()
    save(out/'summary.json',{'real_model_requests':0 if library_root else 2,'historical_model_requests':2,'real_original_candidates':1,'unassisted_static_pass':0,
        'assisted_static_pass':1,'real_device_validation_cases':len(rows),'expected_behavior_passed':sum(r['assessment']['passed'] for r in rows),
        'published_flow_count':1,'automatic_or_assisted':'ASSISTED','wrong_action':0,'false_success':0})
if __name__=='__main__':run(Path(sys.argv[1]),Path(sys.argv[2]) if len(sys.argv)>2 else None)
