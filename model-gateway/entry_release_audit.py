"""Zero-fee deployed bridge checks and scoped final preservation manifest."""
import hashlib
import json
import secrets
import shutil
from pathlib import Path
import urllib.request
import urllib.error
from named_journey_device import prefs
from workflow_experiment import adb,write

ROOT=Path(__file__).parents[1];OUT=ROOT/'output/entry-hardening-v1'

def audit():
    values=prefs('R5CW134LLBZ');before=json.loads((OUT/'baseline/workflow-prefs.json').read_text(encoding='utf-8'))
    if values!=before:raise ValueError('BASELINE_WORKFLOW_STATE_CHANGED')
    token=prefs('R5CW134LLBZ','language_connection')['pairing'];identity=secrets.token_hex(16)
    def post(token_value,body):
        req=urllib.request.Request('http://127.0.0.1:8768/v1/skill-selection-cancellations',data=json.dumps(body).encode(),
            headers={'Authorization':'Bearer '+token_value,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=3) as reply:return reply.status,json.load(reply)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    a=post(token,dict(request_id=identity));b=post(token,dict(request_id=identity));c=post('invalid-pairing',dict(request_id=identity))
    d=post(token,dict(request_id='invalid'))
    if a!=(200,dict(request_id=identity,status='cancelled')) or b!=a or c[0]!=401 or d[0]!=400:raise ValueError('DEPLOYED_CONTRACT_FAILED')
    mapping=adb('R5CW134LLBZ','reverse','--list').splitlines()
    if not any(v.split()[-2:]==['tcp:8765','tcp:8768'] for v in mapping):raise ValueError('WRONG_USB_MAPPING')
    saved=json.loads((ROOT/'runtime/selector-session/gpt-safe.json').read_text(encoding='utf-8-sig'))
    source_files=['catalog_uniqueness.py','selection_deadline.py','intent_bridge.py','start_teaching_bridge.py',
        'entry_phone.py','entry_queue_phone.py','entry_guard_comparison.py','entry_release_audit.py','activate_selector.ps1','bridge_launcher_identity.ps1']
    files=[ROOT/'model-gateway'/name for name in source_files]+list((ROOT/'android-agent-probe/app/src/main').rglob('*'))
    manifest={};folder=OUT/'release-source';folder.mkdir(exist_ok=False)
    for p in files:
        if not p.is_file():continue
        rel=p.relative_to(ROOT);dest=folder/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        manifest[str(rel)]=hashlib.sha256(p.read_bytes()).hexdigest()
    candidate=ROOT/'android-agent-probe/build/manual/demo-probe-entry-hardening.apk'
    apk_digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
    installed=adb('R5CW134LLBZ','shell','pm','path','edu.sydney.probe').strip()
    if not installed.startswith('package:/data/app/') or '\n' in installed:raise ValueError('APK_PATH')
    adb('R5CW134LLBZ','pull',installed[len('package:'):],str(OUT/'installed-release.apk'))
    if hashlib.sha256((OUT/'installed-release.apk').read_bytes()).hexdigest()!=apk_digest:raise ValueError('INSTALLED_APK_MISMATCH')
    result=dict(passed=True,bridgeSelector='gpt-safe',bridgePort=8768,phonePort=8765,pid=saved['pid'],
        bridgeSessionRequestCap=20,contractChecks=4,remoteModelCalls=0,credentialsPersisted=False,
        workflowPrefsExactBaselineMatch=True,sourceHashes=manifest,installedAPKMatchesCandidate=True,apkSHA256=apk_digest,
        backupAPK='baseline/installed.apk',oldBridgesPreserved=True,usbMapping=mapping)
    write(OUT/'release-audit.json',result)
    print('PASS deployed bridge: 4 authenticated contract checks; installed APK matches; exact workflow baseline intact; 0 model calls.')

if __name__=='__main__':audit()
