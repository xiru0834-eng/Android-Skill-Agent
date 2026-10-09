"""Read-only failure localization and relocatable evidence integrity checks."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_route(result,skill):
    positions={s['id']:(i,s['sourceIndex']) for i,s in enumerate(skill['steps'])}
    if len(positions)!=len(skill['steps']):return dict(valid=False,reason='DUPLICATE_SKILL_TARGET')
    last=-1
    for action in result['actions']:
        matched=positions.get(action['id'])
        if matched is None or matched[0]<=last or matched[1]!=action['sourceIndex']:
            return dict(valid=False,reason='ACTION_ORDER_OR_IDENTITY')
        last=matched[0]
    return dict(valid=True,reason='ORDERED_SUBSEQUENCE',inputs=len(result['actions']))


def diagnose(result,journal):
    reason=result.get('reason','UNKNOWN');phase=result.get('terminalPhase')
    step=result.get('terminalStepId');index=result.get('terminalStepIndex')
    # Older deployed APKs put location in the journal envelope, not the result.
    # Only the identical terminal result from this run can supply missing fields.
    if result.get('runId') and not any(k in result for k in ('terminalPhase','terminalStepIndex','terminalStepId')):
        terminals=[j for j in journal if j.get('kind')=='RESULT' and j.get('runId')==result['runId'] and j.get('data')==result]
        if len(terminals)==1:
            event=terminals[0];p=event.get('phase');i=event.get('stepIndex')
            if type(p) is int and 0<=p<=3 and type(i) is int and 0<=i<=8:
                phase=p;index=i
                starts=[j for j in journal if j.get('kind')=='START' and j.get('runId')==result['runId']]
                steps=starts[0].get('data',{}).get('steps',[]) if len(starts)==1 else []
                if i<len(steps) and isinstance(steps[i],dict):step=steps[i].get('id')
    category='UNKNOWN'
    if result.get('status')=='SUCCEEDED':category='COMPLETE'
    elif reason in ('WRONG_APP','STARTUP_TIMEOUT'):category='WINDOW_OR_STARTUP'
    elif reason in ('INVALID_START','UNSAVED_USER_EDITS'):category='PRECONDITION'
    elif reason.startswith('STALE:'):category='OBSERVATION'
    elif reason.startswith(('MISSING:','AMBIGUOUS:','UNUSABLE:')) or reason=='RECOVERY_TIMEOUT':category='LOCATE'
    elif reason=='FINAL_TARGET_MISMATCH':category='JOINT_VERIFICATION'
    elif reason in ('STEP_UNCONFIRMED','INPUT_REJECTED'):category='POST_ACTION_CONFIRMATION'
    elif reason in ('APPROVAL_CHANGED','TASK_TIMEOUT','USER_OR_SERVICE_STOP'):category='EXECUTION_GUARD'
    waits=[j for j in journal if j['kind']=='RECOVERY_WAIT']
    located=[j for j in journal if j['kind']=='RECOVERY_LOCATED']
    return dict(category=category,reason=reason,phase=phase,stepNumber=index+1 if index is not None and index<8 else None,
        targetId=step,actionDispatchedAtFailedStep=bool(step and any(a['id']==step for a in result.get('actions',[]))),
        recoveryReads=len(waits),locatedAfterWait=bool(located),
        recoveredTask=bool(located and result.get('status')=='SUCCEEDED'),causeCertainty='OBSERVED_SYMPTOM_ONLY',
        explanation='Classification uses controller evidence, not the injected fault label. A symptom is not proof of its external root cause.')


def files(root):
    paths=list(root.rglob('*'))
    if any(p.is_symlink() for p in paths):raise ValueError('SYMLINK_NOT_ALLOWED')
    return {p.relative_to(root).as_posix():digest(p) for p in sorted(paths)
            if p.is_file() and p!=root/'integrity.json' and '__pycache__' not in p.relative_to(root).parts}


def seal(root):
    root=Path(root);target=root/'integrity.json'
    if target.exists():raise ValueError('ALREADY_SEALED')
    target.write_text(json.dumps(dict(schema=1,files=files(root)),indent=2),encoding='utf-8')


def verify(root):
    root=Path(root).resolve();manifest=json.loads((root/'integrity.json').read_text(encoding='utf-8'))
    expected=manifest['files']
    for name in expected:
        if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name or ':' in name:
            raise ValueError('UNSAFE_MANIFEST_PATH')
    actual=files(root)
    result=dict(missing=sorted(expected.keys()-actual.keys()),unexpected=sorted(actual.keys()-expected.keys()),
                changed=sorted(k for k in expected.keys()&actual.keys() if expected[k]!=actual[k]))
    result['valid']=not any(result.values());result['fileCount']=len(expected)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--seal',action='store_true')
    args=parser.parse_args()
    if args.seal:seal(args.directory)
    report=verify(args.directory);print(json.dumps(report));raise SystemExit(0 if report['valid'] else 1)
