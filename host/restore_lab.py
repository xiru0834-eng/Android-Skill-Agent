"""Restore only current-run laboratory state; no source approval transfer or broad deletion."""
import hashlib,io,json,re,tarfile,xml.etree.ElementTree as ET
from pathlib import Path,PurePosixPath
from lab_transport import adb,HOSTS
from install_candidate import health
from prepare_g1 import save
ROOT=Path(__file__).parent

def digest(data):return hashlib.sha256(data).hexdigest()

def prior_archive(host,package):
    source=ROOT/'private/before-v93'/host/(package+'.tar');raw=source.read_bytes()
    # Earlier shell stdout added CR before each LF. Preserve the untouched raw
    # capture and recover its binary channel in a NEW artifact, never in-place.
    clean=raw.replace(b'\r\n',b'\n')
    if clean.replace(b'\n',b'\r\n')!=raw or len(clean)%512:raise ValueError('BACKUP_CHANNEL_UNCONFIRMED')
    with tarfile.open(fileobj=io.BytesIO(clean),mode='r:') as archive:
        files={}
        for entry in archive.getmembers():
            path=PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in ('files','shared_prefs'):raise ValueError('BACKUP_PATH_ERROR')
            if entry.isdir():continue
            if not entry.isfile() or entry.name in files:raise ValueError('BACKUP_TYPE_ERROR')
            files[entry.name]=archive.extractfile(entry).read()
    repaired=ROOT/'private/recovered-before-v93'/host/(package+'.tar');repaired.parent.mkdir(parents=True,exist_ok=True)
    if repaired.exists():raise ValueError('PRESERVE_PREVIOUS_RECOVERY')
    repaired.write_bytes(clean)
    return files,{'raw_sha256':digest(raw),'recovered_sha256':digest(clean),'transport_roundtrip':True,'members':len(files)}

def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for host in sorted(HOSTS):
        if health(host).get('busy'):raise ValueError('DO_NOT_RESTORE_LIVE_TASK')
        before=ROOT/'private/after-wireup-r15'/host;before.mkdir(parents=True,exist_ok=False)
        for package in ('edu.sydney.parameterroom','edu.sydney.probe'):
            data=adb(host,'exec-out','run-as',package,'tar','cf','-','files','shared_prefs')
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as archive:archive.getmembers()
            (before/(package+'.tar')).write_bytes(data)
        old,recovery=prior_archive(host,'edu.sydney.parameterroom')
        required={'files/parameter-room-oracle.json','shared_prefs/parameter_room.xml'}
        if not required<=set(old) or set(old)-required-{'shared_prefs/android.app.ActivityThread.IDS.xml'}:raise ValueError('PARAMETER_SNAPSHOT_SCOPE')
        state=ET.fromstring(old['shared_prefs/parameter_room.xml']).find("string[@name='state']").text
        values=[int(v) for v in state.split(',')]
        observed=json.loads(old['files/parameter-room-oracle.json'])['state']
        expected={'bedroom_light.power':'on' if values[0] else 'off','bedroom_light.brightnessPercent':values[1],
            'bedroom_ac.power':'on' if values[2] else 'off','bedroom_ac.temperatureCelsius':values[3]}
        if observed!=expected:raise ValueError('SNAPSHOT_STATE_CONFLICT')
        adb(host,'shell','am','force-stop','edu.sydney.parameterroom') # cancel all test-owned delayed callbacks
        writes=[]
        for path,data in old.items():
            # Exact recovered members only, fixed allowed namespace, no extraction
            # of arbitrary archive paths or recursive removal of App directories.
            adb(host,'shell','run-as','edu.sydney.parameterroom','sh','-c',"'cat > "+path+"'",input=data)
            actual=adb(host,'exec-out','run-as','edu.sydney.parameterroom','cat',path)
            writes.append({'path':path,'sha256':digest(actual),'matches_snapshot':actual==data})
        native,native_recovery=prior_archive(host,'edu.sydney.probe');checks=[]
        for path in ('files/portable-approved.json','shared_prefs/portable_approval.xml','shared_prefs/language_connection.xml'):
            actual=adb(host,'exec-out','run-as','edu.sydney.probe','cat',path)
            checks.append({'path':path,'sha256':digest(actual),'unchanged':native[path]==actual})
        settings=json.loads((ROOT/'private/before-v93'/host/'settings.json').read_text())
        setting_checks=[]
        for name,wanted in settings.items():
            current=adb(host,'shell','settings','get','secure',name).decode().strip()
            # Ordering of service names is not authorization; preserve extras.
            match=set(current.split(':'))==set(wanted.split(':')) if name=='enabled_accessibility_services' else current==wanted
            setting_checks.append({'name':name,'matches_snapshot':match})
        reverse_file=ROOT/'evidence'/('g3-phone-normal-ui-r1' if host=='R5CW134LLBZ' else 'g4-emulator-normal-ui-r1')/'original-reverse.json'
        prior=json.loads(reverse_file.read_text())['list'];mapping={parts[1]:parts[2] for line in prior.splitlines() if len(parts:=line.split())==3}
        current=adb(host,'reverse','--list').decode();now={parts[1]:parts[2] for line in current.splitlines() if len(parts:=line.split())==3}
        if now.get('tcp:8765') in {'tcp:49721','tcp:49722'}:
            if 'tcp:8765' in mapping:adb(host,'reverse','tcp:8765',mapping['tcp:8765'])
            else:adb(host,'reverse','--remove','tcp:8765')
        restored=adb(host,'reverse','--list').decode();after_map={parts[1]:parts[2] for line in restored.splitlines() if len(parts:=line.split())==3}
        # Remove only newly-created diagnostic files, already backed up above.
        removed=[]
        for name in adb(host,'shell','run-as','edu.sydney.probe','ls','files').decode().splitlines():
            if not re.fullmatch(r'(?:flow-audit|product-ui-audit)-[a-f0-9]{32}\.json|(?:flow|product-ui)-incoming\.json',name):continue
            path='files/'+name
            if path in native:continue
            adb(host,'shell','run-as','edu.sydney.probe','rm',path);removed.append(path)
        row={'host':host,'parameter_recovery':recovery,'native_recovery':native_recovery,'restored_business_state':expected,
            'parameter_files':writes,'legacy_approval_and_pairing':checks,'settings':setting_checks,
            'reverse_original_restored':after_map.get('tcp:8765')==mapping.get('tcp:8765'),'removed_test_files':removed,
            'diagnostics_recoverable_backup':str(before),'new_published_knowledge':'RETAINED_LOCAL_INERT_REVIEW_NO_TASK_AUTHORITY',
            'probe_apk':'RETAINED_TESTED_V93_R15','probe_health':health(host),'parameter_app':'STOPPED_WITH_EXACT_RECOVERED_STATE'}
        row['passed']=all(w['matches_snapshot'] for w in writes) and all(c['unchanged'] for c in checks) and all(s['matches_snapshot'] for s in setting_checks) and row['reverse_original_restored'] and row['probe_health'].get('final_status')=='READY' and not row['probe_health'].get('busy')
        rows.append(row);save(out/(host+'.json'),row);print(host,'RESTORED',row['passed'],len(removed),flush=True)
    control=json.loads((ROOT/'evidence/g4-transition-animation-control.json').read_text());v=adb(control['host'],'shell','settings','get','global','transition_animation_scale').decode().strip()
    save(out/'summary.json',{'hosts':rows,'transition_animation_restored':v==control['before'],'passed':all(r['passed'] for r in rows) and v==control['before'],
        'scope':'EXACT_PARAMETER_FILES_ORIGINAL_APPROVAL_PAIRING_SETTINGS_REVERSE; NEW_KNOWLEDGE_AND_TESTED_APK_RETAINED'})
if __name__=='__main__':
    import sys
    run(Path(sys.argv[1]))
