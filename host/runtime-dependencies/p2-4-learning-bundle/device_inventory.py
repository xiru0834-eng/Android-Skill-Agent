"""Evaluator-only inventory/backup. Does not exist in the Agent/query dependency graph."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from android_bridge import ADB,SERIALS
from acceptance_tools import verified_file_digest

BASE=Path(__file__).resolve().parent
KNOWN_FILES=['files/portable-approved.json','files/portable-incoming.json',
             'files/parameter-skill-53b027de1ce94199cde0115d2c350512f2c85aab1dbb50a008e0587fc12ac977.json',
             'files/parameter-skill-64b0d46765b51868e3e7e8d4bf76416069bbbbe5d95463238c412804490f5480.json',
             'shared_prefs/portable_approval.xml']

def command(serial,*args):
    if serial not in SERIALS:raise ValueError('UNKNOWN_HOST')
    r=subprocess.run([str(ADB),'-s',serial,*args],capture_output=True,timeout=20)
    if r.returncode:raise RuntimeError('ADB_INVENTORY_FAILED')
    return r.stdout

def inventory(serial,*,backup=False):
    out={'serial':serial,'packages':{},'protected_files':{}}
    for pkg in ['edu.sydney.probe','edu.sydney.transferlab','edu.sydney.parameterroom']:
        info=command(serial,'shell','dumpsys','package',pkg).decode('utf-8')
        code=re.search(r'versionCode=(\d+)',info);name=re.search(r'versionName=([^\r\n]+)',info)
        out['packages'][pkg]={'version_code':int(code[1]) if code else None,'version_name':name[1].strip() if name else None}
    for path in KNOWN_FILES:
        # shell cat may translate LF on this Windows/device transport. Verify presence/size
        # using shell status, then read original bytes via exec-out. Never trust exec-out's
        # exit code alone for a missing file (the old discovery error is preserved).
        size=subprocess.run([str(ADB),'-s',serial,'shell','run-as','edu.sydney.probe','stat','-c','%s',path],capture_output=True,timeout=15)
        if size.returncode:
            if b'No such file or directory' in size.stdout+size.stderr:
                out['protected_files'][path]={'status':'NOT_PRESENT'};continue
            raise RuntimeError('PROTECTED_FILE_STAT_ERROR')
        expected=int(size.stdout.strip())
        r=subprocess.run([str(ADB),'-s',serial,'exec-out','run-as','edu.sydney.probe','cat',path],capture_output=True,timeout=15)
        if r.returncode:raise RuntimeError('PROTECTED_FILE_READ_ERROR')
        entry=verified_file_digest(r.stdout,expected);sha=entry['sha256'];out['protected_files'][path]=entry
        if backup:
            dst=BASE/'evidence'/'backups'/serial;dst.mkdir(parents=True,exist_ok=True)
            target=dst/path.replace('/','--')
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest()!=sha:raise RuntimeError('BACKUP_ALREADY_EXISTS_DIFFERENT')
            else:target.write_bytes(r.stdout)
    for kind,args in {'accessibility':['shell','settings','get','secure','enabled_accessibility_services'],
                      'size':['shell','wm','size'],'density':['shell','wm','density'],
                      'font_scale':['shell','settings','get','system','font_scale']}.items():
        out[kind]=command(serial,*args).decode('utf-8').strip()
    return out

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['before','after']);a=p.parse_args()
    value=[inventory(s,backup=a.phase=='before') for s in sorted(SERIALS)]
    dest=BASE/'evidence'/('device-inventory-'+a.phase+'.json')
    if dest.exists():raise RuntimeError('INVENTORY_EXISTS_DO_NOT_OVERWRITE')
    dest.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'phase':a.phase,'hosts':[v['serial'] for v in value],'protected_files':[len(v['protected_files']) for v in value]},ensure_ascii=False))
