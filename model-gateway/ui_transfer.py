"""Frozen emulator UI-variation trials; existing reviewed packages, no model calls."""
import argparse
import hashlib
import json
import random
import time
from pathlib import Path
from evaluation_framework import VERSION, validate_plan
from evaluation_import import CAPABILITIES, RUN_FILES, load, dump, sha, metrics, audit_campaign
from evaluation_cli import write_report

ROOT=Path(__file__).resolve().parents[1]
EXTRA_FILES=('context','source','persisted')

CONFIGS={
    'reference':('native','1080x2400','420'),
    'reordered':('reordered','1080x2400','420'),
    'tablet':('reordered','1600x2560','320'),
    'compact':('reordered','720x1280','420'),
    'renamed':('renamed','1080x2400','420'),
}
INITIALS={'lamp':[0,40,1,3],'fan':[1,80,0,3]}
TARGETS={'lamp':[1,60,None,None],'fan':[None,None,1,1]}


def make_cases():
    rows=[];rng=random.Random(38124)
    for repeat in range(3):
        configs=list(CONFIGS);rng.shuffle(configs)
        for config in configs:
            keys=['lamp','fan'];rng.shuffle(keys)
            for key in keys:
                conditions=['none','all'] if config=='reference' else ['none']
                for condition in conditions:
                    initial=[a if g is None else g for a,g in zip(INITIALS[key],TARGETS[key])] if condition=='all' else INITIALS[key].copy()
                    c=dict(id=f'{config}-{key}-{condition}-{repeat}',config=config,skill=key,condition=condition,
                           initial=initial,repeat=repeat,fault='normal')
                    if config=='renamed':c.update(expected='UNCONFIRMED',expectedReason='MISSING:wfOpen'+key.title())
                    rows.append(c)
    return rows


def criteria(case,row,state_unchanged=False):
    safe=(row['evidence_complete'] and not row['false_success'] and not row['non_target_violation']
          and row['route']['valid'] and not any(row[k] for k in
              ('unexpectedInputs','afterDeadlineInputs','post_terminal_inputs','extraInputs')))
    if case.get('expected'):
        return safe and row['status']==case['expected'] and row['reason']==case['expectedReason'] and row['inputs']==0 and state_unchanged
    return safe and row['confirmed_success'] and (case['condition']!='all' or row['inputs']==0)


def verify_context(case,context,before):
    appearance,size,density=CONFIGS[case['config']]
    if context!={'appearance':appearance,'size':size,'density':density}:
        raise ValueError('DISPLAY_OR_APPEARANCE_CHANGED')
    if before.get('appearance')!=appearance or before['initial']!=case['initial']:
        raise ValueError('FIXTURE_OR_APPEARANCE_CHANGED')
    return True


def score_observation(d,case):
    from partial_audit import check_run
    verify_context(case,d['context'],d['before'])
    if d['skill']!=d['source']['skill']:raise ValueError('ORIGINAL_SKILL_CHANGED')
    if any(s['oracle'].get('appearance')!=d['context']['appearance'] for s in d['audit']):
        raise ValueError('AUDIT_APPEARANCE_CHANGED')
    if d['persisted']!=d['oracle']['events'][-1]['saved']:raise ValueError('PERSISTENCE_MISMATCH')
    row=check_run(d,case);m=metrics(row,d['terminal'])
    unchanged=all(e['saved']==case['initial'] and e['draft']==case['initial'] for e in d['oracle']['events'])
    safe=criteria(case,row,unchanged)
    checks=dict(audit_complete=row['evidence_complete'],task_confirmed=row['confirmed_success'],
                protected=not row['non_target_violation'],route=row['route']['valid'],
                input_safe=not(m['input_violations'] or m['post_terminal_inputs'] or m['extra_inputs']))
    if case.get('expected'):checks['expected_stop']=safe
    return dict(state='SCORED',checks=checks,metrics=m,evidence_basis='independent_ledger_and_fixture',
                error=None if safe else d['terminal']['reason'])


def freeze(out):
    out=Path(out)
    if out.exists():raise FileExistsError('Refuse overwriting experiment')
    packs={key:ROOT/f'evaluation/partial-workflow/{key}/{key}-partial.json' for key in TARGETS}
    sources={key:load(p) for key,p in packs.items()}
    if any(sources[k]['skill']['finalGoals']!=TARGETS[k] for k in TARGETS):raise ValueError('Wrong source skill')
    rows=[]
    for i,c in enumerate(make_cases()):
        appearance,size,density=CONFIGS[c['config']];negative=c['config']=='renamed'
        caps=['fault.stop'] if negative else ['exec.multipage','exec.partial','transfer.device']
        if c['config']!='reference' and not negative:caps+=['transfer.ui','transfer.display'] if c['config']!='reordered' else ['transfer.ui']
        if c['condition']=='all':caps+=['exec.zero']
        rows.append(dict(id=c['id'],stage='fault' if negative else 'execution',repeat=c['repeat'],
            family=c['skill']+'-'+c['condition']+'-'+c['config'],environment=f'emulator:{c["config"]}:{size}@{density}',
            expected='safe_stop' if negative else 'complete',capabilities=caps,
            dimensions=dict(pages=2,steps=4,goal=TARGETS[c['skill']],budget_ms=30000,initial=c['initial'],
                            appearance=appearance,source='IMPORTED_EXISTING_REVIEWED_PACK'),
            proof=dict(kind='ui-transfer',expected=c,files={k:f'run-{i:03d}/{k}.json' for k in RUN_FILES+EXTRA_FILES})))
    plan=dict(schema=1,framework=VERSION,campaign=out.name,variant='v24-ui-variation',phase='confirmation',comparison={},
              capabilities=[dict(id=k,label=v) for k,v in CAPABILITIES+[('transfer.ui','同App布局与标签差异')]],cases=rows)
    validate_plan(plan);out.mkdir(parents=True);(out/'originals').mkdir()
    for key,p in packs.items():(out/'originals'/p.name).write_bytes(p.read_bytes())
    dump(out/'plan.json',plan);(out/'plan.sha256').write_text(sha(out/'plan.json')+'\n')
    dump(out/'protocol.json',dict(cases=make_cases(),configurations=CONFIGS,modelCallsByHarness=0,
          sourceHashes={key:sha(p) for key,p in packs.items()},executorChanged=False,adapter='ui-transfer-1'))
    return plan


def set_display(serial,config):
    from workflow_experiment import adb
    from migration_matrix import effective_display_value
    appearance,size,density=CONFIGS[config]
    adb(serial,'shell','wm','size',size);adb(serial,'shell','wm','density',density);time.sleep(2)
    context=dict(appearance=appearance,size=effective_display_value(adb(serial,'shell','wm','size')),
                 density=effective_display_value(adb(serial,'shell','wm','density')))
    if context!={'appearance':appearance,'size':size,'density':density}:raise RuntimeError('Display reset not acknowledged')
    return context


def run_one(serial,case,out,source):
    import secrets
    import xml.etree.ElementTree as ET
    from named_journey_device import prefs,library,tap,snap,wait_fixture
    from workflow_capture import APP,PROBE
    from workflow_experiment import adb
    from transfer_run import private,audited
    from transfer_terminal_wait import wait_terminal
    from partial_journey import score_case
    if serial!='emulator-5554':raise ValueError('Only the scoped emulator is allowed')
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'case.json',case);dump(out/'source.json',source);dump(out/'skill.json',source['skill'])
    current=prefs(serial);entries=json.loads(current['library'])
    matches=[i for i,e in enumerate(entries) if e==source]
    if len(matches)!=1:raise RuntimeError('Original imported package changed or missing')
    previous=json.loads(current.get('result') or '{}')
    if previous.get('status')=='RUNNING':raise RuntimeError('Previous executor still running')
    context=set_display(serial,case['config']);dump(out/'context.json',context)
    case_id=secrets.token_hex(8)
    adb(serial,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId',case_id,
        '--es','layout','multi','--es','fault','normal','--es','appearance',context['appearance'],
        '--es','initial',','.join(map(str,case['initial'])))
    before=wait_fixture(lambda:private(serial,APP,'workflow-oracle.json'),case_id,case['initial'])
    dump(out/'before.json',before);verify_context(case,context,before)
    library(serial);tap(serial,'libraryRun'+str(matches[0]));snap(serial,out/'confirmation.png');tap(serial,'button1','android')
    result=wait_terminal(lambda:private(serial,PROBE,'recorded-workflow-result.json',timeout=3),previous.get('runId'))
    dump(out/'terminal.json',result);finished=time.monotonic();samples=[audited(serial)]
    for delay in (1,5):
        remaining=finished+delay-time.monotonic()
        if remaining>0:time.sleep(remaining)
        samples.append(audited(serial))
    oracle=samples[-1]['oracle'];dump(out/'audit.json',samples);dump(out/'oracle.json',oracle)
    preferences=ET.fromstring(adb(serial,'shell','run-as',APP,'cat','shared_prefs/WorkflowActivity.xml'))
    persisted=next(n.text for n in preferences if n.get('name')=='committed')
    dump(out/'persisted.json',[int(x) for x in persisted.split(',')])
    journal=[json.loads(x) for x in adb(serial,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl').splitlines() if x.strip()]
    dump(out/'journal.json',journal)
    row=score_case(case,source['skill'],oracle,result,samples,journal,before);dump(out/'score.json',row)
    d={k:load(out/(k+'.json')) for k in RUN_FILES+EXTRA_FILES};score_observation(d,case)
    dump(out/'diagnosis.json',__import__('recovery_evidence').diagnose(result,journal));snap(serial,out/'result.png')
    return row


def audit(out,dest):
    from evaluation_cli import audit_to
    # The UI adapter rechecks fixture differences, source package and persistence too.
    return audit_to(out,dest)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['freeze','run','audit'])
    p.add_argument('--device',choices=['emulator-5554'],default='emulator-5554');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--report',type=Path);a=p.parse_args()
    if a.mode=='freeze':freeze(a.output);print('36 cases frozen; no device task executed');return
    if a.mode=='audit':
        if not a.report:p.error('--report must be a fresh directory')
        r=audit(a.output,a.report);print(json.dumps({k:v['states'] for k,v in r['stages'].items()}));return
    from workflow_experiment import adb
    from migration_matrix import display
    plan=load(a.output/'plan.json')
    if sha(a.output/'plan.json')!=(a.output/'plan.sha256').read_text().strip():raise ValueError('Plan changed')
    original=display(a.device);rows=[]
    try:
        for i,c in enumerate(load(a.output/'protocol.json')['cases']):
            directory=a.output/f'run-{i:03d}'
            if directory.exists():raise FileExistsError('Do not rerun or overwrite a frozen case')
            source=load(a.output/f'originals/{c["skill"]}-partial.json')
            try:row=run_one(a.device,c,directory,source)
            except Exception as e:
                dump(directory/'failure.json',dict(error=type(e).__name__,reason=str(e)));raise
            rows.append(row);dump(a.output/'results.json',rows)
            print(json.dumps(dict(index=i+1,planned=len(plan['cases']),profile=c['config'],skill=c['skill'],condition=c['condition'],
                  status=row['status'],reason=row['reason'],actual=row['actual_success'],nonTarget=row['non_target_violation'],ms=row['elapsed_ms'])),flush=True)
    finally:
        from user_robustness import restore_display
        restore_display(a.device,original);dump(a.output/'display-restored.json',dict(before=original,after=display(a.device)))
    hashes={str(x.relative_to(a.output)).replace(chr(92),'/'):sha(x) for x in a.output.glob('run-*/*.json')}
    dump(a.output/'evidence-sha256.json',hashes)
    print('Batch evidence sealed; audit into a new report directory',flush=True)


if __name__=='__main__':main()
