"""Read-only execution gate; no installation, permission changes or phone inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from workflow_experiment import ADB,adb,write
from named_journey_device import prefs,PROBE
from transfer_run import private
from workflow_capture import tree


def application_service_state(ui):
    nodes=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/homeService']
    if len(nodes)!=1:return None
    text=nodes[0].get('text','')
    if text in ('● 无障碍服务已连接','● Accessibility connected'):return True
    if text in ('○ 无障碍服务未连接 · 请在设置中开启','○ Accessibility disconnected · Enable it in Settings'):return False
    return None


def adjudicate(observed,execution=True):
    fields={'deviceState':str,'installedVersion':int,'apkMatches':bool,'serviceBound':bool,
            'permissionEnabled':bool,'locked':bool,'executionStatus':str,'recording':bool,
            'applicationServiceReady':bool}
    missing=[k for k,t in fields.items() if k not in observed or type(observed[k]) is not t]
    if missing:return dict(status='BLOCKED',executionReady=False,reasons=['MISSING_OR_INVALID:'+k for k in missing])
    reasons=[]
    if observed['deviceState']!='device':reasons.append('DEVICE_NOT_AUTHORIZED_OR_PRESENT')
    if observed['installedVersion']!=34:reasons.append('VERSION_MISMATCH')
    if not observed['apkMatches']:reasons.append('APK_MISMATCH')
    if observed['locked']:reasons.append('LOCKED')
    if observed['recording']:reasons.append('RECORDING_ACTIVE')
    if observed['executionStatus']=='RUNNING':reasons.append('TASK_RUNNING_OR_UNRESOLVED')
    if execution:
        if not observed['permissionEnabled']:reasons.append('PERMISSION_NOT_ENABLED')
        if not observed['serviceBound']:reasons.append('SERVICE_NOT_BOUND')
        if not observed['applicationServiceReady']:reasons.append('APPLICATION_SERVICE_NOT_READY')
    return dict(status='BLOCKED' if reasons else 'READY' if execution else 'PREVIEW_ONLY',
                executionReady=not reasons and execution,reasons=reasons)


def inspect(serial,apk):
    devices=subprocess.run([str(ADB),'devices'],capture_output=True,check=True).stdout.decode()
    state=next((line.split()[1] for line in devices.splitlines() if line.startswith(serial+'\t')),'missing')
    if state!='device':return dict(status='BLOCKED',executionReady=False,reasons=['DEVICE_'+state.upper()],device=serial)
    try:
        package=adb(serial,'shell','dumpsys','package',PROBE)
        match=re.search(r'\bversionCode=(\d+)\b',package)
        path=adb(serial,'shell','pm','path',PROBE).strip().removeprefix('package:')
        if not path.startswith('/data/app/') or '\n' in path:raise ValueError('PACKAGE_PATH')
        expected=hashlib.sha256(Path(apk).read_bytes()).hexdigest()
        installed=adb(serial,'shell','sha256sum',path).split()[0]
        accessibility=adb(serial,'shell','dumpsys','accessibility')
        services=adb(serial,'shell','dumpsys','activity','services',PROBE)
        policy=adb(serial,'shell','dumpsys','window','policy')
        # No inference from the Settings "On" label. The actual service record
        # must exist; the enabled component is a separate requirement.
        enabled=PROBE+'/edu.sydney.probe.ProbeService' in accessibility
        bound=bool(re.search(r'ConnectionRecord[^\n]*edu\.sydney\.probe/\.ProbeService',services))
        lock=re.search(r'\bshowing=(true|false)\b',policy)
        if lock is None:raise ValueError('LOCK_STATE_UNCONFIRMED')
        result=json.loads(prefs(serial).get('result','{}'))
        trace=private(serial,PROBE,'workflow-trace.json')
        if trace.get('end') not in ('RECORDING','STOPPED','CANCELLED','TIMEOUT','ERROR','INTERRUPTED'):
            raise ValueError('RECORDING_STATE_UNCONFIRMED')
        recording=trace['end']=='RECORDING'
        observed=dict(deviceState=state,installedVersion=int(match.group(1)) if match else -1,apkMatches=installed==expected,
            serviceBound=bound,permissionEnabled=enabled,locked=lock.group(1)=='true',
            executionStatus=result.get('status','NONE'),recording=recording,
            applicationServiceReady=application_service_state(tree(serial,timeout=5)))
        return dict(adjudicate(observed),device=serial,observed=observed,apkSha256=installed,readOnly=True)
    except (RuntimeError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired,OSError) as error:
        return dict(status='BLOCKED',executionReady=False,device=serial,reasons=['PRECHECK_UNCONFIRMED:'+type(error).__name__],readOnly=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    p.add_argument('--apk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():p.error('Do not overwrite existing evidence')
    outcome=inspect(args.device,args.apk);write(args.output,outcome);print(json.dumps(outcome));raise SystemExit(0 if outcome['executionReady'] else 2)
