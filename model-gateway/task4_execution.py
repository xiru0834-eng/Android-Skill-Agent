"""Frozen transfer trials, fixture setup separated from unchanged business executor."""
import json
import random
import secrets
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
import task3_device_checks as device
from named_journey_device import prefs,library,wait_fixture
from transfer_run import private
from workflow_experiment import adb,write
from workflow_capture import APP,PROBE
from task4_protocol import cases,source_record,DISPLAYS,display_state,display_matches,canonical,summarize
from task4_transfer import restore_commands,fault_score
from task4_files import SERIAL,gate,snapshot,state,click
from task3_audit import rejudge


def read_display():
    raw=dict(size=adb(SERIAL,'shell','wm','size'),density=adb(SERIAL,'shell','wm','density'),font=adb(SERIAL,'shell','settings','get','system','font_scale'))
    return dict(raw=raw,state=display_state(**raw))


def set_display(label):
    gate('Task4Transfer');size,density,font=DISPLAYS[label]
    for command in [['wm','size','x'.join(map(str,size))],['wm','density',str(density)],['settings','put','system','font_scale',str(font)]]:
        adb(SERIAL,'shell',*command)
    actual=read_display()
    if not display_matches(label,actual['state']):raise RuntimeError('DISPLAY_OVERRIDE_NOT_CONFIRMED')
    return actual


def display_proof(row,out):
    actual=read_display();ui=snapshot(out,'fixture-public')
    png=(out/'fixture-public.png').read_bytes()
    if png[:8]!=b'\x89PNG\r\n\x1a\n':raise RuntimeError('SCREENSHOT_NOT_PNG')
    dimensions=list(struct.unpack('>II',png[16:24]));actual['pngDimensions']=dimensions
    if dimensions!=DISPLAYS[row['display']][0] or not display_matches(row['display'],actual['state']):raise RuntimeError('ACTUAL_SCREEN_DIFFERS')
    write(out/'display.json',actual);return ui


def fixture(row,skill):
    case_id=secrets.token_hex(8);layout='single' if skill['startPage']=='single' else 'multi'
    fault=row.get('fault','normal')
    adb(SERIAL,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId',case_id,'--es','layout',layout,
        '--es','appearance',row['appearance'],'--es','initial',','.join(map(str,row['initial'])),'--es','fault',fault)
    before=wait_fixture(lambda:private(SERIAL,APP,'workflow-oracle.json'),case_id,row['initial'])
    if before['fault']!=fault or before['layout']!=layout or before['appearance']!=row['appearance']:raise RuntimeError('FIXTURE_CONDITION_DIFFERS')
    return case_id,before


def start(skill):
    entries=json.loads(prefs(SERIAL)['library']);matches=[i for i,e in enumerate(entries) if canonical(e['skill'])==canonical(skill)]
    if len(matches)!=1:raise RuntimeError('ORIGINAL_SKILL_NOT_UNIQUE')
    library(SERIAL);device.management_control('libraryRun'+str(matches[0]));device.review_controls(device.tree(SERIAL))
    click(lambda n:n.get('resource-id')=='android:id/button1')


def one(row,source,out):
    out.mkdir(parents=True,exist_ok=False);skill=source_record(row['flow'])['skill']
    original=source/row['flow'];meta=json.loads((original/'file.json').read_text(encoding='utf-8'))
    from task4_protocol import package_bytes
    package_bytes((original/meta['filename']).read_bytes(),source_record(row['flow'])['package'])
    write(out/'device.json',gate('Task4Transfer'));write(out/'skill.json',skill)
    case_id,before=fixture(row,skill);write(out/'case.json',dict(row,caseId=case_id));write(out/'before.json',before)
    display_proof(row,out)
    try:previous=private(SERIAL,PROBE,'recorded-workflow-result.json')['runId']
    except RuntimeError as error:
        if 'No such file' not in str(error):raise
        previous=None
    write(out/'previous.json',dict(previousRun=previous))
    start(skill)
    result,oracle,journal,samples,disk=device.collect(skill,row['initial'],case_id,out,previous)
    if result['runId']==previous:raise RuntimeError('OLD_RESULT_REUSED')
    ui=snapshot(out,'terminal-public')
    score=(fault_score(row,skill,row['initial'],result,oracle,journal,samples,disk,case_id,ui) if row['group']=='negative'
        else rejudge(skill,row['initial'],result,oracle,journal,samples,disk,case_id))
    write(out/'score.json',score);okay=score.get('safeStop',score.get('correctCompletion',False))
    item=dict(id=row['id'],status='PASS' if okay else ('FAIL' if score['evidenceQualified'] else 'UNVERIFIED'),
        evidenceQualified=score['evidenceQualified'],elapsedMs=score['elapsedMs'],falseSuccess=score['falseSuccess'],inputs=len(result['actions']))
    print(row['id']+' '+item['status']+' '+str(score['errors']),flush=True);return item


def confirm(source,out,development=False):
    plan=[r for r in cases() if r['group']!='chain']
    if development:
        plan=[r for r in plan if r['group']=='normal' and r['display']=='D0' and r['appearance']=='native' and r['initialIndex']==0 and r['repeat']==0]
    else:
        ordered=[];rng=random.Random(400731)
        for label in DISPLAYS:
            block=[r for r in plan if r['display']==label];rng.shuffle(block);ordered+=block
        plan=ordered
    write(out/'execution-order.json',plan);write(out/'development.json',dict(developmentOnly=development,paidCalls=0))
    original=read_display();write(out/'display-before.json',original);before=state();write(out/'preferences-before.json',before)
    rows=[];display=None
    try:
        for row in plan:
            where=out/row['id']
            try:
                if row['display']!=display:set_display(row['display']);display=row['display']
                item=one(row,source,where);rows.append(item);write(out/'rows.json',rows)
                if not development:write(out/'summary.json',summarize(rows))
                if item['status']!='PASS':raise RuntimeError('CONFIRMATION_NOT_CORRECT')
            except Exception as error:
                where.mkdir(parents=True,exist_ok=True)
                if not any(r['id']==row['id'] for r in rows):
                    rows.append(dict(id=row['id'],status='BLOCKED',evidenceQualified=False,reason=str(error)));write(out/'rows.json',rows)
                write(where/'failure.json',dict(reason=str(error),paidCalls=0))
                try:snapshot(where,'failure')
                except Exception:pass
                raise
    finally:
        try:
            gate('Task4Transfer')
            for command in restore_commands(original['state']):adb(SERIAL,'shell',*command)
            after=read_display();write(out/'display-after.json',after)
            restored=after['state']==original['state'];write(out/'restoration.json',dict(restored=restored,paidCalls=0))
            if not restored:raise RuntimeError('DISPLAY_NOT_RESTORED')
        except Exception as error:
            write(out/'restoration-failure.json',dict(reason=str(error)));raise
        finally:
            after=state();write(out/'preferences-after.json',after)
            old=json.loads(before.get('library','[]'));new=json.loads(after.get('library','[]'))
            write(out/'library-preservation.json',dict(preserved=old==new,paidCalls=0))
            if old!=new:raise RuntimeError('OLD_LIBRARY_CHANGED')
