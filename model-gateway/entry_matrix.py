"""Installed phone/emulator entry matrix, injected carrier responses; zero paid calls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from intent_bridge import BridgeServer,Handler
from named_journey_device import prefs,library,home,tap,text,snap,PROBE,APP
from workflow_capture import tree
from workflow_experiment import adb,write
from transfer_run import private
from entry_phone import reverse_target,restore_input,read_input

EVENTS={
 'U01':'invoke-zh','U02':'invoke-en','U03':'clarify','U04':'reject',
 'U05':'cancel','U06':'edit','U07':'leave','U08':'deadline','U09':'rapid-submit',
 'U10':'catalog-change','U11':'approval-change','U12':'process-reentry',
 'U13':'busy','U14':'http401','U15':'http429','U16':'http502','U17':'http503',
 'U18':'unknown-skill','U19':'wrong-request','U20':'oversize-reply','U21':'malformed-reply',
 'U22':'duplicate-key','U23':'oversize-input','U24':'empty-input'}
DISPLAY={'U01','U02','U03','U04','U05','U06','U07','U08','U14','U18','U23','U24'}
UNSUPPORTED={'U10','U11','U12'}


def cases(repeats,display=False):
    if type(repeats) is not int or not 1<=repeats<=3:raise ValueError('INVALID_REPEATS')
    return [dict(caseId=key,event=value,repeat=rep,automatable=key not in UNSUPPORTED)
            for rep in range(repeats) for key,value in EVENTS.items() if not display or key in DISPLAY]


def mutate_reply(key,code,body):
    body=dict(body)
    failures={'U13':(409,'BUSY'),'U14':(401,'PAIRING_REQUIRED'),'U15':(429,'SESSION_LIMIT'),
              'U16':(502,'INVALID_MODEL_RESPONSE'),'U17':(503,'SELECTION_DEADLINE')}
    if code==200 and key in failures:code,reason=failures[key];body=dict(error=reason)
    if code==200:
        if key=='U18':body['skill_id']='e'*64
        if key=='U19':body['request_id']='e'*32
        if key=='U20':body['message']='x'*5000
        if key=='U21':return code,b'{broken json'
        if key=='U22':
            raw=json.dumps(body,separators=(',',':')).replace('"status":"invoke"','"status":"reject","status":"invoke"')
            return code,raw.encode()
    return code,json.dumps(body,ensure_ascii=False).encode()


def summarize(rows,planned):
    executed=[r for r in rows if r['status']!='NOT_RUN']
    passed=sum(r['status']=='PASS' for r in executed)
    return dict(planned=len(planned),attempted=len(executed),passed=passed,
        failed=sum(r['status']=='FAIL' for r in executed),notRun=len(planned)-len(executed),
        harnessErrors=sum(r['status']=='HARNESS_ERROR' for r in executed),
        matrixPassed=len(executed)==len(planned) and passed==len(planned),
        modelCalls=0,injectedTransportNotModelAccuracy=True,
        nativeInteractionLatencyMeasured=False)


class MatrixHandler(Handler):
    def do_POST(self):
        self.injection=self.server.matrix_case.copy()
        super().do_POST()

    def reply(self,code,body):
        if self.path!='/v1/skill-selections':return super().reply(code,body)
        key=self.injection['caseId'];code,data=mutate_reply(key,code,body)
        try:
            self.connection.settimeout(5);self.send_response(code)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
        except OSError:pass


def ui_field(ui,key):
    found=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/'+key]
    if len(found)!=1:raise RuntimeError('FIELD_NOT_UNIQUE:'+key)
    return found[0]


def has_confirmation(ui):
    return any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node'))


def wait_confirmation(read,clock=time.monotonic,sleep=time.sleep):
    """Observe, never input. Share one 3s budget with each actual ADB read."""
    deadline=clock()+3
    while True:
        remaining=deadline-clock()
        if remaining<=0:raise RuntimeError('CONFIRMATION_OBSERVATION_TIMEOUT')
        ui=read(timeout=remaining)
        if clock()>deadline:raise RuntimeError('CONFIRMATION_OBSERVATION_TIMEOUT')
        if has_confirmation(ui):return ui
        remaining=deadline-clock()
        if remaining<=0:return ui
        sleep(min(.15,remaining))
        if clock()>=deadline:return ui


def verify_input(serial,command,ui):
    if command=='':
        # Accessibility text may contain EditText's hint. Read the real value
        # persisted by the ordinary Activity.onPause, never infer it from hint.
        home(serial)
        stored=prefs(serial,'WorkflowLibraryActivity')
        assert 'text' in stored and stored['text'] in ('',None),'INPUT_NOT_PRESERVED'
        library(serial)
        return tree(serial)
    assert ui_field(ui,'libraryInput').get('text','')==command,'INPUT_NOT_PRESERVED'
    return ui


def run(serial,out,repeats=3,display=False):
    out.mkdir(parents=True,exist_ok=False)
    installed=adb(serial,'shell','dumpsys','package',PROBE)
    if not re.search(r'\bversionCode=34\b',installed):raise RuntimeError('EXPECTED_INSTALLED_V34')
    before=prefs(serial);oracle=private(serial,APP,'workflow-oracle.json')
    prior=reverse_target(serial);token=prefs(serial,'language_connection')['pairing']
    saved=read_input(serial)
    write(out/'input-before.json',dict(text=saved))
    planned=cases(repeats,display);rows=[];entered=threading.Event();release=threading.Event()
    requests=[]
    def select(command,skills,budget):
        current=server.matrix_case.copy();entered.set()
        requests.append(dict(caseId=current['caseId'],text=command,
            catalogSha256=hashlib.sha256(json.dumps(skills,sort_keys=True).encode()).hexdigest()))
        def response(payload,timeout):
            if current['caseId'] in {'U05','U06','U07','U08','U09'}:release.wait(15)
            key=current['caseId'];status='clarify' if key=='U03' else 'reject' if key=='U04' else 'invoke'
            return dict(status=status,skill_id=skills[0]['id'] if status=='invoke' else None,
                        message='Injected contract test; preview only.')
        return budget.call(response,{},'INJECTED')
    server=BridgeServer(('127.0.0.1',0),token,bounded_selector=select,max_calls=100)
    server.RequestHandlerClass=MatrixHandler;server.matrix_case={}
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    protocol=dict(device=serial,installedVersion=34,cases=planned,modelCalls=0,
        expected='U01/U02/U09 correct proposal only; all other events no confirmation',
        untouched=['library','approved','result','targetOracle'],resourceBudgetSeconds=8,
        sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),displaySuite=display)
    write(out/'protocol.json',protocol)
    try:
        adb(serial,'reverse','tcp:8765','tcp:'+str(server.server_port))
        for index,case in enumerate(planned):
            folder=out/f'{index:02d}-{case["caseId"]}';folder.mkdir()
            if not case['automatable']:
                row=dict(case,status='NOT_RUN',reason='No non-destructive product-level injection; installed-client tests are separate.')
                rows.append(row);write(folder/'row.json',row);continue
            started=time.monotonic();server.matrix_case=case;entered.clear();release.clear()
            library(serial)
            command='请执行我保存的技能。' if case['caseId']=='U01' else 'Please run my saved skill unchanged.'
            if case['caseId']=='U23':command='Run skill. '+'A'*500+' DO NOT EXECUTE.'
            if case['caseId']=='U24':command=''
            text(serial,'libraryInput',command);ids_before=set(server.selection_events)
            observed=verify_input(serial,command,tree(serial));choose=ui_field(observed,'libraryChoose')
            if case['caseId'] in {'U23','U24'}:
                assert choose.get('enabled')=='false','INVALID_INPUT_ENABLED'
                assert not has_confirmation(observed),'INVALID_INPUT_CONFIRMATION'
                time.sleep(.1)
            else:
                bounds=list(map(int,re.findall(r'-?\d+',choose.get('bounds',''))))
                tap(serial,'libraryChoose');assert entered.wait(5),'NO_ACCEPTED_REQUEST'
                key=case['caseId']
                if key=='U05':tap(serial,'libraryCancel')
                elif key=='U06':text(serial,'libraryInput','Do not execute. The prior command is cancelled.')
                elif key=='U07':home(serial)
                elif key=='U08':time.sleep(9.2)
                elif key=='U09':adb(serial,'shell','input','tap',(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
                release.set();time.sleep(.35)
                want=key in {'U01','U02','U09'}
                ui=wait_confirmation(lambda timeout:tree(serial,timeout=timeout)) if want else tree(serial)
                assert has_confirmation(ui)==want,'UNEXPECTED_CONFIRMATION_STATE'
                if want:tap(serial,'button2','android')
            after=prefs(serial);protected=after==before and private(serial,APP,'workflow-oracle.json')==oracle
            assert protected,'PROTECTED_STATE_CHANGED'
            new_ids=set(server.selection_events)-ids_before
            assert len(new_ids)==(0 if case['caseId'] in {'U23','U24'} else 1),'REQUEST_COUNT_MISMATCH'
            audits=[a for a in server.selection_audit if a['request_id'] in new_ids]
            row=dict(case,status='PASS',protected=True,requestCount=len(new_ids),audit=audits,
                harnessWallMs=round((time.monotonic()-started)*1000),targetInputs=0,modelCalls=0)
            rows.append(row);write(folder/'row.json',row);write(out/'results.json',rows)
            print('ENTRY PASS '+case['caseId']+' repeat '+str(case['repeat']),flush=True)
    except Exception as error:
        status='HARNESS_ERROR' if isinstance(error,RuntimeError) and str(error).startswith('Text input failed') else 'FAIL'
        row=dict(case,status=status,error=type(error).__name__,reason=str(error));rows.append(row)
        write(folder/'row.json',row);write(out/'failure.json',row)
        snap(serial,out/'failure.png')
        raise
    finally:
        release.set();server.shutdown();server.server_close();worker.join(3)
        if prior:adb(serial,'reverse','tcp:8765',prior)
        else:adb(serial,'reverse','--remove','tcp:8765')
        restored=restore_input(serial,saved)
        protected=prefs(serial)==before and private(serial,APP,'workflow-oracle.json')==oracle
        write(out/'restored.json',dict(inputRestored=restored,protectedStateUnchanged=protected,
            reverseRestored=reverse_target(serial)==prior,modelCalls=0))
        write(out/'requests.json',requests);write(out/'results.json',rows)
        write(out/'summary.json',summarize(rows,planned))
        if not restored or not protected or reverse_target(serial)!=prior:raise RuntimeError('RESTORATION_NOT_VERIFIED')
    return summarize(rows,planned)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--display',action='store_true')
    args=parser.parse_args();print(json.dumps(run(args.device,args.output,args.repeats,args.display)))
