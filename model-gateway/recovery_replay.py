"""Replay one sealed experimental case; never import or approve a skill silently."""
import argparse
import json
import shutil
import time
from pathlib import Path
import workflow_experiment
from workflow_experiment import adb,write
from workflow_capture import APP,PROBE
from transfer_run import approved,run
from migration_matrix import CONFIGS,display,effective_display_value
from recovery_matrix import install,installed_hash,source_closure
from recovery_evidence import verify,digest,diagnose


def select_case(protocol,index):
    flat=[dict(config=b['config'],policy=b['policy'],cases=[c]) for b in protocol['blocks'] for c in b['cases']]
    if type(index) is not int or not 0<=index<len(flat):raise ValueError('CASE_INDEX')
    return flat[index]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--index',type=int,required=True)
    parser.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    parser.add_argument('--adb',type=Path,default=workflow_experiment.ADB)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--allow-experiment',action='store_true')
    args=parser.parse_args()
    if not args.allow_experiment:parser.error('Explicit experimental replay required')
    workflow_experiment.ADB=args.adb.resolve();bundle=args.bundle.resolve();root=args.output.resolve()
    if not verify(bundle)['valid']:raise RuntimeError('BUNDLE_INTEGRITY_FAILED')
    load=lambda path:json.loads(path.read_text(encoding='utf-8'))
    source=load(bundle/'protocol.json');block=select_case(source,args.index);serial=args.device
    skill=load(bundle/'skill.json')
    if skill.get('appPackage')!=APP or approved(serial)!=skill:raise RuntimeError('REVIEW_SAME_SKILL_ON_TARGET_FIRST')
    original=display(serial)
    if 'Override' in str(original):raise RuntimeError('DISPLAY_ALREADY_OVERRIDDEN')
    if block['config'] in CONFIGS and serial!='emulator-5554':raise RuntimeError('DISPLAY_CHANGES_ARE_EMULATOR_ONLY')
    root.mkdir(parents=True,exist_ok=False);write(root/'skill.json',skill)
    artifacts={};backups={}
    for key,value in source['artifacts'].items():
        name=value['path']
        if Path(name).name!=name or digest(bundle/name)!=value['sha256']:raise RuntimeError('ARTIFACT_MISMATCH')
        shutil.copyfile(bundle/name,root/name);artifacts[key]=value
    for package,name in [(PROBE,'original-probe.apk'),(APP,'original-fixture.apk')]:
        path,sha=installed_hash(serial,package);adb(serial,'pull',path,str(root/name))
        if digest(root/name)!=sha:raise RuntimeError('BACKUP_MISMATCH')
        backups[package]=dict(path=name,sha256=sha)
    tools=root/'harness';tools.mkdir()
    for name in source_closure(Path(__file__).parent,['recovery_replay.py','recovery_audit.py']):
        shutil.copyfile(Path(__file__).with_name(name),tools/name)
    write(root/'protocol.json',dict(device=serial,blocks=[block],artifacts=artifacts,backups=backups,
        original=original,skillSha256=digest(root/'skill.json'),sourceBundleManifestSha256=digest(bundle/'integrity.json'),
        sourceCaseIndex=args.index,modelCalls=0,budgetMs=30000,execution='Normal reviewed skill Run button',
        scope='Single replay; not an independent new skill or a repeated full teach/import process.'))
    rows=[]
    try:
        install(serial,root/artifacts['fixture']['path']);install(serial,root/artifacts[block['policy']]['path'])
        if block['config'] in CONFIGS:
            size,density=CONFIGS[block['config']]
            adb(serial,'shell','wm','size',size);adb(serial,'shell','wm','density',density);time.sleep(3)
            actual=display(serial)
            if (effective_display_value(actual['size']),effective_display_value(actual['density']))!=(size,density):raise RuntimeError('DISPLAY_MISMATCH')
        for key,package in [('fixture',APP),(block['policy'],PROBE)]:
            if installed_hash(serial,package)[1]!=artifacts[key]['sha256']:raise RuntimeError('INSTALLED_HASH_MISMATCH')
        launch=adb(serial,'shell','am','start','-W','-n',PROBE+'/.MainActivity','-f','0x04000000')
        if 'Status: ok' not in launch:raise RuntimeError('CONTROLLER_NOT_READY')
        time.sleep(2)
        write(root/'block-00.json',dict(config=block['config'],policy=block['policy'],display=display(serial),
            installedSha256=installed_hash(serial,PROBE)[1],fixtureSha256=installed_hash(serial,APP)[1]))
        result=run(serial,block['cases'][0],root/'run-000',skill)
        terminal=load(root/'run-000/terminal.json');journal=load(root/'run-000/journal.json')
        if terminal['recoveryPolicy']!=block['policy']:raise RuntimeError('WRONG_POLICY')
        write(root/'run-000/diagnosis.json',diagnose(terminal,journal))
        rows.append(dict(config=block['config'],policy=block['policy'],**result));print(json.dumps(result),flush=True)
    except Exception as error:
        write(root/'aborted.json',dict(error=str(error)))
        rows.append(dict(config=block['config'],policy=block['policy'],case=block['cases'][0],evidence_complete=False,infrastructureFailure=str(error)))
        raise
    finally:
        write(root/'results.json',rows);restored={}
        for package,backup in backups.items():
            try:
                install(serial,root/backup['path']);restored[package]=installed_hash(serial,package)[1]==backup['sha256']
            except Exception as error:restored[package]=dict(error=str(error))
        if block['config'] in CONFIGS:
            adb(serial,'shell','wm','size','reset');adb(serial,'shell','wm','density','reset')
        restored['display']=display(serial)==original;restored['approval']=approved(serial)==skill
        write(root/'restored.json',restored)
        if not all(v is True for v in restored.values()):raise RuntimeError('RESTORATION_INCOMPLETE')


if __name__=='__main__':main()
