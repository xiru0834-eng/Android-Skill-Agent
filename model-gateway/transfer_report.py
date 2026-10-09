"""Generate descriptive results from persisted trials, including all failures."""
import argparse
import csv
import json
import statistics
from pathlib import Path
from workflow_experiment import write

def main():
    p=argparse.ArgumentParser();p.add_argument('directories',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);table=[];summaries=[]
    for folder in a.directories:
        protocol=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
        rows=json.loads((folder/'results.json').read_text(encoding='utf-8')) if (folder/'results.json').exists() else []
        groups={}
        for i,row in enumerate(rows):
            case=row['case'];key=case['initialId'] if protocol['suite']=='normal' else case.get('condition',case['fault'])
            groups.setdefault(key,[]).append(row)
            entry=dict(batch=folder.name,index=i,group=key,status=row.get('status','INFRA_FAILURE'),
                confirmed=row.get('confirmed_success',False),false_success=row.get('false_success',False),
                elapsed_ms=row.get('elapsed_ms'),inputs=row.get('inputs'),reason=row.get('reason',row.get('infrastructureFailure','')))
            table.append(entry)
        summary=dict(batch=folder.name,planned=len(protocol['cases']),executed=len(rows),
            confirmed=sum(r.get('confirmed_success',False) for r in rows),
            false_success=sum(r.get('false_success',False) for r in rows),
            unknown=sum(not r.get('evidence_complete',False) for r in rows),groups={})
        for key,items in groups.items():
            times=[r['elapsed_ms'] for r in items if r.get('confirmed_success')]
            summary['groups'][key]=dict(n=len(items),confirmed=sum(r.get('confirmed_success',False) for r in items),
                false_success=sum(r.get('false_success',False) for r in items),
                successMedianMs=statistics.median(times) if times else None,successMinMs=min(times) if times else None,
                successMaxMs=max(times) if times else None,failedElapsedMs=[r.get('elapsed_ms') for r in items if not r.get('confirmed_success')])
        summaries.append(summary)
    write(a.output/'summary.json',summaries)
    with (a.output/'trials.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]) if table else ['batch']);writer.writeheader();writer.writerows(table)
    print(json.dumps(summaries,ensure_ascii=False))

if __name__=='__main__':main()
