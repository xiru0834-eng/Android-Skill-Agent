"""Restore this R3 snapshot, with binary backups and independent post-install reads."""
import json
from pathlib import Path
import re
import subprocess

from lab_transport import adb, ADB
from install_candidate import health
from g3_device_eval import reconnect
from prepare_g1 import save
from repair_r3_gate import sha
from restore_deadline_repair import members, mapping
import repair_r3 as r3

MUTABLE=re.compile(r'files/(?:flow-incoming|published-flow-incoming|published-flow-local|flow-user-selection|flow-user-result|product-ui-incoming|parameter-room-oracle)\.json|shared_prefs/(?:flow_knowledge_review|portable_approval|parameter_room|android\.app\.ActivityThread\.IDS)\.xml')
NEW_OWNED=re.compile(r'files/(?:flow-audit|product-ui-audit)-[a-f0-9]{32}\.json|files/(?:flow-incoming|product-ui-incoming|published-flow-incoming|flow-user-selection|flow-user-result|published-flow-local)\.json')


def changes(old,current):
    changed=[p for p,v in old.items() if current.get(p)!=v]
    unknown=[p for p in changed if not MUTABLE.fullmatch(p)]
    if unknown:raise ValueError('UNOWNED_CHANGED_FILE:'+','.join(unknown))
    return changed


def run():
    out=r3.RUN/'restoration'
    out.mkdir(exist_ok=False)
    rows=[]
    for host in r3.HOSTS:
        snapshot=json.loads((r3.PRIVATE/host/'snapshot.json').read_text(encoding='utf-8'))
        if health(host).get('busy'):raise ValueError('LIVE_TASK_NOT_RESTORABLE')
        backup=r3.PRIVATE/'after-r3'/host
        backup.mkdir(parents=True,exist_ok=False)
        originals={}
        for pkg in ('edu.sydney.probe','edu.sydney.parameterroom'):
            saved=snapshot['packages'][pkg]
            original=(r3.PRIVATE/host/(pkg+'.tar')).read_bytes()
            if sha(original)!=saved['tar_sha256']:raise ValueError('SNAPSHOT_DIGEST')
            old=members(original)
            if {p:sha(v) for p,v in old.items()}!=saved['files']:raise ValueError('SNAPSHOT_MEMBERS')
            originals[pkg]=old
            adb(host,'shell','am','force-stop',pkg)
            raw=adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60)
            (backup/(pkg+'.tar')).write_bytes(raw)
            if members((backup/(pkg+'.tar')).read_bytes())!=members(raw):raise ValueError('BACKUP_READBACK')
            changes(old,members(raw)) # Fail before data overwrite if user-owned content changed.
        apk=r3.PRIVATE/host/'edu.sydney.probe.apk'
        if sha(apk.read_bytes())!=snapshot['packages']['edu.sydney.probe']['apk_sha256']:raise ValueError('SNAPSHOT_APK')
        installed=adb(host,'install','-r','-d',str(apk),timeout=60).decode()
        if 'Success' not in installed:raise ValueError('SNAPSHOT_INSTALL_FAILED')
        details=[]
        for pkg,old in originals.items():
            adb(host,'shell','am','force-stop',pkg)
            current=members(adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60))
            changed=changes(old,current)
            for p in changed:
                adb(host,'shell','run-as',pkg,'sh','-c',"'cat > "+p+"'",input=old[p])
            removed=[]
            for p in sorted(set(current)-set(old)):
                if NEW_OWNED.fullmatch(p):
                    if p not in members((backup/(pkg+'.tar')).read_bytes()):
                        raise ValueError('NEW_FILE_NOT_BACKED_UP:'+p)
                    adb(host,'shell','run-as',pkg,'rm',p)
                    removed.append(p)
            details.append({'package':pkg,'restored_changed_files':changed,'removed_backed_up_r3_files':removed,
                            'backup':str(backup/(pkg+'.tar'))})
        prior=mapping(snapshot['reverse'])
        current=mapping(adb(host,'reverse','--list').decode())
        if current.get('tcp:8765') in {'tcp:49721','tcp:49722'}:
            if 'tcp:8765' in prior:adb(host,'reverse','tcp:8765',prior['tcp:8765'])
            else:adb(host,'reverse','--remove','tcp:8765')
        reconnect(host,r3.PRIVATE/host/'snapshot.json')
        final_health=health(host)
        for detail in details:
            pkg=detail['package']
            actual=members(adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60))
            original=originals[pkg]
            checks={p:sha(actual.get(p,b''))==sha(v) for p,v in original.items()}
            path=adb(host,'shell','pm','path',pkg).decode().strip().removeprefix('package:')
            actual_apk=sha(adb(host,'exec-out','cat',path,timeout=60))
            detail.update(original_members=len(checks),original_member_checks=checks,all_original_members_match=all(checks.values()),
                          installed_apk_sha256=actual_apk,apk_matches_current_r3_snapshot=actual_apk==snapshot['packages'][pkg]['apk_sha256'],
                          new_observation_metadata=sorted(set(actual)-set(original)))
        settings=[]
        for key,wanted in snapshot['settings'].items():
            namespace,name=key.split('.',1)
            actual=adb(host,'shell','settings','get',namespace,name).decode().strip()
            matches=set(actual.split(':'))==set(wanted.split(':')) if name=='enabled_accessibility_services' else actual==wanted
            settings.append({'setting':key,'matches_snapshot':matches})
        display={k:adb(host,'shell','wm',k).decode() for k in ('size','density')}
        pid_read=subprocess.run([ADB,'-s',host,'shell','pidof','edu.sydney.parameterroom'],capture_output=True,timeout=20)
        if pid_read.returncode not in (0,1):raise ValueError('TARGET_PROCESS_READ_FAILED')
        target_pid=pid_read.stdout.decode().strip()
        row={'host':host,'snapshot':str(r3.PRIVATE/host/'snapshot.json'),'packages':details,'settings':settings,
             'display_matches':display==snapshot['display'],
             'reverse_matches':mapping(adb(host,'reverse','--list').decode())==prior,
             'health':final_health,'target_process_absent':not target_pid,
             'foreground':adb(host,'shell','dumpsys','activity','activities').decode(),
             'transient_authority_restored':False,'model_calls_during_restore':0}
        row['passed']=(all(d['all_original_members_match'] and d['apk_matches_current_r3_snapshot'] for d in details)
            and all(s['matches_snapshot'] for s in settings) and row['display_matches'] and row['reverse_matches']
            and row['target_process_absent'] and final_health.get('final_status')=='READY' and final_health.get('busy') is False)
        rows.append(row)
        save(out/(host+'.json'),row)
        print('CURRENT_SNAPSHOT_RESTORED',host,row['passed'],flush=True)
        if not row['passed']:raise ValueError('INDEPENDENT_RESTORE_READBACK_FAILED')
    save(out/'summary.json',{'passed':all(r['passed'] for r in rows),'hosts':r3.HOSTS,'restore_policy':'CURRENT_R3_SNAPSHOT',
         'new_metadata_is_not_old_observation':True,'backed_up_test_files_removed_only':True,'model_requests':0})


if __name__=='__main__':run()
