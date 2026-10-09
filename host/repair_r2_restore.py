"""Restore only CURRENT r2 snapshots, then independently read back after final install."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from lab_transport import adb,HOSTS
from install_candidate import health
from prepare_g1 import save
import restore_deadline_repair as recovery

ROOT=Path(__file__).parent
RUN=ROOT/'evidence/flow-deadline-repair/r2'
PRIVATE=ROOT/'private/flow-deadline-repair-r2'
sha=lambda data:hashlib.sha256(data).hexdigest()

def run(retain=False):
    recovery.PRIVATE=PRIVATE
    recovery.run(RUN/'restoration/recovery',retain)
    out=RUN/'restoration/final-readback';out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for host in sorted(HOSTS):
        saved=json.loads((PRIVATE/host/'snapshot.json').read_text(encoding='utf-8'))
        current_health=health(host);packages=[]
        for pkg,before in saved['packages'].items():
            current=recovery.members(adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60))
            different=[name for name,digest in before['files'].items() if sha(current.get(name,b''))!=digest]
            # Android framework-generated ActivityThread IDs are not app business state.
            framework=[name for name in different if name=='shared_prefs/android.app.ActivityThread.IDS.xml']
            product=[name for name in different if name not in framework]
            path=adb(host,'shell','pm','path',pkg).decode().strip()
            if '\n' in path or not path.startswith('package:/data/app/') or not path.endswith('/base.apk'):raise ValueError('APK_PATH_NOT_UNIQUE')
            apk=sha(adb(host,'exec-out','cat',path.removeprefix('package:'),timeout=60))
            wanted=sha((ROOT/'native/build/manual/flow-probe-v102-final-boundary.apk').read_bytes()) if retain and pkg=='edu.sydney.probe' else before['apk_sha256']
            dump=adb(host,'shell','dumpsys','package',pkg).decode()
            new=sorted(set(current)-set(before['files']))
            packages.append({'package':pkg,'original_members':len(before['files']),
                 'different_original_members':different,'product_state_differences':product,
                 'framework_metadata_differences':framework,'strict_all_original_bytes_equal':not different,
                 'product_bytes_restored':not product,'installed_apk_sha256':apk,'apk_matches_policy':apk==wanted,
                 'version':[s.strip() for s in dump.splitlines() if 'versionCode=' in s or 'versionName=' in s],
                 'new_files':new,'new_files_only_status_receipts':all(re.fullmatch(r'files/flow-audit-[a-f0-9]{32}\.json',name) for name in new)})
        settings=[]
        for key,wanted in saved['settings'].items():
            namespace,name=key.split('.',1);actual=adb(host,'shell','settings','get',namespace,name).decode().strip()
            matches=set(actual.split(':'))==set(wanted.split(':')) if name=='enabled_accessibility_services' else actual==wanted
            settings.append({'setting':key,'matches_snapshot':matches})
        pid=adb(host,'shell','pidof','edu.sydney.probe').decode().strip()
        if not re.fullmatch(r'\d+',pid):raise ValueError('PROBE_PID_NOT_UNIQUE')
        threads=adb(host,'shell','ps','-T','-p',pid).decode();(out/(host+'-threads.txt')).write_text(threads,encoding='utf-8')
        residual=[s for s in threads.splitlines() if 'portable-skill' in s]
        target=any(s.rstrip().endswith('edu.sydney.parameterroom') for s in adb(host,'shell','ps','-A').decode().splitlines())
        reverse=recovery.mapping(adb(host,'reverse','--list').decode()).get('tcp:8765')==recovery.mapping(saved['reverse']).get('tcp:8765')
        row={'host':host,'packages':packages,'settings':settings,'health':current_health,
             'residual_runtime_threads':residual,'target_process_absent':not target,'owned_reverse_restored':reverse,
             'model_calls':0,'business_actions':0,'restore_policy':'RETAIN_SCOPED_TESTED_V102' if retain else 'ROLLBACK_CURRENT_R2_SNAPSHOT_V93'}
        row['product_restoration_passed']=all(p['product_bytes_restored'] and p['apk_matches_policy'] and p['new_files_only_status_receipts'] for p in packages) and all(s['matches_snapshot'] for s in settings) and current_health.get('final_status')=='READY' and not current_health.get('busy') and not residual and not target and reverse
        row['strict_byte_restoration_passed']=row['product_restoration_passed'] and all(p['strict_all_original_bytes_equal'] for p in packages)
        rows.append(row);save(out/(host+'.json'),row)
    # Read-only host process inventory; do not emit command lines/credentials.
    command="@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'flow_bridge\\.py' -and $_.CommandLine -match 'flow-deadline-repair' } | ForEach-Object { [int]$_.ProcessId }) | ConvertTo-Json -Compress"
    raw=subprocess.check_output(['powershell','-NoProfile','-Command',command]).decode().strip()
    gateways=json.loads(raw) if raw else []
    if isinstance(gateways,int):gateways=[gateways]
    result={'hosts':rows,'owned_gateway_pids':gateways,
        'product_restoration_passed':all(r['product_restoration_passed'] for r in rows) and not gateways,
        'strict_byte_restoration_passed':all(r['strict_byte_restoration_passed'] for r in rows) and not gateways,
        'framework_metadata_exception_disclosed':True,'model_calls':0}
    save(out/'summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='hosts'},ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--retain-tested-apk',action='store_true');a=parser.parse_args();run(a.retain_tested_apk)
