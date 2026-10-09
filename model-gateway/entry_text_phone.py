"""Actual input field boundaries, no bridge or model and no target input."""
import argparse
import base64
from pathlib import Path
from entry_phone import restore_input
from named_journey_device import library,text,tree,prefs,APP,PROBE,snap
from transfer_run import private
from workflow_experiment import write,adb


def field(ui,key):
    nodes=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/'+key]
    if len(nodes)!=1:raise RuntimeError('UNIQUE_FIELD_REQUIRED')
    return nodes[0]


def run(out):
    out.mkdir(parents=True,exist_ok=False);serial='R5CW134LLBZ';before=prefs(serial)
    oracle=private(serial,APP,'workflow-oracle.json');library(serial)
    saved=field(tree(serial),'libraryInput').get('text','');rows=[]
    deny=' DO NOT EXECUTE.'
    cases=[('ascii499','A'*499),('ascii500','A'*500),
        ('tail-denial501','Run Reading60. '+' '* (501-15-len(deny))+deny),
        ('tail-denial520','Run Reading60. '+' '* (520-15-len(deny))+deny),
        ('emoji500','😀'*250),('emoji502','😀'*251)]
    write(out/'protocol.json',dict(cases=[dict(caseId=k,text=v,utf16Units=len(v.encode('utf-16-le'))//2) for k,v in cases],
        assertions='Full input preserved; oversize blocked; no selection click; protected state unchanged',modelCalls=0))
    try:
        for key,value in cases:
            # The normal setter asserts an exact match and stops on truncation.
            # Here a mismatch is the DUT result we need to retain, not skip.
            result=adb(serial,'shell','am','instrument','-w','-e','field','libraryInput','-e','value',
                base64.b64encode(value.encode()).decode(),'edu.sydney.evaluation/.LanguageInput')
            write(out/(key+'-setter.json'),dict(instrumentation=result))
            if 'PASS UI text set' not in result:
                write(out/'harness-error.json',dict(caseId=key,reason='INJECTION_NOT_DELIVERED',
                    scoresValid=False,modelCalls=0))
                raise RuntimeError('HARNESS_INJECTION_NOT_DELIVERED')
            ui=tree(serial)
            observed=field(ui,'libraryInput').get('text','');enabled=field(ui,'libraryChoose').get('enabled')=='true'
            units=len(value.encode('utf-16-le'))//2
            row=dict(caseId=key,utf16Units=units,preserved=observed==value,
                observedUtf16Units=len(observed.encode('utf-16-le'))//2,chooseEnabled=enabled,
                passed=observed==value and enabled==(units<=500),modelCalls=0,targetInputs=0)
            rows.append(row);write(out/'results.json',rows)
            if units>500:snap(serial,out/(key+'.png'))
        write(out/'summary.json',dict(passed=sum(r['passed'] for r in rows),n=len(rows),modelCalls=0))
        return rows
    finally:
        restored=restore_input(serial,saved);after=prefs(serial)
        write(out/'restored.json',dict(inputRestored=restored,workflowPrefsUnchanged=before==after,
            oracleUnchanged=private(serial,APP,'workflow-oracle.json')==oracle))
        if not restored or before!=after or private(serial,APP,'workflow-oracle.json')!=oracle:raise RuntimeError('RESTORATION_NOT_VERIFIED')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=run(a.output);print('Input boundary '+str(sum(r['passed'] for r in rows))+'/'+str(len(rows)))
    raise SystemExit(0 if all(r['passed'] for r in rows) else 1)
