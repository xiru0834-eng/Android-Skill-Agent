"""Verified scoped backup before a non-destructive Probe upgrade; never stores pairing."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import subprocess
import tarfile
from workflow_experiment import ADB

PROBE='edu.sydney.probe'
PREFERENCES={'recorded_workflows','teaching_journey','skills','two_step_skills',
             'deployments','trace_bundles','workflow_resources'}


def allowed(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',name):return False
    if name.startswith('/') or '..' in name.split('/'):return False
    if name.startswith('shared_prefs/'):
        return name in {'shared_prefs/'+key+'.xml' for key in PREFERENCES}
    return bool(re.fullmatch(r'files/(workflow[-A-Za-z0-9_.]*|recorded-workflow[-A-Za-z0-9_.]*|teaching[-A-Za-z0-9_.]*)',name))


def validate_archive(blob,expected):
    if not expected or any(not allowed(name) for name in expected):raise ValueError('INVALID_BACKUP_SCOPE')
    found={}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob),mode='r:') as bundle:
            for member in bundle:
                if member.isdir():continue
                if not member.isfile() or member.name in found or member.name not in expected:
                    raise ValueError('UNEXPECTED_BACKUP_MEMBER')
                with bundle.extractfile(member) as data:
                    found[member.name]=hashlib.file_digest(data,'sha256').hexdigest()
    except (tarfile.TarError,EOFError,OSError) as error:
        raise ValueError('INVALID_TAR') from error
    if found!=expected:raise ValueError('BACKUP_CONTENT_MISMATCH')
    return found


def adb_bytes(serial,*args,timeout=90,input_data=None):
    result=subprocess.run([str(ADB),'-s',serial,*map(str,args)],input=input_data,capture_output=True,timeout=timeout)
    if result.returncode:raise ValueError('ADB_OPERATION_FAILED')
    return result.stdout


def device_manifest(serial):
    raw=adb_bytes(serial,'shell','run-as',PROBE,'find','files','shared_prefs','-type','f',
                  '-exec','sha256sum','{}','+').decode('utf-8',errors='strict')
    result={}
    for line in raw.splitlines():
        match=re.fullmatch(r'([a-f0-9]{64})\s+(.+)',line)
        if not match:raise ValueError('INVALID_DEVICE_MANIFEST')
        digest,name=match.groups()
        if allowed(name):
            if name in result:raise ValueError('DUPLICATE_DEVICE_MEMBER')
            result[name]=digest
    if 'shared_prefs/recorded_workflows.xml' not in result:raise ValueError('MISSING_WORKFLOW_PREFERENCES')
    return result


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def backup(serial,out):
    out.mkdir(parents=True,exist_ok=False)
    expected=device_manifest(serial);save(out/'manifest-before.json',expected)
    remote='cache/entry-backup-'+secrets.token_hex(8)+'.tar'
    # A list on stdin avoids CreateProcess's argument limit without a shell pipe.
    names=''.join(name+'\n' for name in sorted(expected)).encode('utf-8')
    adb_bytes(serial,'shell','-T','run-as',PROBE,'tar','-cf',remote,'-T','-',input_data=names)
    digest=adb_bytes(serial,'shell','run-as',PROBE,'sha256sum',remote).decode().split()[0]
    blob=adb_bytes(serial,'exec-out','run-as',PROBE,'cat',remote)
    (out/'workflow-backup.tar').write_bytes(blob)
    if hashlib.sha256(blob).hexdigest()!=digest:raise ValueError('BACKUP_TRANSPORT_MISMATCH')
    validated=validate_archive(blob,expected)
    if device_manifest(serial)!=expected:raise ValueError('STATE_CHANGED_DURING_BACKUP')
    save(out/'backup-validation.json',dict(valid=True,members=len(validated),sha256=digest,
         deviceArchive=remote,pairingIncluded=False,verifiedBeforeInstall=True))
    return expected


def deploy(serial,apk,out,version):
    apk=Path(apk).resolve();out=Path(out)
    if not apk.is_file() or type(version) is not int or version<1:raise ValueError('INVALID_DEPLOYMENT_ARGUMENT')
    expected=backup(serial,out)
    if device_manifest(serial)!=expected:raise ValueError('STATE_CHANGED_BEFORE_INSTALL')
    identity=hashlib.sha256(apk.read_bytes()).hexdigest()
    save(out/'install-gate.json',dict(backupValid=True,expectedVersion=version,apkSha256=identity))
    reply=adb_bytes(serial,'install','-r',apk).decode()
    if 'Success' not in reply:raise ValueError('INSTALL_NOT_CONFIRMED')
    package=adb_bytes(serial,'shell','dumpsys','package',PROBE).decode()
    if not re.search(r'\bversionCode='+str(version)+r'\b',package):raise ValueError('INSTALLED_VERSION_MISMATCH')
    paths=adb_bytes(serial,'shell','pm','path',PROBE).decode().splitlines()
    if len(paths)!=1 or not paths[0].startswith('package:/data/app/'):raise ValueError('INSTALLED_PATH_MISMATCH')
    installed=adb_bytes(serial,'exec-out','cat',paths[0][8:])
    if hashlib.sha256(installed).hexdigest()!=identity:raise ValueError('INSTALLED_APK_MISMATCH')
    after=device_manifest(serial);save(out/'manifest-after.json',after)
    if after!=expected:raise ValueError('SCOPED_STATE_CHANGED_AFTER_INSTALL')
    save(out/'deployment.json',dict(status='PASS',version=version,apkSha256=identity,
         installReply=reply.strip(),scopedStateUnchanged=True,backupVerifiedBeforeInstall=True))
    return expected


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--apk',type=Path)
    parser.add_argument('--version',type=int,default=34)
    args=parser.parse_args()
    try:
        result=deploy(args.device,args.apk,args.output,args.version) if args.apk else backup(args.device,args.output)
        print('Verified scoped files: '+str(len(result))+'; pairing excluded.')
    except Exception as error:
        if args.output.is_dir():save(args.output/'failure.json',dict(error=type(error).__name__,reason=str(error)))
        raise
