"""Offline recorder evidence cross-check against independently captured fixture ledger."""
import argparse
import hashlib
import json
from pathlib import Path

def inspect(folder):
    load=lambda name:json.loads((folder/name).read_text(encoding='utf-8'))
    trace=load('trace.json');audit=load('audit.json');oracle=load('oracle.json');sent=load('inputs.json')
    ids=[x['key'] for x in sent]
    clicks=[x for x in audit['events'] if x['kind'] in ('CLICK','UNRESOLVED_CLICK')]
    received=[x['id'] for x in clicks]
    actual=[e['kind'].split(':',1)[1] for e in oracle['events'] if e['kind'].startswith(('input:', 'edit:'))]
    assert audit['traceId']==trace['traceId'], 'trace correlation'
    assert trace['source']=='AUTOMATED', 'test provenance'
    assert ids==actual, ('fixture input mismatch',ids,actual)
    assert len(clicks)==len(ids), ('click count mismatch',received,ids)
    for key,event in zip(ids,clicks):
        assert event['id']==key or (event['kind']=='UNRESOLVED_CLICK' and key in event['candidateIds']), ('click attribution mismatch',key,event)
    assert trace['end']==audit['end'] and trace['error']==audit['error'], 'terminal mismatch'
    if trace['error']:
        assert audit.get('pending'), 'failure lost its pending click'
    if (folder/'candidate.json').exists():
        assert oracle['events'][-1]['saved']==load('candidate.json')['finalGoals'], 'saved goal mismatch'
        assert trace['end']=='STOPPED' and not trace['error'], 'invalid candidate'
    return dict(folder=str(folder),submitted=len(ids),observed=len(received),actualInputs=len(actual),error=trace['error'],
                noops=sum(e['kind']=='NOOP' for e in audit['events']),
                layoutEvents=sum(e['kind'].startswith('LAYOUT_') for e in audit['events']),
                unresolvedClicks=sum(e['kind']=='UNRESOLVED_CLICK' for e in clicks),status='PASS')

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    results=[]
    for folder in sorted(a.root.iterdir()):
        if folder.is_dir() and (folder/'result.json').exists():
            try:results.append(inspect(folder))
            except Exception as e:results.append(dict(folder=str(folder),status='FAIL',error=str(e)))
    manifest={str(p.relative_to(a.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.root.rglob('*') if p.is_file() and p.name not in ('audit-report.json','sha256.json')}
    (a.root/'audit-report.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    (a.root/'sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
    if not results or any(r['status']!='PASS' for r in results):raise SystemExit(1)

if __name__=='__main__':main()
