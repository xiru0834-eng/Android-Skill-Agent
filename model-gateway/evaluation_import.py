"""Recompute source evidence, seal selected files, and support read-only re-audit."""
import hashlib
import json
import re
import shutil
from pathlib import Path
from evaluation_framework import VERSION, validate_plan

CAPABILITIES=[
    ('teach.automated','自动化四步示范整理'),('teach.human','真人独立示范'),
    ('language.zh','中文技能选择'),('language.en','英文技能选择'),
    ('language.negative','澄清/拒绝边界'),('language.parameters','未示范参数泛化'),
    ('exec.singlepage','单页多控件任务'),('teach.freeform','自由操作顺序示范'),
    ('exec.multipage','跨页四步执行'),('exec.partial','非目标设备保护'),
    ('exec.initial','不同初态复用'),('exec.zero','已到位零输入'),
    ('exec.eight','八步完整流程'),('transfer.device','同App跨设备复用'),
    ('transfer.display','显示条件变化'),('transfer.review','相同包导入与本地审核'),
    ('transfer.newapp','新App三页重绑定'),('fault.stop','丢失/歧义控件正确停止'),
    ('ux.cancel','拒绝/取消不执行'),('ux.firstuse','真人首次使用体验'),
]
RUN_FILES=('case','skill','terminal','oracle','journal','audit','before','score')


def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def metrics(score,terminal):
    safety=score.get('inputSafety',{})
    return dict(actual_success=score['actual_success'],reported_success=terminal['status']=='SUCCEEDED',
                non_target_violation=None if score.get('non_target_applicability')=='N/A' else score['non_target_violation'],
                input_count=score['inputs'],extra_inputs=score.get('extraInputs',safety.get('extraInputs')),
                input_violations=score.get('unexpectedInputs',safety.get('unexpectedIds',0))+score.get('afterDeadlineInputs',safety.get('afterDeadlineInputs',0)),
                post_terminal_inputs=score['post_terminal_inputs'],
                goal_fields_met=score['goal_fields_met'],goal_fields=score['goal_fields'],
                reported_reason=terminal.get('reason'),failure_step=terminal.get('terminalStepIndex'),
                failure_control=terminal.get('terminalStepId'),terminal_phase=terminal.get('terminalPhase'),
                timings=dict(execution_ms=score['elapsed_ms']))


def score_proof(kind,files,expected):
    d={k:load(p) for k,p in files.items()}
    if kind=='ui-transfer':
        from ui_transfer import score_observation
        return score_observation(d,expected)
    if kind in ('partial','legacy'):
        if kind=='partial':from partial_audit import check_run
        else:from named_journey_audit import check_run
        # This one additional field belongs to the fault runner, not the base score.
        d['score'].pop('passFailureCriteria',None)
        scored=check_run(d,expected)
        if kind=='legacy':scored['inputSafety']=d['score']['inputSafety']
        m=metrics(scored,d['terminal'])
        checks=dict(audit_complete=scored['evidence_complete'],task_confirmed=scored['confirmed_success'],
                    protected=not scored['non_target_violation'],route=d['score']['route']['valid'],
                    input_safe=not(m['input_violations'] or m['post_terminal_inputs'] or m['extra_inputs']))
        if expected.get('expected'):
            checks['expected_stop']=(d['terminal']['status']==expected['expected']
                                     and d['terminal']['reason']==expected['expectedReason'])
        return dict(state='SCORED',checks=checks,metrics=m,evidence_basis='independent_ledger',
                    error=None if scored['confirmed_success'] else d['terminal']['reason'])
    if kind=='language':
        from skill_selection import validate_selection
        request,result,catalog=d['request'],d['result'],d['catalog']
        if result['case']!=expected or request['text']!=expected['text'] or request['skills']!=catalog:
            raise ValueError('Language schedule/catalog changed')
        if 'result' not in result:
            return dict(state='BLOCKED',error=result.get('error','Model unavailable'),
                        metrics=dict(timings=dict(model_ms=result.get('ms'))),evidence_basis='recorded_request')
        decision=result['result'];validate_selection(decision,catalog)
        target=expected.get('expected')
        if target:
            goal={'lamp':[1,60,None,None],'fan':[None,None,1,1]}[target]
            candidates=[c['id'] for c in catalog if c['finalGoals']==goal]
            if len(candidates)!=1:raise ValueError('Ambiguous expected catalog target')
            correct=decision['status']=='invoke' and decision['skill_id']==candidates[0]
        else:correct=decision['status']!='invoke' and decision['skill_id'] is None
        return dict(state='SCORED',checks=dict(decision_correct=correct),
                    metrics=dict(timings=dict(model_ms=result['ms']),
                                 false_invoke=target is None and decision['status']=='invoke',
                                 decision_status=decision['status'],positive=target is not None),
                    evidence_basis='decision_recomputed',error=None if correct else 'LANGUAGE_DECISION')
    if kind=='teaching':
        from workflow_contract import compile_evidence
        trace=d['trace'];candidate=compile_evidence(trace)
        if trace['source']!=expected['source']:raise ValueError('Demonstration source changed')
        faithful=(candidate==d['local_candidate']==d['model_candidate']==d['saved_skill']
                  and candidate['finalGoals']==expected['target'])
        saved=any(e['skill']==candidate for e in d['library'])
        return dict(state='SCORED',checks=dict(record_complete=len(trace['steps'])==4 and trace['end']=='STOPPED',
                    faithful=faithful,saved=saved),metrics={},evidence_basis='trajectory_contract',
                    error=None if faithful and saved else 'GUIDE_OR_SAVE_MISMATCH')
    if kind=='migration':
        pack=d['source'];before,pending,after=d['before'],d['pending'],d['after']
        pending_pack=json.loads(pending['pendingNamed']);skill=json.loads(after['approved'])
        same=pack==pending_pack and pack['skill']==skill
        unchanged=before.get('approved')==pending.get('approved') and before.get('result')==pending.get('result')==after.get('result')
        reviewed='pendingNamed' not in after and any(e==pack for e in json.loads(after['library']))
        return dict(state='SCORED',checks=dict(same_skill=same,local_review=unchanged and reviewed),
                    metrics={},evidence_basis='approval_transition',error=None if same and reviewed else 'IMPORT_REVIEW')
    if kind=='ux':
        e=d['evidence'];before,after=e['before'],e['after']['oracle']
        if before['caseId']!=after['caseId'] or before['initial']!=after['initial']:
            raise ValueError('UI test ledger changed')
        prefix=before['events'];events=after['events']
        if events[:len(prefix)]!=prefix:raise ValueError('UI ledger prefix changed')
        inputs=[x for x in events[len(prefix):] if x['kind'].startswith(('input:','edit:'))]
        unchanged=all(x['saved']==before['events'][-1]['saved'] and x['draft']==before['events'][-1]['draft'] for x in events[len(prefix):])
        return dict(state='SCORED',checks=dict(no_execution=e['resultUnchanged'] and unchanged,no_inputs=not inputs),
                    metrics=dict(input_count=len(inputs)),evidence_basis='ledger_and_recorded_UI_assertion',
                    error=None if not inputs and unchanged else 'CANCEL_DID_NOT_STOP')
    raise ValueError('Unsupported proof adapter')


def audit_campaign(root):
    root=Path(root).resolve();plan=load(root/'plan.json');validate_plan(plan)
    if sha(root/'plan.json')!=(root/'plan.sha256').read_text().strip():
        raise ValueError('Frozen evaluation plan changed')
    hashes=load(root/'evidence-sha256.json') if (root/'evidence-sha256.json').exists() else {}
    observations=[]
    for c in plan['cases']:
        proof=c['proof'];files={};bad=None
        for name,relative in proof['files'].items():
            p=(root/relative).resolve()
            if not p.is_relative_to(root):raise ValueError('Evidence path escapes campaign')
            if p.exists():
                if relative in hashes and sha(p)!=hashes[relative]:bad='Evidence hash mismatch'
                files[name]=p
            elif relative in hashes:bad='Sealed evidence missing'
        if bad:result=dict(state='INVALID',error=bad)
        elif not files:continue  # Still planned, never silently removed from the denominator.
        elif len(files)!=len(proof['files']):result=dict(state='INVALID',error='Incomplete evidence files')
        else:
            try:
                dims=c['dimensions']
                unsupported={'language.parameters','transfer.newapp','ux.firstuse','teach.freeform'}&set(c['capabilities'])
                if unsupported:raise ValueError('This adapter cannot verify '+','.join(sorted(unsupported)))
                if 'teach.human' in c['capabilities'] and proof['expected'].get('source')!='HUMAN_DECLARED':
                    raise ValueError('Human demonstration was not declared')
                if 'skill' in files and dims.get('goal') is not None and load(files['skill'])['finalGoals']!=dims['goal']:
                    raise ValueError('Goal differs from frozen plan')
                if 'skill' in files:
                    steps=load(files['skill'])['steps']
                    pages={s[k] for s in steps for k in ('page','afterPage')}
                    if 'exec.singlepage' in c['capabilities'] and len(pages)!=1:
                        raise ValueError('Multi-page evidence cannot prove single-page capability')
                    if 'exec.eight' in c['capabilities'] and len(steps)!=8:
                        raise ValueError('Four-step evidence cannot prove eight-step capability')
                    if dims.get('pages') is not None and len(pages)!=dims['pages']:
                        raise ValueError('Page count differs from frozen plan')
                    if dims.get('steps') is not None and len(steps)!=dims['steps']:
                        raise ValueError('Step count differs from frozen plan')
                if 'terminal' in files and dims.get('budget_ms') is not None:
                    result=load(files['terminal'])
                    if result['deadlineMs']-result['startedMs']!=dims['budget_ms']:
                        raise ValueError('Budget differs from frozen plan')
                result=score_proof(proof['kind'],files,proof['expected'])
            except (ValueError,AssertionError,KeyError,TypeError,IndexError) as e:
                result=dict(state='INVALID',error=type(e).__name__+': '+str(e))
        observations.append(dict(case_id=c['id'],evidence=proof,**result))
    return plan,observations


def import_partial(source,output):
    source=Path(source).resolve();output=Path(output)
    if output.exists():raise FileExistsError('Refuse overwriting evaluation')
    pending=[];cases=[]
    def add(cid,stage,cap,family,repeat,environment,expected,kind,files,dimensions):
        cases.append(dict(id=cid,stage=stage,capabilities=cap,family=family,repeat=repeat,
                          environment=environment,expected='safe_stop' if stage=='fault' else 'complete',
                          dimensions=dimensions,proof=dict(kind=kind,expected=expected,files={})))
        pending.append(files)
    for suite,environment in [('phone-matrix','S23+'),('emulator-reference','emulator1080x2400@420'),
                               ('emulator-compact-final','emulator720x1280@420'),('faults','S23+')]:
        protocol=load(source/suite/'protocol.json')
        for i,case in enumerate(protocol['cases']):
            folder=source/suite/f'run-{i:03d}';fault=suite=='faults'
            cap=['fault.stop'] if fault else ['exec.multipage','exec.partial','exec.initial']
            if not fault and case['condition']=='all':cap+=['exec.zero']
            if environment.startswith('emulator') and not fault:cap+=['transfer.device','transfer.display']
            family=json.dumps({k:v for k,v in case.items() if k!='repeat'},sort_keys=True)
            add(f'{suite}.{i:03d}','fault' if fault else 'execution',cap,family,case['repeat'],environment,case,
                'partial',{k:folder/(k+'.json') for k in RUN_FILES},
                dict(pages=2,steps=4,target_fields=2,initial=case['initial'],condition=case['condition'],
                     goal=[1,60,None,None] if case['skill']=='lamp' else [None,None,1,1],
                     budget_ms=30000,source='AUTOMATED'))
    for name in ['ui-chinese','ui-english']:
        case=load(source/name/'case.json')
        add(name,'execution',['exec.multipage','exec.partial'],name,0,'S23+',case,'partial',
            {k:source/name/(k+'.json') for k in RUN_FILES},dict(pages=2,steps=4,entry=name,budget_ms=30000))
    for name in ('legacy-reading-final','legacy-original'):
        case=load(source/name/'case.json')
        add(name,'execution',['exec.eight'],name,0,'S23+',case,'legacy',
            {k:source/name/(k+'.json') for k in (*RUN_FILES,'persisted')},
            dict(pages=3,steps=8,budget_ms=30000))
    protocol=load(source/'language/protocol.json')
    for i,case in enumerate(protocol['cases']):
        language='zh' if re.search('[\u4e00-\u9fff]',case['text']) else 'en'
        cap=['language.'+language]+([] if case['expected'] else ['language.negative'])
        add(f'language.{i:03d}','language',cap,case['text'],0,'remote-api',case,'language',
            dict(request=source/'language'/f'case-{i:03d}/request.json',
                 result=source/'language'/f'case-{i:03d}/result.json',catalog=source/'language/catalog.json'),
            dict(language=language,positive=case['expected'] is not None,model='unknown_per_case',selection_only=True))
    for key in ('lamp','fan'):
        p=source/key;protocol=load(p/'protocol.json')
        add('teaching.'+key,'teaching',['teach.automated'],key,0,'S23+',protocol,'teaching',
            dict(trace=p/'trace.json',local_candidate=p/'local-candidate.json',model_candidate=p/'model-candidate.json',
                 saved_skill=p/'saved-skill.json',library=p/'library-after.json'),dict(source='AUTOMATED',steps=4))
        p=source/('import-'+key)
        add('import.'+key,'migration',['transfer.review'],key,0,'emulator',{},'migration',
            dict(source=source/key/(key+'-partial.json'),before=p/'before.json',pending=p/'pending.json',after=p/'after.json'),
            dict(source_device='S23+',same_app=True))
    for name in ('ui-reject','ui-confirm-cancel'):
        add(name,'ux',['ux.cancel'],name,0,'S23+',{},'ux',dict(evidence=source/name/'evidence.json'),
            dict(source='AUTOMATED',interaction=name))
    snapshot=load(source/'implementation-snapshot/manifest.json')
    plan=dict(schema=1,framework=VERSION,campaign=output.name,phase='retrospective',variant='v24',
              comparison={},capabilities=[dict(id=k,label=v) for k,v in CAPABILITIES],cases=cases,
              builds=snapshot['installed'],source_note=snapshot['note'],
              incidents=[dict(path=str(source/name),phase='before_task',note=note) for name,note in [
                  ('emulator-compact','Initial acknowledgement failed; exact mismatching value not retained.'),
                  ('emulator-compact-confirmation','Test-operator final scroll not reread.'),
                  ('legacy-reading','Old skill button not reached.'),
                  ('legacy-reading-recheck','Test-operator scrolling overshoot.'),
                  ('emulator-setup.png','System UI ANR before task execution.')]])
    validate_plan(plan);output.mkdir(parents=True);hashes={}
    for i,(case,files) in enumerate(zip(cases,pending)):
        folder=output/'proof'/f'case-{i:03d}';folder.mkdir(parents=True)
        for logical,original in files.items():
            relative=(Path('proof')/folder.name/(logical+'.json')).as_posix()
            case['proof']['files'][logical]=relative
            if original.exists():
                data=original.read_bytes()
                if re.search(rb'(?:sk-(?:proj-|ws-)?|apikey_)[A-Za-z0-9._-]{24,}',data):
                    raise ValueError('Possible credential in evidence; not copied')
                shutil.copyfile(original,output/relative);hashes[relative]=sha(output/relative)
    dump(output/'plan.json',plan);(output/'plan.sha256').write_text(sha(output/'plan.json')+'\n')
    dump(output/'evidence-sha256.json',hashes)
    return audit_campaign(output)
