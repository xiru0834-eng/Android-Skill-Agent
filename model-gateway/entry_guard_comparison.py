"""Paired gate-only counterfactual using identical saved GPT replies; no API calls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from accuracy_confirmation import adjudicate,verify_protocol
from entry_confirmation import summarize
from workflow_experiment import write

def analyse(root):
    out=root/'gpt-confirmation';protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    baseline=root/'baseline';p=baseline/'source/model-gateway/catalog_uniqueness.py'
    manifest=json.loads((baseline/'manifest.json').read_text(encoding='utf-8'))
    old_digest=manifest['source']['model-gateway\\catalog_uniqueness.py']
    if hashlib.sha256(p.read_bytes()).hexdigest()!=old_digest:raise ValueError('BASELINE_CHANGED')
    current=Path(__file__).with_name('skill_selection.py')
    if hashlib.sha256(current.read_bytes()).hexdigest()!=manifest['source']['model-gateway\\skill_selection.py']:
        raise ValueError('GPT_PROMPT_CHANGED_CANNOT_ISOLATE_GATE')
    spec=importlib.util.spec_from_file_location('baseline_catalog_gate',p);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rows=json.loads((out/'results.json').read_text(encoding='utf-8'));before=[];changed=[]
    for i,row in enumerate(rows):
        prior=copy.deepcopy(row)
        if row['available']:
            response=json.loads((out/f'trials/{i:03d}/response-1.json').read_text(encoding='utf-8'))
            prior['selection']=old.guard_selection(row['case']['text'],row['case']['skills'],response['draft'])
            adjudicate(prior)
            if prior['selection']!=row['selection']:
                changed.append(dict(index=i,caseId=row['case']['caseId'],repeat=row['repeat'],
                    before=prior['selection'],after=row['selection'],beforeCorrect=prior['correct'],afterCorrect=row['correct']))
        before.append(prior)
    result=dict(comparison='same actual GPT reply; old vs new local guard; NOT separate provider A/B',
        old=summarize(before,protocol),new=summarize(rows,protocol),changed=changed,
        improvement=sum(r['correct'] for r in rows)-sum(r['correct'] for r in before),additionalAPIRequests=0,
        oldLatencyNotMeasured=True,oldGateHash=old_digest)
    write(root/'guard-comparison.json',result)
    print(json.dumps(dict(n=len(rows),oldCorrect=result['old']['correct'],newCorrect=result['new']['correct'],improvement=result['improvement'],unsafe=result['new']['unsafeSuggestions'])))

if __name__=='__main__':analyse(Path(__file__).parents[1]/'output/entry-hardening-v1')
