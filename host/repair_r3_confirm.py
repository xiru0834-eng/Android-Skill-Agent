"""R3 frozen confirmation. Any failed normal entry closes all downstream gates."""
import argparse
import json
from pathlib import Path
import sys

import repair_r3 as r3
from repair_r3_gate import Batch, GateClosed, sha
from prepare_g1 import save

ROOT = Path(__file__).parent
RUN = r3.RUN
OUT = RUN / 'confirmation-r2'


def check_product():
    frozen = json.loads((RUN/'candidate-v103/freeze.json').read_text(encoding='utf-8'))
    for name, expected in frozen['source_files'].items():
        if name.replace('\\','/').startswith('native/') and sha((ROOT/name).read_bytes()) != expected:
            raise ValueError('FROZEN_PRODUCT_CHANGED:'+name)
    if sha(r3.APK.read_bytes()) != r3.APK_HASH:
        raise ValueError('FROZEN_APK_CHANGED')


def normal(host, scenario, rep):
    check_product()
    # Reuse the exact original evaluator, but never overwrite diagnostics.
    r3.RUN = OUT/'normal'
    r3.RUN.mkdir(parents=True,exist_ok=True)
    r3.case_one(host, scenario, rep)


def prepare(host, case, initial=(0,50,0,22), fault='normal', delay=0):
    import time
    from g1_device_eval import oracle
    from lab_transport import adb
    adb(host,'shell','am','start','-n','edu.sydney.parameterroom/.ParameterRoomActivity',
        '--es','initial',','.join(map(str,initial)),'--es','caseId',case,
        '--es','fault',fault,'--ei','commitDelayMs',str(delay))
    deadline = time.monotonic()+12
    while time.monotonic()<deadline:
        try:
            row=oracle(host)
        except json.JSONDecodeError:
            time.sleep(.05)
            continue
        if row['case_id']==case and row['initial']==list(initial) and not row['events']:
            return row
        time.sleep(.1)
    raise ValueError('INITIALIZATION_FAILED')


def protection(host, kind):
    check_product()
    from repair_r2_verify import guarded_assessment
    import g1_device_eval as g1
    import repair_cancel_eval as cancellation
    folder=OUT/'regression'/(kind+'-'+host)
    original_save = save

    def checked_save(path, row):
        # Save evidence first, then raise BEFORE the old loop can dispatch its
        # next case. Summary-only checking would be too late.
        original_save(path,row)
        if 'assessment' in row and not row['assessment']['passed']:
            raise ValueError('G1_CASE_FAILED:'+row['case'])
        if 'passed' in row and 'case' in row and not row['passed']:
            raise ValueError('CANCEL_CASE_FAILED:'+row['case'])

    if kind=='g1':
        g1.prepare=prepare
        g1.assess=guarded_assessment(g1.assess)
        g1.save=checked_save
        g1.run(host,folder)
        expected=11
    else:
        cancellation.prepare=prepare
        cancellation.save=checked_save
        cancellation.run(host,folder)
        expected=2
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    if not (summary['passed']==summary['executed']==summary['planned']==expected):
        raise ValueError('PROTECTION_INCOMPLETE')
    r3.receipt('PASS',folder/'summary.json')


def specs():
    commands=[]
    for host in r3.HOSTS:
        for scenario in ('E1','E2'):
            for rep in range(3):
                argv=[sys.executable,'-X','utf8',__file__,'normal','--host',host,
                      '--scenario',scenario,'--rep',str(rep)]
                commands.append({'id':f'{host}-{scenario}-{rep}','kind':'device','accept':['PASS'],'argv':argv})
    for kind in ('g1','cancel'):
        for host in r3.HOSTS:
            argv=[sys.executable,'-X','utf8',__file__,kind,'--host',host]
            commands.append({'id':kind+'-'+host,'kind':'device','accept':['PASS'],'argv':argv})
    bound=['repair_r3_confirm.py','repair_r3.py','repair_r3_gate.py','lab_transport.py',
           'g1_device_eval.py','repair_cancel_eval.py','repair_r2_verify.py']
    for command in commands:
        command['argv_sha256']=sha(json.dumps(command['argv']).encode())
        command['source_files']={str(ROOT/name):sha((ROOT/name).read_bytes()) for name in bound}
    return commands


def run():
    r3.gate_proved()
    check_product()
    diagnostic=json.loads((RUN/'reproduction-v103/summary.json').read_text(encoding='utf-8'))
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in (RUN/'reproduction-v103').glob('*-E[12]-*.json')]
    if diagnostic['performance_failed'] or len(rows)!=12 or not all(r['assessment']['passed'] for r in rows):
        raise ValueError('DIAGNOSTIC_GATE_CLOSED')
    commands=specs()
    batch=Batch.create(OUT/'runner','r3-20261008-r1-confirm-v103-eval2',r3.APK_HASH,commands)
    save(OUT/'freeze.json',{'apk_sha256':r3.APK_HASH,'commands':commands,'normal_cases':12,
        'g1_cases':22,'cancel_cases':4,'model_requests':0,'retry':False,'normal_budget_ms':8000,
        'formal_failure_rule':'HALT; preserve unrun; no replacing failed normal case',
        'product_freeze':str(RUN/'candidate-v103/freeze.json'),
        'candidate_claim':'diagnostic timing only; no proven performance repair'})
    try:
        for command in commands:
            batch.run(command['id'],command['argv'],timeout=240 if command['id'].startswith('g1') else 90,cwd=ROOT)
            print('CONFIRMED',command['id'],flush=True)
    except GateClosed:
        from lab_transport import cancel
        for host in r3.HOSTS:
            try:
                cancel(host)
            except Exception as error:
                print('RECOVERY_CANCEL_ERROR',host,type(error).__name__,flush=True)
        raise
    save(OUT/'result.json',{'NORMAL_AND_PROTECTION_GATE':'PASS','model_requests':0,'runner_state':batch.state()})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['run','normal','g1','cancel'])
    parser.add_argument('--host',choices=r3.HOSTS)
    parser.add_argument('--scenario',choices=['E1','E2'])
    parser.add_argument('--rep',type=int)
    args=parser.parse_args()
    r3.configure('v103')
    if args.operation=='normal': normal(args.host,args.scenario,args.rep)
    elif args.operation in {'g1','cancel'}: protection(args.host,args.operation)
    else: run()
