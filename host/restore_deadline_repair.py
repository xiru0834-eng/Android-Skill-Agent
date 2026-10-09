"""Exact current-run recovery; binary snapshots and narrow, backed-up file removal."""
import argparse,hashlib,io,json,re,tarfile
from pathlib import Path,PurePosixPath
from lab_transport import adb,HOSTS
from install_candidate import health
from g3_device_eval import reconnect
from prepare_g1 import save
ROOT=Path(__file__).parent
PRIVATE=ROOT/'private/flow-deadline-repair-r1'
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def members(raw):
    files={}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for entry in archive.getmembers():
            path=PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0] not in {'files','shared_prefs'}:raise ValueError('SNAPSHOT_SCOPE')
            if entry.isdir():continue
            if not entry.isfile() or entry.name in files:raise ValueError('SNAPSHOT_TYPE')
            files[entry.name]=archive.extractfile(entry).read()
    return files

def mapping(raw):return {p[1]:p[2] for line in raw.splitlines() if len(p:=line.split())==3}

def run(out,retain):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for host in sorted(HOSTS):
        if health(host).get('busy'):raise ValueError('DO_NOT_RESTORE_LIVE_TASK')
        snapshot=json.loads((PRIVATE/host/'snapshot.json').read_text(encoding='utf-8'))
        backup=PRIVATE/('after-'+out.name)/host;backup.mkdir(parents=True,exist_ok=False)
        details=[]
        for pkg in ('edu.sydney.parameterroom','edu.sydney.probe'):
            raw=(PRIVATE/host/(pkg+'.tar')).read_bytes();saved=snapshot['packages'][pkg]
            if sha(raw)!=saved['tar_sha256']:raise ValueError('SNAPSHOT_DIGEST')
            old=members(raw)
            if {p:sha(v) for p,v in old.items()}!=saved['files']:raise ValueError('SNAPSHOT_MEMBER_DIGEST')
            adb(host,'shell','am','force-stop',pkg) # cancel owned pending target callbacks / stop transient authority
            current_raw=adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60)
            (backup/(pkg+'.tar')).write_bytes(current_raw);current=members(current_raw)
            changes=[p for p,v in old.items() if current.get(p)!=v]
            # Only this evaluator's known namespaces may be restored automatically.
            allowed=re.compile(r'files/(?:portable|published-flow|flow|product-ui)[a-zA-Z0-9_.-]*|shared_prefs/(?:portable_approval|flow_knowledge|parameter_room)\.xml|shared_prefs/android\.app\.ActivityThread\.IDS\.xml|files/parameter-room-oracle\.json')
            if any(not allowed.fullmatch(p) for p in changes):raise ValueError('UNOWNED_CHANGED_FILE: '+','.join(p for p in changes if not allowed.fullmatch(p)))
            for path in changes:
                adb(host,'shell','run-as',pkg,'sh','-c',"'cat > "+path+"'",input=old[path])
            new=set(current)-set(old);removed=[]
            owned=re.compile(r'files/(?:flow-audit|product-ui-audit)-[a-f0-9]{32}\.json|files/(?:flow|product-ui)-incoming\.json')
            for path in sorted(new):
                if owned.fullmatch(path):adb(host,'shell','run-as',pkg,'rm',path);removed.append(path)
            verified=members(adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60))
            checks={p:sha(verified.get(p,b''))==sha(v) for p,v in old.items()}
            details.append({'package':pkg,'restored_changed_files':changes,'original_members_checked':len(checks),
                'original_members_match':all(checks.values()),'removed_owned_test_files':removed,
                'retained_new_files':sorted(set(verified)-set(old)),'binary_backup':str(backup/(pkg+'.tar'))})
        if not retain:
            result=adb(host,'install','-r','-d',str(PRIVATE/host/'edu.sydney.probe.apk'),timeout=60).decode()
            if 'Success' not in result:raise ValueError('ROLLBACK_INSTALL_FAILED')
        prior=mapping(snapshot['reverse']);current=mapping(adb(host,'reverse','--list').decode())
        if current.get('tcp:8765') in {'tcp:49721','tcp:49722'}:
            if 'tcp:8765' in prior:adb(host,'reverse','tcp:8765',prior['tcp:8765'])
            else:adb(host,'reverse','--remove','tcp:8765')
        reconnect(host,PRIVATE/host/'snapshot.json')
        setting_checks=[]
        for key,wanted in snapshot['settings'].items():
            namespace,name=key.split('.',1);value=adb(host,'shell','settings','get',namespace,name).decode().strip()
            # Do not overwrite unrelated services or any new user settings.
            matches=set(value.split(':'))==set(wanted.split(':')) if name=='enabled_accessibility_services' else value==wanted
            setting_checks.append({'setting':key,'matches_snapshot':matches})
        final=health(host)
        row={'host':host,'packages':details,'settings':setting_checks,'reverse_restored':mapping(adb(host,'reverse','--list').decode()).get('tcp:8765')==prior.get('tcp:8765'),
            'probe_apk':'RETAINED_SCOPED_TESTED_V97' if retain else 'ROLLBACK_CURRENT_RUN_SNAPSHOT_V93',
            'probe_health':final,'target_stopped':True,'old_transient_authority_restored':False}
        row['passed']=all(p['original_members_match'] for p in details) and all(s['matches_snapshot'] for s in setting_checks) and row['reverse_restored'] and final.get('final_status')=='READY' and not final.get('busy')
        rows.append(row);save(out/(host+'.json'),row);print(host,'RESTORED',row['passed'],flush=True)
    save(out/'summary.json',{'passed':all(r['passed'] for r in rows),'hosts':rows,'model_calls':0})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--retain-tested-apk',action='store_true');a=p.parse_args();run(a.out,a.retain_tested_apk)
