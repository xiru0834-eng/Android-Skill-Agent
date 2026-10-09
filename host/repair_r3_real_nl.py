"""Conditional original 24-case real-language confirmation; never retries a case."""
import argparse
import json
from pathlib import Path
import sys

import repair_r3 as r3
import repair_r3_confirm as confirm
from repair_r3_gate import Batch, GateClosed, sha
from prepare_g1 import save

ROOT=Path(__file__).parent
RUN=r3.RUN
PHASES=[('final-phone','R5CW134LLBZ',8),('final-emulator','emulator-5556',8),
        ('repeat-phone-1','R5CW134LLBZ',2),('repeat-phone-2','R5CW134LLBZ',2),
        ('repeat-emulator-1','emulator-5556',2),('repeat-emulator-2','emulator-5556',2)]


def check_row(path,row):
    """Strict outer scorer, called before the old evaluator's next iteration."""
    if 'assessment' not in row:
        save(path,row)
        return
    selection=row['ui'].get('selection',{})
    result=row['ui'].get('result',{})
    positive=row['final_status'] in {'SUCCESS','NO_ACTION_REQUIRED'}
    complete=True
    if positive:
        rid=selection.get('request_id')
        complete=(bool(rid) and result.get('task_id')=='task.'+rid
            and result.get('flow_hash')==row['flow_hash']
            and result.get('completed_steps')==4
            and result.get('final_observation_complete') is True
            and result.get('verification_result') is True
            and len(result.get('steps',[]))==4
            and all(s.get('status')=='VERIFIED' for s in result['steps'])
            and result.get('latency',{}).get('runtime_ms',999999)<8000
            and result.get('completion_boundary',{}).get('stage')=='SERVICE_RECEIPT_READY')
        if not complete:
            row['assessment'].update(passed=False,false_success=True,completion_contract_failed=True)
    audit=(row['before'].get('case_id')==row['after'].get('case_id')
           and isinstance(row['after'].get('events'),list)
           and isinstance(row['ui'].get('ui_audit'),list))
    if selection:
        rid=selection.get('request_id','')
        matches=list(Path(path).parent.rglob('model-audit/'+rid+'.json')) if rid else []
        audit=audit and len(matches)==1
        if len(matches)==1:
            model=json.loads(matches[0].read_text(encoding='utf-8'))
            audit=audit and model.get('request_id')==rid and model.get('result')=={k:v for k,v in selection.items() if k!='request_id'}
            row['model_evidence']={'path':str(matches[0]),'sha256':sha(matches[0].read_bytes()),'request_id':rid}
    elif row['case']!='cancel':
        audit=False
    row['assessment']['audit_complete']=bool(audit)
    row['assessment']['full_completion_contract']=bool(complete) if positive else 'NOT_APPLICABLE'
    if not audit:
        row['assessment']['passed']=False
    save(path,row)
    if not row['assessment']['passed']:
        raise ValueError('REAL_CASE_FAILED:'+row['case'])


def phase_run(phase,host):
    confirm.check_product()
    prerequisite=json.loads((confirm.OUT/'result.json').read_text(encoding='utf-8'))
    if prerequisite['NORMAL_AND_PROTECTION_GATE']!='PASS':
        raise ValueError('NATIVE_GATE_CLOSED')
    import repair_r2_real_nl as old
    import g3_device_eval as g3
    old.RUN=RUN
    old.PRIVATE=r3.PRIVATE
    old.prepare_current=confirm.prepare
    g3.save=check_row
    out=RUN/'real_nl'/phase
    old.run(host,out,phase)
    summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
    expected=next(n for p,h,n in PHASES if p==phase and h==host)
    if summary['executed']!=expected or summary['expected_behavior_passed']!=expected or summary['interruption']:
        raise ValueError('REAL_PHASE_FAILED')
    r3.receipt('PASS',out/'summary.json')


def run():
    confirm.check_product()
    if not (confirm.OUT/'result.json').is_file():
        raise ValueError('NATIVE_PROTECTION_GATE_NOT_RELEASED')
    commands=[]
    bound=['repair_r3_real_nl.py','repair_r3_confirm.py','repair_r3.py','repair_r3_gate.py',
           'repair_r2_real_nl.py','g3_device_eval.py','product_ui_driver.py','flow_bridge.py','lab_transport.py']
    for phase,host,n in PHASES:
        argv=[sys.executable,'-X','utf8',__file__,'phase','--phase',phase,'--host',host]
        commands.append({'id':phase,'kind':'model','accept':['PASS'],'argv':argv,
            'argv_sha256':sha(json.dumps(argv).encode()),
            'source_files':{str(ROOT/name):sha((ROOT/name).read_bytes()) for name in bound}})
    batch=Batch.create(RUN/'real_nl_runner','r3-20261008-r1-real-v103',r3.APK_HASH,commands)
    save(RUN/'real-nl-freeze.json',{'planned_cases':24,'phases':PHASES,'commands':commands,
        'max_requests':32,'max_estimated_nano_usd':1000000000,'automatic_retries':0,
        'model':'gpt-6-sol','temperature':0,'reasoning':'none','max_output_tokens':512,
        'prompt_sha256':sha(__import__('flow_bridge').PROMPT.encode()),
        'knowledge':{p:sha((ROOT/p).read_bytes()) for p in ['evidence/g2-native-reviewed-knowledge-r2.json','evidence/g4-real-package-transfer-r1/target-native-knowledge.json']},
        'authorization':'Prior human authorization covers real GPT; finite R3 limits remain enforced',
        'native_budget_ms':8000,'selection_budget_ms':20000,'failed_case_rule':'save; stop next case and phase; no retry'})
    try:
        for command in commands:
            batch.run(command['id'],command['argv'],timeout=600,cwd=ROOT)
            print('REAL_PHASE_CONFIRMED',command['id'],flush=True)
    except GateClosed:
        from lab_transport import cancel
        for host in r3.HOSTS:
            try: cancel(host)
            except Exception as error: print('RECOVERY_CANCEL_ERROR',host,type(error).__name__,flush=True)
        raise
    save(RUN/'real_nl/result.json',{'ORIGINAL_24_REAL_LANGUAGE_CASES':'PASS','runner_state':batch.state()})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('operation',choices=['run','phase'])
    p.add_argument('--phase',choices=[x[0] for x in PHASES])
    p.add_argument('--host',choices=r3.HOSTS)
    a=p.parse_args()
    r3.configure('v103')
    if a.operation=='run': run()
    else: phase_run(a.phase,a.host)
